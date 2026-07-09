from __future__ import annotations

import csv
import logging
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Callable

import numpy as np

from sprtz.config import Receptor, Source, SuiteConfig, parse_datetime_value, parse_field_z_levels, run_datetime
from sprtz.core.grid import Grid
from sprtz.core.physics import (
    depletion_factor,
    dispersion_parameters,
    effective_release_height,
    gaussian_plume,
    gaussian_puff,
)
from sprtz.exceptions import DataFormatError
from sprtz.io.calpuff import write_calpuff_concentration_dat
from sprtz.io.jsonio import read_json
from sprtz.io.legacy_outputs import infer_format, write_legacy_table
from sprtz.io.netcdf_cf import DenseConcentrationWriter, read_cf_meteorology, write_cf_concentration
from sprtz.parallel import get_gpu_context, get_mpi_context

LOGGER = logging.getLogger(__name__)


def wildfire_plume_rise(intensity_kw_per_m: float, perimeter_m: float, u_ms: float) -> float:
    """Effective smoke release height using a Briggs buoyancy-dominated estimate."""
    q_heat_w = max(0.0, intensity_kw_per_m) * max(0.0, perimeter_m) * 1000.0
    g, cp, rho, t0 = 9.81, 1005.0, 1.2, 293.0
    fb = (g / (cp * rho * t0)) * q_heat_w
    u_safe = max(float(u_ms), 0.5)
    if fb > 55.0:
        return float(1.6 * fb**0.333 * (10.0 * max(perimeter_m, 1.0)) ** 0.667 / u_safe)
    return float(21.425 * fb**0.75 / u_safe)


def _mean_wind(meteo: dict[str, Any]) -> tuple[float, float, float]:
    try:
        u = np.asarray(meteo.get("u", meteo.get("eastward_wind", [[2.0]])), dtype=float)
        v = np.asarray(meteo.get("v", meteo.get("northward_wind", [[0.0]])), dtype=float)
    except (TypeError, ValueError) as exc:
        raise DataFormatError("meteorology u/v fields must be numeric arrays") from exc
    if u.shape != v.shape:
        raise DataFormatError(f"meteorology u/v shape mismatch: {u.shape} vs {v.shape}")
    if u.size == 0:
        raise DataFormatError("meteorology fields must not be empty")
    um = float(np.nanmean(u))
    vm = float(np.nanmean(v))
    speed = max(float(np.hypot(um, vm)), 0.1)
    return um, vm, speed


def _axis_values(meteo: dict[str, Any], name: str, size: int, spacing: float = 1.0) -> np.ndarray:
    values = meteo.get(name)
    if values is None:
        return np.arange(size, dtype=float) * float(spacing)
    arr = np.asarray(values, dtype=float)
    if arr.ndim != 1 or arr.size != size:
        return np.arange(size, dtype=float) * float(spacing)
    return arr


def _interp_axis(source_axis: np.ndarray, target_axis: np.ndarray, values: np.ndarray, *, nearest: bool) -> np.ndarray:
    source = np.asarray(source_axis, dtype=float)
    target = np.asarray(target_axis, dtype=float)
    arr = np.asarray(values, dtype=float)
    order = np.argsort(source)
    source = source[order]
    arr = arr[..., order]
    if source.size != arr.shape[-1] or np.any(np.diff(source) <= 0.0):
        raise DataFormatError("terrain axes must be one-dimensional, unique, and match terrain shape")
    if target[0] < source[0] or target[-1] > source[-1]:
        raise DataFormatError("terrain grid does not cover the Spritz dispersion grid")
    if nearest:
        indexes = np.searchsorted(source, target, side="left")
        indexes = np.clip(indexes, 0, source.size - 1)
        previous = np.clip(indexes - 1, 0, source.size - 1)
        choose_previous = np.abs(target - source[previous]) <= np.abs(target - source[indexes])
        return arr[..., np.where(choose_previous, previous, indexes)]
    flat = arr.reshape((-1, source.size))
    interpolated = np.vstack([np.interp(target, source, row) for row in flat])
    return interpolated.reshape((*arr.shape[:-1], target.size))


def _interp_terrain_2d(
    values: np.ndarray,
    source_x: np.ndarray,
    source_y: np.ndarray,
    target_x: np.ndarray,
    target_y: np.ndarray,
    *,
    nearest: bool,
) -> np.ndarray:
    x_values = _interp_axis(source_x, target_x, values, nearest=nearest)
    return _interp_axis(source_y, target_y, x_values.T, nearest=nearest).T


def _terrain_variable(ds: Any, names: tuple[str, ...]) -> Any | None:
    lowered = {name.lower(): name for name in ds.variables}
    for name in names:
        actual = lowered.get(name.lower())
        if actual is not None:
            return ds.variables[actual]
    return None


def terrain_fields_for_grid(terrain_path: str | Path | None, config: SuiteConfig) -> dict[str, np.ndarray]:
    if terrain_path is None:
        return {}
    path = Path(terrain_path)
    if not path.exists():
        raise FileNotFoundError(f"terrain input not found: {path}")
    try:
        from netCDF4 import Dataset  # type: ignore
    except Exception as exc:
        raise DataFormatError("netCDF4 is required to read terrain input NetCDF files") from exc
    grid = Grid(**asdict(config.grid))
    with Dataset(path) as ds:
        dem_var = _terrain_variable(ds, ("surface_altitude", "elevation_m", "dem_elevation_m", "terrain_m", "terrain"))
        if dem_var is None:
            raise DataFormatError(f"terrain input lacks a DEM/surface altitude variable: {path}")
        dem = np.asarray(dem_var[:], dtype=float)
        if dem.ndim != 2:
            raise DataFormatError("terrain DEM variable must be two-dimensional")
        dims = tuple(str(dim) for dim in getattr(dem_var, "dimensions", ()))
        y_dim = dims[-2] if len(dims) >= 2 else "y"
        x_dim = dims[-1] if len(dims) >= 1 else "x"
        source_x = np.asarray(ds.variables[x_dim][:], dtype=float) if x_dim in ds.variables else np.arange(dem.shape[1], dtype=float)
        source_y = np.asarray(ds.variables[y_dim][:], dtype=float) if y_dim in ds.variables else np.arange(dem.shape[0], dtype=float)
        result = {"terrain_m": _interp_terrain_2d(dem, source_x, source_y, grid.x, grid.y, nearest=False)}
        lc_var = _terrain_variable(ds, ("land_cover", "landuse_class", "landuse", "land_use"))
        if lc_var is not None:
            lc = np.asarray(lc_var[:], dtype=float)
            if lc.shape == dem.shape:
                result["land_cover"] = _interp_terrain_2d(lc, source_x, source_y, grid.x, grid.y, nearest=True)
        return result


def _terrain_row_fields(terrain_fields: dict[str, np.ndarray], iy: int, ix: int) -> dict[str, float]:
    values: dict[str, float] = {}
    if "terrain_m" in terrain_fields:
        values["terrain_m"] = float(terrain_fields["terrain_m"][iy, ix])
    if "land_cover" in terrain_fields:
        values["land_cover"] = float(terrain_fields["land_cover"][iy, ix])
    return values


def _terrain_row_fields_for_receptor(terrain_fields: dict[str, np.ndarray], receptor_id: str) -> dict[str, float]:
    if not terrain_fields or not receptor_id.startswith("G"):
        return {}
    parts = receptor_id[1:].split("_")
    try:
        iy, ix = (int(parts[0]), int(parts[1])) if len(parts) == 2 else (int(parts[1]), int(parts[2]))
    except (IndexError, ValueError):
        return {}
    return _terrain_row_fields(terrain_fields, iy, ix)


def _terrain_at_xy(terrain_fields: dict[str, np.ndarray], grid: Grid, x: float, y: float) -> float:
    terrain = terrain_fields.get("terrain_m")
    if terrain is None:
        return 0.0
    return float(_interp_terrain_2d(np.asarray(terrain, dtype=float), grid.x, grid.y, np.asarray([x]), np.asarray([y]), nearest=False)[0, 0])


def _source_ground_altitude_m(src: Source, terrain_fields: dict[str, np.ndarray], grid: Grid) -> float:
    return _terrain_at_xy(terrain_fields, grid, float(src.x), float(src.y)) + float(src.z)


def _source_release_height_agl_m(src: Source) -> float:
    if src.height_agl_m is not None:
        return float(src.height_agl_m)
    return 0.0


def _wind_4d(meteo: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    try:
        u = np.asarray(meteo.get("u", meteo.get("eastward_wind", [[[[2.0]]]])), dtype=float)
        v = np.asarray(meteo.get("v", meteo.get("northward_wind", [[[[0.0]]]])), dtype=float)
    except (TypeError, ValueError) as exc:
        raise DataFormatError("meteorology u/v fields must be numeric arrays") from exc
    if u.ndim == 2:
        u = u[np.newaxis, np.newaxis, :, :]
    elif u.ndim == 3:
        u = u[:, np.newaxis, :, :]
    if v.ndim == 2:
        v = v[np.newaxis, np.newaxis, :, :]
    elif v.ndim == 3:
        v = v[:, np.newaxis, :, :]
    if u.ndim != 4 or v.ndim != 4:
        raise DataFormatError("meteorology u/v fields must be y,x; time,y,x; or time,z,y,x")
    if u.shape != v.shape:
        raise DataFormatError(f"meteorology u/v shape mismatch: {u.shape} vs {v.shape}")
    return u, v


def _surface_wind_3d(values: Any, *, name: str, target_shape: tuple[int, int, int]) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    nt, ny, nx = target_shape
    if arr.ndim == 2:
        arr = arr[np.newaxis, :, :]
    if arr.ndim != 3:
        raise DataFormatError(f"meteorology {name} must be shaped as y,x or time,y,x")
    if arr.shape == (1, ny, nx) and nt > 1:
        arr = np.repeat(arr, nt, axis=0)
    if arr.shape != target_shape:
        raise DataFormatError(f"meteorology {name} shape {arr.shape} does not match time/y/x shape {target_shape}")
    return arr


def _augment_with_diagnostic_10m(
    meteo: dict[str, Any],
    u: np.ndarray,
    v: np.ndarray,
    z_axis: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Use diagnostic 10 m wind as the lower-boundary layer when available.

    SpritzMet stores WRF U10M/V10M separately because the true reference is
    10 m above local ground, often DEM + 10 m in above-sea-level grids. The
    dispersion samplers use source/receptor heights above ground, so they need
    that diagnostic near-surface wind before falling back to model levels aloft.
    """
    if "u10m" not in meteo or "v10m" not in meteo or z_axis.size == 0:
        return u, v, z_axis
    if np.nanmin(z_axis) <= 10.0 + 1.0e-6:
        return u, v, z_axis
    nt, _nz, ny, nx = u.shape
    u10 = _surface_wind_3d(meteo["u10m"], name="u10m", target_shape=(nt, ny, nx))
    v10 = _surface_wind_3d(meteo["v10m"], name="v10m", target_shape=(nt, ny, nx))
    z_aug = np.concatenate(([10.0], z_axis.astype(float)))
    u_aug = np.concatenate((u10[:, np.newaxis, :, :], u), axis=1)
    v_aug = np.concatenate((v10[:, np.newaxis, :, :], v), axis=1)
    order = np.argsort(z_aug)
    return u_aug[:, order, :, :], v_aug[:, order, :, :], z_aug[order]


def _bracket(axis: np.ndarray, values: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if axis.size == 1:
        zeros = np.zeros(values.shape, dtype=int)
        return zeros, zeros, np.zeros(values.shape, dtype=float)
    increasing = axis[-1] >= axis[0]
    work_axis = axis if increasing else axis[::-1]
    clipped = np.clip(values, work_axis[0], work_axis[-1])
    upper = np.searchsorted(work_axis, clipped, side="right")
    upper = np.clip(upper, 1, work_axis.size - 1)
    lower = upper - 1
    span = np.maximum(work_axis[upper] - work_axis[lower], 1.0e-12)
    weight = (clipped - work_axis[lower]) / span
    if not increasing:
        lower, upper = axis.size - 1 - upper, axis.size - 1 - lower
    return lower.astype(int), upper.astype(int), weight.astype(float)


def sample_wind(
    meteo: dict[str, Any],
    x: Any,
    y: Any,
    z: Any,
    time_s: Any,
    *,
    grid_dx: float = 1.0,
    grid_dy: float = 1.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Interpolate eastward/northward wind from a SpritzMet time,z,y,x cube."""
    u, v = _wind_4d(meteo)
    nt, nz, ny, nx = u.shape
    x_axis = _axis_values(meteo, "x", nx, grid_dx)
    y_axis = _axis_values(meteo, "y", ny, grid_dy)
    z_axis = _axis_values(meteo, "z", nz, 1.0)
    u, v, z_axis = _augment_with_diagnostic_10m(meteo, u, v, z_axis)
    t_axis = _axis_values(meteo, "time", nt, 1.0)
    bx = np.broadcast_arrays(np.asarray(x, dtype=float), np.asarray(y, dtype=float), np.asarray(z, dtype=float), np.asarray(time_s, dtype=float))
    x_arr, y_arr, z_arr, t_arr = bx
    x0, x1, wx = _bracket(x_axis, x_arr)
    y0, y1, wy = _bracket(y_axis, y_arr)
    z0, z1, wz = _bracket(z_axis, z_arr)
    t0, t1, wt = _bracket(t_axis, t_arr)

    def interp(values: np.ndarray) -> np.ndarray:
        out = np.zeros(x_arr.shape, dtype=float)
        for ti, tw in ((t0, 1.0 - wt), (t1, wt)):
            for zi, zw in ((z0, 1.0 - wz), (z1, wz)):
                for yi, yw in ((y0, 1.0 - wy), (y1, wy)):
                    for xi, xw in ((x0, 1.0 - wx), (x1, wx)):
                        out += values[ti, zi, yi, xi] * tw * zw * yw * xw
        return out

    return interp(u), interp(v)


class WindSampler:
    """Reusable interpolator for SpritzMet wind cubes."""

    def __init__(self, meteo: dict[str, Any], *, grid_dx: float = 1.0, grid_dy: float = 1.0) -> None:
        self.u, self.v = _wind_4d(meteo)
        nt, nz, ny, nx = self.u.shape
        self.x_axis = _axis_values(meteo, "x", nx, grid_dx)
        self.y_axis = _axis_values(meteo, "y", ny, grid_dy)
        self.z_axis = _axis_values(meteo, "z", nz, 1.0)
        self.u, self.v, self.z_axis = _augment_with_diagnostic_10m(meteo, self.u, self.v, self.z_axis)
        self.t_axis = _axis_values(meteo, "time", nt, 1.0)

    def sample(self, x: Any, y: Any, z: Any, time_s: Any) -> tuple[np.ndarray, np.ndarray]:
        bx = np.broadcast_arrays(
            np.asarray(x, dtype=float),
            np.asarray(y, dtype=float),
            np.asarray(z, dtype=float),
            np.asarray(time_s, dtype=float),
        )
        x_arr, y_arr, z_arr, t_arr = bx
        x0, x1, wx = _bracket(self.x_axis, x_arr)
        y0, y1, wy = _bracket(self.y_axis, y_arr)
        z0, z1, wz = _bracket(self.z_axis, z_arr)
        t0, t1, wt = _bracket(self.t_axis, t_arr)

        def interp(values: np.ndarray) -> np.ndarray:
            out = np.zeros(x_arr.shape, dtype=float)
            for ti, tw in ((t0, 1.0 - wt), (t1, wt)):
                for zi, zw in ((z0, 1.0 - wz), (z1, wz)):
                    for yi, yw in ((y0, 1.0 - wy), (y1, wy)):
                        for xi, xw in ((x0, 1.0 - wx), (x1, wx)):
                            out += values[ti, zi, yi, xi] * tw * zw * yw * xw
            return out

        return interp(self.u), interp(self.v)

    def vector(self, x: float, y: float, z: float, time_s: float) -> tuple[float, float, float]:
        u, v = self.sample(x, y, z, time_s)
        uf = float(np.asarray(u).reshape(-1)[0])
        vf = float(np.asarray(v).reshape(-1)[0])
        return uf, vf, max(float(np.hypot(uf, vf)), 0.1)


def sampled_wind_vector(
    meteo: dict[str, Any],
    x: float,
    y: float,
    z: float,
    time_s: float,
    *,
    grid_dx: float = 1.0,
    grid_dy: float = 1.0,
) -> tuple[float, float, float]:
    return WindSampler(meteo, grid_dx=grid_dx, grid_dy=grid_dy).vector(x, y, z, time_s)


def _mean_precipitation_rate(meteo: dict[str, Any]) -> float:
    try:
        precipitation = np.asarray(meteo.get("precipitation_rate", [[0.0]]), dtype=float)
    except (TypeError, ValueError) as exc:
        raise DataFormatError("meteorology precipitation_rate field must be numeric") from exc
    if precipitation.size == 0:
        return 0.0
    return max(float(np.nanmean(precipitation)), 0.0)


def _down_cross(dx: float, dy: float, u: float, v: float, speed: float) -> tuple[float, float]:
    ex, ey = u / speed, v / speed
    xdown = dx * ex + dy * ey
    ycross = -dx * ey + dy * ex
    return xdown, ycross


def _gaussian_puff_array(
    *,
    mass: float,
    x_receptor: np.ndarray,
    y_receptor: np.ndarray,
    z_receptor: float,
    x_center: float,
    y_center: float,
    z_center: float,
    sigma_x: float,
    sigma_y: float,
    sigma_z: float,
    xp: Any = np,
) -> Any:
    sx = max(float(sigma_x), 1.0e-12)
    sy = max(float(sigma_y), 1.0e-12)
    sz = max(float(sigma_z), 1.0e-12)
    norm = float(mass) / (((2.0 * float(xp.pi)) ** 1.5) * sx * sy * sz)
    gx = xp.exp(-0.5 * ((x_receptor - float(x_center)) / sx) ** 2)
    gy = xp.exp(-0.5 * ((y_receptor - float(y_center)) / sy) ** 2)
    gz = xp.exp(-0.5 * ((float(z_receptor) - float(z_center)) / sz) ** 2)
    gz += xp.exp(-0.5 * ((float(z_receptor) + float(z_center)) / sz) ** 2)
    return norm * gx * gy * gz


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _run_value(config: SuiteConfig, *names: str, default: Any = None) -> Any:
    for name in names:
        value = config.run.get(name, config.run.get(name.upper()))
        if value is not None:
            return value
    return default


def weather_start_datetime(config: SuiteConfig) -> datetime | None:
    return run_datetime(config.run, "weather_start_datetime", "simulation_start_datetime")


def sample_datetime(config: SuiteConfig, sample_time_s: float) -> datetime | None:
    start = weather_start_datetime(config)
    if start is None:
        return None
    return start + timedelta(seconds=float(sample_time_s))


def _source_window(config: SuiteConfig, source: Source) -> tuple[datetime | None, datetime | None]:
    start = parse_datetime_value(source.start_datetime, field_name=f"source {source.id} start_datetime")
    end = parse_datetime_value(source.end_datetime, field_name=f"source {source.id} end_datetime")
    if start is None:
        start = run_datetime(config.run, "event_start_datetime", "fire_start_datetime")
    if end is None:
        end = run_datetime(config.run, "event_end_datetime", "fire_end_datetime")
    return start, end


def _source_active(config: SuiteConfig, source: Source, when: datetime | None) -> bool:
    if when is None:
        return True
    start, end = _source_window(config, source)
    if start is not None and when < start:
        return False
    if end is not None and when > end:
        return False
    return True


def _firefighters_emission_factor(config: SuiteConfig, when: datetime | None) -> float:
    if when is None:
        return 1.0
    start = run_datetime(config.run, "firefighters_start_datetime")
    end = run_datetime(config.run, "firefighters_end_datetime")
    if start is None or end is None or not (start <= when <= end):
        return 1.0
    return float(_run_value(config, "firefighters_emission_factor", default=1.0))


def precipitation_washout_rate(config: SuiteConfig, meteo: dict[str, Any]) -> float:
    enabled = _truthy(
        _run_value(
            config,
            "precipitation_washout",
            "use_precipitation_washout",
            default=False,
        )
    )
    if not enabled:
        return 0.0
    coefficient = float(
        _run_value(
            config,
            "precipitation_washout_coefficient_s_per_mm_h",
            default=1.0e-5,
        )
    )
    return max(coefficient, 0.0) * _mean_precipitation_rate(meteo)


def concentration_output_mode(config: SuiteConfig) -> str:
    """Resolve receptor-table, grid-field, or combined concentration output."""
    mode_value = config.run.get("concentration_output", config.run.get("CONCENTRATION_OUTPUT"))
    if mode_value is None:
        field_requested = _truthy(
            config.run.get(
                "output_field",
                config.run.get("OUTPUT_FIELD", config.run.get("concentration_field", False)),
            )
        )
        if field_requested:
            return "both" if config.receptors else "grid"
        return "receptors" if config.receptors else "grid"
    mode = str(mode_value).strip().lower()
    aliases = {
        "receptor": "receptors",
        "receptors": "receptors",
        "grid": "grid",
        "field": "grid",
        "grid_field": "grid",
        "both": "both",
    }
    try:
        return aliases[mode]
    except KeyError as exc:
        raise DataFormatError("run.concentration_output must be receptors, grid, or both") from exc


def field_z_levels(config: SuiteConfig) -> tuple[float, ...]:
    """Return vertical levels used when a gridded concentration field is requested."""
    return parse_field_z_levels(
        config.run.get(
            "field_z_levels",
            config.run.get("FIELD_Z_LEVELS", config.run.get("z_levels", config.run.get("Z_LEVELS"))),
        )
    )


def _grid_geographic_transformer(config: SuiteConfig) -> Any | None:
    metadata = config.raw.get("metadata", {}) if isinstance(config.raw, dict) else {}
    if not isinstance(metadata, dict) or "center_lat" not in metadata or "center_lon" not in metadata:
        return None
    try:
        from pyproj import CRS, Transformer
    except Exception:
        return None
    center_lat = float(metadata["center_lat"])
    center_lon = float(metadata["center_lon"])
    local = CRS.from_proj4(
        f"+proj=aeqd +lat_0={center_lat:.12f} +lon_0={center_lon:.12f} "
        "+x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs"
    )
    return Transformer.from_crs(local, CRS.from_epsg(4326), always_xy=True)


def _grid_receptors(config: SuiteConfig, z_levels: tuple[float, ...] | None = None) -> tuple[Receptor, ...]:
    grid = Grid(**asdict(config.grid))
    levels = z_levels if z_levels is not None else (0.0,)
    transformer = _grid_geographic_transformer(config)
    receptors: list[Receptor] = []
    for iz, z_value in enumerate(levels):
        for iy, y in enumerate(grid.y):
            for ix, x in enumerate(grid.x):
                receptor_id = f"G{iy}_{ix}" if len(levels) == 1 else f"G{iz}_{iy}_{ix}"
                latitude = None
                longitude = None
                if transformer is not None:
                    longitude, latitude = transformer.transform(float(x), float(y))
                receptors.append(
                    Receptor(
                        id=receptor_id,
                        x=float(x),
                        y=float(y),
                        z=float(z_value),
                        latitude=None if latitude is None else float(latitude),
                        longitude=None if longitude is None else float(longitude),
                    )
                )
    return tuple(receptors)


def model_receptors(config: SuiteConfig) -> tuple[Receptor, ...]:
    """Return the receptor set implied by the concentration output mode."""
    mode = concentration_output_mode(config)
    if mode == "receptors":
        return config.receptors or _grid_receptors(config)
    grid = _grid_receptors(config, field_z_levels(config))
    if mode == "grid":
        return grid
    return tuple(config.receptors) + grid


def read_meteorology(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if p.suffix.lower() in {".nc", ".cdf", ".netcdf"}:
        return read_cf_meteorology(p)
    return read_json(p)


def output_times(config: SuiteConfig) -> tuple[float, ...]:
    """Resolve optional concentration output times in seconds.

    The default remains the historical single output at ``time=0``. When
    ``run.output_interval_s`` is present, Spritz emits rows at that interval
    independently from the meteorological input cadence. The default duration is
    ``run.averaging_time_s`` so existing one-hour examples can request, for
    example, 600-second outputs without changing meteorology.
    """
    interval_value = config.run.get("output_interval_s", config.run.get("OUTPUT_INTERVAL_S"))
    if interval_value is None:
        return (0.0,)
    interval = float(interval_value)
    if interval <= 0:
        raise DataFormatError("run.output_interval_s must be positive")
    weather_start = weather_start_datetime(config)
    weather_end = run_datetime(config.run, "weather_end_datetime", "simulation_end_datetime")
    if weather_start is not None and weather_end is not None:
        default_duration = max((weather_end - weather_start).total_seconds(), interval)
    else:
        default_duration = config.run.get("averaging_time_s", config.run.get("AVERAGING_TIME_S", interval))
    duration = float(
        config.run.get(
            "output_duration_s",
            config.run.get("OUTPUT_DURATION_S", default_duration),
        )
    )
    if duration <= 0:
        raise DataFormatError("run.output_duration_s must be positive")
    start = float(config.run.get("output_start_s", config.run.get("OUTPUT_START_S", interval)))
    if start < 0:
        raise DataFormatError("run.output_start_s must be non-negative")
    values = np.arange(start, duration + interval * 1.0e-9, interval, dtype=float)
    if values.size == 0:
        values = np.asarray([duration], dtype=float)
    return tuple(float(np.round(value, 9)) for value in values)


def _compute_gaussian_grid_concentrations(
    *,
    config: SuiteConfig,
    meteo: dict[str, Any],
    times: tuple[float, ...],
    field_ids: set[str],
    stability: str,
    interval_mass_time: float,
    puff_samples: int,
    initial_sigma_h: float,
    initial_sigma_z: float,
    ambient_temperature: float,
    mixing_height: float,
    washout_rate: float,
    wind_sampler: WindSampler,
    terrain_fields: dict[str, np.ndarray],
    progress_callback: Callable[[int, float], None] | None,
) -> list[dict[str, float | str]]:
    """Evaluate a clean-room CALPUFF-style puff ensemble on the output grid."""
    grid = Grid(**asdict(config.grid))
    field_levels = field_z_levels(config)
    x2d, y2d = np.meshgrid(grid.x.astype(float), grid.y.astype(float))
    terrain_m = np.asarray(terrain_fields.get("terrain_m", np.zeros((grid.ny, grid.nx), dtype=float)), dtype=float)
    rows: list[dict[str, float | str]] = []
    downwash = bool(config.run.get("stack_tip_downwash", True))
    transformer = _grid_geographic_transformer(config)

    for time_index, sample_time in enumerate(times, start=1):
        sample_dt = sample_datetime(config, sample_time)
        firefighter_factor = _firefighters_emission_factor(config, sample_dt)
        concentration = np.zeros((len(field_levels), grid.ny, grid.nx), dtype=float)
        dry_flux = np.zeros_like(concentration)
        wet_flux = np.zeros_like(concentration)
        emission_window = min(interval_mass_time, max(float(sample_time), 1.0))
        dt = emission_window / float(max(puff_samples, 1))

        for src in config.sources:
            if not _source_active(config, src, sample_dt):
                continue
            source_ground_asl = _source_ground_altitude_m(src, terrain_fields, grid)
            release_height_agl = _source_release_height_agl_m(src)
            source_wet_rate = max(src.wet_scavenging, 0.0) + washout_rate
            emission_rate = src.emission_rate * firefighter_factor
            for sample_index in range(max(puff_samples, 1)):
                age_s = (sample_index + 0.5) * dt
                release_time = max(float(sample_time) - age_s, 0.0)
                u, v, speed = wind_sampler.vector(
                    src.x,
                    src.y,
                    max(source_ground_asl + release_height_agl, 0.0),
                    release_time,
                )
                center_x = src.x + u * age_s
                center_y = src.y + v * age_s
                travel_distance = max(speed * age_s, 1.0)
                eff_h = effective_release_height(
                    stack_height=release_height_agl,
                    source_z=source_ground_asl,
                    receptor_z=0.0,
                    wind_speed=speed,
                    downwind_distance=travel_distance,
                    stack_diameter=src.stack_diameter,
                    exit_velocity=src.exit_velocity,
                    exit_temperature=src.exit_temperature,
                    ambient_temperature=ambient_temperature,
                    heat_release=src.heat_release,
                    downwash=downwash,
                )
                depletion = depletion_factor(
                    travel_time_s=age_s,
                    decay_rate_s=src.decay_rate,
                    deposition_velocity_m_s=src.deposition_velocity,
                    mixing_height_m=mixing_height,
                    wet_scavenging_s=source_wet_rate,
                    settling_velocity_m_s=src.settling_velocity,
                )
                sigmas = dispersion_parameters(
                    travel_distance,
                    stability,
                    elapsed_s=age_s,
                    initial_sigma_y=initial_sigma_h,
                    initial_sigma_z=initial_sigma_z,
                    source_width=src.width,
                    source_length=src.length,
                    source_height=max(src.height, 0.0),
                )
                mass = emission_rate * dt * depletion
                for level_index, level in enumerate(field_levels):
                    value = _gaussian_puff_array(
                        mass=mass,
                        x_receptor=x2d,
                        y_receptor=y2d,
                        z_receptor=float(level),
                        x_center=center_x,
                        y_center=center_y,
                        z_center=eff_h,
                        sigma_x=sigmas.sigma_x,
                        sigma_y=sigmas.sigma_y,
                        sigma_z=sigmas.sigma_z,
                    )
                    concentration[level_index] += value
                    dry_flux[level_index] += value * max(src.deposition_velocity, 0.0)
                    wet_flux[level_index] += value * source_wet_rate * mixing_height

        for level_index, level in enumerate(field_levels):
            below_ground = float(level) < terrain_m
            concentration[level_index][below_ground] = 0.0
            dry_flux[level_index][below_ground] = 0.0
            wet_flux[level_index][below_ground] = 0.0
            concentration[level_index][concentration[level_index] < 1.0e-30] = 0.0
            dry_flux[level_index][dry_flux[level_index] < 1.0e-30] = 0.0
            wet_flux[level_index][wet_flux[level_index] < 1.0e-30] = 0.0
            for iy, y in enumerate(grid.y):
                for ix, x in enumerate(grid.x):
                    rec_id = f"G{iy}_{ix}" if len(field_levels) == 1 else f"G{level_index}_{iy}_{ix}"
                    row: dict[str, float | str] = {
                        "time": sample_time,
                        "receptor": rec_id,
                        "output_kind": "field" if rec_id in field_ids else "receptor",
                        "x": float(x),
                        "y": float(y),
                        "z": float(level),
                        **_terrain_row_fields(terrain_fields, iy, ix),
                        "concentration": float(concentration[level_index, iy, ix]),
                        "dry_flux": float(dry_flux[level_index, iy, ix]),
                        "wet_flux": float(wet_flux[level_index, iy, ix]),
                    }
                    if transformer is not None:
                        longitude, latitude = transformer.transform(float(x), float(y))
                        row["latitude"] = float(latitude)
                        row["longitude"] = float(longitude)
                    if sample_dt is not None:
                        row["datetime"] = sample_dt.isoformat()
                    rows.append(row)
        if progress_callback is not None:
            progress_callback(time_index, sample_time)
        else:
            LOGGER.info(
                "Spritz Gaussian puff: concentration output interval reached index=%d output_time_s=%.0f",
                time_index,
                sample_time,
            )
    return rows


def _field_lat_lon(config: SuiteConfig) -> tuple[np.ndarray, np.ndarray] | tuple[None, None]:
    grid = Grid(**asdict(config.grid))
    transformer = _grid_geographic_transformer(config)
    if transformer is None:
        return None, None
    x2d, y2d = np.meshgrid(grid.x.astype(float), grid.y.astype(float))
    longitude, latitude = transformer.transform(x2d, y2d)
    return np.asarray(latitude, dtype=float), np.asarray(longitude, dtype=float)


def _stream_gaussian_grid_concentrations(
    *,
    config: SuiteConfig,
    meteo: dict[str, Any],
    output: str | Path,
    times: tuple[float, ...],
    stability: str,
    interval_mass_time: float,
    puff_samples: int,
    initial_sigma_h: float,
    initial_sigma_z: float,
    ambient_temperature: float,
    mixing_height: float,
    washout_rate: float,
    wind_sampler: WindSampler,
    terrain_fields: dict[str, np.ndarray],
    progress_callback: Callable[[int, float], None] | None,
    gpu_backend: str | None = None,
) -> list[dict[str, float | str]]:
    """Write gridded Gaussian puff arrays directly to NetCDF-CF."""
    grid = Grid(**asdict(config.grid))
    field_levels = field_z_levels(config)
    gpu = get_gpu_context(gpu_backend or str(config.run.get("gpu_backend", "numpy")))
    xp = gpu.xp
    x2d, y2d = xp.meshgrid(xp.asarray(grid.x), xp.asarray(grid.y))
    terrain_m = np.asarray(terrain_fields.get("terrain_m", np.zeros((grid.ny, grid.nx), dtype=float)), dtype=float)
    land_cover = terrain_fields.get("land_cover")
    latitude, longitude = _field_lat_lon(config)
    point_receptors = tuple(config.receptors) if concentration_output_mode(config) == "both" else ()
    point_templates: list[dict[str, float | str]] = []
    for rec in point_receptors:
        row: dict[str, float | str] = {
            "receptor": rec.id,
            "output_kind": "receptor",
            "x": rec.x,
            "y": rec.y,
            "z": rec.z,
            **_terrain_row_fields_for_receptor(terrain_fields, rec.id),
        }
        if rec.latitude is not None and rec.longitude is not None:
            row["latitude"] = float(rec.latitude)
            row["longitude"] = float(rec.longitude)
        point_templates.append(row)
    datetimes = {
        float(time_value): dt.isoformat()
        for time_value in times
        if (dt := sample_datetime(config, time_value)) is not None
    }
    rows: list[dict[str, float | str]] = []
    downwash = bool(config.run.get("stack_tip_downwash", True))

    with DenseConcentrationWriter(
        output,
        times=times,
        x=grid.x,
        y=grid.y,
        z=field_levels,
        point_receptors=point_templates,
        z_reference=str(meteo.get("z_reference", "height_above_sea_level")),
        latitude=latitude,
        longitude=longitude,
        surface_altitude=terrain_m if "terrain_m" in terrain_fields else None,
        land_cover=land_cover,
        datetimes=datetimes or None,
    ) as writer:
        for time_index, sample_time in enumerate(times, start=1):
            sample_dt = sample_datetime(config, sample_time)
            firefighter_factor = _firefighters_emission_factor(config, sample_dt)
            storage_xp = np if gpu.backend == "mlx" else xp
            concentration = storage_xp.zeros((len(field_levels), grid.ny, grid.nx), dtype=float)
            dry_flux = storage_xp.zeros_like(concentration)
            wet_flux = storage_xp.zeros_like(concentration)
            point_values = {
                rec.id: {"concentration": 0.0, "dry_flux": 0.0, "wet_flux": 0.0}
                for rec in point_receptors
            }
            emission_window = min(interval_mass_time, max(float(sample_time), 1.0))
            dt = emission_window / float(max(puff_samples, 1))

            for src in config.sources:
                if not _source_active(config, src, sample_dt):
                    continue
                source_ground_asl = _source_ground_altitude_m(src, terrain_fields, grid)
                release_height_agl = _source_release_height_agl_m(src)
                source_wet_rate = max(src.wet_scavenging, 0.0) + washout_rate
                emission_rate = src.emission_rate * firefighter_factor
                for sample_index in range(max(puff_samples, 1)):
                    age_s = (sample_index + 0.5) * dt
                    release_time = max(float(sample_time) - age_s, 0.0)
                    u, v, speed = wind_sampler.vector(
                        src.x,
                        src.y,
                        max(source_ground_asl + release_height_agl, 0.0),
                        release_time,
                    )
                    center_x = src.x + u * age_s
                    center_y = src.y + v * age_s
                    travel_distance = max(speed * age_s, 1.0)
                    eff_h = effective_release_height(
                        stack_height=release_height_agl,
                        source_z=source_ground_asl,
                        receptor_z=0.0,
                        wind_speed=speed,
                        downwind_distance=travel_distance,
                        stack_diameter=src.stack_diameter,
                        exit_velocity=src.exit_velocity,
                        exit_temperature=src.exit_temperature,
                        ambient_temperature=ambient_temperature,
                        heat_release=src.heat_release,
                        downwash=downwash,
                    )
                    depletion = depletion_factor(
                        travel_time_s=age_s,
                        decay_rate_s=src.decay_rate,
                        deposition_velocity_m_s=src.deposition_velocity,
                        mixing_height_m=mixing_height,
                        wet_scavenging_s=source_wet_rate,
                        settling_velocity_m_s=src.settling_velocity,
                    )
                    sigmas = dispersion_parameters(
                        travel_distance,
                        stability,
                        elapsed_s=age_s,
                        initial_sigma_y=initial_sigma_h,
                        initial_sigma_z=initial_sigma_z,
                        source_width=src.width,
                        source_length=src.length,
                        source_height=max(src.height, 0.0),
                    )
                    mass = emission_rate * dt * depletion
                    for level_index, level in enumerate(field_levels):
                        value = _gaussian_puff_array(
                            mass=mass,
                            x_receptor=x2d,
                            y_receptor=y2d,
                            z_receptor=float(level),
                            x_center=center_x,
                            y_center=center_y,
                            z_center=eff_h,
                            sigma_x=sigmas.sigma_x,
                            sigma_y=sigmas.sigma_y,
                            sigma_z=sigmas.sigma_z,
                            xp=xp,
                        )
                        value_out = gpu.asnumpy(value) if gpu.backend == "mlx" else value
                        concentration[level_index] += value_out
                        dry_flux[level_index] += value_out * max(src.deposition_velocity, 0.0)
                        wet_flux[level_index] += value_out * source_wet_rate * mixing_height
                    for rec in point_receptors:
                        value = gaussian_puff(
                            mass=mass,
                            x_receptor=rec.x,
                            y_receptor=rec.y,
                            z_receptor=rec.z,
                            x_center=center_x,
                            y_center=center_y,
                            z_center=eff_h,
                            sigmas=sigmas,
                        )
                        point_values[rec.id]["concentration"] += value
                        point_values[rec.id]["dry_flux"] += value * max(src.deposition_velocity, 0.0)
                        point_values[rec.id]["wet_flux"] += value * source_wet_rate * mixing_height

            for level_index, level in enumerate(field_levels):
                below_ground = float(level) < storage_xp.asarray(terrain_m)
                concentration[level_index][below_ground] = 0.0
                dry_flux[level_index][below_ground] = 0.0
                wet_flux[level_index][below_ground] = 0.0
                concentration[level_index][concentration[level_index] < 1.0e-30] = 0.0
                dry_flux[level_index][dry_flux[level_index] < 1.0e-30] = 0.0
                wet_flux[level_index][wet_flux[level_index] < 1.0e-30] = 0.0

            point_rows: list[dict[str, float | str]] = []
            for template, rec in zip(point_templates, point_receptors):
                values = point_values[rec.id]
                row = {
                    **template,
                    "time": sample_time,
                    **({} if sample_dt is None else {"datetime": sample_dt.isoformat()}),
                    "concentration": float(values["concentration"]),
                    "dry_flux": float(values["dry_flux"]),
                    "wet_flux": float(values["wet_flux"]),
                }
                point_rows.append(row)
                rows.append(row)
            writer.write_time(
                sample_time,
                concentration=gpu.asnumpy(concentration),
                dry_flux=gpu.asnumpy(dry_flux),
                wet_flux=gpu.asnumpy(wet_flux),
                receptor_rows=point_rows,
            )
            if progress_callback is not None:
                progress_callback(time_index, sample_time)
            else:
                LOGGER.info(
                    "Spritz Gaussian puff: concentration output interval reached index=%d output_time_s=%.0f",
                    time_index,
                    sample_time,
                )
    return rows


def compute_concentrations(
    config: SuiteConfig,
    meteo: dict[str, Any],
    *,
    terrain_fields: dict[str, np.ndarray] | None = None,
    parallel: str = "serial",
    gpu_backend: str | None = None,
    progress_callback: Callable[[int, float], None] | None = None,
) -> list[dict[str, float | str]]:
    config.validate()
    rows: list[dict[str, float | str]] = []
    receptors = model_receptors(config)
    output_mode = concentration_output_mode(config)
    field_ids = (
        {rec.id for rec in _grid_receptors(config, field_z_levels(config))}
        if output_mode in {"grid", "both"}
        else set()
    )
    stability = str(config.run.get("stability", config.run.get("STABILITY", "D")))
    numerical_mode = str(config.run.get("numerical_mode", config.run.get("NUMERICAL_MODE", "puff"))).lower()
    averaging_time = float(config.run.get("averaging_time_s", config.run.get("AVERAGING_TIME_S", 3600.0)))
    times = output_times(config)
    output_interval = config.run.get("output_interval_s", config.run.get("OUTPUT_INTERVAL_S"))
    interval_mass_time = float(output_interval) if output_interval is not None else averaging_time
    legacy_steady_output = output_interval is None
    puff_samples = max(1, int(config.run.get("gaussian_puff_samples", config.run.get("GAUSSIAN_PUFF_SAMPLES", 6))))
    initial_sigma_h = float(
        config.run.get(
            "gaussian_initial_sigma_h",
            config.run.get("GAUSSIAN_INITIAL_SIGMA_H", config.run.get("particle_sigma_h", 0.0)),
        )
    )
    initial_sigma_z = float(
        config.run.get(
            "gaussian_initial_sigma_z",
            config.run.get("GAUSSIAN_INITIAL_SIGMA_Z", config.run.get("particle_sigma_z", 0.0)),
        )
    )
    sampled_terrain = terrain_fields or {}
    ambient_temperature = float(np.nanmean(np.asarray(meteo.get("temperature", [[293.15]]), dtype=float)))
    mixing_height = float(np.nanmean(np.asarray(meteo.get("mixing_height", [[1000.0]]), dtype=float)))
    washout_rate = precipitation_washout_rate(config, meteo)
    wind_sampler = WindSampler(meteo, grid_dx=config.grid.dx, grid_dy=config.grid.dy)
    grid = Grid(**asdict(config.grid))
    ctx = get_mpi_context(parallel)
    gpu = get_gpu_context(gpu_backend or str(config.run.get("gpu_backend", "numpy")), rank=ctx.rank)
    if output_mode == "grid" and numerical_mode == "puff" and ctx.size == 1:
        return _compute_gaussian_grid_concentrations(
            config=config,
            meteo=meteo,
            times=times,
            field_ids=field_ids,
            stability=stability,
            interval_mass_time=interval_mass_time,
            puff_samples=puff_samples,
            initial_sigma_h=initial_sigma_h,
            initial_sigma_z=initial_sigma_z,
            ambient_temperature=ambient_temperature,
            mixing_height=mixing_height,
            washout_rate=washout_rate,
            wind_sampler=wind_sampler,
            terrain_fields=sampled_terrain,
            progress_callback=progress_callback,
        )
    local_receptors = [receptors[i] for i in ctx.partition(len(receptors))]
    local_rows: list[dict[str, float | str]] = []
    for time_index, sample_time in enumerate(times, start=1):
        for rec in local_receptors:
            sample_dt = sample_datetime(config, sample_time)
            firefighter_factor = _firefighters_emission_factor(config, sample_dt)
            total = 0.0
            dry_total = 0.0
            wet_total = 0.0
            for src_index, src in enumerate(config.sources):
                if not _source_active(config, src, sample_dt):
                    continue
                source_ground_asl = _source_ground_altitude_m(src, sampled_terrain, grid)
                release_height_agl = _source_release_height_agl_m(src)
                u, v, speed = wind_sampler.vector(
                    0.5 * (src.x + rec.x),
                    0.5 * (src.y + rec.y),
                    max(0.5 * (source_ground_asl + release_height_agl + rec.z), 0.0),
                    sample_time,
                )
                dx = rec.x - src.x
                dy = rec.y - src.y
                xdown = dx * (u / speed) + dy * (v / speed)
                ycross = -dx * (v / speed) + dy * (u / speed)
                if numerical_mode == "plume" and xdown <= 0:
                    continue
                source_wet_rate = max(src.wet_scavenging, 0.0) + washout_rate
                emission_rate = src.emission_rate * firefighter_factor
                travel_time = xdown / speed
                puff_age_s = min(max(sample_time, 1.0), interval_mass_time)
                elapsed_s = travel_time if legacy_steady_output else puff_age_s
                puff_center_x = xdown if legacy_steady_output else speed * puff_age_s
                eff_h = effective_release_height(
                    stack_height=release_height_agl,
                    source_z=source_ground_asl,
                    receptor_z=0.0,
                    wind_speed=speed,
                    downwind_distance=max(puff_center_x, xdown, 1.0),
                    stack_diameter=src.stack_diameter,
                    exit_velocity=src.exit_velocity,
                    exit_temperature=src.exit_temperature,
                    ambient_temperature=ambient_temperature,
                    heat_release=src.heat_release,
                    downwash=bool(config.run.get("stack_tip_downwash", True)),
                )
                depletion = depletion_factor(
                    travel_time_s=elapsed_s,
                    decay_rate_s=src.decay_rate,
                    deposition_velocity_m_s=src.deposition_velocity,
                    mixing_height_m=mixing_height,
                    wet_scavenging_s=source_wet_rate,
                    settling_velocity_m_s=src.settling_velocity,
                )
                if numerical_mode == "plume":
                    conc = gaussian_plume(
                        q=emission_rate * depletion,
                        wind_speed=speed,
                        x_downwind=xdown,
                        y_crosswind=ycross,
                        z=rec.z,
                        h=eff_h,
                        stability=stability,
                    )
                else:
                    if legacy_steady_output:
                        sigmas = dispersion_parameters(
                            max(puff_center_x, 1.0),
                            stability,
                            elapsed_s=elapsed_s,
                            initial_sigma_y=initial_sigma_h,
                            initial_sigma_z=initial_sigma_z,
                            source_width=src.width,
                            source_length=src.length,
                            source_height=max(src.height, 0.0),
                        )
                        emission_window = min(interval_mass_time, max(elapsed_s, 1.0))
                        mass = emission_rate * emission_window * depletion
                        conc = gaussian_puff(
                            mass=mass,
                            x_receptor=xdown,
                            y_receptor=ycross,
                            z_receptor=rec.z,
                            x_center=puff_center_x,
                            y_center=0.0,
                            z_center=eff_h,
                            sigmas=sigmas,
                        )
                        conc = conc / max(emission_window, 1.0)
                    else:
                        # Continuous sources emit throughout each output
                        # window. Integrate clean-room Gaussian puff kernels
                        # over release ages instead of representing the whole
                        # window with one aged puff center.
                        emission_window = min(interval_mass_time, max(sample_time, 1.0))
                        dt = emission_window / float(puff_samples)
                        conc = 0.0
                        for sample_index in range(puff_samples):
                            age_s = (sample_index + 0.5) * dt
                            center_x = speed * age_s
                            age_eff_h = effective_release_height(
                                stack_height=release_height_agl,
                                source_z=source_ground_asl,
                                receptor_z=0.0,
                                wind_speed=speed,
                                downwind_distance=max(center_x, xdown, 1.0),
                                stack_diameter=src.stack_diameter,
                                exit_velocity=src.exit_velocity,
                                exit_temperature=src.exit_temperature,
                                ambient_temperature=ambient_temperature,
                                heat_release=src.heat_release,
                                downwash=bool(config.run.get("stack_tip_downwash", True)),
                            )
                            age_depletion = depletion_factor(
                                travel_time_s=age_s,
                                decay_rate_s=src.decay_rate,
                                deposition_velocity_m_s=src.deposition_velocity,
                                mixing_height_m=mixing_height,
                                wet_scavenging_s=source_wet_rate,
                                settling_velocity_m_s=src.settling_velocity,
                            )
                            sigmas = dispersion_parameters(
                                max(center_x, 1.0),
                                stability,
                                elapsed_s=age_s,
                                initial_sigma_y=initial_sigma_h,
                                initial_sigma_z=initial_sigma_z,
                                source_width=src.width,
                                source_length=src.length,
                                source_height=max(src.height, 0.0),
                            )
                            conc += gaussian_puff(
                                mass=emission_rate * dt * age_depletion,
                                x_receptor=xdown,
                                y_receptor=ycross,
                                z_receptor=rec.z,
                                x_center=center_x,
                                y_center=0.0,
                                z_center=age_eff_h,
                                sigmas=sigmas,
                            )
                total += conc
                dry_total += conc * max(src.deposition_velocity, 0.0)
                wet_total += conc * source_wet_rate * mixing_height
            row: dict[str, float | str] = {
                "time": sample_time,
                "receptor": rec.id,
                "output_kind": "field" if rec.id in field_ids else "receptor",
                "x": rec.x,
                "y": rec.y,
                "z": rec.z,
                **_terrain_row_fields_for_receptor(sampled_terrain, rec.id),
                "concentration": total,
                "dry_flux": dry_total,
                "wet_flux": wet_total,
            }
            if rec.latitude is not None and rec.longitude is not None:
                row["latitude"] = float(rec.latitude)
                row["longitude"] = float(rec.longitude)
            if sample_dt is not None:
                row["datetime"] = sample_dt.isoformat()
            local_rows.append(row)
        if ctx.is_root:
            if progress_callback is not None:
                progress_callback(time_index, sample_time)
            else:
                LOGGER.info(
                    "Spritz: concentration output interval reached index=%d output_time_s=%.0f",
                    time_index,
                    sample_time,
                )
    return ctx.gather_flat(local_rows)


def write_csv(path: str | Path, rows: list[dict[str, float | str]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "time",
        "datetime",
        "receptor",
        "output_kind",
        "x",
        "y",
        "z",
        "concentration",
        "dry_flux",
        "wet_flux",
    ]
    if any("latitude" in row and "longitude" in row for row in rows):
        fields.extend(["latitude", "longitude"])
    if any("terrain_m" in row for row in rows):
        fields.append("terrain_m")
    if any("land_cover" in row for row in rows):
        fields.append("land_cover")
    with NamedTemporaryFile("w", newline="", encoding="utf-8", dir=p.parent, delete=False) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)
        tmp_name = handle.name
    Path(tmp_name).replace(p)


def write_concentration(path: str | Path, rows: list[dict[str, float | str]], output_format: str = "auto") -> None:
    fmt = infer_format(path, output_format)
    if fmt == "netcdf":
        write_cf_concentration(path, rows)
    elif fmt == "calpuff":
        write_calpuff_concentration_dat(path, rows)
    elif fmt == "legacy":
        write_legacy_table(path, "Spritz concentration and deposition table", rows)
    else:
        write_csv(path, rows)


def run(
    config: SuiteConfig,
    meteo_path: str | Path,
    output: str | Path,
    output_format: str = "auto",
    *,
    terrain_input: str | Path | None = None,
    parallel: str = "serial",
    gpu_backend: str | None = None,
    progress_callback: Callable[[int, float], None] | None = None,
) -> list[dict[str, float | str]]:
    ctx = get_mpi_context(parallel)
    meteo = read_meteorology(meteo_path)
    terrain_fields = terrain_fields_for_grid(terrain_input, config)
    fmt = infer_format(output, output_format)
    if ctx.is_root and ctx.size == 1 and fmt == "netcdf" and concentration_output_mode(config) in {"grid", "both"}:
        config.validate()
        stability = str(config.run.get("stability", config.run.get("STABILITY", "D")))
        numerical_mode = str(config.run.get("numerical_mode", config.run.get("NUMERICAL_MODE", "puff"))).lower()
        if numerical_mode == "puff":
            times = output_times(config)
            output_interval = config.run.get("output_interval_s", config.run.get("OUTPUT_INTERVAL_S"))
            averaging_time = float(config.run.get("averaging_time_s", config.run.get("AVERAGING_TIME_S", 3600.0)))
            interval_mass_time = float(output_interval) if output_interval is not None else averaging_time
            puff_samples = max(1, int(config.run.get("gaussian_puff_samples", config.run.get("GAUSSIAN_PUFF_SAMPLES", 6))))
            initial_sigma_h = float(
                config.run.get(
                    "gaussian_initial_sigma_h",
                    config.run.get("GAUSSIAN_INITIAL_SIGMA_H", config.run.get("particle_sigma_h", 0.0)),
                )
            )
            initial_sigma_z = float(
                config.run.get(
                    "gaussian_initial_sigma_z",
                    config.run.get("GAUSSIAN_INITIAL_SIGMA_Z", config.run.get("particle_sigma_z", 0.0)),
                )
            )
            ambient_temperature = float(np.nanmean(np.asarray(meteo.get("temperature", [[293.15]]), dtype=float)))
            mixing_height = float(np.nanmean(np.asarray(meteo.get("mixing_height", [[1000.0]]), dtype=float)))
            rows = _stream_gaussian_grid_concentrations(
                config=config,
                meteo=meteo,
                output=output,
                times=times,
                stability=stability,
                interval_mass_time=interval_mass_time,
                puff_samples=puff_samples,
                initial_sigma_h=initial_sigma_h,
                initial_sigma_z=initial_sigma_z,
                ambient_temperature=ambient_temperature,
                mixing_height=mixing_height,
                washout_rate=precipitation_washout_rate(config, meteo),
                wind_sampler=WindSampler(meteo, grid_dx=config.grid.dx, grid_dy=config.grid.dy),
                terrain_fields=terrain_fields,
                progress_callback=progress_callback,
                gpu_backend=gpu_backend,
            )
            ctx.barrier()
            return rows
    rows = compute_concentrations(
        config,
        meteo,
        terrain_fields=terrain_fields,
        parallel=parallel,
        gpu_backend=gpu_backend,
        progress_callback=progress_callback,
    )
    if ctx.is_root:
        write_concentration(output, rows, output_format)
    ctx.barrier()
    return rows

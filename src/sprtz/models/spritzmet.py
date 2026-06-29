from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
import logging
from pathlib import Path
from typing import Any, Callable

import numpy as np
from pyproj import CRS, Transformer

from sprtz.config import SuiteConfig
from sprtz.core.grid import Grid
from sprtz.core.physics import wind_components
from sprtz.io.jsonio import write_json
from sprtz.io.legacy_outputs import infer_format
from sprtz.io.netcdf_cf import (
    available as netcdf_available,
    cf_time_units,
    iso_utc,
    write_cf_meteorology,
    write_cf_time_coordinate,
)
from sprtz.models.spritzwrf import WRFWindField
from sprtz.parallel import get_gpu_context, get_mpi_context


LOGGER = logging.getLogger(__name__)

LAND_COVER_ROUGHNESS_M = {
    10: 0.30,
    20: 0.10,
    30: 0.05,
    40: 0.08,
    50: 1.00,
    60: 0.03,
    70: 0.02,
    80: 0.0002,
    90: 0.20,
    100: 0.02,
    111: 1.20,
    112: 0.80,
    121: 0.60,
    122: 0.50,
    123: 0.40,
    124: 0.50,
    131: 0.03,
    132: 0.03,
    133: 0.05,
    141: 0.15,
    142: 0.15,
    211: 0.08,
    212: 0.08,
    213: 0.08,
    221: 0.25,
    222: 0.25,
    223: 0.25,
    231: 0.05,
    241: 0.15,
    242: 0.15,
    243: 0.15,
    244: 0.20,
    311: 1.20,
    312: 1.00,
    313: 1.10,
    321: 0.05,
    322: 0.20,
    323: 0.10,
    324: 0.30,
    331: 0.03,
    332: 0.02,
    333: 0.02,
    334: 0.02,
    335: 0.02,
    411: 0.20,
    412: 0.15,
    421: 0.10,
    422: 0.10,
    423: 0.10,
    511: 0.0002,
    512: 0.0002,
    521: 0.0002,
    522: 0.0002,
    523: 0.0002,
}

DEFAULT_ROUGHNESS_M = 0.10
REFERENCE_ROUGHNESS_M = 0.10
MIN_ROUGHNESS_M = 1.0e-4
ROUGHNESS_WIND_EXPONENT = 0.08
ELEVATION_WIND_SCALE_M = 10000.0
UPSLOPE_WIND_FACTOR = 0.35
OROGRAPHIC_PRECIP_SCALE_M = 3000.0
OROGRAPHIC_UPSLOPE_FACTOR = 0.25
LAND_PRECIP_FACTOR = 0.03
AI_DETAIL_GAIN = 0.18
AI_TERRAIN_GAIN = 0.06
AI_MAX_RELATIVE_ADJUSTMENT = 0.20
DIFFUSION_STEPS = 18
DIFFUSION_RATE = 0.12
DIFFUSION_TERRAIN_EDGE_SCALE = 0.35
DIFFUSION_DETAIL_REINJECTION = 0.08
DownscalingModel = Callable[[dict[str, np.ndarray]], dict[str, np.ndarray]]


def _csv_value(row: dict[str, str], *names: str) -> str | None:
    lowered = {key.strip().lower(): value for key, value in row.items() if key is not None}
    for name in names:
        value = lowered.get(name.lower())
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    return None


def _csv_float(row: dict[str, str], *names: str) -> float | None:
    value = _csv_value(row, *names)
    return float(value) if value is not None else None


def read_station_measurements_csv(
    path: str | Path,
    *,
    center_lat: float | None = None,
    center_lon: float | None = None,
) -> list[dict[str, float | str]]:
    """Read weather-station residual observations for SpritzMet downscaling.

    The CSV must provide either local SpritzMet coordinates `x,y` in meters or
    geographic coordinates `latitude,longitude`/`lat,lon`. Geographic rows are
    projected with the same local azimuthal-equidistant CRS used by SpritzMet,
    so `center_lat` and `center_lon` are required for that form. Recognized
    observation columns are `wind_speed`, `wind_dir`, and
    `precipitation_rate`; at least one observation must be present per row.
    """
    station_path = Path(path)
    stations: list[dict[str, float | str]] = []
    transformer: Transformer | None = None
    with station_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"station measurement CSV {station_path} must include a header row")
        for row_number, row in enumerate(reader, start=2):
            x = _csv_float(row, "x", "x_m", "local_x", "local_x_m")
            y = _csv_float(row, "y", "y_m", "local_y", "local_y_m")
            if x is None or y is None:
                lat = _csv_float(row, "latitude", "lat")
                lon = _csv_float(row, "longitude", "lon", "lng")
                if lat is None or lon is None:
                    raise ValueError(
                        f"station measurement row {row_number} must provide x/y or latitude/longitude"
                    )
                if center_lat is None or center_lon is None:
                    raise ValueError("center_lat and center_lon are required for station latitude/longitude CSV rows")
                if transformer is None:
                    transformer = Transformer.from_crs(
                        CRS.from_epsg(4326), local_crs(center_lat, center_lon), always_xy=True
                    )
                x_value, y_value = transformer.transform(lon, lat)
                x = float(x_value)
                y = float(y_value)
            station: dict[str, float | str] = {"x": float(x), "y": float(y)}
            station_id = _csv_value(row, "id", "station_id", "name")
            if station_id is not None:
                station["id"] = station_id
            for target, aliases in {
                "wind_speed": ("wind_speed", "wind_speed_m_s", "speed", "speed_m_s"),
                "wind_dir": ("wind_dir", "wind_direction", "wind_from_direction", "direction_deg"),
                "precipitation_rate": ("precipitation_rate", "precip_rate", "rain_rate", "rain_mm_h"),
            }.items():
                value = _csv_float(row, *aliases)
                if value is not None:
                    station[target] = value
            if not any(key in station for key in ("wind_speed", "wind_dir", "precipitation_rate")):
                raise ValueError(
                    f"station measurement row {row_number} must include wind_speed/wind_dir or precipitation_rate"
                )
            if ("wind_speed" in station) != ("wind_dir" in station):
                raise ValueError(f"station measurement row {row_number} must provide wind_speed and wind_dir together")
            stations.append(station)
    if not stations:
        raise ValueError(f"station measurement CSV {station_path} does not contain any data rows")
    return stations


def rh_t_to_fmc(rh_pct: np.ndarray, temp_k: np.ndarray) -> np.ndarray:
    """Nelson-style equilibrium moisture content for dead fine fuels."""
    rh = np.asarray(rh_pct, dtype=np.float32)
    temp = np.asarray(temp_k, dtype=np.float32)
    tc = temp - 273.15
    fmc = np.where(
        rh < 10,
        0.03229 + 0.281073 * rh - 0.000578 * rh * tc,
        np.where(
            rh < 50,
            2.22749 + 0.160107 * rh - 0.014780 * tc,
            21.0606 + 0.005565 * rh**2 - 0.000350 * rh * tc - 0.483199 * rh,
        ),
    )
    return np.clip(fmc / 100.0, 0.01, 0.40).astype(np.float32)


def build_meteorology(
    config: SuiteConfig,
    power: float = 2.0,
    *,
    parallel: str = "serial",
    gpu_backend: str | None = None,
) -> dict[str, object]:
    """Build a deterministic SpritzMet-like diagnostic field.

    Station wind vector, temperature, and mixing height are downscaled by
    inverse-distance weighting. The preferred interchange format is NetCDF-CF,
    while JSON and legacy text remain available for compatibility workflows.
    """
    config.validate()
    if power <= 0:
        raise ValueError("downscaling power must be positive")
    ctx = get_mpi_context(parallel)
    gpu = get_gpu_context(gpu_backend or str(config.run.get("gpu_backend", "numpy")), rank=ctx.rank)
    if ctx.is_root:
        LOGGER.info(
            "SpritzMet: building diagnostic meteorology grid=%sx%s stations=%s parallel=%s gpu=%s",
            config.grid.nx,
            config.grid.ny,
            len(config.stations),
            "mpi" if ctx.enabled else "serial",
            gpu.backend,
        )
    xp = gpu.xp
    grid = Grid(**asdict(config.grid))
    xx, yy = grid.mesh()
    row_range = ctx.partition(grid.ny) if ctx.enabled else range(grid.ny)
    row_start = row_range.start
    row_stop = row_range.stop
    LOGGER.debug(
        "SpritzMet: rank %s processing rows [%s:%s) of %s",
        ctx.rank,
        row_start,
        row_stop,
        grid.ny,
    )
    local_xx = xx[row_start:row_stop, :]
    local_yy = yy[row_start:row_stop, :]
    xxa = xp.asarray(local_xx)
    yya = xp.asarray(local_yy)
    local_shape = (row_stop - row_start, grid.nx)
    u = xp.zeros(local_shape, dtype=float)
    v = xp.zeros_like(u)
    temp = xp.zeros_like(u)
    mixh = xp.zeros_like(u)
    precip = xp.zeros_like(u)
    weights = xp.zeros_like(u)
    default_precip = float(config.run.get("default_precipitation_rate", 0.0))

    if not config.stations:
        if ctx.is_root:
            LOGGER.info("SpritzMet: no stations supplied; using configured default fields")
        u.fill(float(config.run.get("default_u", 2.0)))
        v.fill(float(config.run.get("default_v", 0.0)))
        temp.fill(float(config.run.get("default_temperature", 293.15)))
        mixh.fill(float(config.run.get("default_mixing_height", 1000.0)))
        precip.fill(default_precip)
    else:
        if ctx.is_root:
            LOGGER.info("SpritzMet: applying inverse-distance station downscaling")
        for station in config.stations:
            dist = xp.hypot(xxa - station.x, yya - station.y)
            w = 1.0 / xp.maximum(dist, 1.0) ** power
            su, sv = wind_components(station.wind_speed, station.wind_dir)
            u += w * su
            v += w * sv
            temp += w * station.temperature
            mixh += w * station.mixing_height
            precip += w * station.precipitation_rate
            weights += w
        u = xp.divide(u, weights, out=xp.zeros_like(u), where=weights > 0)
        v = xp.divide(v, weights, out=xp.zeros_like(v), where=weights > 0)
        temp = xp.divide(temp, weights, out=xp.full_like(temp, 293.15), where=weights > 0)
        mixh = xp.divide(mixh, weights, out=xp.full_like(mixh, 1000.0), where=weights > 0)
        precip = xp.divide(precip, weights, out=xp.full_like(precip, default_precip), where=weights > 0)

    u_local = np.asarray(gpu.asnumpy(u), dtype=float)
    v_local = np.asarray(gpu.asnumpy(v), dtype=float)
    temp_local = np.asarray(gpu.asnumpy(temp), dtype=float)
    mixh_local = np.asarray(gpu.asnumpy(mixh), dtype=float)
    precip_local = np.asarray(gpu.asnumpy(precip), dtype=float)
    if ctx.enabled:
        LOGGER.debug("SpritzMet: rank %s gathering local meteorology slice", ctx.rank)
        pieces = ctx.allgather((row_start, row_stop, u_local, v_local, temp_local, mixh_local, precip_local))
        u = np.zeros((grid.ny, grid.nx), dtype=float)
        v = np.zeros_like(u)
        temp = np.zeros_like(u)
        mixh = np.zeros_like(u)
        precip = np.zeros_like(u)
        for start, stop, uu, vv, tt, mm, pp in pieces:
            u[start:stop, :] = uu
            v[start:stop, :] = vv
            temp[start:stop, :] = tt
            mixh[start:stop, :] = mm
            precip[start:stop, :] = pp
    else:
        u = u_local
        v = v_local
        temp = temp_local
        mixh = mixh_local
        precip = precip_local
    speed = np.hypot(u, v)
    rh = np.full_like(temp, float(config.run.get("default_relative_humidity", 50.0)))
    fmc = rh_t_to_fmc(rh, temp)
    if ctx.is_root:
        LOGGER.info(
            "SpritzMet: diagnostic field ready wind_speed=%.3f..%.3f m/s precipitation=%.3f..%.3f mm/h",
            float(np.nanmin(speed)),
            float(np.nanmax(speed)),
            float(np.nanmin(precip)),
            float(np.nanmax(precip)),
        )
    return {
        "component": "spritzmet",
        "grid": asdict(config.grid),
        "u": u.tolist(),
        "v": v.tolist(),
        "wind_speed": speed.tolist(),
        "temperature": temp.tolist(),
        "mixing_height": mixh.tolist(),
        "precipitation_rate": precip.tolist(),
        "relative_humidity": rh.tolist(),
        "fmc": fmc.tolist(),
        "stations": [asdict(s) for s in config.stations],
        "metadata": {
            "kernel": "inverse-distance diagnostic",
            "schema_version": "1.1",
            "parallel": "mpi-domain" if ctx.enabled else "serial",
            "gpu_backend": gpu.backend,
            "gpu_device_id": gpu.device_id if gpu.enabled else None,
        },
    }


def run(
    config: SuiteConfig,
    output: str | Path,
    output_format: str = "auto",
    *,
    parallel: str = "serial",
    gpu_backend: str | None = None,
) -> dict[str, object]:
    ctx = get_mpi_context(parallel)
    if ctx.is_root:
        LOGGER.info("SpritzMet: starting run output=%s format=%s", output, output_format)
    result = build_meteorology(config, parallel=parallel, gpu_backend=gpu_backend)
    fmt = infer_format(output, output_format)
    if ctx.is_root:
        LOGGER.info("SpritzMet: writing %s meteorology to %s", fmt, output)
        if fmt == "netcdf":
            write_cf_meteorology(output, result)
        else:
            write_json(output, result)
    ctx.barrier()
    if ctx.is_root:
        LOGGER.info("SpritzMet: run complete")
    return result


@dataclass(frozen=True)
class LocalMeteorology:
    x: np.ndarray
    y: np.ndarray
    latitude: np.ndarray
    longitude: np.ndarray
    u: np.ndarray
    v: np.ndarray
    precipitation_rate: np.ndarray
    center_lat: float
    center_lon: float
    dx_m: float
    dy_m: float
    source: str
    valid_datetime_utc: str | None = None
    valid_datetimes_utc: list[str] | None = None
    downscaling_metadata: dict[str, Any] | None = None

    @property
    def wind_4d(self) -> tuple[np.ndarray, np.ndarray]:
        u = np.asarray(self.u, dtype=float)
        v = np.asarray(self.v, dtype=float)
        if u.shape != v.shape:
            raise ValueError(f"u/v shape mismatch: {u.shape} vs {v.shape}")
        if u.ndim == 2:
            return u[np.newaxis, np.newaxis, :, :], v[np.newaxis, np.newaxis, :, :]
        if u.ndim == 3:
            return u[:, np.newaxis, :, :], v[:, np.newaxis, :, :]
        if u.ndim == 4:
            return u, v
        raise ValueError("local wind must be shaped as y,x; time,y,x; or time,z,y,x")

    @property
    def precipitation_3d(self) -> np.ndarray:
        precipitation = np.asarray(self.precipitation_rate, dtype=float)
        if precipitation.ndim == 2:
            return precipitation[np.newaxis, :, :]
        if precipitation.ndim == 3:
            return precipitation
        raise ValueError("precipitation_rate must be shaped as y,x or time,y,x")

    @property
    def surface_u(self) -> np.ndarray:
        return self.wind_4d[0][0, 0, :, :]

    @property
    def surface_v(self) -> np.ndarray:
        return self.wind_4d[1][0, 0, :, :]

    @property
    def wind_speed(self) -> np.ndarray:
        u, v = self.wind_4d
        return np.hypot(u, v)

    @property
    def wind_from_direction(self) -> np.ndarray:
        u, v = self.wind_4d
        return (270.0 - np.rad2deg(np.arctan2(v, u))) % 360.0

    @property
    def z_levels_m(self) -> list[float] | None:
        metadata = self.downscaling_metadata or {}
        raw_levels = metadata.get("level_meters")
        if not isinstance(raw_levels, list):
            return None
        levels = [float(level) for level in raw_levels]
        if len(levels) != self.wind_4d[0].shape[1]:
            return None
        return levels

    def to_payload(self) -> dict[str, Any]:
        time_datetime = iso_utc(self.valid_datetime_utc)
        time_datetimes = [iso_utc(value) for value in (self.valid_datetimes_utc or [])]
        time_datetimes = [value for value in time_datetimes if value]
        if not time_datetimes and time_datetime:
            time_datetimes = [time_datetime]
        u4, v4 = self.wind_4d
        precipitation3 = self.precipitation_3d
        return {
            "component": "spritzmet.local_meteorology",
            "center_lat": self.center_lat,
            "center_lon": self.center_lon,
            "x": self.x.tolist(),
            "y": self.y.tolist(),
            "latitude": self.latitude.tolist(),
            "longitude": self.longitude.tolist(),
            "z": self.z_levels_m or list(range(u4.shape[1])),
            "u": u4.tolist(),
            "v": v4.tolist(),
            "wind_speed": self.wind_speed.tolist(),
            "wind_from_direction": self.wind_from_direction.tolist(),
            "precipitation_rate": precipitation3.tolist(),
            "dx_m": self.dx_m,
            "dy_m": self.dy_m,
            "source": self.source,
            **(
                {
                    "time": list(range(len(time_datetimes))),
                    "time_units": cf_time_units(time_datetimes[0]),
                    "time_datetime": time_datetimes,
                }
                if time_datetimes
                else {}
            ),
            "metadata": {
                "spritzwrf_to_spritzmet": True,
                "downscaling": "inverse-distance weighting on WRF latitude/longitude nodes",
                "schema_version": "1.2",
                **(self.downscaling_metadata or {}),
                **({"valid_datetime_utc": time_datetime} if time_datetime else {}),
                **({"valid_datetimes_utc": time_datetimes} if time_datetimes else {}),
            },
        }


def local_crs(center_lat: float, center_lon: float) -> CRS:
    return CRS.from_proj4(
        f"+proj=aeqd +lat_0={center_lat:.12f} +lon_0={center_lon:.12f} "
        "+datum=WGS84 +units=m +no_defs"
    )


def local_grid_latlon(
    center_lat: float,
    center_lon: float,
    nx: int,
    ny: int,
    dx_m: float,
    dy_m: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    x = (np.arange(nx, dtype=float) - (nx - 1) / 2.0) * dx_m
    y = (np.arange(ny, dtype=float) - (ny - 1) / 2.0) * dy_m
    xx, yy = np.meshgrid(x, y)
    transformer = Transformer.from_crs(
        local_crs(center_lat, center_lon), CRS.from_epsg(4326), always_xy=True
    )
    lon, lat = transformer.transform(xx, yy)
    return xx, yy, np.asarray(lat, dtype=float), np.asarray(lon, dtype=float)


def _idw_downscale(
    src_lat: np.ndarray,
    src_lon: np.ndarray,
    src_value: np.ndarray,
    dst_lat: np.ndarray,
    dst_lon: np.ndarray,
    power: float = 2.0,
    k: int = 8,
) -> np.ndarray:
    if power <= 0:
        raise ValueError("power must be positive")
    if k <= 0:
        raise ValueError("k must be positive")
    src_points = np.column_stack([src_lat.ravel(), src_lon.ravel()])
    src_values = src_value.ravel()
    dst_points = np.column_stack([dst_lat.ravel(), dst_lon.ravel()])
    out = np.empty(dst_points.shape[0], dtype=float)
    k_eff = min(k, src_points.shape[0])
    for i, point in enumerate(dst_points):
        d2 = np.sum((src_points - point) ** 2, axis=1)
        nearest = np.argpartition(d2, k_eff - 1)[:k_eff]
        if np.any(d2[nearest] == 0):
            out[i] = float(src_values[nearest[np.argmin(d2[nearest])]])
            continue
        weights = 1.0 / np.maximum(d2[nearest], 1.0e-20) ** (power / 2.0)
        out[i] = float(np.sum(weights * src_values[nearest]) / np.sum(weights))
    return out.reshape(dst_lat.shape)


def _metadata_list(metadata: dict[str, Any] | None, key: str) -> list[Any]:
    if not metadata:
        return []
    value = metadata.get(key)
    return value if isinstance(value, list) else []


def _validated_level_meters(metadata: dict[str, Any] | None, nz: int) -> list[float] | None:
    levels = _metadata_list(metadata, "level_meters")
    if not levels:
        return None
    if len(levels) != nz:
        raise ValueError(
            f"level_meters contains {len(levels)} heights, but downscaled wind has {nz} vertical levels"
        )
    return [float(level) for level in levels]


def _metadata_index(metadata: dict[str, Any] | None, key: str) -> str | None:
    if not metadata:
        return None
    value = metadata.get(key)
    return str(value) if value is not None else None


def _time_label(metadata: dict[str, Any] | None, index: int | None) -> tuple[str, str]:
    configured = _metadata_index(metadata, "time_index")
    datetimes = _metadata_list(metadata, "time_datetimes")
    selected_datetime = str(metadata.get("time_datetime")) if metadata and metadata.get("time_datetime") else None
    if index is None:
        shown_index = configured or "0"
        return shown_index, selected_datetime or "unknown"
    if configured and configured != "all" and len(datetimes) <= 1:
        shown_index = configured
    else:
        shown_index = str(index)
    if datetimes and index < len(datetimes):
        return shown_index, str(datetimes[index])
    return shown_index, selected_datetime or "unknown"


def _level_label(metadata: dict[str, Any] | None, index: int | None) -> tuple[str, str]:
    configured = _metadata_index(metadata, "level_index")
    levels = _metadata_list(metadata, "level_meters")
    if index is None:
        shown_index = configured or "0"
    elif configured and configured != "all" and len(levels) <= 1:
        shown_index = configured
    else:
        shown_index = str(index)
    if levels:
        level_index = 0 if index is None or len(levels) == 1 else index
        if level_index < len(levels):
            return shown_index, f"{float(levels[level_index]):.3f}"
    return shown_index, "unknown"


def _log_downscaling_slice(
    field_name: str,
    index: tuple[int, ...] | None,
    metadata: dict[str, Any] | None,
) -> None:
    time_i = index[0] if index and len(index) >= 1 else None
    level_i = index[1] if index and len(index) >= 2 else None
    time_index, datetime_utc = _time_label(metadata, time_i)
    level_index, level_m = _level_label(metadata, level_i)
    LOGGER.info(
        "SpritzMet: downscaling %s time_index=%s datetime_utc=%s level_index=%s level_m=%s",
        field_name,
        time_index,
        datetime_utc,
        level_index,
        level_m,
    )


def _downscale_spatial_stack(
    src_lat: np.ndarray,
    src_lon: np.ndarray,
    src_value: np.ndarray,
    dst_lat: np.ndarray,
    dst_lon: np.ndarray,
    *,
    power: float,
    neighbours: int,
    field_name: str,
    metadata: dict[str, Any] | None = None,
) -> np.ndarray:
    values = np.asarray(src_value, dtype=float)
    if values.ndim == 2:
        _log_downscaling_slice(field_name, None, metadata)
        return _idw_downscale(src_lat, src_lon, values, dst_lat, dst_lon, power=power, k=neighbours)
    if values.ndim not in {3, 4}:
        raise ValueError("WRF field must be shaped as y,x; time,y,x; or time,z,y,x")
    leading_shape = values.shape[:-2]
    downscaled = np.empty((*leading_shape, *dst_lat.shape), dtype=float)
    for index in np.ndindex(leading_shape):
        _log_downscaling_slice(field_name, index, metadata)
        downscaled[index] = _idw_downscale(src_lat, src_lon, values[index], dst_lat, dst_lon, power=power, k=neighbours)
    return downscaled


def _wind_time_count(values: np.ndarray) -> int:
    arr = np.asarray(values, dtype=float)
    if arr.ndim == 4:
        return arr.shape[0]
    if arr.ndim == 3:
        return arr.shape[0]
    return 1


def _as_wind_4d(name: str, values: np.ndarray) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    if arr.ndim == 2:
        return arr[np.newaxis, np.newaxis, :, :]
    if arr.ndim == 3:
        return arr[:, np.newaxis, :, :]
    if arr.ndim == 4:
        return arr
    raise ValueError(f"{name} must be shaped as y,x; time,y,x; or time,z,y,x")


def _as_precipitation_3d(values: np.ndarray, ntime: int, shape: tuple[int, int]) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    if arr.ndim == 2:
        arr = np.broadcast_to(arr[np.newaxis, :, :], (ntime, *shape)).copy()
    if arr.ndim != 3:
        raise ValueError("precipitation_rate must be shaped as y,x or time,y,x")
    if arr.shape[-2:] != shape:
        raise ValueError(f"precipitation_rate grid shape {arr.shape[-2:]} must match wind grid shape {shape}")
    if arr.shape[0] == 1 and ntime != 1:
        arr = np.broadcast_to(arr, (ntime, *shape)).copy()
    if arr.shape[0] != ntime:
        raise ValueError(f"precipitation_rate time dimension {arr.shape[0]} must match wind time dimension {ntime}")
    return arr


def _require_grid_field(name: str, values: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    field = np.asarray(values, dtype=float)
    if field.shape != shape:
        raise ValueError(f"{name} shape {field.shape} must match local grid shape {shape}")
    if not np.all(np.isfinite(field)):
        raise ValueError(f"{name} must contain only finite values")
    return field


def _land_cover_roughness(land_cover: np.ndarray) -> np.ndarray:
    classes = np.asarray(np.rint(land_cover), dtype=int)
    roughness = np.full(classes.shape, DEFAULT_ROUGHNESS_M, dtype=float)
    for code, value in LAND_COVER_ROUGHNESS_M.items():
        roughness[classes == code] = value
    return roughness


def _expand_to_field(field: np.ndarray, target_ndim: int) -> np.ndarray:
    expanded = np.asarray(field, dtype=float)
    while expanded.ndim < target_ndim:
        expanded = expanded[np.newaxis, ...]
    return expanded


def _diagnostic_wind_adjustment(
    u: np.ndarray,
    v: np.ndarray,
    elevation: np.ndarray,
    roughness: np.ndarray,
    *,
    dx_m: float,
    dy_m: float,
) -> tuple[np.ndarray, np.ndarray, dict[str, float]]:
    """Apply clean-room CALMET-style terrain and roughness wind adjustments."""
    grad_y, grad_x = np.gradient(elevation, dy_m, dx_m)
    slope = np.hypot(grad_x, grad_y)
    roughness_factor = np.clip(
        (REFERENCE_ROUGHNESS_M / np.maximum(roughness, MIN_ROUGHNESS_M)) ** ROUGHNESS_WIND_EXPONENT,
        0.80,
        1.20,
    )
    elevation_factor = np.clip(
        1.0 + (elevation - float(np.nanmean(elevation))) / ELEVATION_WIND_SCALE_M,
        0.90,
        1.10,
    )

    u_arr = np.asarray(u, dtype=float)
    v_arr = np.asarray(v, dtype=float)
    speed = np.hypot(u_arr, v_arr)
    upslope_component = np.divide(
        u_arr * grad_x + v_arr * grad_y,
        np.maximum(speed, 1.0e-9),
        out=np.zeros_like(speed),
        where=speed > 0.0,
    )
    terrain_factor = np.clip(1.0 + UPSLOPE_WIND_FACTOR * upslope_component, 0.75, 1.25)
    wind_factor = _expand_to_field(roughness_factor * elevation_factor, u_arr.ndim)
    return (
        u_arr * wind_factor * terrain_factor,
        v_arr * wind_factor * terrain_factor,
        {
            "max_slope_m_per_m": float(np.nanmax(slope)),
            "max_wind_factor": float(np.nanmax(wind_factor * terrain_factor)),
            "min_wind_factor": float(np.nanmin(wind_factor * terrain_factor)),
        },
    )


def _diagnostic_precipitation_adjustment(
    precipitation_rate: np.ndarray,
    wind_u: np.ndarray,
    wind_v: np.ndarray,
    elevation: np.ndarray,
    roughness: np.ndarray,
    *,
    dx_m: float,
    dy_m: float,
) -> tuple[np.ndarray, dict[str, float]]:
    """Apply clean-room orographic and land-cover precipitation adjustments."""
    grad_y, grad_x = np.gradient(elevation, dy_m, dx_m)
    precip_arr = np.asarray(precipitation_rate, dtype=float)
    precip_wind_u = np.asarray(wind_u, dtype=float)
    precip_wind_v = np.asarray(wind_v, dtype=float)
    while precip_wind_u.ndim > precip_arr.ndim:
        precip_wind_u = np.take(precip_wind_u, 0, axis=1)
        precip_wind_v = np.take(precip_wind_v, 0, axis=1)
    wind_speed = np.hypot(precip_wind_u, precip_wind_v)
    upslope = np.divide(
        precip_wind_u * grad_x + precip_wind_v * grad_y,
        np.maximum(wind_speed, 1.0e-9),
        out=np.zeros_like(wind_speed),
        where=wind_speed > 0.0,
    )
    relief_factor = np.clip(
        1.0 + (elevation - float(np.nanmean(elevation))) / OROGRAPHIC_PRECIP_SCALE_M,
        0.75,
        1.50,
    )
    upslope_factor = np.clip(1.0 + OROGRAPHIC_UPSLOPE_FACTOR * np.maximum(upslope, 0.0), 1.0, 1.30)
    land_factor = np.clip(
        1.0 + LAND_PRECIP_FACTOR * np.log1p(roughness / REFERENCE_ROUGHNESS_M),
        0.95,
        1.15,
    )
    precip_factor = _expand_to_field(relief_factor * upslope_factor * land_factor, precip_arr.ndim)
    corrected = np.clip(precip_arr * precip_factor, 0.0, None)
    return (
        corrected,
        {
            "max_precipitation_factor": float(np.nanmax(precip_factor)),
            "min_precipitation_factor": float(np.nanmin(precip_factor)),
        },
    )


def _apply_surface_downscaling(
    u: np.ndarray,
    v: np.ndarray,
    precipitation_rate: np.ndarray,
    *,
    dem_elevation_m: np.ndarray | None,
    land_cover: np.ndarray | None,
    dx_m: float,
    dy_m: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    metadata: dict[str, Any] = {"terrain_downscaling": False}
    if dem_elevation_m is None and land_cover is None:
        LOGGER.info("SpritzMet: terrain-aware downscaling disabled")
        return u, v, precipitation_rate, metadata

    grid_shape = u.shape[-2:]
    LOGGER.info(
        "SpritzMet: applying terrain-aware deterministic downscaling dem=%s land_cover=%s grid=%sx%s",
        dem_elevation_m is not None,
        land_cover is not None,
        grid_shape[1],
        grid_shape[0],
    )
    elevation = (
        _require_grid_field("dem_elevation_m", dem_elevation_m, grid_shape)
        if dem_elevation_m is not None
        else np.zeros(grid_shape, dtype=float)
    )
    roughness = (
        _land_cover_roughness(_require_grid_field("land_cover", land_cover, grid_shape))
        if land_cover is not None
        else np.full(grid_shape, REFERENCE_ROUGHNESS_M, dtype=float)
    )

    corrected_u, corrected_v, wind_metadata = _diagnostic_wind_adjustment(
        u,
        v,
        elevation,
        roughness,
        dx_m=dx_m,
        dy_m=dy_m,
    )
    corrected_precipitation, precipitation_metadata = _diagnostic_precipitation_adjustment(
        precipitation_rate,
        corrected_u,
        corrected_v,
        elevation,
        roughness,
        dx_m=dx_m,
        dy_m=dy_m,
    )

    metadata.update(
        {
            "terrain_downscaling": True,
            "downscaling_algorithm": "clean_room_calmet_style_diagnostic",
            "uses_dem_elevation_m": dem_elevation_m is not None,
            "uses_land_cover": land_cover is not None,
            "roughness_source": "land_cover_lookup" if land_cover is not None else "uniform_reference",
            **wind_metadata,
            **precipitation_metadata,
        }
    )
    return corrected_u, corrected_v, corrected_precipitation, metadata


def _station_value(station: Any, name: str) -> float | None:
    if isinstance(station, dict):
        value = station.get(name)
    else:
        value = getattr(station, name, None)
    if value is None:
        return None
    return float(value)


def _apply_station_measurement_improvement(
    u: np.ndarray,
    v: np.ndarray,
    precipitation_rate: np.ndarray,
    *,
    stations: list[Any] | None,
    dst_x: np.ndarray,
    dst_y: np.ndarray,
    power: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    if not stations:
        LOGGER.info("SpritzMet: station measurement improvement disabled")
        return u, v, precipitation_rate, {"station_measurement_improvement": False}

    LOGGER.info("SpritzMet: applying station measurement improvement stations=%s", len(stations))
    u4 = _as_wind_4d("u", u)
    v4 = _as_wind_4d("v", v)
    p3 = _as_precipitation_3d(precipitation_rate, u4.shape[0], u4.shape[-2:])
    correction_u = np.zeros(u4.shape[-2:], dtype=float)
    correction_v = np.zeros_like(correction_u)
    correction_p = np.zeros_like(correction_u)
    weights_u = np.zeros_like(correction_u)
    weights_v = np.zeros_like(correction_u)
    weights_p = np.zeros_like(correction_u)

    for station in stations:
        sx = _station_value(station, "x")
        sy = _station_value(station, "y")
        if sx is None or sy is None:
            continue
        dist = np.hypot(dst_x - sx, dst_y - sy)
        w = 1.0 / np.maximum(dist, 1.0) ** power
        ws = _station_value(station, "wind_speed")
        wd = _station_value(station, "wind_dir")
        if ws is not None and wd is not None:
            su, sv = wind_components(ws, wd)
            nearest = np.unravel_index(int(np.argmin(dist)), dist.shape)
            correction_u += w * (su - float(u4[0, 0, nearest[0], nearest[1]]))
            correction_v += w * (sv - float(v4[0, 0, nearest[0], nearest[1]]))
            weights_u += w
            weights_v += w
        sp = _station_value(station, "precipitation_rate")
        if sp is not None:
            nearest = np.unravel_index(int(np.argmin(dist)), dist.shape)
            correction_p += w * (sp - float(p3[0, nearest[0], nearest[1]]))
            weights_p += w

    du = np.divide(correction_u, weights_u, out=np.zeros_like(correction_u), where=weights_u > 0)
    dv = np.divide(correction_v, weights_v, out=np.zeros_like(correction_v), where=weights_v > 0)
    dp = np.divide(correction_p, weights_p, out=np.zeros_like(correction_p), where=weights_p > 0)
    return (
        u4 + du[np.newaxis, np.newaxis, :, :],
        v4 + dv[np.newaxis, np.newaxis, :, :],
        np.clip(p3 + dp[np.newaxis, :, :], 0.0, None),
        {"station_measurement_improvement": True, "station_measurement_count": len(stations)},
    )


def _standardized(values: np.ndarray) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    spread = float(np.nanstd(arr))
    if spread <= 1.0e-12:
        return np.zeros_like(arr, dtype=float)
    return (arr - float(np.nanmean(arr))) / spread


def _neighbor_mean_2d(field: np.ndarray) -> np.ndarray:
    padded = np.pad(np.asarray(field, dtype=float), 1, mode="edge")
    return (
        padded[:-2, 1:-1]
        + padded[2:, 1:-1]
        + padded[1:-1, :-2]
        + padded[1:-1, 2:]
        + 4.0 * padded[1:-1, 1:-1]
    ) / 8.0


def _bounded_mean_preserving_update(base: np.ndarray, proposal: np.ndarray, max_relative: float) -> np.ndarray:
    original = np.asarray(base, dtype=float)
    updated = np.asarray(proposal, dtype=float)
    original_mean = float(np.nanmean(original))
    updated = updated - float(np.nanmean(updated)) + original_mean
    limit = max(max(abs(original_mean), float(np.nanstd(original))), 1.0)
    return np.clip(updated, original - max_relative * limit, original + max_relative * limit)


def _terrain_feature(
    shape: tuple[int, int],
    dem_elevation_m: np.ndarray | None,
    land_cover: np.ndarray | None,
) -> np.ndarray:
    feature = np.zeros(shape, dtype=float)
    if dem_elevation_m is not None:
        elevation = _require_grid_field("dem_elevation_m", dem_elevation_m, shape)
        gy, gx = np.gradient(elevation)
        feature += 0.7 * _standardized(elevation) + 0.3 * _standardized(np.hypot(gx, gy))
    if land_cover is not None:
        roughness = _land_cover_roughness(_require_grid_field("land_cover", land_cover, shape))
        feature += 0.4 * _standardized(np.log(np.maximum(roughness, MIN_ROUGHNESS_M)))
    if not np.any(feature):
        yy, xx = np.indices(shape, dtype=float)
        feature = _standardized((xx - float(np.mean(xx))) * (yy - float(np.mean(yy))))
    return _standardized(feature)


def _apply_ai_feature_downscaling(
    u: np.ndarray,
    v: np.ndarray,
    precipitation_rate: np.ndarray,
    *,
    dem_elevation_m: np.ndarray | None,
    land_cover: np.ndarray | None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    """Apply an in-package clean-room feature residual downscaler.

    The kernel behaves like a tiny deterministic inference model: each local
    slice is transformed through normalized high-frequency meteorological
    residuals and static terrain/roughness features, then bounded and shifted to
    preserve the slice mean. It is intentionally dependency-free and does not
    embed third-party weights or parameter tables.
    """
    u4 = _as_wind_4d("u", u)
    v4 = _as_wind_4d("v", v)
    p3 = _as_precipitation_3d(precipitation_rate, u4.shape[0], u4.shape[-2:])
    feature = _terrain_feature(u4.shape[-2:], dem_elevation_m, land_cover)
    uu = np.empty_like(u4)
    vv = np.empty_like(v4)
    for index in np.ndindex(u4.shape[:-2]):
        speed_scale = max(float(np.nanstd(np.hypot(u4[index], v4[index]))), 0.05)
        for source, target in ((u4, uu), (v4, vv)):
            base = source[index]
            detail = base - _neighbor_mean_2d(base)
            proposal = base + AI_DETAIL_GAIN * detail + AI_TERRAIN_GAIN * speed_scale * feature
            target[index] = _bounded_mean_preserving_update(base, proposal, AI_MAX_RELATIVE_ADJUSTMENT)
    pp = np.empty_like(p3)
    for index in np.ndindex(p3.shape[:-2]):
        base = p3[index]
        detail = base - _neighbor_mean_2d(base)
        proposal = base + AI_DETAIL_GAIN * detail + AI_TERRAIN_GAIN * max(float(np.nanstd(base)), 0.02) * feature
        pp[index] = np.clip(_bounded_mean_preserving_update(base, proposal, AI_MAX_RELATIVE_ADJUSTMENT), 0.0, None)
    return uu, vv, pp, {
        "model_status": "applied_builtin",
        "model_family": "clean_room_feature_residual_ai",
        "model_training_data": "none_runtime_deterministic_features",
    }


def _diffuse_2d(field: np.ndarray, terrain_edge: np.ndarray) -> np.ndarray:
    base = np.asarray(field, dtype=float)
    smoothed = base.copy()
    conductance = np.exp(-DIFFUSION_TERRAIN_EDGE_SCALE * np.abs(terrain_edge))
    for _ in range(DIFFUSION_STEPS):
        padded = np.pad(smoothed, 1, mode="edge")
        laplacian = (
            padded[:-2, 1:-1]
            + padded[2:, 1:-1]
            + padded[1:-1, :-2]
            + padded[1:-1, 2:]
            - 4.0 * padded[1:-1, 1:-1]
        )
        smoothed = smoothed + DIFFUSION_RATE * conductance * laplacian
    detail = base - _neighbor_mean_2d(base)
    return _bounded_mean_preserving_update(base, smoothed + DIFFUSION_DETAIL_REINJECTION * detail, 0.15)


def _apply_diffusion_downscaling(
    u: np.ndarray,
    v: np.ndarray,
    precipitation_rate: np.ndarray,
    *,
    dem_elevation_m: np.ndarray | None,
    land_cover: np.ndarray | None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    """Apply deterministic terrain-conditioned diffusion refinement."""
    u4 = _as_wind_4d("u", u)
    v4 = _as_wind_4d("v", v)
    p3 = _as_precipitation_3d(precipitation_rate, u4.shape[0], u4.shape[-2:])
    terrain_edge = _terrain_feature(u4.shape[-2:], dem_elevation_m, land_cover)
    uu = np.empty_like(u4)
    vv = np.empty_like(v4)
    for index in np.ndindex(u4.shape[:-2]):
        uu[index] = _diffuse_2d(u4[index], terrain_edge)
        vv[index] = _diffuse_2d(v4[index], terrain_edge)
    pp = np.empty_like(p3)
    for index in np.ndindex(p3.shape[:-2]):
        pp[index] = np.clip(_diffuse_2d(p3[index], terrain_edge), 0.0, None)
    return uu, vv, pp, {
        "model_status": "applied_builtin",
        "model_family": "clean_room_anisotropic_diffusion",
        "diffusion_steps": DIFFUSION_STEPS,
    }


def _apply_optional_model_downscaling(
    method: str,
    u: np.ndarray,
    v: np.ndarray,
    precipitation_rate: np.ndarray,
    *,
    dem_elevation_m: np.ndarray | None,
    land_cover: np.ndarray | None,
    ai_model: DownscalingModel | None,
    diffusion_model: DownscalingModel | None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    metadata: dict[str, Any] = {"downscaling_mode": method}
    if method == "deterministic":
        LOGGER.info("SpritzMet: optional model downscaling disabled; using deterministic mode")
        return u, v, precipitation_rate, metadata
    model = ai_model if method == "ai" else diffusion_model
    metadata["model_supplied"] = model is not None
    if model is None:
        LOGGER.info("SpritzMet: applying built-in %s downscaling model", method)
        if method == "ai":
            uu, vv, pp, model_metadata = _apply_ai_feature_downscaling(
                u,
                v,
                precipitation_rate,
                dem_elevation_m=dem_elevation_m,
                land_cover=land_cover,
            )
        else:
            uu, vv, pp, model_metadata = _apply_diffusion_downscaling(
                u,
                v,
                precipitation_rate,
                dem_elevation_m=dem_elevation_m,
                land_cover=land_cover,
            )
        metadata.update(model_metadata)
        return uu, vv, pp, metadata
    LOGGER.info("SpritzMet: applying %s downscaling model", method)
    result = model(
        {
            "u": _as_wind_4d("u", u),
            "v": _as_wind_4d("v", v),
            "precipitation_rate": precipitation_rate,
            "dem_elevation_m": np.asarray(dem_elevation_m, dtype=float) if dem_elevation_m is not None else None,
            "land_cover": np.asarray(land_cover, dtype=float) if land_cover is not None else None,
        }
    )
    uu = _as_wind_4d("model u", np.asarray(result.get("u", u), dtype=float))
    vv = _as_wind_4d("model v", np.asarray(result.get("v", v), dtype=float))
    pp = _as_precipitation_3d(
        np.asarray(result.get("precipitation_rate", precipitation_rate), dtype=float),
        uu.shape[0],
        uu.shape[-2:],
    )
    if vv.shape != uu.shape:
        raise ValueError(f"model v shape {vv.shape} must match model u shape {uu.shape}")
    metadata["model_status"] = "applied"
    return uu, vv, pp, metadata


def _netcdf_attribute_value(value: Any) -> str | int | float:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float, str)):
        return value
    return str(value)


def terrain_downscaling_inputs_from_rasters(
    *,
    center_lat: float,
    center_lon: float,
    nx: int,
    ny: int,
    dx_m: float,
    dy_m: float,
    dem_path: str | Path | None = None,
    land_cover_path: str | Path | None = None,
) -> tuple[np.ndarray | None, np.ndarray | None, dict[str, Any]]:
    """Read optional DEM and land-cover rasters on the exact SpritzMet grid.

    DEM values are continuous and are bilinearly resampled. Land-cover values
    are categorical labels and are sampled with nearest-neighbor logic.
    GeoTIFF/COG input is supported through the optional `rasterio` dependency
    used by the terrain package.
    """
    metadata: dict[str, Any] = {}
    if dem_path is None and land_cover_path is None:
        LOGGER.info("SpritzMet: no DEM or land-cover rasters requested")
        return None, None, metadata

    from sprtz.terrain.providers.base import RasterRequest
    from sprtz.terrain.providers.local import LocalRasterProvider
    from sprtz.terrain.regrid import DomainDefinition, build_target_grid, resample_dem, resample_land_cover

    domain = DomainDefinition(
        center_lat=center_lat,
        center_lon=center_lon,
        nx=nx,
        ny=ny,
        dx_m=dx_m,
        dy_m=dy_m,
    )
    grid = build_target_grid(domain)
    LOGGER.info(
        "SpritzMet: preparing terrain inputs center=(%.6f, %.6f) grid=%sx%s spacing=%.3fx%.3f m",
        center_lat,
        center_lon,
        nx,
        ny,
        dx_m,
        dy_m,
    )
    dem = None
    land_cover = None
    if dem_path is not None:
        LOGGER.info("SpritzMet: reading DEM raster %s", dem_path)
        raster = LocalRasterProvider(dem_path, "dem", dataset="spritzmet-dem").fetch(
            RasterRequest("dem", domain, ".")
        )
        LOGGER.info("SpritzMet: resampling DEM raster to local grid")
        dem = resample_dem(raster, grid)
        metadata.update(
            {
                "dem_source": raster.source,
                "dem_dataset": raster.dataset,
                "dem_crs": raster.crs,
                "dem_resampling": "bilinear",
            }
        )
    if land_cover_path is not None:
        LOGGER.info("SpritzMet: reading land-cover raster %s", land_cover_path)
        raster = LocalRasterProvider(land_cover_path, "landcover", dataset="spritzmet-land-cover").fetch(
            RasterRequest("landcover", domain, ".")
        )
        LOGGER.info("SpritzMet: resampling land-cover raster to local grid")
        land_cover = resample_land_cover(raster, grid)
        metadata.update(
            {
                "land_cover_source": raster.source,
                "land_cover_dataset": raster.dataset,
                "land_cover_crs": raster.crs,
                "land_cover_resampling": "nearest",
            }
        )
    return dem, land_cover, metadata


def downscale_wrf_to_local_grid(
    wrf: WRFWindField,
    *,
    center_lat: float,
    center_lon: float,
    nx: int = 101,
    ny: int = 101,
    dx_m: float = 100.0,
    dy_m: float = 100.0,
    power: float = 2.0,
    neighbours: int = 8,
    dem_elevation_m: np.ndarray | None = None,
    land_cover: np.ndarray | None = None,
    terrain_input_metadata: dict[str, Any] | None = None,
    downscaling_mode: str = "deterministic",
    station_measurements: list[Any] | None = None,
    ai_model: DownscalingModel | None = None,
    diffusion_model: DownscalingModel | None = None,
) -> LocalMeteorology:
    """Downscale SpritzWRF near-surface fields to a local SpritzMet grid.

    When aligned DEM elevation and land-cover arrays are supplied, SpritzMet
    defaults to a deterministic clean-room diagnostic adjustment that uses both
    DEM and land-cover information. Optional ``ai`` and ``diffusion`` modes run
    built-in clean-room NumPy refinements unless callers supply model callables.
    All modes can be improved with weather-station residual measurements.
    """
    mode = downscaling_mode.lower().replace("_", "-")
    mode = {"deterministic": "deterministic", "ai": "ai", "ai-based": "ai", "diffusion": "diffusion", "diffusion-model": "diffusion"}.get(mode, mode)
    if mode not in {"deterministic", "ai", "diffusion"}:
        raise ValueError("downscaling_mode must be one of: deterministic, ai, diffusion")
    if nx < 2 or ny < 2:
        raise ValueError("nx and ny must be at least 2")
    if dx_m <= 0 or dy_m <= 0:
        raise ValueError("dx_m and dy_m must be positive")
    LOGGER.info(
        "SpritzMet: downscaling WRF source=%s mode=%s target_grid=%sx%s spacing=%.3fx%.3f m",
        wrf.source_path,
        mode,
        nx,
        ny,
        dx_m,
        dy_m,
    )
    xx, yy, dst_lat, dst_lon = local_grid_latlon(center_lat, center_lon, nx, ny, dx_m, dy_m)
    LOGGER.info("SpritzMet: local latitude/longitude grid ready")
    LOGGER.info("SpritzMet: downscaling eastward wind shape=%s", np.asarray(wrf.u).shape)
    u = _downscale_spatial_stack(
        wrf.latitude,
        wrf.longitude,
        wrf.u,
        dst_lat,
        dst_lon,
        power=power,
        neighbours=neighbours,
        field_name="eastward_wind",
        metadata=wrf.metadata,
    )
    LOGGER.info("SpritzMet: downscaling northward wind shape=%s", np.asarray(wrf.v).shape)
    v = _downscale_spatial_stack(
        wrf.latitude,
        wrf.longitude,
        wrf.v,
        dst_lat,
        dst_lon,
        power=power,
        neighbours=neighbours,
        field_name="northward_wind",
        metadata=wrf.metadata,
    )
    if wrf.precipitation_rate is None:
        LOGGER.info("SpritzMet: WRF precipitation unavailable; using zero precipitation field")
        precipitation_rate = np.zeros((_wind_time_count(u), *dst_lat.shape), dtype=float)
    else:
        LOGGER.info("SpritzMet: downscaling precipitation shape=%s", np.asarray(wrf.precipitation_rate).shape)
        precipitation_rate = _downscale_spatial_stack(
            wrf.latitude,
            wrf.longitude,
            wrf.precipitation_rate,
            dst_lat,
            dst_lon,
            power=power,
            neighbours=neighbours,
            field_name="precipitation_rate",
            metadata=wrf.metadata,
        )
    u, v, precipitation_rate, downscaling_metadata = _apply_surface_downscaling(
        u,
        v,
        precipitation_rate,
        dem_elevation_m=dem_elevation_m,
        land_cover=land_cover,
        dx_m=dx_m,
        dy_m=dy_m,
    )
    u, v, precipitation_rate, optional_metadata = _apply_optional_model_downscaling(
        mode,
        u,
        v,
        precipitation_rate,
        dem_elevation_m=dem_elevation_m,
        land_cover=land_cover,
        ai_model=ai_model,
        diffusion_model=diffusion_model,
    )
    station_metadata: dict[str, Any]
    u, v, precipitation_rate, station_metadata = _apply_station_measurement_improvement(
        u,
        v,
        precipitation_rate,
        stations=station_measurements,
        dst_x=xx,
        dst_y=yy,
        power=power,
    )
    u = _as_wind_4d("u", u)
    v = _as_wind_4d("v", v)
    if v.shape != u.shape:
        raise ValueError(f"v shape {v.shape} must match u shape {u.shape}")
    precipitation_rate = _as_precipitation_3d(precipitation_rate, u.shape[0], u.shape[-2:])
    level_meters = _validated_level_meters(wrf.metadata, u.shape[1])
    downscaling_metadata = {
        **downscaling_metadata,
        **optional_metadata,
        **station_metadata,
        "wind_dimensions": "time,z,y,x",
        "precipitation_dimensions": "time,y,x",
    }
    if level_meters is not None:
        downscaling_metadata["level_meters"] = level_meters
        downscaling_metadata["level_meters_kind"] = (
            wrf.metadata or {}
        ).get("level_meters_kind", "height_above_ground")
        downscaling_metadata["level_meters_source"] = (
            wrf.metadata or {}
        ).get("level_meters_source", "spritzwrf")
    if terrain_input_metadata:
        downscaling_metadata = {**downscaling_metadata, **terrain_input_metadata}
    LOGGER.info(
        "SpritzMet: downscaling complete wind_shape=%s precipitation_shape=%s",
        u.shape,
        precipitation_rate.shape,
    )
    valid_datetime = None
    valid_datetimes = None
    if wrf.metadata:
        valid_datetime = str(wrf.metadata.get("time_datetime", "") or "") or None
        raw_datetimes = wrf.metadata.get("time_datetimes")
        if isinstance(raw_datetimes, list):
            valid_datetimes = [str(value) for value in raw_datetimes]
    return LocalMeteorology(
        xx,
        yy,
        dst_lat,
        dst_lon,
        u,
        v,
        precipitation_rate,
        center_lat,
        center_lon,
        dx_m,
        dy_m,
        str(wrf.source_path),
        valid_datetime_utc=valid_datetime,
        valid_datetimes_utc=valid_datetimes,
        downscaling_metadata=downscaling_metadata,
    )


def write_local_meteorology(
    path: str | Path, met: LocalMeteorology, *, prefer_netcdf: bool = True
) -> str:
    """Write a SpritzMet local meteorology product as NetCDF-CF or JSON fallback."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = met.to_payload()
    if prefer_netcdf and netcdf_available():
        from netCDF4 import Dataset  # type: ignore

        with Dataset(out, "w") as ds:
            u4, v4 = met.wind_4d
            precipitation3 = met.precipitation_3d
            ntime, nz, ny, nx = u4.shape
            LOGGER.info(
                "SpritzMet: writing NetCDF-CF local meteorology path=%s wind_shape=%s precipitation_shape=%s",
                out,
                u4.shape,
                precipitation3.shape,
            )
            if precipitation3.shape != (ntime, ny, nx):
                raise ValueError(
                    f"precipitation_rate shape {precipitation3.shape} must match wind time/y/x {(ntime, ny, nx)}"
                )
            ds.createDimension("time", ntime)
            ds.createDimension("z", nz)
            ds.createDimension("y", ny)
            ds.createDimension("x", nx)
            ds.Conventions = "CF-1.8"
            ds.title = "Spritz SpritzMet high-resolution meteorology field"
            ds.history = "Created by SpritzWRF -> SpritzMet use case pipeline"
            ds.source = met.source
            ds.center_latitude = float(met.center_lat)
            ds.center_longitude = float(met.center_lon)
            for key, value in (met.downscaling_metadata or {}).items():
                setattr(ds, f"spritzmet_{key}", _netcdf_attribute_value(value))
            time_datetimes = [iso_utc(value) for value in (met.valid_datetimes_utc or [])]
            time_datetimes = [value for value in time_datetimes if value]
            if not time_datetimes and met.valid_datetime_utc:
                parsed = iso_utc(met.valid_datetime_utc) or str(met.valid_datetime_utc)
                ds.valid_datetime_utc = parsed
                time_datetimes = [parsed]
            write_cf_time_coordinate(ds, time_datetimes or None)
            z = ds.createVariable("z", "f8", ("z",))
            z_levels = met.z_levels_m
            if z_levels is None:
                z.long_name = "vertical level index"
                z.units = "1"
                z[:] = np.arange(nz, dtype=float)
            else:
                level_kind = str((met.downscaling_metadata or {}).get("level_meters_kind", "height_above_ground"))
                z.standard_name = "height"
                z.long_name = (
                    "height above mean sea level"
                    if level_kind == "height_above_sea_level"
                    else "height above local ground"
                )
                z.units = "m"
                z[:] = np.asarray(z_levels, dtype=float)
            z.positive = "up"
            variables = [
                ("x", met.x[0], ("x",), "m", "local projection x coordinate"),
                ("y", met.y[:, 0], ("y",), "m", "local projection y coordinate"),
                ("latitude", met.latitude, ("y", "x"), "degrees_north", "latitude"),
                ("longitude", met.longitude, ("y", "x"), "degrees_east", "longitude"),
                ("eastward_wind", u4, ("time", "z", "y", "x"), "m s-1", "eastward wind"),
                ("northward_wind", v4, ("time", "z", "y", "x"), "m s-1", "northward wind"),
                (
                    "precipitation_rate",
                    precipitation3,
                    ("time", "y", "x"),
                    "mm h-1",
                    "precipitation rate",
                ),
                ("wind_speed", met.wind_speed, ("time", "z", "y", "x"), "m s-1", "wind speed"),
                (
                    "wind_from_direction",
                    met.wind_from_direction,
                    ("time", "z", "y", "x"),
                    "degree",
                    "wind direction from which blowing",
                ),
            ]
            for name, values, dims, units, long_name in variables:
                var = ds.createVariable(name, "f8", dims, zlib=True)
                var.units = units
                var.long_name = long_name
                var[:] = np.asarray(values, dtype=float)
        return "NetCDF-CF"
    LOGGER.info("SpritzMet: writing JSON local meteorology path=%s", out)
    write_json(out, payload)
    return "json"

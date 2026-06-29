from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

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

    Station wind vector, temperature, and mixing height are interpolated by
    inverse-distance weighting. The preferred interchange format is NetCDF-CF,
    while JSON and legacy text remain available for compatibility workflows.
    """
    config.validate()
    if power <= 0:
        raise ValueError("interpolation power must be positive")
    ctx = get_mpi_context(parallel)
    gpu = get_gpu_context(gpu_backend or str(config.run.get("gpu_backend", "numpy")), rank=ctx.rank)
    xp = gpu.xp
    grid = Grid(**asdict(config.grid))
    xx, yy = grid.mesh()
    row_range = ctx.partition(grid.ny) if ctx.enabled else range(grid.ny)
    row_start = row_range.start
    row_stop = row_range.stop
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
        u.fill(float(config.run.get("default_u", 2.0)))
        v.fill(float(config.run.get("default_v", 0.0)))
        temp.fill(float(config.run.get("default_temperature", 293.15)))
        mixh.fill(float(config.run.get("default_mixing_height", 1000.0)))
        precip.fill(default_precip)
    else:
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
    result = build_meteorology(config, parallel=parallel, gpu_backend=gpu_backend)
    fmt = infer_format(output, output_format)
    if ctx.is_root:
        if fmt == "netcdf":
            write_cf_meteorology(output, result)
        else:
            write_json(output, result)
    ctx.barrier()
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
                "interpolation": "inverse-distance weighting on WRF latitude/longitude nodes",
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


def _idw_interpolate(
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


def _interpolate_spatial_stack(
    src_lat: np.ndarray,
    src_lon: np.ndarray,
    src_value: np.ndarray,
    dst_lat: np.ndarray,
    dst_lon: np.ndarray,
    *,
    power: float,
    neighbours: int,
) -> np.ndarray:
    values = np.asarray(src_value, dtype=float)
    if values.ndim == 2:
        return _idw_interpolate(src_lat, src_lon, values, dst_lat, dst_lon, power=power, k=neighbours)
    if values.ndim not in {3, 4}:
        raise ValueError("WRF field must be shaped as y,x; time,y,x; or time,z,y,x")
    leading_shape = values.shape[:-2]
    interpolated = np.empty((*leading_shape, *dst_lat.shape), dtype=float)
    for index in np.ndindex(leading_shape):
        interpolated[index] = _idw_interpolate(src_lat, src_lon, values[index], dst_lat, dst_lon, power=power, k=neighbours)
    return interpolated


def _wind_time_count(values: np.ndarray) -> int:
    arr = np.asarray(values, dtype=float)
    if arr.ndim == 4:
        return arr.shape[0]
    if arr.ndim == 3:
        return arr.shape[0]
    return 1


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
        return u, v, precipitation_rate, metadata

    grid_shape = u.shape[-2:]
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
    dem = None
    land_cover = None
    if dem_path is not None:
        raster = LocalRasterProvider(dem_path, "dem", dataset="spritzmet-dem").fetch(
            RasterRequest("dem", domain, ".")
        )
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
        raster = LocalRasterProvider(land_cover_path, "landcover", dataset="spritzmet-land-cover").fetch(
            RasterRequest("landcover", domain, ".")
        )
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
) -> LocalMeteorology:
    """Interpolate SpritzWRF near-surface fields to a local SpritzMet grid.

    When aligned DEM elevation and land-cover arrays are supplied, SpritzMet
    applies a clean-room CALMET-style diagnostic adjustment: objective WRF
    interpolation first, then terrain/slope, elevation, and land-cover
    roughness corrections for wind and orographic/land-cover precipitation
    factors.
    """
    if nx < 2 or ny < 2:
        raise ValueError("nx and ny must be at least 2")
    if dx_m <= 0 or dy_m <= 0:
        raise ValueError("dx_m and dy_m must be positive")
    xx, yy, dst_lat, dst_lon = local_grid_latlon(center_lat, center_lon, nx, ny, dx_m, dy_m)
    u = _interpolate_spatial_stack(
        wrf.latitude,
        wrf.longitude,
        wrf.u,
        dst_lat,
        dst_lon,
        power=power,
        neighbours=neighbours,
    )
    v = _interpolate_spatial_stack(
        wrf.latitude,
        wrf.longitude,
        wrf.v,
        dst_lat,
        dst_lon,
        power=power,
        neighbours=neighbours,
    )
    if wrf.precipitation_rate is None:
        precipitation_rate = np.zeros((_wind_time_count(u), *dst_lat.shape), dtype=float)
    else:
        precipitation_rate = _interpolate_spatial_stack(
            wrf.latitude,
            wrf.longitude,
            wrf.precipitation_rate,
            dst_lat,
            dst_lon,
            power=power,
            neighbours=neighbours,
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
    level_meters = _validated_level_meters(wrf.metadata, LocalMeteorology(
        xx, yy, dst_lat, dst_lon, u, v, precipitation_rate, center_lat, center_lon, dx_m, dy_m, str(wrf.source_path)
    ).wind_4d[0].shape[1])
    if terrain_input_metadata:
        downscaling_metadata = {**downscaling_metadata, **terrain_input_metadata}
    if level_meters is not None:
        downscaling_metadata["level_meters"] = level_meters
        downscaling_metadata["level_meters_kind"] = (wrf.metadata or {}).get(
            "level_meters_kind", "height_above_ground"
        )
        downscaling_metadata["level_meters_source"] = (wrf.metadata or {}).get(
            "level_meters_source", "spritzwrf"
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
                z.standard_name = "height"
                z.long_name = "height above local ground"
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
    write_json(out, payload)
    return "json"

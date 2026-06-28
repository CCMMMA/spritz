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

    def to_payload(self) -> dict[str, Any]:
        time_datetime = iso_utc(self.valid_datetime_utc)
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
            "z": [10.0],
            "u": u4.tolist(),
            "v": v4.tolist(),
            "wind_speed": self.wind_speed.tolist(),
            "wind_from_direction": self.wind_from_direction.tolist(),
            "precipitation_rate": precipitation3.tolist(),
            "dx_m": self.dx_m,
            "dy_m": self.dy_m,
            "source": self.source,
            **({"time": [0.0], "time_units": cf_time_units(time_datetime), "time_datetime": [time_datetime]} if time_datetime else {}),
            "metadata": {
                "spritzwrf_to_spritzmet": True,
                "interpolation": "inverse-distance weighting on WRF latitude/longitude nodes",
                "schema_version": "1.2",
                **({"valid_datetime_utc": time_datetime} if time_datetime else {}),
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
) -> LocalMeteorology:
    """Interpolate SpritzWRF near-surface wind to a local SpritzMet grid."""
    if nx < 2 or ny < 2:
        raise ValueError("nx and ny must be at least 2")
    if dx_m <= 0 or dy_m <= 0:
        raise ValueError("dx_m and dy_m must be positive")
    xx, yy, dst_lat, dst_lon = local_grid_latlon(center_lat, center_lon, nx, ny, dx_m, dy_m)
    u = _idw_interpolate(wrf.latitude, wrf.longitude, wrf.u, dst_lat, dst_lon, power=power, k=neighbours)
    v = _idw_interpolate(wrf.latitude, wrf.longitude, wrf.v, dst_lat, dst_lon, power=power, k=neighbours)
    if wrf.precipitation_rate is None:
        precipitation_rate = np.zeros_like(u)
    else:
        precipitation_rate = _idw_interpolate(
            wrf.latitude,
            wrf.longitude,
            wrf.precipitation_rate,
            dst_lat,
            dst_lon,
            power=power,
            k=neighbours,
        )
    valid_datetime = None
    if wrf.metadata:
        valid_datetime = str(wrf.metadata.get("time_datetime", "") or "") or None
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
            if met.valid_datetime_utc:
                ds.valid_datetime_utc = iso_utc(met.valid_datetime_utc) or str(met.valid_datetime_utc)
            write_cf_time_coordinate(ds, [met.valid_datetime_utc] if met.valid_datetime_utc else None)
            z = ds.createVariable("z", "f8", ("z",))
            z.standard_name = "height"
            z.long_name = "height above ground"
            z.units = "m"
            z.positive = "up"
            z[:] = np.asarray([10.0] * nz, dtype=float)
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

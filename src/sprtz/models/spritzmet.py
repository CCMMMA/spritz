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
from sprtz.io.netcdf_cf import available as netcdf_available, write_cf_meteorology
from sprtz.models.spritzwrf import WRFWindField


def build_meteorology(config: SuiteConfig, power: float = 2.0) -> dict[str, object]:
    """Build a deterministic SpritzMet-like diagnostic field.

    Station wind vector, temperature, and mixing height are interpolated by
    inverse-distance weighting. The preferred interchange format is NetCDF-CF,
    while JSON and legacy text remain available for compatibility workflows.
    """
    config.validate()
    if power <= 0:
        raise ValueError("interpolation power must be positive")
    grid = Grid(**asdict(config.grid))
    xx, yy = grid.mesh()
    u = np.zeros((grid.ny, grid.nx), dtype=float)
    v = np.zeros_like(u)
    temp = np.zeros_like(u)
    mixh = np.zeros_like(u)
    weights = np.zeros_like(u)

    if not config.stations:
        u.fill(float(config.run.get("default_u", 2.0)))
        v.fill(float(config.run.get("default_v", 0.0)))
        temp.fill(float(config.run.get("default_temperature", 293.15)))
        mixh.fill(float(config.run.get("default_mixing_height", 1000.0)))
    else:
        for station in config.stations:
            dist = np.hypot(xx - station.x, yy - station.y)
            w = 1.0 / np.maximum(dist, 1.0) ** power
            su, sv = wind_components(station.wind_speed, station.wind_dir)
            u += w * su
            v += w * sv
            temp += w * station.temperature
            mixh += w * station.mixing_height
            weights += w
        u = np.divide(u, weights, out=np.zeros_like(u), where=weights > 0)
        v = np.divide(v, weights, out=np.zeros_like(v), where=weights > 0)
        temp = np.divide(temp, weights, out=np.full_like(temp, 293.15), where=weights > 0)
        mixh = np.divide(mixh, weights, out=np.full_like(mixh, 1000.0), where=weights > 0)

    speed = np.hypot(u, v)
    return {
        "component": "spritzmet",
        "grid": asdict(config.grid),
        "u": u.tolist(),
        "v": v.tolist(),
        "wind_speed": speed.tolist(),
        "temperature": temp.tolist(),
        "mixing_height": mixh.tolist(),
        "stations": [asdict(s) for s in config.stations],
        "metadata": {"kernel": "inverse-distance diagnostic", "schema_version": "1.1"},
    }


def run(config: SuiteConfig, output: str | Path, output_format: str = "auto") -> dict[str, object]:
    result = build_meteorology(config)
    fmt = infer_format(output, output_format)
    if fmt == "netcdf":
        write_cf_meteorology(output, result)
    else:
        write_json(output, result)
    return result


@dataclass(frozen=True)
class LocalMeteorology:
    x: np.ndarray
    y: np.ndarray
    latitude: np.ndarray
    longitude: np.ndarray
    u: np.ndarray
    v: np.ndarray
    center_lat: float
    center_lon: float
    dx_m: float
    dy_m: float
    source: str

    @property
    def wind_speed(self) -> np.ndarray:
        return np.hypot(self.u, self.v)

    @property
    def wind_from_direction(self) -> np.ndarray:
        return (270.0 - np.rad2deg(np.arctan2(self.v, self.u))) % 360.0

    def to_payload(self) -> dict[str, Any]:
        return {
            "component": "spritzmet.local_meteorology",
            "center_lat": self.center_lat,
            "center_lon": self.center_lon,
            "x": self.x.tolist(),
            "y": self.y.tolist(),
            "latitude": self.latitude.tolist(),
            "longitude": self.longitude.tolist(),
            "u": self.u.tolist(),
            "v": self.v.tolist(),
            "wind_speed": self.wind_speed.tolist(),
            "wind_from_direction": self.wind_from_direction.tolist(),
            "dx_m": self.dx_m,
            "dy_m": self.dy_m,
            "source": self.source,
            "metadata": {
                "spritzwrf_to_spritzmet": True,
                "interpolation": "inverse-distance weighting on WRF latitude/longitude nodes",
                "schema_version": "1.2",
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
    return LocalMeteorology(
        xx,
        yy,
        dst_lat,
        dst_lon,
        u,
        v,
        center_lat,
        center_lon,
        dx_m,
        dy_m,
        str(wrf.source_path),
    )


def write_local_meteorology(
    path: str | Path, met: LocalMeteorology, *, prefer_netcdf: bool = True
) -> str:
    """Write a SpritzMet local wind product as NetCDF-CF or JSON fallback."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = met.to_payload()
    if prefer_netcdf and netcdf_available():
        from netCDF4 import Dataset  # type: ignore

        with Dataset(out, "w") as ds:
            ny, nx = met.u.shape
            ds.createDimension("time", 1)
            ds.createDimension("y", ny)
            ds.createDimension("x", nx)
            ds.Conventions = "CF-1.8"
            ds.title = "Sprtz SpritzMet high-resolution wind field"
            ds.history = "Created by SpritzWRF -> SpritzMet use case pipeline"
            ds.source = met.source
            ds.center_latitude = float(met.center_lat)
            ds.center_longitude = float(met.center_lon)
            variables = [
                ("x", met.x[0], ("x",), "m", "local projection x coordinate"),
                ("y", met.y[:, 0], ("y",), "m", "local projection y coordinate"),
                ("latitude", met.latitude, ("y", "x"), "degrees_north", "latitude"),
                ("longitude", met.longitude, ("y", "x"), "degrees_east", "longitude"),
                ("eastward_wind", met.u, ("time", "y", "x"), "m s-1", "eastward wind"),
                ("northward_wind", met.v, ("time", "y", "x"), "m s-1", "northward wind"),
                ("wind_speed", met.wind_speed, ("time", "y", "x"), "m s-1", "wind speed"),
                (
                    "wind_from_direction",
                    met.wind_from_direction,
                    ("time", "y", "x"),
                    "degree",
                    "wind direction from which blowing",
                ),
            ]
            for name, values, dims, units, long_name in variables:
                var = ds.createVariable(name, "f8", dims, zlib=True)
                var.units = units
                var.long_name = long_name
                if len(dims) == 3:
                    var[0, :, :] = np.asarray(values, dtype=float)
                else:
                    var[:] = np.asarray(values, dtype=float)
        return "NetCDF-CF"
    write_json(out, payload)
    return "json"

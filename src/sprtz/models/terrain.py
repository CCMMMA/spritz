from __future__ import annotations

"""Terrain: clean-room terrain extraction and resampling for Spritz.

Terrain reads terrain rasters, resamples them to a local modeling grid,
assigns terrain heights to model cells/receptors, and writes a NetCDF-CF terrain
product for SpritzMet, MakeGeo, and Spritz dispersion workflows.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from sprtz.io.jsonio import write_json
from sprtz.io.netcdf_cf import (
    annotate_latitude,
    annotate_local_x,
    annotate_local_y,
    annotate_longitude,
    annotate_surface_altitude,
    available as netcdf_available,
)
from sprtz.models.ctgproc import read_ascii_grid
from sprtz.models.spritzmet import local_grid_latlon


@dataclass(frozen=True)
class TerrainProduct:
    """Terrain on a Spritz local grid."""

    x: np.ndarray
    y: np.ndarray
    latitude: np.ndarray
    longitude: np.ndarray
    elevation_m: np.ndarray
    center_lat: float
    center_lon: float
    dx_m: float
    dy_m: float
    source: str
    method: str = "bilinear"

    def to_payload(self) -> dict[str, Any]:
        return {
            "component": "terrain.terrain",
            "center_lat": self.center_lat,
            "center_lon": self.center_lon,
            "dx_m": self.dx_m,
            "dy_m": self.dy_m,
            "source": self.source,
            "method": self.method,
            "x": self.x.tolist(),
            "y": self.y.tolist(),
            "latitude": self.latitude.tolist(),
            "longitude": self.longitude.tolist(),
            "elevation_m": self.elevation_m.tolist(),
            "metadata": {
                "former_role": "Terrain",
                "clean_room": True,
                "schema_version": "1.0",
            },
        }


def _axis_for_source(size: int, spacing_m: float) -> np.ndarray:
    if size <= 0:
        raise ValueError("source raster dimensions must be positive")
    if spacing_m <= 0:
        raise ValueError("source spacing must be positive")
    return (np.arange(size, dtype=float) - (size - 1) / 2.0) * spacing_m


def _bilinear_regular_grid(values: np.ndarray, src_x: np.ndarray, src_y: np.ndarray, dst_x: np.ndarray, dst_y: np.ndarray) -> np.ndarray:
    """Bilinearly resample a regular terrain raster to arbitrary points."""
    z = np.asarray(values, dtype=float)
    if z.ndim != 2:
        raise ValueError("terrain raster must be two-dimensional")
    if src_x.size != z.shape[1] or src_y.size != z.shape[0]:
        raise ValueError("source axes do not match terrain raster shape")
    flat_x = np.asarray(dst_x, dtype=float).ravel()
    flat_y = np.asarray(dst_y, dtype=float).ravel()
    out = np.empty_like(flat_x, dtype=float)

    # np.interp-style clipping keeps edge values stable for target grids that
    # slightly exceed the source domain.
    x = np.clip(flat_x, src_x[0], src_x[-1])
    y = np.clip(flat_y, src_y[0], src_y[-1])
    ix1 = np.searchsorted(src_x, x, side="right")
    iy1 = np.searchsorted(src_y, y, side="right")
    ix1 = np.clip(ix1, 1, len(src_x) - 1)
    iy1 = np.clip(iy1, 1, len(src_y) - 1)
    ix0 = ix1 - 1
    iy0 = iy1 - 1
    x0 = src_x[ix0]
    x1 = src_x[ix1]
    y0 = src_y[iy0]
    y1 = src_y[iy1]
    wx = np.divide(x - x0, x1 - x0, out=np.zeros_like(x), where=(x1 != x0))
    wy = np.divide(y - y0, y1 - y0, out=np.zeros_like(y), where=(y1 != y0))
    z00 = z[iy0, ix0]
    z10 = z[iy0, ix1]
    z01 = z[iy1, ix0]
    z11 = z[iy1, ix1]
    out[:] = (1.0 - wx) * (1.0 - wy) * z00 + wx * (1.0 - wy) * z10 + (1.0 - wx) * wy * z01 + wx * wy * z11
    return out.reshape(np.asarray(dst_x).shape)


def terrain_to_local_grid(
    terrain: np.ndarray,
    *,
    center_lat: float,
    center_lon: float,
    nx: int,
    ny: int,
    dx_m: float,
    dy_m: float,
    source_dx_m: float = 100.0,
    source_dy_m: float | None = None,
    source: str = "in-memory terrain",
) -> TerrainProduct:
    """Resample a terrain raster to a Spritz local modeling grid."""
    if nx < 2 or ny < 2:
        raise ValueError("nx and ny must be at least 2")
    if dx_m <= 0 or dy_m <= 0:
        raise ValueError("target grid spacing must be positive")
    src = np.asarray(terrain, dtype=float)
    if src.ndim != 2:
        raise ValueError("terrain must be a 2-D array")
    src_dy = float(source_dy_m if source_dy_m is not None else source_dx_m)
    xx, yy, lat, lon = local_grid_latlon(center_lat, center_lon, nx, ny, dx_m, dy_m)
    src_x = _axis_for_source(src.shape[1], float(source_dx_m))
    src_y = _axis_for_source(src.shape[0], src_dy)
    elev = _bilinear_regular_grid(src, src_x, src_y, xx, yy)
    return TerrainProduct(xx, yy, lat, lon, elev, center_lat, center_lon, dx_m, dy_m, source)


def assign_receptor_terrain(product: TerrainProduct, receptors: Iterable[dict[str, float]]) -> list[dict[str, float]]:
    """Assign terrain heights to receptor dictionaries with local x/y coordinates."""
    src_x = product.x[0, :]
    src_y = product.y[:, 0]
    assigned: list[dict[str, float]] = []
    for rec in receptors:
        x = float(rec.get("x", 0.0))
        y = float(rec.get("y", 0.0))
        elev = float(_bilinear_regular_grid(product.elevation_m, src_x, src_y, np.asarray([[x]]), np.asarray([[y]]))[0, 0])
        new = dict(rec)
        new["terrain_m"] = elev
        assigned.append(new)
    return assigned


def write_terrain_product(path: str | Path, product: TerrainProduct, *, prefer_netcdf: bool = True) -> str:
    """Write a terrain product as NetCDF-CF or JSON fallback."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if prefer_netcdf and netcdf_available():
        from netCDF4 import Dataset  # type: ignore

        with Dataset(out, "w") as ds:
            ny, nx = product.elevation_m.shape
            ds.createDimension("y", ny)
            ds.createDimension("x", nx)
            ds.Conventions = "CF-1.8"
            ds.title = "Spritz Terrain product"
            ds.source = product.source
            ds.center_latitude = float(product.center_lat)
            ds.center_longitude = float(product.center_lon)
            for name, values, dims, units, long_name in [
                ("x", product.x[0], ("x",), "m", "local projection x coordinate"),
                ("y", product.y[:, 0], ("y",), "m", "local projection y coordinate"),
                ("latitude", product.latitude, ("y", "x"), "degrees_north", "latitude"),
                ("longitude", product.longitude, ("y", "x"), "degrees_east", "longitude"),
                ("surface_altitude", product.elevation_m, ("y", "x"), "m", "surface altitude above mean sea level"),
            ]:
                var = ds.createVariable(name, "f8", dims, zlib=True)
                var.long_name = long_name
                if name == "x":
                    annotate_local_x(var)
                    var.long_name = long_name
                elif name == "y":
                    annotate_local_y(var)
                    var.long_name = long_name
                elif name == "latitude":
                    annotate_latitude(var)
                elif name == "longitude":
                    annotate_longitude(var)
                elif name == "surface_altitude":
                    annotate_surface_altitude(var)
                var[:] = np.asarray(values, dtype=float)
        return "NetCDF-CF"
    write_json(out, product.to_payload())
    return "json"


def run(
    terrain_path: str | Path,
    output: str | Path,
    *,
    center_lat: float,
    center_lon: float,
    nx: int = 101,
    ny: int = 101,
    dx_m: float = 100.0,
    dy_m: float = 100.0,
    source_dx_m: float = 100.0,
    source_dy_m: float | None = None,
    prefer_netcdf: bool = True,
) -> dict[str, Any]:
    """Read terrain, resample it, write a Terrain product, and return metadata."""
    p = Path(terrain_path)
    terrain = read_ascii_grid(p)
    product = terrain_to_local_grid(
        terrain,
        center_lat=center_lat,
        center_lon=center_lon,
        nx=nx,
        ny=ny,
        dx_m=dx_m,
        dy_m=dy_m,
        source_dx_m=source_dx_m,
        source_dy_m=source_dy_m,
        source=str(p),
    )
    fmt = write_terrain_product(output, product, prefer_netcdf=prefer_netcdf)
    return {
        "component": "terrain",
        "output": str(output),
        "format": fmt,
        "nx": nx,
        "ny": ny,
        "center_lat": center_lat,
        "center_lon": center_lon,
    }

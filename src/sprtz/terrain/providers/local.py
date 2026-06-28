from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from sprtz.io.jsonio import read_json
from sprtz.models.ctgproc import read_ascii_grid
from sprtz.terrain.providers.base import (
    RasterData,
    RasterKind,
    RasterRequest,
    TerrainConfigurationError,
    TerrainDependencyError,
)


@dataclass(frozen=True)
class LocalRasterProvider:
    """Open a local DEM or land-cover raster without network access.

    Lightweight ASCII grids, JSON arrays, and NumPy arrays are supported with no
    optional dependencies. GeoTIFF/COG and NetCDF paths are accepted too, but
    require `rasterio` or `netCDF4` respectively and fail with explicit install
    guidance when those optional packages are absent.
    """

    path: str | Path
    kind: RasterKind
    dataset: str = "local-raster"
    crs: str = "LOCAL"
    x_spacing_m: float = 100.0
    y_spacing_m: float = 100.0
    nodata: float | None = None
    variable: str | None = None
    name: str = "local"

    def fetch(self, request: RasterRequest) -> RasterData:
        if request.kind != self.kind:
            raise TerrainConfigurationError(
                f"local provider configured for {self.kind!r}, requested {request.kind!r}"
            )
        path = Path(self.path)
        if not path.exists():
            raise TerrainConfigurationError(f"local {self.kind} raster not found: {path}")
        values, metadata = self._read(path)
        nodata = self.nodata if self.nodata is not None else metadata.get("nodata")
        return RasterData(
            values=values,
            kind=self.kind,
            source=str(path),
            provider=self.name,
            dataset=self.dataset,
            resolution=f"{self.x_spacing_m:g}m",
            crs=str(metadata.get("crs", self.crs)),
            x_spacing_m=float(metadata.get("x_spacing_m", self.x_spacing_m)),
            y_spacing_m=float(metadata.get("y_spacing_m", self.y_spacing_m)),
            nodata=None if nodata is None else float(nodata),
            metadata=metadata,
        ).validated()

    def _read(self, path: Path) -> tuple[np.ndarray, dict[str, Any]]:
        suffix = path.suffix.lower()
        if suffix in {".asc", ".txt"}:
            return read_ascii_grid(path), {}
        if suffix == ".json":
            payload = read_json(path)
            values = payload.get("values", payload.get("data"))
            if values is None:
                raise TerrainConfigurationError(f"JSON raster lacks values/data: {path}")
            metadata = {k: v for k, v in payload.items() if k not in {"values", "data"}}
            return np.asarray(values, dtype=float), metadata
        if suffix == ".npy":
            return np.load(path), {}
        if suffix in {".tif", ".tiff", ".cog"}:
            return self._read_rasterio(path)
        if suffix in {".nc", ".nc4", ".cdf", ".netcdf"}:
            return self._read_netcdf(path)
        raise TerrainConfigurationError(
            f"unsupported local raster format {suffix!r}; "
            "use ASCII, JSON, NumPy, GeoTIFF/COG, or NetCDF"
        )

    def _read_rasterio(self, path: Path) -> tuple[np.ndarray, dict[str, Any]]:
        try:
            import rasterio  # type: ignore
        except Exception as exc:
            raise TerrainDependencyError(
                f"rasterio is required to read GeoTIFF/COG terrain inputs: {path}; "
                "install sprtz[geo]"
            ) from exc
        with rasterio.open(path) as src:
            values = src.read(1).astype(float)
            x_spacing = abs(float(src.transform.a)) if src.transform else self.x_spacing_m
            y_spacing = abs(float(src.transform.e)) if src.transform else self.y_spacing_m
            cols = np.arange(src.width, dtype=float) + 0.5
            rows = np.arange(src.height, dtype=float) + 0.5
            x_coords = np.asarray([src.transform * (col, 0.5) for col in cols], dtype=float)[:, 0]
            y_coords = np.asarray([src.transform * (0.5, row) for row in rows], dtype=float)[:, 1]
            return values, {
                "crs": str(src.crs or self.crs),
                "x_spacing_m": x_spacing,
                "y_spacing_m": y_spacing,
                "nodata": src.nodata,
                "transform": tuple(src.transform),
                "bounds": tuple(src.bounds),
                "x_coords": x_coords.tolist(),
                "y_coords": y_coords.tolist(),
            }

    def _read_netcdf(self, path: Path) -> tuple[np.ndarray, dict[str, Any]]:
        try:
            from netCDF4 import Dataset  # type: ignore
        except Exception as exc:
            raise TerrainDependencyError(
                f"netCDF4 is required to read NetCDF terrain inputs: {path}; install sprtz[netcdf]"
            ) from exc
        candidates = [self.variable] if self.variable else []
        candidates.extend(["surface_altitude", "elevation_m", "land_cover", "landuse_class"])
        with Dataset(path) as ds:
            for name in candidates:
                if name and name in ds.variables:
                    values = np.asarray(ds.variables[name][:], dtype=float)
                    if values.ndim == 3:
                        values = values[0]
                    return values, {"crs": getattr(ds, "source_crs", self.crs)}
        raise TerrainConfigurationError(f"no supported terrain variable found in {path}")

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from sprtz.io.jsonio import read_json, write_json
from sprtz.io.netcdf_cf import available as netcdf_available
from sprtz.terrain.cache import terrain_cache_dir, write_cache_metadata
from sprtz.terrain.landuse import (
    derive_surface_parameters,
    landuse_table_payload,
    remap_land_cover,
)
from sprtz.terrain.providers import (
    CopernicusDEMProvider,
    ESAWorldCoverProvider,
    LocalRasterProvider,
    RasterData,
    RasterProvider,
    RasterRequest,
    TerrainConfigurationError,
)
from sprtz.terrain.provenance import build_provenance
from sprtz.terrain.regrid import (
    DomainDefinition,
    TargetGrid,
    aoi_bounds,
    build_target_grid,
    resample_dem,
    resample_land_cover,
)


@dataclass(frozen=True)
class TerrainGeoProduct:
    domain: DomainDefinition
    grid: TargetGrid
    elevation_m: np.ndarray
    land_cover: np.ndarray
    landuse_class: np.ndarray
    surface_parameters: dict[str, np.ndarray]
    provenance: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        return {
            "component": "terrain.geo",
            "domain": {
                "center_lat": self.domain.center_lat,
                "center_lon": self.domain.center_lon,
                "nx": self.domain.nx,
                "ny": self.domain.ny,
                "dx_m": self.domain.dx_m,
                "dy_m": self.domain.dy_m,
                "projection": self.domain.projection,
                "buffer_m": self.domain.buffer_m,
            },
            "x": self.grid.x.tolist(),
            "y": self.grid.y.tolist(),
            "latitude": self.grid.latitude.tolist(),
            "longitude": self.grid.longitude.tolist(),
            "elevation_m": self.elevation_m.tolist(),
            "land_cover": self.land_cover.tolist(),
            "landuse_class": self.landuse_class.tolist(),
            "surface_parameters": {
                key: value.tolist() for key, value in self.surface_parameters.items()
            },
            "landuse_table": landuse_table_payload(),
            "provenance": self.provenance,
        }


def _local_provider(kind: str, spec: dict[str, Any]) -> LocalRasterProvider:
    path = spec.get("path") or spec.get("file") or spec.get("source_path")
    if not path:
        raise TerrainConfigurationError(f"local {kind} provider requires a path")
    return LocalRasterProvider(
        path=path,
        kind="dem" if kind == "dem" else "landcover",
        dataset=str(spec.get("dataset", "local-raster")),
        crs=str(spec.get("crs", "LOCAL")),
        x_spacing_m=float(spec.get("source_dx_m", spec.get("dx_m", spec.get("resolution_m", 100.0)))),
        y_spacing_m=float(spec.get("source_dy_m", spec.get("dy_m", spec.get("resolution_m", 100.0)))),
        nodata=None if spec.get("nodata") is None else float(spec["nodata"]),
        variable=None if spec.get("variable") is None else str(spec["variable"]),
    )


def provider_from_spec(kind: str, spec: dict[str, Any]) -> RasterProvider:
    source = str(spec.get("source", "local")).lower()
    if source in {"local", "file", "local-raster"}:
        return _local_provider(kind, spec)
    if kind == "dem" and source in {"copernicus-dem", "copernicus", "copernicus-30"}:
        return CopernicusDEMProvider(
            resolution=str(spec.get("resolution", "30m")),
            stac_url=None if spec.get("stac_url") is None else str(spec["stac_url"]),
        )
    if kind == "landuse" and source in {"esa-worldcover", "worldcover", "esa-worldcover-2021"}:
        return ESAWorldCoverProvider(
            year=int(spec.get("year", 2021)),
            stac_url=None if spec.get("stac_url") is None else str(spec["stac_url"]),
        )
    raise TerrainConfigurationError(f"unsupported {kind} terrain provider source: {source}")


def _terrain_section(config: dict[str, Any]) -> dict[str, Any]:
    terrain = dict(config.get("terrain", {}))
    if not terrain:
        raise TerrainConfigurationError("configuration requires a terrain section")
    return terrain


def load_acquisition_config(path: str | Path) -> dict[str, Any]:
    data = read_json(path)
    if not isinstance(data, dict):
        raise TerrainConfigurationError(f"terrain configuration must be a JSON object: {path}")
    return data


def build_product(
    config: dict[str, Any],
    *,
    cache_dir: str | Path | None = None,
    allow_network: bool = False,
) -> TerrainGeoProduct:
    domain_data = config.get("domain")
    if not isinstance(domain_data, dict):
        raise TerrainConfigurationError("configuration requires a domain section")
    terrain = _terrain_section(config)
    domain = DomainDefinition.from_mapping(domain_data)
    cache = terrain_cache_dir(cache_dir or terrain.get("cache_dir"))
    grid = build_target_grid(domain)
    request_options = {"aoi_bounds": aoi_bounds(domain)}

    dem_provider = provider_from_spec("dem", dict(terrain.get("dem", {})))
    land_provider = provider_from_spec("landuse", dict(terrain.get("landuse", {})))
    dem = dem_provider.fetch(
        RasterRequest("dem", domain, str(cache), allow_network=allow_network, options=request_options)
    )
    landcover = land_provider.fetch(
        RasterRequest(
            "landcover",
            domain,
            str(cache),
            allow_network=allow_network,
            options=request_options,
        )
    )
    elevation = resample_dem(dem, grid)
    land_cover = resample_land_cover(landcover, grid)
    landuse = remap_land_cover(land_cover)
    surface_parameters = derive_surface_parameters(landuse)
    provenance = build_provenance(
        domain=domain,
        dem=dem,
        landcover=RasterData(
            values=landcover.values,
            kind=landcover.kind,
            source=landcover.source,
            provider=landcover.provider,
            dataset=landcover.dataset,
            resolution=landcover.resolution,
            crs=landcover.crs,
            x_spacing_m=landcover.x_spacing_m,
            y_spacing_m=landcover.y_spacing_m,
            nodata=landcover.nodata,
            access_date=landcover.access_date,
            metadata={**landcover.metadata, "year": terrain.get("landuse", {}).get("year", "")},
        ),
        source_crs=f"DEM={dem.crs}; landcover={landcover.crs}",
        target_crs=grid.target_crs,
    )
    write_cache_metadata(cache, provenance["cache_key"], provenance)
    return TerrainGeoProduct(domain, grid, elevation, land_cover, landuse, surface_parameters, provenance)


def write_geo_product(
    path: str | Path,
    product: TerrainGeoProduct,
    *,
    prefer_netcdf: bool = True,
) -> str:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if prefer_netcdf and netcdf_available():
        from netCDF4 import Dataset  # type: ignore

        with Dataset(out, "w") as ds:
            ny, nx = product.elevation_m.shape
            ds.createDimension("y", ny)
            ds.createDimension("x", nx)
            ds.Conventions = "CF-1.8"
            ds.title = "Sprtz Terrain GEO product"
            for key, value in product.provenance.items():
                setattr(ds, key, str(value))
            for name, values, dims, units, long_name in [
                ("x", product.grid.x[0], ("x",), "m", "model grid x coordinate"),
                ("y", product.grid.y[:, 0], ("y",), "m", "model grid y coordinate"),
                ("latitude", product.grid.latitude, ("y", "x"), "degrees_north", "latitude"),
                ("longitude", product.grid.longitude, ("y", "x"), "degrees_east", "longitude"),
                ("surface_altitude", product.elevation_m, ("y", "x"), "m", "surface altitude"),
                ("land_cover", product.land_cover, ("y", "x"), "1", "source land-cover class"),
                ("landuse_class", product.landuse_class, ("y", "x"), "1", "Sprtz land-use class"),
            ]:
                dtype = "i4" if name in {"land_cover", "landuse_class"} else "f8"
                var = ds.createVariable(name, dtype, dims, zlib=True)
                var.units = units
                var.long_name = long_name
                var[:] = np.asarray(values)
            for name, values in product.surface_parameters.items():
                var = ds.createVariable(name, "f8", ("y", "x"), zlib=True)
                var.units = "1" if name != "roughness_length_m" else "m"
                var.long_name = name.replace("_", " ")
                var[:] = np.asarray(values, dtype=float)
        return "NetCDF-CF"
    write_json(out, product.to_payload())
    return "json"


def run_acquisition(
    config: dict[str, Any] | str | Path,
    *,
    output: str | Path | None = None,
    prefer_netcdf: bool = True,
    allow_network: bool = False,
    cache_dir: str | Path | None = None,
) -> dict[str, Any]:
    data = load_acquisition_config(config) if isinstance(config, (str, Path)) else dict(config)
    terrain = _terrain_section(data)
    output_path = output or terrain.get("output")
    if not output_path:
        raise TerrainConfigurationError("terrain output path is required")
    product = build_product(data, cache_dir=cache_dir, allow_network=allow_network)
    fmt = write_geo_product(output_path, product, prefer_netcdf=prefer_netcdf)
    return {
        "component": "terrain",
        "output": str(output_path),
        "format": fmt,
        "nx": product.domain.nx,
        "ny": product.domain.ny,
        "cache_key": product.provenance["cache_key"],
        "target_crs": product.grid.target_crs,
    }

from __future__ import annotations

from pathlib import Path

import numpy as np

from sprtz.cli import sprtz_terrain_main
from sprtz.io.jsonio import read_json
from sprtz.terrain.acquisition import build_product, run_acquisition
from sprtz.terrain.cache import cache_key
from sprtz.terrain.landuse import derive_surface_parameters, remap_land_cover
from sprtz.terrain.providers import (
    CopernicusDEMProvider,
    LocalRasterProvider,
    RasterRequest,
    TerrainNetworkDisabledError,
)
from sprtz.terrain.regrid import DomainDefinition, build_target_grid, resample_land_cover
from sprtz.workflow import run_workflow


def _local_config(tmp_path: Path) -> dict[str, object]:
    return {
        "domain": {
            "center_lat": 40.85,
            "center_lon": 14.27,
            "nx": 7,
            "ny": 7,
            "dx_m": 100.0,
            "dy_m": 100.0,
            "projection": "auto-utm",
            "buffer_m": 250.0,
        },
        "terrain": {
            "enabled": True,
            "cache_dir": str(tmp_path / "cache"),
            "dem": {
                "source": "local",
                "path": "examples/data/highres_dem.asc",
                "source_dx_m": 100.0,
                "source_dy_m": 100.0,
            },
            "landuse": {
                "source": "local",
                "path": "examples/data/highres_landcover.asc",
                "year": 2021,
                "source_dx_m": 100.0,
                "source_dy_m": 100.0,
            },
            "output": str(tmp_path / "geo.json"),
        },
    }


def test_cache_key_is_stable() -> None:
    left = cache_key({"provider": "local", "dataset": "demo", "aoi": [1, 2, 3, 4]})
    right = cache_key({"aoi": [1, 2, 3, 4], "dataset": "demo", "provider": "local"})
    assert left == right


def test_domain_auto_utm_grid() -> None:
    domain = DomainDefinition.from_mapping(
        {
            "center_lat": 40.85,
            "center_lon": 14.27,
            "nx": 5,
            "ny": 5,
            "dx_m": 100.0,
            "dy_m": 100.0,
            "projection": "auto-utm",
        }
    )
    grid = build_target_grid(domain)
    assert grid.x.shape == (5, 5)
    assert grid.target_crs == "EPSG:32633"
    assert abs(float(grid.latitude[2, 2]) - 40.85) < 1.0e-8


def test_local_raster_provider_reads_ascii(tmp_path: Path) -> None:
    domain = DomainDefinition.from_mapping(
        {
            "center_lat": 40.85,
            "center_lon": 14.27,
            "nx": 3,
            "ny": 3,
            "dx_m": 100.0,
            "dy_m": 100.0,
        }
    )
    provider = LocalRasterProvider(
        "examples/data/highres_dem.asc",
        "dem",
        x_spacing_m=100.0,
        y_spacing_m=100.0,
    )
    raster = provider.fetch(RasterRequest("dem", domain, str(tmp_path)))
    assert raster.values.shape == (7, 7)
    assert raster.provider == "local"


def test_online_provider_requires_explicit_network(tmp_path: Path) -> None:
    domain = DomainDefinition.from_mapping(
        {
            "center_lat": 40.85,
            "center_lon": 14.27,
            "nx": 3,
            "ny": 3,
            "dx_m": 100.0,
            "dy_m": 100.0,
        }
    )
    provider = CopernicusDEMProvider()
    try:
        provider.fetch(RasterRequest("dem", domain, str(tmp_path), allow_network=False))
    except TerrainNetworkDisabledError as exc:
        assert "allow-network" in str(exc)
    else:  # pragma: no cover - defensive guard
        raise AssertionError("online provider did not require network opt-in")


def test_categorical_resampling_and_landuse_mapping() -> None:
    domain = DomainDefinition.from_mapping(
        {
            "center_lat": 40.85,
            "center_lon": 14.27,
            "nx": 3,
            "ny": 3,
            "dx_m": 100.0,
            "dy_m": 100.0,
        }
    )
    grid = build_target_grid(domain)
    raster = LocalRasterProvider(
        "examples/data/highres_landcover.asc",
        "landcover",
        x_spacing_m=100.0,
        y_spacing_m=100.0,
    ).fetch(RasterRequest("landcover", domain, "."))
    land_cover = resample_land_cover(raster, grid)
    assert set(np.unique(land_cover)).issubset({10, 20, 30, 40, 50, 60, 80, 90})
    landuse = remap_land_cover(land_cover)
    params = derive_surface_parameters(landuse)
    assert params["roughness_length_m"].shape == landuse.shape
    assert int(remap_land_cover(np.asarray([[50]]))[0, 0]) == 5


def test_acquisition_writes_json_with_provenance(tmp_path: Path) -> None:
    config = _local_config(tmp_path)
    result = run_acquisition(config, prefer_netcdf=False)
    data = read_json(result["output"])
    assert result["format"] == "json"
    assert data["component"] == "terrain.geo"
    assert data["provenance"]["resampling_landuse"] == "nearest-neighbor categorical"
    assert data["provenance"]["target_crs"] == "EPSG:32633"
    assert "roughness_length_m" in data["surface_parameters"]


def test_build_product_aligns_grids(tmp_path: Path) -> None:
    product = build_product(_local_config(tmp_path))
    assert product.elevation_m.shape == product.landuse_class.shape == (7, 7)
    assert product.grid.latitude.shape == (7, 7)


def test_sprtz_terrain_fetch_cli(tmp_path: Path) -> None:
    config = _local_config(tmp_path)
    config_path = tmp_path / "terrain.json"
    from sprtz.io.jsonio import write_json

    write_json(config_path, config)
    assert sprtz_terrain_main(["fetch", "--config", str(config_path), "--json"]) == 0
    assert (tmp_path / "geo.json").exists()


def test_workflow_runs_configured_auto_terrain(tmp_path: Path) -> None:
    result = run_workflow(
        "examples/highres_terrain_local.json",
        tmp_path / "workflow",
        interchange="json",
    )
    assert Path(result["terrain"]).exists()
    assert Path(result["concentration"]).exists()

from __future__ import annotations

from pathlib import Path

import numpy as np

from sprtz.cli import sprtz_terrain_main
from sprtz.io.jsonio import read_json
from sprtz.terrain.acquisition import build_product, run_acquisition
from sprtz.terrain.cache import cache_key
from sprtz.terrain.landuse import derive_surface_parameters, land_cover_mapping, remap_land_cover
from sprtz.terrain.providers import (
    CopernicusDEMProvider,
    LocalRasterProvider,
    RasterData,
    RasterRequest,
    TerrainNetworkDisabledError,
)
from sprtz.terrain.regrid import (
    DomainDefinition,
    build_target_grid,
    resample_dem,
    resample_land_cover,
)
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


def test_copernicus_lc100_land_cover_mapping() -> None:
    source = np.asarray([[111, 40, 50], [60, 80, 200], [90, 100, 0]])
    landuse = remap_land_cover(source, mapping=land_cover_mapping("copernicus-lc100"))

    assert landuse.tolist() == [[1, 4, 5], [6, 8, 8], [9, 11, 0]]


def test_acquisition_accepts_copernicus_lc100_local_landcover(tmp_path: Path) -> None:
    dem_path = tmp_path / "dem.json"
    lc_path = tmp_path / "lc100.json"
    from sprtz.io.jsonio import write_json

    write_json(dem_path, {"values": np.ones((7, 7), dtype=float).tolist()})
    write_json(
        lc_path,
        {
            "values": np.full((7, 7), 111, dtype=int).tolist(),
            "crs": "LOCAL",
            "x_spacing_m": 100.0,
            "y_spacing_m": 100.0,
        },
    )
    config = _local_config(tmp_path)
    terrain = config["terrain"]
    assert isinstance(terrain, dict)
    terrain["dem"] = {"source": "local", "path": str(dem_path), "source_dx_m": 100.0}
    terrain["landuse"] = {
        "source": "local",
        "path": str(lc_path),
        "source_dx_m": 100.0,
        "target_categories": "copernicus-lc100",
        "year": 2019,
    }

    product = build_product(config)

    assert set(np.unique(product.landuse_class)) == {1}


def test_resample_dem_uses_geotiff_source_crs_coordinates() -> None:
    domain = DomainDefinition.from_mapping(
        {
            "center_lat": 40.85,
            "center_lon": 14.27,
            "nx": 3,
            "ny": 3,
            "dx_m": 100.0,
            "dy_m": 100.0,
            "projection": "auto-utm",
        }
    )
    grid = build_target_grid(domain)
    lon_axis = np.linspace(
        float(grid.longitude.min()) - 0.01,
        float(grid.longitude.max()) + 0.01,
        7,
    )
    lat_axis = np.linspace(
        float(grid.latitude.min()) - 0.01,
        float(grid.latitude.max()) + 0.01,
        7,
    )
    lon_values, lat_values = np.meshgrid(lon_axis, lat_axis)
    values = 100.0 * lat_values + 10.0 * lon_values
    raster = RasterData(
        values=values,
        kind="dem",
        source="cop30-test.tif",
        provider="local",
        dataset="Copernicus DEM GLO-30 / COP30 test",
        resolution="30m",
        crs="EPSG:4326",
        metadata={"x_coords": lon_axis.tolist(), "y_coords": lat_axis.tolist()},
    )

    elevation = resample_dem(raster, grid)

    expected = 100.0 * grid.latitude + 10.0 * grid.longitude
    assert np.allclose(elevation, expected, atol=1.0e-6)


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


def test_geo_netcdf_has_cf_spatial_coordinates(tmp_path: Path) -> None:
    try:
        from netCDF4 import Dataset  # type: ignore
    except Exception:
        return
    config = _local_config(tmp_path)
    config["terrain"] = {**config["terrain"], "output": str(tmp_path / "geo.nc")}
    result = run_acquisition(config, prefer_netcdf=True)
    assert result["format"] == "NetCDF-CF"
    with Dataset(result["output"]) as ds:
        assert ds.Conventions == "CF-1.8"
        assert ds.variables["x"].axis == "X"
        assert ds.variables["y"].axis == "Y"
        assert ds.variables["latitude"].standard_name == "latitude"
        assert ds.variables["longitude"].standard_name == "longitude"
        assert ds.variables["surface_altitude"].standard_name == "surface_altitude"
        assert ds.variables["surface_altitude"].coordinates == "latitude longitude"
        assert ds.variables["land_cover"].coordinates == "latitude longitude"


def test_sprtz_terrain_fetch_cli(tmp_path: Path) -> None:
    config = _local_config(tmp_path)
    config_path = tmp_path / "terrain.json"
    from sprtz.io.jsonio import write_json

    write_json(config_path, config)
    assert sprtz_terrain_main(["fetch", "--config", str(config_path), "--json"]) == 0
    assert (tmp_path / "geo.json").exists()


def test_sprtz_terrain_fetch_cli_accepts_lc100_mapping(tmp_path: Path) -> None:
    from sprtz.io.jsonio import write_json

    dem_path = tmp_path / "dem.json"
    lc_path = tmp_path / "lc100.json"
    output = tmp_path / "geo.json"
    write_json(dem_path, {"values": np.ones((7, 7), dtype=float).tolist()})
    write_json(lc_path, {"values": np.full((7, 7), 111, dtype=int).tolist()})

    assert (
        sprtz_terrain_main(
            [
                "fetch",
                "--center-lat",
                "40.85",
                "--center-lon",
                "14.27",
                "--nx",
                "7",
                "--ny",
                "7",
                "--dx",
                "100",
                "--dy",
                "100",
                "--dem",
                str(dem_path),
                "--landuse",
                str(lc_path),
                "--landuse-mapping",
                "copernicus-lc100",
                "--output",
                str(output),
                "--cache-dir",
                str(tmp_path / "cache"),
                "--json",
            ]
        )
        == 0
    )

    data = read_json(output)
    assert set(np.unique(np.asarray(data["landuse_class"], dtype=int))) == {1}


def test_workflow_runs_configured_auto_terrain(tmp_path: Path) -> None:
    result = run_workflow(
        "examples/highres_terrain_local.json",
        tmp_path / "workflow",
        interchange="json",
    )
    assert Path(result["terrain"]).exists()
    assert Path(result["concentration"]).exists()

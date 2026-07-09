from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from sprtz.config import load_config


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "usecases"
    / "03_satellite_ai_evaluation"
    / "demo"
    / "align_satellite.py"
)
SPEC = importlib.util.spec_from_file_location("usecase03_align_satellite", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

EVALUATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "usecases"
    / "03_satellite_ai_evaluation"
    / "demo"
    / "model_evaluation.py"
)
EVALUATION_SPEC = importlib.util.spec_from_file_location(
    "usecase03_model_evaluation",
    EVALUATION_PATH,
)
assert EVALUATION_SPEC is not None and EVALUATION_SPEC.loader is not None
EVALUATION = importlib.util.module_from_spec(EVALUATION_SPEC)
EVALUATION_SPEC.loader.exec_module(EVALUATION)

DOWNLOADER_PATH = (
    Path(__file__).resolve().parents[1] / "tools" / "copernicus-s5p-no2-download.py"
)
DOWNLOADER_SPEC = importlib.util.spec_from_file_location(
    "copernicus_s5p_downloader",
    DOWNLOADER_PATH,
)
assert DOWNLOADER_SPEC is not None and DOWNLOADER_SPEC.loader is not None
DOWNLOADER = importlib.util.module_from_spec(DOWNLOADER_SPEC)
DOWNLOADER_SPEC.loader.exec_module(DOWNLOADER)


def test_spritz_domain_bbox_matches_concentration_field_domain() -> None:
    config = load_config(
        Path(__file__).resolve().parents[1]
        / "usecases"
        / "03_satellite_ai_evaluation"
        / "demo"
        / "config.json"
    )

    bbox = MODULE._spritz_domain_bbox(config)

    assert bbox[0] == pytest.approx(13.978233658477112)
    assert bbox[1] == pytest.approx(40.84170416816385)
    assert bbox[2] == pytest.approx(14.693337754513296)
    assert bbox[3] == pytest.approx(41.1570113905857)


def test_conservative_downscale_preserves_coarse_means() -> None:
    coarse = np.asarray([[0.5, 1.0], [2.0, 4.0]])
    y, x = np.mgrid[0:1:6j, 0:1:6j]
    weights = 1.0 + x + 0.5 * y

    field, report = MODULE.conservative_downscale(
        coarse,
        (6, 6),
        weights,
        smoothing_iterations=3,
    )
    labels_y, labels_x = MODULE._coarse_labels(coarse.shape, field.shape)

    for row in range(2):
        for col in range(2):
            members = (labels_y == row) & (labels_x == col)
            assert float(np.mean(field[members])) == pytest.approx(coarse[row, col])
    assert report["maximum_coarse_mean_error"] < 1.0e-12


def test_conservative_downscale_preserves_missing_footprint() -> None:
    coarse = np.asarray([[1.0, np.nan], [2.0, 3.0]])
    field, _ = MODULE.conservative_downscale(
        coarse,
        (4, 4),
        np.ones((4, 4)),
        smoothing_iterations=1,
    )
    labels_y, labels_x = MODULE._coarse_labels(coarse.shape, field.shape)
    assert np.isnan(field[(labels_y == 0) & (labels_x == 1)]).all()


def test_boundary_diagnostic_ignores_floating_point_edge_ghost(tmp_path: Path) -> None:
    netcdf4 = pytest.importorskip("netCDF4")
    path = tmp_path / "concentration.nc"
    with netcdf4.Dataset(path, "w") as ds:
        ds.createDimension("time", 1)
        ds.createDimension("field_z", 1)
        ds.createDimension("field_y", 5)
        ds.createDimension("field_x", 5)
        ds.createVariable("field_x", "f8", ("field_x",))[:] = np.arange(5) * 100.0
        ds.createVariable("field_y", "f8", ("field_y",))[:] = np.arange(5) * 100.0
        concentration = ds.createVariable(
            "concentration_field",
            "f8",
            ("time", "field_z", "field_y", "field_x"),
        )
        values = np.zeros((1, 1, 5, 5), dtype=float)
        values[0, 0, 2, 2] = 1.0
        values[0, 0, 2, -1] = 1.0e-20
        concentration[:] = values

    diagnostic = EVALUATION._field_boundary_diagnostics(path)

    assert diagnostic is not None
    assert diagnostic["any_boundary_contact"] is False
    timestep = diagnostic["timesteps"][0]
    assert timestep["active_threshold"] == pytest.approx(1.0e-12)
    assert timestep["boundary_active_cells"]["east"] == 0
    assert timestep["margins"]["east_cells"] == 2


def test_boundary_diagnostic_ignores_negligible_edge_mass_fraction(tmp_path: Path) -> None:
    netcdf4 = pytest.importorskip("netCDF4")
    path = tmp_path / "concentration.nc"
    with netcdf4.Dataset(path, "w") as ds:
        ds.createDimension("time", 1)
        ds.createDimension("field_z", 1)
        ds.createDimension("field_y", 5)
        ds.createDimension("field_x", 5)
        ds.createVariable("field_x", "f8", ("field_x",))[:] = np.arange(5) * 100.0
        ds.createVariable("field_y", "f8", ("field_y",))[:] = np.arange(5) * 100.0
        concentration = ds.createVariable(
            "concentration_field",
            "f8",
            ("time", "field_z", "field_y", "field_x"),
        )
        values = np.zeros((1, 1, 5, 5), dtype=float)
        values[0, 0, 2, 2] = 1.0
        values[0, 0, 2, -1] = 1.0e-8
        concentration[:] = values

    diagnostic = EVALUATION._field_boundary_diagnostics(
        path,
        mass_fraction_threshold=1.0e-6,
    )

    assert diagnostic is not None
    assert diagnostic["any_boundary_contact"] is False
    timestep = diagnostic["timesteps"][0]
    assert timestep["raw_boundary_contact"]["east"] is True
    assert timestep["boundary_contact"]["east"] is False
    assert timestep["boundary_mass_fraction"]["east"] == pytest.approx(1.0e-8)


def test_station_validation_uses_in_domain_stations_and_thresholds_model_tails(tmp_path: Path) -> None:
    netcdf4 = pytest.importorskip("netCDF4")
    concentration = tmp_path / "concentration.nc"
    with netcdf4.Dataset(concentration, "w") as ds:
        ds.createDimension("time", 1)
        ds.createDimension("field_z", 1)
        ds.createDimension("field_y", 2)
        ds.createDimension("field_x", 2)
        variable = ds.createVariable(
            "concentration_field",
            "f8",
            ("time", "field_z", "field_y", "field_x"),
        )
        values = np.zeros((1, 1, 2, 2), dtype=float)
        values[0, 0, 0, 0] = 1.0
        values[0, 0, 1, 1] = 1.0e-20
        variable[:] = values

    satellite = tmp_path / "satellite.json"
    satellite.write_text(
        json.dumps(
            {
                "downscaled_field": [[0.8, 0.2], [0.3, 0.1]],
                "provenance": {"domain_bbox_wgs84": [14.0, 40.0, 15.0, 41.0]},
            }
        )
        + "\n"
    )
    stations = tmp_path / "stations.csv"
    stations.write_text(
        "id,LAT,LON,NO2\n"
        "northwest,41.0,14.0,30\n"
        "southeast,40.0,15.0,10\n"
        "outside,39.0,15.0,99\n"
    )

    result = EVALUATION._station_validation(
        concentration_path=concentration,
        satellite_mask_path=satellite,
        station_observations_path=stations,
        time_index=0,
    )

    assert result["station_count"] == 3
    assert result["in_domain_count"] == 2
    assert result["model_active_threshold"] == pytest.approx(1.0e-12)
    assert result["samples"][0]["model_probability_at_station"] == pytest.approx(1.0)
    assert result["samples"][1]["model_concentration"] == pytest.approx(0.0)
    assert result["samples"][1]["model_probability_at_station"] == pytest.approx(0.0)


def test_sentinel5p_downloader_dry_run_honors_min_qa(tmp_path: Path) -> None:
    output = tmp_path / "s5p.tif"

    assert DOWNLOADER.main(
        [
            "--bbox",
            "13.97",
            "40.83",
            "14.70",
            "41.17",
            "--time-start",
            "2024-06-19T11:55:42Z",
            "--time-end",
            "2024-06-19T12:47:58Z",
            "--band",
            "AER_AI_340_380",
            "--min-qa",
            "0",
            "--width",
            "32",
            "--height",
            "32",
            "--output",
            str(output),
            "--dry-run",
        ],
        prog="copernicus-s5p-download.py",
    ) == 0

    request = json.loads(output.with_suffix(output.suffix + ".request.json").read_text())
    assert request["input"]["data"][0]["processing"]["minQa"] == 0
    assert request["output"]["width"] == 32
    assert request["output"]["height"] == 32


def test_sentinel5p_downloader_rejects_empty_raster(tmp_path: Path) -> None:
    rasterio = pytest.importorskip("rasterio")

    output = tmp_path / "empty.tif"
    with rasterio.open(
        output,
        "w",
        driver="GTiff",
        width=4,
        height=3,
        count=1,
        dtype="float32",
        nodata=-9999.0,
    ) as dataset:
        dataset.write(np.full((3, 4), -9999.0, dtype=np.float32), 1)

    with pytest.raises(DOWNLOADER.EmptySentinel5PSubsetError, match="zero finite pixels"):
        DOWNLOADER._validate_downloaded_raster(output, band="AER_AI_340_380")


def test_sentinel5p_downloader_allows_empty_raster_for_provenance(tmp_path: Path) -> None:
    rasterio = pytest.importorskip("rasterio")

    output = tmp_path / "empty.tif"
    with rasterio.open(
        output,
        "w",
        driver="GTiff",
        width=4,
        height=3,
        count=1,
        dtype="float32",
        nodata=-9999.0,
    ) as dataset:
        dataset.write(np.full((3, 4), -9999.0, dtype=np.float32), 1)

    assert (
        DOWNLOADER._validate_downloaded_raster(
            output,
            band="AER_AI_340_380",
            allow_empty=True,
        )
        == 0
    )

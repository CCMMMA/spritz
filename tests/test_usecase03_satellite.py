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

PLOT_PATH = MODULE_PATH.with_name("plot_satellite_downscaling.py")
PLOT_SPEC = importlib.util.spec_from_file_location("usecase03_plot_satellite", PLOT_PATH)
assert PLOT_SPEC is not None and PLOT_SPEC.loader is not None
PLOT_MODULE = importlib.util.module_from_spec(PLOT_SPEC)
PLOT_SPEC.loader.exec_module(PLOT_MODULE)

NO2_PATH = MODULE_PATH.with_name("evaluate_no2_column.py")
NO2_SPEC = importlib.util.spec_from_file_location("usecase03_evaluate_no2", NO2_PATH)
assert NO2_SPEC is not None and NO2_SPEC.loader is not None
NO2_MODULE = importlib.util.module_from_spec(NO2_SPEC)
NO2_SPEC.loader.exec_module(NO2_MODULE)

TRACER_PATH = MODULE_PATH.with_name("controlled_tracer_validation.py")
TRACER_SPEC = importlib.util.spec_from_file_location("usecase03_controlled_tracer", TRACER_PATH)
assert TRACER_SPEC is not None and TRACER_SPEC.loader is not None
TRACER_MODULE = importlib.util.module_from_spec(TRACER_SPEC)
TRACER_SPEC.loader.exec_module(TRACER_MODULE)

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


def test_satellite_plot_uses_one_color_scale_for_both_fields() -> None:
    original = np.asarray([[0.0, 1.0], [2.0, np.nan]])
    downscaled = np.asarray([[0.5, 1.5], [3.0, 4.0]])

    low, high = PLOT_MODULE.shared_color_limits(original, downscaled)

    combined = np.asarray([0.0, 1.0, 2.0, 0.5, 1.5, 3.0, 4.0])
    assert low == pytest.approx(np.percentile(combined, 2.0))
    assert high == pytest.approx(np.percentile(combined, 98.0))


def test_seamless_regularization_reduces_coarse_pixel_edge() -> None:
    field = np.ones((31, 31), dtype=float)
    field[:, 16:] = 5.0

    regularized = MODULE.seamless_regularize(field, radius_cells=4, blend=1.0)

    original_jump = float(np.mean(np.abs(field[:, 16] - field[:, 15])))
    regularized_jump = float(np.mean(np.abs(regularized[:, 16] - regularized[:, 15])))
    assert regularized_jump < 0.25 * original_jump
    assert np.mean(regularized) == pytest.approx(np.mean(field))


def test_guided_downscale_preserves_south_to_north_orientation() -> None:
    # Input row zero is already the southern row after the explicit GeoTIFF flip.
    coarse = np.asarray([[1.0, 1.0], [4.0, 4.0]])

    field = MODULE._guided_seamless_downscale(coarse, np.ones((20, 20)))

    assert np.mean(field[0]) < np.mean(field[-1])
    assert np.mean(field) == pytest.approx(np.mean(coarse))


def test_satellite_plot_reads_normalized_spritz_model_plume(tmp_path: Path) -> None:
    netcdf4 = pytest.importorskip("netCDF4")
    path = tmp_path / "concentration.nc"
    with netcdf4.Dataset(path, "w") as dataset:
        dataset.createDimension("time", 2)
        dataset.createDimension("field_z", 1)
        dataset.createDimension("field_y", 3)
        dataset.createDimension("field_x", 4)
        variable = dataset.createVariable(
            "concentration_field", "f8", ("time", "field_z", "field_y", "field_x")
        )
        values = np.zeros((2, 1, 3, 4), dtype=float)
        values[1, 0, 1, 2] = 8.0
        variable[:] = values

    plume = PLOT_MODULE._read_model_plume(path, 1, 0)

    assert plume.shape == (3, 4)
    assert np.min(plume) >= 0.0
    assert np.max(plume) == pytest.approx(1.0)


def test_no2_model_column_integration_converts_to_moles(tmp_path: Path) -> None:
    netcdf4 = pytest.importorskip("netCDF4")
    path = tmp_path / "no2.nc"
    with netcdf4.Dataset(path, "w") as dataset:
        dataset.createDimension("time", 1)
        dataset.createDimension("field_z", 2)
        dataset.createDimension("field_y", 1)
        dataset.createDimension("field_x", 1)
        dataset.createVariable("field_z", "f8", ("field_z",))[:] = [0.0, 100.0]
        variable = dataset.createVariable(
            "concentration_field", "f8", ("time", "field_z", "field_y", "field_x")
        )
        variable.units = "g m-3"
        variable[:] = np.full((1, 2, 1, 1), NO2_MODULE.NO2_MOLAR_MASS_G_MOL)

    column, levels = NO2_MODULE._integrated_model_column(path, 0)

    assert levels.tolist() == [0.0, 100.0]
    assert column[0, 0] == pytest.approx(100.0)


def test_no2_native_aggregation_flips_model_rows_to_satellite_orientation() -> None:
    model = np.asarray([[1.0, 1.0], [4.0, 4.0]])  # south row, then north row

    satellite_order = NO2_MODULE._aggregate_to_shape(model, (2, 2))

    assert satellite_order[0].tolist() == [4.0, 4.0]
    assert satellite_order[1].tolist() == [1.0, 1.0]


def test_controlled_tracer_metrics_report_standard_factor_scores() -> None:
    predicted = np.asarray([1.0, 2.0, 0.0, 8.0])
    observed = np.asarray([1.0, 1.0, 1.0, 2.0])

    metrics = TRACER_MODULE.validation_metrics(predicted, observed, detection_limit=0.5)

    assert metrics["paired_sample_count"] == 4
    assert metrics["fraction_within_factor_2"] == pytest.approx(0.5)
    assert metrics["fraction_within_factor_5"] == pytest.approx(0.75)
    assert metrics["false_negative"] == 1
    assert metrics["false_positive"] == 0


def test_controlled_tracer_pairing_requires_receptor_and_time_match() -> None:
    model = [
        {"receptor_id": "R1", "time": 60.0, "concentration": 2.0},
        {"receptor_id": "R2", "time": 60.0, "concentration": 5.0},
    ]
    observations = [
        {"receptor_id": "R1", "time_s": 60.0, "concentration": 1.5},
        {"receptor_id": "R2", "time_s": 120.0, "concentration": 4.0},
    ]

    predicted, observed, pairs = TRACER_MODULE.paired_samples(model, observations)

    assert predicted.tolist() == [2.0]
    assert observed.tolist() == [1.5]
    assert len(pairs) == 1


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


def test_station_correction_uses_only_valid_in_domain_observations(tmp_path: Path) -> None:
    config = load_config(
        Path(__file__).resolve().parents[1]
        / "usecases"
        / "03_satellite_ai_evaluation"
        / "demo"
        / "config.json"
    )
    stations = tmp_path / "stations.csv"
    stations.write_text(
        "id,LAT,LON,NO2\n"
        "near-source,40.9769,14.2168,80\n"
        "east,40.9769,14.2762,10\n"
        "outside,50.0,20.0,500\n",
        encoding="utf-8",
    )
    base = np.linspace(0.0, 1.0, config.grid.nx)[None, :]
    base = np.repeat(base, config.grid.ny, axis=0)

    correction, report = MODULE._station_correction(stations, base, config)

    assert correction.shape == (config.grid.ny, config.grid.nx)
    assert report["station_observations_used"] == 2
    assert report["station_ids_used"] == ["near-source", "east"]
    assert report["station_correction_status"] == "applied"
    assert np.min(correction) >= 0.5
    assert np.max(correction) <= 2.0


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

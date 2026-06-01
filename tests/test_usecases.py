from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import numpy as np

from sprtz.io.jsonio import write_json
from sprtz.models import spritzwrf

USECASES = Path(__file__).resolve().parents[1] / "usecases"
sys.path.insert(0, str(USECASES))

from high_resolution_wind import interpolate_wrf_to_100m, resolve_wrf_input  # noqa: E402
from model_evaluation import evaluate_wildfire_event  # noqa: E402
from production_incidents import build_incident_config, load_incident_catalog, select_event  # noqa: E402
from sailing_forecast import SailingForecastRequest, build_sailing_forecast, parse_bbox  # noqa: E402
from wildfire import build_wildfire_config, run_wildfire_event  # noqa: E402


def test_high_resolution_wind_json_synthetic(tmp_path: Path) -> None:
    out = tmp_path / "wind.json"
    result = interpolate_wrf_to_100m(
        None,
        out,
        center_lat=40.85,
        center_lon=14.27,
        nx=9,
        ny=7,
        prefer_netcdf=False,
        allow_synthetic=True,
    )
    assert out.exists()
    assert result.nx == 9
    assert result.format == "json"


def test_build_wildfire_config(tmp_path: Path) -> None:
    cfg_path = tmp_path / "wildfire.json"
    config = build_wildfire_config(
        cfg_path,
        center_lat=40.85,
        center_lon=14.27,
        burning_temperature_k=1000.0,
        burning_duration_s=1800.0,
        burning_area_m2=1000.0,
    )
    assert cfg_path.exists()
    assert config["sources"][0]["heat_release"] > 0
    assert config["sources"][0]["emission_rate"] > 0
    assert len(config["receptors"]) > 0


def test_run_wildfire_event_json_synthetic(tmp_path: Path) -> None:
    result = run_wildfire_event(
        tmp_path / "case",
        center_lat=40.85,
        center_lon=14.27,
        burning_temperature_k=1000.0,
        burning_duration_s=600.0,
        burning_area_m2=500.0,
        backend="gaussian",
        interchange="json",
        allow_synthetic_wrf=True,
    )
    assert result.config_path.exists()
    assert Path(result.workflow["concentration"]).exists()


def test_evaluate_wildfire_event(tmp_path: Path) -> None:
    concentration = tmp_path / "concentration.json"
    rows = [
        {"x": 0.0, "y": 0.0, "concentration": 1.0},
        {"x": 1.0, "y": 0.0, "concentration": 0.8},
        {"x": 0.0, "y": 1.0, "concentration": 0.2},
        {"x": 1.0, "y": 1.0, "concentration": 0.0},
    ]
    write_json(concentration, {"format": "cf-json-fallback", "rows": rows})
    mask = tmp_path / "mask.json"
    write_json(mask, {"mask": [[1.0, 1.0], [0.0, 0.0]]})
    report = tmp_path / "evaluation.json"
    result = evaluate_wildfire_event(concentration, mask, report)
    assert report.exists()
    assert result["metrics"]["accuracy"] >= 0.5
    assert "ai_calibration" in result


def test_meteo_uniparthenope_url_builder() -> None:
    assert spritzwrf.meteo_uniparthenope_wrf_url("2026-05-27", 0).endswith(
        "/2026/05/27/wrf5_d03_20260527Z0000.nc"
    )
    assert spritzwrf.meteo_uniparthenope_wrf_url("2026-05-27", "18").endswith(
        "wrf5_d03_20260527Z1800.nc"
    )


def test_resolve_wrf_input_prefers_local_path(tmp_path: Path) -> None:
    wrf = tmp_path / "wrf5_d03_20260527Z0000.nc"
    wrf.write_bytes(b"placeholder")
    assert resolve_wrf_input(wrf, download_date="2026-05-27") == wrf


def test_production_incident_catalog_and_config(tmp_path: Path) -> None:
    events = load_incident_catalog()
    assert {event.code for event in events} >= {"2021_44", "2023_14"}
    event = select_event(events, "2023_14")
    assert event.place == "San Marcellino"
    assert event.latitude == 40.98472
    assert event.longitude == 14.18250
    config_path = tmp_path / "incident.json"
    config = build_incident_config(
        event,
        config_path,
        receptor_radius_m=500.0,
        receptor_spacing_m=500.0,
    )
    assert config_path.exists()
    assert config["metadata"]["event"]["cod_gisa"] == "2023_14"
    assert config["metadata"]["event"]["duration_h"] == 3.0
    assert "latitude" in config["receptors"][0]
    assert "longitude" in config["receptors"][0]


def test_sailing_forecast_small_grid(tmp_path: Path) -> None:
    output = tmp_path / "sailing.json"
    result = build_sailing_forecast(
        SailingForecastRequest(
            initialization_date=date(2026, 6, 1),
            outlook_h=0.25,
            bbox=parse_bbox("14.20,40.72,14.205,40.725"),
            horizontal_resolution_m=250.0,
            vertical_resolution_m=10.0,
            time_resolution_s=600.0,
            top_altitude_m=20.0,
        ),
        output,
    )
    assert output.exists()
    assert result["initialization_utc"] == "2026-06-01T00:00:00Z"
    assert result["time_resolution_s"] == 600.0
    assert result["vertical_resolution_m"] == 10.0
    assert len(result["height_m"]) == 3


def test_usecases_are_not_packaged_as_suite_modules() -> None:
    assert not (Path("src/sprtz/usecases")).exists()

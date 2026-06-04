from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import numpy as np

from sprtz.io.jsonio import write_json
from sprtz.io.netcdf_cf import available as netcdf_available
from sprtz.models import spritzwrf

USECASES = Path(__file__).resolve().parents[1] / "usecases"
sys.path.insert(0, str(USECASES))

from high_resolution_wind import interpolate_wrf_to_100m, resolve_wrf_input  # noqa: E402
from model_evaluation import evaluate_wildfire_event  # noqa: E402
from production_incidents import build_incident_config, load_incident_catalog, select_event  # noqa: E402
from sailing_forecast import (  # noqa: E402
    BAY_OF_NAPLES_RACE_BOX,
    DEFAULT_OUTLOOK_H,
    DEFAULT_TIME_RESOLUTION_S,
    DEFAULT_VERTICAL_RESOLUTION_M,
    SailingForecastRequest,
    build_sailing_forecast,
    parse_bbox,
)
from wildfire import (  # noqa: E402
    _load_fire_events,
    build_wildfire_config,
    run_wildfire_event,
)
from acerra_waste_to_energy import (  # noqa: E402
    ACERRA_STACK_HEIGHT_M,
    build_acerra_config,
)


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


def test_build_wildfire_config_supports_multi_fire_materials_and_windows(tmp_path: Path) -> None:
    cfg_path = tmp_path / "multi_fire.json"
    config = build_wildfire_config(
        cfg_path,
        center_lat=40.85,
        center_lon=14.27,
        burning_start="2026-06-01T00:00:00+00:00",
        burning_duration_s=3600.0,
        fire_events=[
            {
                "id": "PAPER_FIRE",
                "latitude": 40.85,
                "longitude": 14.27,
                "height_agl_m": 0.0,
                "start_datetime": "2026-06-01T00:00:00+00:00",
                "end_datetime": "2026-06-01T01:00:00+00:00",
                "material": "paper",
                "area_m2": 100.0,
            },
            {
                "id": "PLASTIC_FIRE",
                "latitude": 40.851,
                "longitude": 14.271,
                "height_agl_m": 2.0,
                "start_datetime": "2026-06-01T00:30:00+00:00",
                "end_datetime": "2026-06-01T02:00:00+00:00",
                "material": "plastic",
                "area_m2": 200.0,
            },
        ],
        weather_start="2026-06-01T00:00:00+00:00",
        weather_end="2026-06-01T02:00:00+00:00",
        firefighters_start="2026-06-01T01:00:00+00:00",
        firefighters_end="2026-06-01T02:00:00+00:00",
        firefighters_emission_factor=0.4,
        precipitation_washout=True,
    )
    assert cfg_path.exists()
    assert len(config["sources"]) == 2
    assert {source["material"] for source in config["sources"]} == {"paper", "plastic"}
    assert config["sources"][1]["stack_height"] == 2.0
    assert config["run"]["firefighters_emission_factor"] == 0.4
    assert config["run"]["precipitation_washout"] is True


def test_wildfire_cli_fire_events_json_accepts_inline_and_file(tmp_path: Path) -> None:
    inline = '[{"id":"F1","latitude":40.85,"longitude":14.27,"material":"paper"}]'
    from_inline = _load_fire_events(inline)
    assert from_inline is not None
    assert from_inline[0]["material"] == "paper"
    path = tmp_path / "events.json"
    path.write_text(inline, encoding="utf-8")
    from_file = _load_fire_events(str(path))
    assert from_file == from_inline


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


def test_acerra_waste_to_energy_config(tmp_path: Path) -> None:
    cfg_path = tmp_path / "acerra.json"
    config = build_acerra_config(cfg_path)
    assert cfg_path.exists()
    assert config["sources"][0]["latitude"] == 40.978473
    assert config["sources"][0]["longitude"] == 14.384058
    assert config["sources"][0]["stack_height"] == ACERRA_STACK_HEIGHT_M
    assert config["run"]["event_start_datetime"] == "2026-06-01T00:00:00+00:00"
    assert config["run"]["event_end_datetime"] == "2026-06-01T12:00:00+00:00"
    assert config["run"]["output_interval_s"] == 3600.0


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


def test_wrf_precipitation_rate_extraction(tmp_path: Path) -> None:
    if not netcdf_available():
        return
    from netCDF4 import Dataset  # type: ignore

    path = tmp_path / "wrf_precip.nc"
    with Dataset(path, "w") as ds:
        ds.createDimension("Time", 2)
        ds.createDimension("south_north", 2)
        ds.createDimension("west_east", 2)
        for name, values in [
            ("XLAT", np.full((2, 2, 2), 40.0)),
            ("XLONG", np.full((2, 2, 2), 14.0)),
            ("U10", np.full((2, 2, 2), 3.0)),
            ("V10", np.zeros((2, 2, 2))),
            ("RAINC", np.asarray([np.zeros((2, 2)), np.full((2, 2), 0.2)])),
            ("RAINNC", np.asarray([np.ones((2, 2)), np.full((2, 2), 1.7)])),
        ]:
            var = ds.createVariable(name, "f8", ("Time", "south_north", "west_east"))
            var[:, :, :] = values
    wrf = spritzwrf.load_near_surface_wind(path, time_index=1)
    assert wrf.precipitation_rate is not None
    np.testing.assert_allclose(wrf.precipitation_rate, np.full((2, 2), 0.9))


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


def test_sailing_forecast_demo_defaults() -> None:
    assert BAY_OF_NAPLES_RACE_BOX == (14.18, 40.78, 14.33, 40.85)
    assert DEFAULT_OUTLOOK_H == 24.0
    assert DEFAULT_VERTICAL_RESOLUTION_M == 10.0
    assert DEFAULT_TIME_RESOLUTION_S == 600.0


def test_usecases_are_not_packaged_as_suite_modules() -> None:
    assert not (Path("src/sprtz/usecases")).exists()

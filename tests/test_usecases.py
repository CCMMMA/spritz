from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pytest

from sprtz.io.jsonio import read_json, write_json
from sprtz.io.netcdf_cf import available as netcdf_available
from sprtz.models import spritzmet, spritzwrf

USECASES = Path(__file__).resolve().parents[1] / "usecases"
sys.path.insert(0, str(USECASES))

from acerra_waste_to_energy import (  # noqa: E402
    ACERRA_STACK_HEIGHT_M,
    build_acerra_config,
)
from high_resolution_wind import interpolate_wrf_to_100m, resolve_wrf_input  # noqa: E402
from model_evaluation import evaluate_wildfire_event  # noqa: E402
from production_incidents import (  # noqa: E402
    build_incident_config,
    load_incident_catalog,
    select_event,
)
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


def _load_usecase_step(folder: str, script: str):
    path = USECASES / folder / script
    spec = importlib.util.spec_from_file_location(f"test_{folder}_{script}", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


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


def test_high_resolution_wind_netcdf_synthetic_requires_valid_time(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="valid-time metadata"):
        interpolate_wrf_to_100m(
            None,
            tmp_path / "wind.nc",
            center_lat=40.85,
            center_lon=14.27,
            nx=9,
            ny=7,
            prefer_netcdf=True,
            allow_synthetic=True,
        )


def test_high_resolution_wind_run_entrypoint_synthetic(tmp_path: Path) -> None:
    module = _load_usecase_step("01_high_resolution_wind_field", "step_01_interpolate_wind.py")
    out = tmp_path / "wind.json"

    assert (
        module.main(
            [
                "--allow-synthetic",
                "--json",
                "--output",
                str(out),
                "--center-lat",
                "40.85",
                "--center-lon",
                "14.27",
                "--nx",
                "7",
                "--ny",
                "7",
            ]
        )
        == 0
    )
    assert out.exists()


def test_high_resolution_wind_run_entrypoint_bbox_synthetic(tmp_path: Path) -> None:
    module = _load_usecase_step("01_high_resolution_wind_field", "step_01_interpolate_wind.py")
    out = tmp_path / "wind_bbox.json"

    assert (
        module.main(
            [
                "--allow-synthetic",
                "--json",
                "--output",
                str(out),
                "--south",
                "40.84",
                "--north",
                "40.86",
                "--west",
                "14.26",
                "--east",
                "14.28",
                "--dx",
                "100",
                "--dy",
                "100",
            ]
        )
        == 0
    )
    assert out.exists()
    payload = read_json(out)
    assert payload["dx_m"] == 100.0
    assert payload["dy_m"] == 100.0
    assert len(payload["latitude"]) > 2
    assert len(payload["latitude"][0]) > 2


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
    inline = '[{"id":"F1","latitude":40.85,"longitude":14.27,"material":"paper","start_datetime":"20260601Z0000"}]'
    from_inline = _load_fire_events(inline)
    assert from_inline is not None
    assert from_inline[0]["material"] == "paper"
    assert from_inline[0]["start_datetime"] == "2026-06-01T00:00:00+00:00"
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


def test_wildfire_run_entrypoint_synthetic(tmp_path: Path) -> None:
    module = _load_usecase_step("02_wildfire_arson_effects", "step_02_build_config.py")
    out = tmp_path / "wildfire"
    config = out / "wildfire_event.json"
    out.mkdir()

    assert (
        module.main(
            [
                "--start",
                "20260601Z0000",
                "--end",
                "20260601Z0010",
                "--output",
                str(config),
                "--center-lat",
                "40.85",
                "--center-lon",
                "14.27",
                "--duration-s",
                "600",
                "--area-m2",
                "500",
            ]
        )
        == 0
    )
    assert config.exists()


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


def test_acerra_run_entrypoint_config_only(tmp_path: Path) -> None:
    module = _load_usecase_step("06_acerra_waste_to_energy", "step_01_build_config.py")
    out = tmp_path / "acerra"
    out.mkdir()

    assert module.main(["--output", str(out / "acerra_waste_to_energy.json")]) == 0
    assert (out / "acerra_waste_to_energy.json").exists()


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


def test_satellite_evaluation_run_entrypoint(tmp_path: Path) -> None:
    module = _load_usecase_step("03_satellite_ai_evaluation", "step_02_evaluate.py")
    concentration = tmp_path / "concentration.json"
    mask = tmp_path / "mask.json"
    output = tmp_path / "evaluation.json"
    write_json(
        concentration,
        {
            "format": "cf-json-fallback",
            "rows": [
                {"x": 0.0, "y": 0.0, "concentration": 1.0},
                {"x": 1.0, "y": 0.0, "concentration": 0.0},
                {"x": 0.0, "y": 1.0, "concentration": 0.4},
                {"x": 1.0, "y": 1.0, "concentration": 0.2},
            ],
        },
    )
    write_json(mask, {"mask": [[1.0, 0.0], [0.0, 0.0]]})

    assert (
        module.main(
            [
                "--concentration",
                str(concentration),
                "--satellite-mask",
                str(mask),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    assert output.exists()


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


def test_wrf_four_dimensional_wind_selects_time_and_level_independently(tmp_path: Path) -> None:
    if not netcdf_available():
        return
    from netCDF4 import Dataset  # type: ignore

    path = tmp_path / "wrf_4d_wind.nc"
    with Dataset(path, "w") as ds:
        ds.createDimension("Time", 2)
        ds.createDimension("bottom_top", 3)
        ds.createDimension("south_north", 2)
        ds.createDimension("west_east", 2)
        lat_values = np.asarray([[[40.0, 40.0], [40.01, 40.01]], [[41.0, 41.0], [41.01, 41.01]]])
        lon_values = np.asarray([[[14.0, 14.01], [14.0, 14.01]], [[15.0, 15.01], [15.0, 15.01]]])
        for name, values in [("XLAT", lat_values), ("XLONG", lon_values)]:
            var = ds.createVariable(name, "f8", ("Time", "south_north", "west_east"))
            var[:, :, :] = values
        u_values = np.zeros((2, 3, 2, 2), dtype=float)
        v_values = np.zeros((2, 3, 2, 2), dtype=float)
        for time in range(2):
            for level in range(3):
                u_values[time, level, :, :] = 100.0 * time + 10.0 * level + 3.0
                v_values[time, level, :, :] = 100.0 * time + 10.0 * level + 4.0
        for name, values in [("U", u_values), ("V", v_values)]:
            var = ds.createVariable(name, "f8", ("Time", "bottom_top", "south_north", "west_east"))
            var[:, :, :, :] = values

    wrf = spritzwrf.load_near_surface_wind(path, time_index=1, level_index=2)
    np.testing.assert_allclose(wrf.latitude, lat_values[1])
    np.testing.assert_allclose(wrf.u, np.full((2, 2), 123.0))
    np.testing.assert_allclose(wrf.v, np.full((2, 2), 124.0))
    assert wrf.metadata is not None
    assert wrf.metadata["time_index"] == "1"
    assert wrf.metadata["level_index"] == "2"


def test_wrf_to_local_netcdf_writes_cf_time_from_wrf_times(tmp_path: Path) -> None:
    if not netcdf_available():
        return
    from netCDF4 import Dataset  # type: ignore

    path = tmp_path / "wrf5_d03_20260527Z0000.nc"
    with Dataset(path, "w") as ds:
        ds.createDimension("Time", 1)
        ds.createDimension("DateStrLen", 19)
        ds.createDimension("south_north", 2)
        ds.createDimension("west_east", 2)
        times = ds.createVariable("Times", "S1", ("Time", "DateStrLen"))
        times[0, :] = np.asarray(list("2026-05-27_00:00:00"), dtype="S1")
        lat_values = np.asarray([[[40.0, 40.0], [40.01, 40.01]]])
        lon_values = np.asarray([[[14.0, 14.01], [14.0, 14.01]]])
        for name, values in [
            ("XLAT", lat_values),
            ("XLONG", lon_values),
            ("U10", np.full((1, 2, 2), 3.0)),
            ("V10", np.zeros((1, 2, 2))),
        ]:
            var = ds.createVariable(name, "f8", ("Time", "south_north", "west_east"))
            var[:, :, :] = values

    wrf = spritzwrf.load_near_surface_wind(path, time_index=0)
    assert wrf.metadata is not None
    assert wrf.metadata["time_datetime"] == "2026-05-27T00:00:00Z"
    met = spritzmet.downscale_wrf_to_local_grid(
        wrf,
        center_lat=40.005,
        center_lon=14.005,
        nx=3,
        ny=3,
        dx_m=100.0,
        dy_m=100.0,
    )
    out = tmp_path / "local.nc"
    spritzmet.write_local_meteorology(out, met)

    with Dataset(out) as ds:
        assert "time" in ds.variables
        assert ds.variables["eastward_wind"].dimensions == ("time", "z", "y", "x")
        assert ds.variables["eastward_wind"].shape == (1, 1, 3, 3)
        assert ds.variables["northward_wind"].shape == (1, 1, 3, 3)
        assert ds.variables["precipitation_rate"].dimensions == ("time", "y", "x")
        assert ds.variables["precipitation_rate"].shape == (1, 3, 3)
        assert ds.variables["time"].standard_name == "time"
        assert ds.variables["time"].units == "seconds since 2026-05-27 00:00:00 UTC"
        assert ds.variables["time"][0] == pytest.approx(0.0)
        assert str(ds.variables["time_datetime"][0]) == "2026-05-27T00:00:00Z"


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


def test_production_incident_run_entrypoint_config_only(tmp_path: Path) -> None:
    module = _load_usecase_step("04_production_incidents", "step_01_build_config.py")
    out = tmp_path / "incident"
    out.mkdir()

    assert (
        module.main(
            [
                "--code",
                "2021_44",
                "--output",
                str(out / "2021_44_config.json"),
            ]
        )
        == 0
    )
    assert (out / "2021_44_config.json").exists()


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


def test_sailing_forecast_run_entrypoint(tmp_path: Path) -> None:
    module = _load_usecase_step("05_sailing_wind_forecast", "step_01_build_forecast.py")
    output = tmp_path / "sailing.json"

    assert (
        module.main(
            [
                "--initialization-time",
                "20260601Z0000",
                "--outlook-hours",
                "0.25",
                "--bbox",
                "14.20,40.72,14.205,40.725",
                "--horizontal-resolution-m",
                "250",
                "--vertical-resolution-m",
                "10",
                "--time-resolution-s",
                "600",
                "--top-altitude-m",
                "20",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    assert output.exists()


def test_sailing_forecast_demo_defaults() -> None:
    assert BAY_OF_NAPLES_RACE_BOX == (14.18, 40.78, 14.33, 40.85)
    assert DEFAULT_OUTLOOK_H == 24.0
    assert DEFAULT_VERTICAL_RESOLUTION_M == 10.0
    assert DEFAULT_TIME_RESOLUTION_S == 600.0


def test_fire_workflow_run_entrypoints_route_backends(monkeypatch, tmp_path: Path) -> None:
    calls = []

    def fake_run_workflow(config, output_dir, *, backend=None, interchange=None, **kwargs):
        calls.append(
            {
                "config": Path(config).name,
                "output_dir": Path(output_dir).name,
                "backend": backend,
                "interchange": interchange,
                "kwargs": kwargs,
            }
        )
        return {"concentration": str(Path(output_dir) / "concentration.json")}

    for folder in [
        "06_wildfire_fire_spread",
        "07_wildfire_fire_and_smoke",
        "08_firms_satellite_ignition",
        "09_gpu_accelerated_spread",
    ]:
        script = {
            "06_wildfire_fire_spread": "step_01_run_fire_spread.py",
            "07_wildfire_fire_and_smoke": "step_02_run_smoke.py",
            "08_firms_satellite_ignition": "step_01_run_firms_ignition.py",
            "09_gpu_accelerated_spread": "step_01_run_gpu_spread.py",
        }[folder]
        module = _load_usecase_step(folder, script)
        module.__file__ = str(tmp_path / "repo" / "usecases" / folder / script)
        monkeypatch.setattr(module, "run_workflow", fake_run_workflow)
        assert module.main() is None

    assert [call["backend"] for call in calls] == [
        "firefront",
        "fire+puff",
        "firms+fire",
        "firefront",
    ]
    assert all(call["config"] == "wildfire_minimal.json" for call in calls)
    assert all(call["interchange"] == "netcdf" for call in calls)


def test_backward_run_entrypoints_route_models(monkeypatch, tmp_path: Path) -> None:
    plume_met = _load_usecase_step("10_backward_plume_origin", "step_01_prepare_meteorology.py")
    plume_back = _load_usecase_step("10_backward_plume_origin", "step_02_estimate_source.py")
    fire = _load_usecase_step("11_backward_fire_origin", "step_01_estimate_ignition.py")
    calls = []

    def fake_spritzmet_run(config, output, fmt):
        calls.append(("spritzmet", Path(output).name, fmt))
        write_json(output, {"component": "meteo"})
        return {"output": str(output)}

    def fake_backward_run(config, meteo, output, *, model):
        calls.append(
            ("backward", None if meteo is None else Path(meteo).name, Path(output).name, model)
        )
        write_json(output, {"model": model})
        return {"output": str(output)}

    monkeypatch.setattr(plume_met.spritzmet, "run", fake_spritzmet_run)
    monkeypatch.setattr(plume_back.backward, "run_backward", fake_backward_run)
    monkeypatch.setattr(fire.backward, "run_backward", fake_backward_run)
    monkeypatch.setattr(plume_met, "load_config", lambda path: {"path": str(path)})
    monkeypatch.setattr(plume_back, "load_config", lambda path: {"path": str(path)})
    monkeypatch.setattr(fire, "load_config", lambda path: {"path": str(path)})
    plume_met.__file__ = str(tmp_path / "repo" / "usecases" / "10_backward_plume_origin" / "step_01_prepare_meteorology.py")
    plume_back.__file__ = str(tmp_path / "repo" / "usecases" / "10_backward_plume_origin" / "step_02_estimate_source.py")
    fire.__file__ = str(tmp_path / "repo" / "usecases" / "11_backward_fire_origin" / "step_01_estimate_ignition.py")

    assert plume_met.main() is None
    assert plume_back.main() is None
    assert fire.main() is None

    assert ("spritzmet", "meteo.nc", "netcdf") in calls
    assert ("backward", "meteo.nc", "source_likelihood.json", "gaussian") in calls
    assert ("backward", None, "ignition_likelihood.json", "firefront") in calls


def test_usecases_are_not_packaged_as_suite_modules() -> None:
    assert not (Path("src/sprtz/usecases")).exists()

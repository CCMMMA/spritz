from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pytest

from sprtz.io.jsonio import read_json, write_json
from sprtz.io.netcdf_cf import available as netcdf_available
from sprtz.models import spritzmet, spritzwrf

USECASES = Path(__file__).resolve().parents[1] / "usecases"
USECASE_IMPORT_DIRS = [
    USECASES / "common",
    USECASES / "01_high_resolution_wind_field" / "demo",
    USECASES / "02_wildfire_arson_effects" / "demo",
    USECASES / "03_satellite_ai_evaluation" / "demo",
    USECASES / "04_production_incidents" / "demo",
    USECASES / "05_sailing_wind_forecast" / "demo",
    USECASES / "06_acerra_waste_to_energy" / "demo",
]
for path in USECASE_IMPORT_DIRS:
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from acerra_waste_to_energy import (  # noqa: E402
    ACERRA_STACK_HEIGHT_M,
    build_acerra_config,
)
from high_resolution_wind import (  # noqa: E402
    UseCaseDependencyError,
    downscale_wrf_to_100m,
    resolve_wrf_input,
)
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
    DEFAULT_WILDFIRE_PARTICLE_ADVECTION_STEPS,
    DEFAULT_WILDFIRE_PARTICLE_COUNT,
    DEFAULT_WILDFIRE_PARTICLE_SIGMA_H_M,
    DEFAULT_WILDFIRE_PARTICLE_SIGMA_Z_M,
    _load_fire_events,
    build_wildfire_config,
    ensure_wildfire_receptor_coordinates,
    run_wildfire_event,
)


def _load_usecase_step(folder: str, script: str):
    path = USECASES / folder / "demo" / script
    spec = importlib.util.spec_from_file_location(f"test_{folder}_{script}", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_high_resolution_wind_json_synthetic(tmp_path: Path) -> None:
    out = tmp_path / "wind.json"
    calmet = tmp_path / "CALMET.DAT"
    result = downscale_wrf_to_100m(
        None,
        out,
        center_lat=40.85,
        center_lon=14.27,
        nx=9,
        ny=7,
        prefer_netcdf=False,
        allow_synthetic=True,
        calmet_dat_path=calmet,
    )
    assert out.exists()
    assert calmet.exists()
    assert result.nx == 9
    assert result.format == "json"
    assert result.calmet_dat_path == calmet


def test_high_resolution_wind_netcdf_synthetic_requires_valid_time(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="valid-time metadata"):
        downscale_wrf_to_100m(
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
    module = _load_usecase_step("01_high_resolution_wind_field", "step_01_downscale_wind.py")
    out = tmp_path / "wind.json"

    assert (
        module.main(
            [
                "--allow-synthetic",
                "--json",
                "--output",
                str(out),
                "--config",
                "usecases/01_high_resolution_wind_field/demo/config.json",
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
    payload = read_json(out)
    assert payload["z"] == pytest.approx(
        [10.0, 15.0, 25.0, 50.0, 75.0, 100.0, 150.0, 250.0, 500.0, 750.0, 1000.0, 1250.0]
    )
    assert payload["metadata"]["level_meters_kind"] == "height_above_sea_level"
    assert payload["metadata"]["physics_operators_enabled"] is True
    assert payload["metadata"]["mass_consistency_iterations"] == 80
    assert (
        payload["metadata"]["mass_consistency_divergence_rms_after_s-1"]
        <= payload["metadata"]["mass_consistency_divergence_rms_before_s-1"]
    )


def test_high_resolution_wind_run_entrypoint_writes_calmet_dat(tmp_path: Path) -> None:
    module = _load_usecase_step("01_high_resolution_wind_field", "step_01_downscale_wind.py")
    out = tmp_path / "wind.json"
    calmet = tmp_path / "CALMET.DAT"

    assert (
        module.main(
            [
                "--allow-synthetic",
                "--json",
                "--output",
                str(out),
                "--calmet-dat",
                str(calmet),
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
    assert calmet.exists()
    assert calmet.read_bytes()[4:14].rstrip() == b"CALMET.DAT"


def test_high_resolution_wind_geotiff_dependency_fails_before_wrf_work(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake_find_spec(name: str):
        if name == "rasterio":
            return None
        return importlib.util.find_spec(name)

    monkeypatch.setattr("high_resolution_wind.importlib.util.find_spec", fake_find_spec)
    with pytest.raises(UseCaseDependencyError, match=r"python -m pip install -e '.\[geo,netcdf\]'"):
        downscale_wrf_to_100m(
            tmp_path / "missing-wrf.nc",
            tmp_path / "wind.json",
            center_lat=40.85,
            center_lon=14.27,
            prefer_netcdf=False,
            dem_path=tmp_path / "dem.tif",
        )


def test_high_resolution_wind_entrypoint_uses_dem_and_land_cover_rasters(tmp_path: Path) -> None:
    module = _load_usecase_step("01_high_resolution_wind_field", "step_01_downscale_wind.py")
    out = tmp_path / "wind_terrain.json"

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
                "--dem",
                "examples/data/highres_dem.asc",
                "--land-cover",
                "examples/data/highres_landcover.asc",
            ]
        )
        == 0
    )
    payload = read_json(out)
    metadata = payload["metadata"]
    assert metadata["downscaling_algorithm"] == "clean_room_calmet_style_diagnostic"
    assert metadata["uses_dem_elevation_m"] is True
    assert metadata["uses_land_cover"] is True
    assert metadata["dem_resampling"] == "bilinear"
    assert metadata["land_cover_resampling"] == "nearest"


def test_high_resolution_wind_run_entrypoint_bbox_synthetic(tmp_path: Path) -> None:
    module = _load_usecase_step("01_high_resolution_wind_field", "step_01_downscale_wind.py")
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
                "--dem",
                "examples/data/highres_dem.asc",
                "--land-cover",
                "examples/data/highres_landcover.asc",
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
    assert config["sources"][0]["x"] == pytest.approx(0.0, abs=1.0e-6)
    assert config["sources"][0]["y"] == pytest.approx(0.0, abs=1.0e-6)
    assert config["sources"][0]["latitude"] == pytest.approx(40.85)
    assert config["sources"][0]["longitude"] == pytest.approx(14.27)
    assert config["grid"]["x0"] + ((config["grid"]["nx"] - 1) / 2.0) * config["grid"]["dx"] == pytest.approx(0.0)
    assert config["grid"]["y0"] + ((config["grid"]["ny"] - 1) / 2.0) * config["grid"]["dy"] == pytest.approx(0.0)
    assert config["run"]["field_z_levels"][-1] >= 2000.0
    assert config["run"]["particles"] == DEFAULT_WILDFIRE_PARTICLE_COUNT
    assert config["run"]["particle_sigma_h"] == DEFAULT_WILDFIRE_PARTICLE_SIGMA_H_M
    assert config["run"]["particle_sigma_z"] == DEFAULT_WILDFIRE_PARTICLE_SIGMA_Z_M
    assert config["run"]["particle_advection_steps"] == DEFAULT_WILDFIRE_PARTICLE_ADVECTION_STEPS
    assert len(config["receptors"]) > 0
    assert all("latitude" in receptor and "longitude" in receptor for receptor in config["receptors"])
    center_receptor = min(
        config["receptors"],
        key=lambda receptor: abs(float(receptor["x"])) + abs(float(receptor["y"])),
    )
    assert center_receptor["latitude"] == pytest.approx(40.85)
    assert center_receptor["longitude"] == pytest.approx(14.27)


def test_build_wildfire_config_supports_multiple_field_z_levels(tmp_path: Path) -> None:
    cfg_path = tmp_path / "wildfire_vertical.json"
    config = build_wildfire_config(
        cfg_path,
        center_lat=40.85,
        center_lon=14.27,
        burning_temperature_k=1000.0,
        field_z_levels=[1.5, 10.0, 50.0, 100.0],
    )

    assert config["run"]["field_z_levels"] == [1.5, 10.0, 50.0, 100.0]
    assert read_json(cfg_path)["run"]["field_z_levels"] == [1.5, 10.0, 50.0, 100.0]


def test_wildfire_step3_preserves_explicit_field_z_levels(tmp_path: Path) -> None:
    step3 = _load_usecase_step("02_wildfire_arson_effects", "step_03_run_model.py")
    cfg_path = tmp_path / "wildfire.json"
    write_json(
        cfg_path,
        {
            "grid": {"nx": 1, "ny": 1, "dx": 100.0, "dy": 100.0, "x0": 0.0, "y0": 0.0},
            "sources": [{"id": "S", "x": 0.0, "y": 0.0, "z": 0.0, "emission_rate": 1.0}],
            "receptors": [],
            "run": {"field_z_levels": [2.5, 5.0, 10.0, 300.0]},
        },
    )

    config, _interval, changed = step3._ensure_time_dependent_plume_config(cfg_path, None)

    assert changed is True
    assert config["run"]["field_z_levels"] == [2.5, 5.0, 10.0, 300.0]
    assert read_json(cfg_path)["run"]["field_z_levels"] == [2.5, 5.0, 10.0, 300.0]


def test_wildfire_step3_logs_seconds_per_simulated_hour(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    if not netcdf_available():
        pytest.skip("netCDF4 unavailable")
    from netCDF4 import Dataset  # type: ignore

    module = _load_usecase_step("02_wildfire_arson_effects", "step_03_run_model.py")
    concentration = tmp_path / "concentration.nc"
    with Dataset(concentration, "w") as ds:
        ds.createDimension("time", 2)
        time_var = ds.createVariable("time", "f8", ("time",))
        time_var[:] = np.asarray([3600.0, 7200.0], dtype=float)

    caplog.set_level(logging.INFO, logger=module.LOGGER.name)
    module._log_backend_hourly_performance(
        backend="particles",
        workflow={"concentration": str(concentration), "output_interval_s": 3600.0},
        elapsed_s=8.0,
        output_interval_s=3600.0,
    )

    messages = [record.getMessage() for record in caplog.records]
    assert any("seconds_per_simulated_hour=4.000" in message for message in messages)
    assert not any("step 3/3 progress: backend=particles computed_hour=" in message for message in messages)


def test_usecase_plotting_shim_imports_from_usecases_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo_root = USECASES.parent.resolve()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "path",
        [
            entry
            for entry in sys.path
            if entry
            and Path(entry).resolve() != repo_root
            and Path(entry).resolve() != Path.cwd().resolve()
        ],
    )
    monkeypatch.syspath_prepend(str(USECASES))
    sys.modules.pop("plotting", None)
    sys.modules.pop("usecases", None)

    module = importlib.import_module("plotting")

    assert callable(module.add_plot_argument)


def test_plot_netcdf_can_overlay_plume_vectors_from_meteo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import plotting  # noqa: PLC0415

    @dataclass(frozen=True)
    class FakeVectors:
        u: np.ndarray
        v: np.ndarray
        label: str = "Wind vector"

    @dataclass(frozen=True)
    class FakeField:
        values: np.ndarray
        vectors: FakeVectors | None

    plume = tmp_path / "concentration.nc"
    meteo = tmp_path / "meteo.nc"
    out = tmp_path / "concentration_map.png"
    plume.write_text("", encoding="utf-8")
    meteo.write_text("", encoding="utf-8")

    class FakePlotter:
        def read_map_field(self, path, **kwargs):
            if Path(path) == meteo:
                vectors = FakeVectors(np.ones((2, 2)), np.zeros((2, 2)))
                return FakeField(np.zeros((2, 2)), vectors)
            return FakeField(np.zeros((2, 2)), None)

        def plot_map(self, field, output_path, **kwargs):
            assert field.vectors is not None
            Path(output_path).write_text("ok", encoding="utf-8")
            return Path(output_path)

    monkeypatch.setattr(plotting, "_load_plotter", lambda: FakePlotter())
    plotted = plotting.plot_netcdf_if_available(
        plume,
        out,
        variable="concentration_field",
        vector_source_path=meteo,
        vector_variable="wind_speed",
        vector_level_index=0,
    )

    assert plotted == out
    assert out.read_text(encoding="utf-8") == "ok"


def test_plot_workflow_netcdfs_writes_3d_concentration(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import plotting  # noqa: PLC0415

    concentration = tmp_path / "concentration.nc"
    terrain = tmp_path / "geo.nc"
    concentration.write_text("", encoding="utf-8")
    terrain.write_text("", encoding="utf-8")

    monkeypatch.setattr(plotting, "plot_netcdf_if_available", lambda *args, **kwargs: None)
    monkeypatch.setattr(plotting, "plot_concentration_vertical_profiles_if_available", lambda *args, **kwargs: None)
    monkeypatch.setattr(plotting, "plot_vertical_profiles_if_available", lambda *args, **kwargs: None)
    calls: list[dict[str, object]] = []

    def fake_plot_3d(input_path, output_path, **kwargs):
        calls.append({"input_path": input_path, "output_path": output_path, **kwargs})
        return Path(output_path)

    monkeypatch.setattr(plotting, "plot_3d_volume_if_available", fake_plot_3d)

    products = plotting.plot_workflow_netcdfs(
        {"concentration": str(concentration), "terrain": str(terrain)},
        tmp_path,
    )

    assert products["concentration_3d"] == str(tmp_path / "concentration_3d.png")
    assert calls[0]["terrain_path"] == str(terrain)
    assert calls[0]["variable"] == "concentration_field"


def test_wildfire_step3_plots_only_when_requested(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    module = _load_usecase_step("02_wildfire_arson_effects", "step_03_run_model.py")
    config = tmp_path / "wildfire.json"
    config.write_text("{}", encoding="utf-8")
    output_dir = tmp_path / "model"
    concentration = output_dir / "concentration.nc"

    monkeypatch.setattr(module, "ensure_wildfire_receptor_coordinates", lambda path: False)
    monkeypatch.setattr(
        module,
        "_ensure_time_dependent_plume_config",
        lambda config_path, meteo_path: ({"metadata": {}}, 3600.0, False),
    )
    monkeypatch.setattr(
        module,
        "_run_workflow_with_performance_log",
        lambda **kwargs: {"concentration": str(concentration), "meteo": str(output_dir / "meteo.nc"), "post": str(output_dir / "post.json")},
    )
    plotted: list[Path] = []

    def fake_plot_concentration(input_path, output_path, **kwargs):
        plotted.append(Path(output_path))
        return Path(output_path)

    monkeypatch.setattr(module, "plot_concentration_vertical_profiles_if_available", fake_plot_concentration)
    monkeypatch.setattr(module, "plot_3d_volume_if_available", fake_plot_concentration)

    assert module.main(["--config", str(config), "--output-dir", str(output_dir), "--backend", "particles"]) == 0
    assert plotted == []

    assert module.main(["--config", str(config), "--output-dir", str(output_dir), "--backend", "particles", "--plot"]) == 0
    assert plotted == [
        output_dir / "particles_concentration_vertical_profiles.png",
        output_dir / "particles_concentration_3d.png",
    ]


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


def test_wildfire_config_upgrade_adds_receptor_coordinates(tmp_path: Path) -> None:
    cfg_path = tmp_path / "legacy_wildfire.json"
    config = build_wildfire_config(
        cfg_path,
        center_lat=40.85,
        center_lon=14.27,
        burning_temperature_k=1000.0,
    )
    for receptor in config["receptors"]:
        receptor.pop("latitude", None)
        receptor.pop("longitude", None)
    write_json(cfg_path, config)

    assert ensure_wildfire_receptor_coordinates(cfg_path) is True
    upgraded = read_json(cfg_path)
    assert all("latitude" in receptor and "longitude" in receptor for receptor in upgraded["receptors"])


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
        dem_path="examples/data/highres_dem.asc",
        land_cover_path="examples/data/highres_landcover.asc",
    )
    assert result.config_path.exists()
    assert result.calmet_dat_path == tmp_path / "case" / "CALMET.DAT"
    assert result.calmet_dat_path.exists()
    assert Path(result.workflow["concentration"]).exists()
    meteo = read_json(tmp_path / "case" / "wrf_100m_wind.json")
    assert meteo["metadata"]["uses_dem_elevation_m"] is True
    assert meteo["metadata"]["uses_land_cover"] is True


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
                "--nx",
                "9",
                "--ny",
                "7",
                "--dx",
                "200",
                "--dy",
                "100",
                "--duration-s",
                "600",
                "--area-m2",
                "500",
                "--field-z-levels",
                "1.5,10,50",
            ]
        )
        == 0
    )
    assert config.exists()
    payload = read_json(config)
    assert payload["grid"]["nx"] == 9
    assert payload["grid"]["ny"] == 7
    assert payload["grid"]["dx"] == 200.0
    assert payload["grid"]["dy"] == 100.0
    assert payload["grid"]["x0"] + ((payload["grid"]["nx"] - 1) / 2.0) * payload["grid"]["dx"] == pytest.approx(0.0)
    assert payload["grid"]["y0"] + ((payload["grid"]["ny"] - 1) / 2.0) * payload["grid"]["dy"] == pytest.approx(0.0)
    assert payload["run"]["field_z_levels"] == [1.5, 10.0, 50.0]


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
    url = spritzwrf.meteo_uniparthenope_wrf_url("2026-05-27", 0)
    evening_url = spritzwrf.meteo_uniparthenope_wrf_url("2026-05-27", "18")

    assert url == (
        "https://data.meteo.uniparthenope.it/files/wrf5/d03/history/2026/05/27/"
        "wrf5_d03_20260527Z0000.nc"
    )
    assert "/history/" in evening_url
    assert "/archive/" not in evening_url
    assert evening_url.endswith("wrf5_d03_20260527Z1800.nc")


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
        height = ds.createVariable("height_m", "f8", ("bottom_top",))
        height[:] = np.asarray([10.0, 80.0, 250.0])
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
    assert wrf.metadata["level_meters"] == [250.0]
    assert wrf.metadata["level_meters_kind"] == "height_above_sea_level"


def test_wrf_level_meters_from_geopotential_height(tmp_path: Path) -> None:
    if not netcdf_available():
        return
    from netCDF4 import Dataset  # type: ignore

    path = tmp_path / "wrf_geopotential_height.nc"
    with Dataset(path, "w") as ds:
        ds.createDimension("Time", 1)
        ds.createDimension("bottom_top", 2)
        ds.createDimension("bottom_top_stag", 3)
        ds.createDimension("south_north", 2)
        ds.createDimension("west_east", 2)
        lat_values = np.asarray([[[40.0, 40.0], [40.01, 40.01]]])
        lon_values = np.asarray([[[14.0, 14.01], [14.0, 14.01]]])
        for name, values in [("XLAT", lat_values), ("XLONG", lon_values)]:
            var = ds.createVariable(name, "f8", ("Time", "south_north", "west_east"))
            var[:, :, :] = values
        for name in ("U", "V"):
            var = ds.createVariable(name, "f8", ("Time", "bottom_top", "south_north", "west_east"))
            var[:, :, :, :] = np.ones((1, 2, 2, 2), dtype=float)
        hgt = ds.createVariable("HGT", "f8", ("Time", "south_north", "west_east"))
        hgt[:, :, :] = np.full((1, 2, 2), 100.0)
        ph = ds.createVariable("PH", "f8", ("Time", "bottom_top_stag", "south_north", "west_east"))
        phb = ds.createVariable("PHB", "f8", ("Time", "bottom_top_stag", "south_north", "west_east"))
        ph[:, :, :, :] = 0.0
        phb[:, :, :, :] = np.asarray([[[[100.0]], [[120.0]], [[160.0]]]]) * 9.80665

    wrf = spritzwrf.load_near_surface_wind(path, time_index=0, level_index=1)

    assert wrf.metadata is not None
    assert wrf.metadata["level_meters"] == [140.0]
    assert wrf.metadata["level_meters_kind"] == "height_above_sea_level"


def test_wrf_u10_level_meters_is_ten_above_ground(tmp_path: Path) -> None:
    if not netcdf_available():
        return
    from netCDF4 import Dataset  # type: ignore

    path = tmp_path / "wrf_u10_with_geopotential.nc"
    with Dataset(path, "w") as ds:
        ds.createDimension("Time", 1)
        ds.createDimension("bottom_top_stag", 3)
        ds.createDimension("south_north", 2)
        ds.createDimension("west_east", 2)
        lat_values = np.asarray([[[40.0, 40.0], [40.01, 40.01]]])
        lon_values = np.asarray([[[14.0, 14.01], [14.0, 14.01]]])
        for name, values in [("XLAT", lat_values), ("XLONG", lon_values)]:
            var = ds.createVariable(name, "f8", ("Time", "south_north", "west_east"))
            var[:, :, :] = values
        for name in ("U10", "V10"):
            var = ds.createVariable(name, "f8", ("Time", "south_north", "west_east"))
            var[:, :, :] = np.ones((1, 2, 2), dtype=float)
        hgt = ds.createVariable("HGT", "f8", ("Time", "south_north", "west_east"))
        hgt[:, :, :] = np.full((1, 2, 2), 100.0)
        ph = ds.createVariable("PH", "f8", ("Time", "bottom_top_stag", "south_north", "west_east"))
        phb = ds.createVariable("PHB", "f8", ("Time", "bottom_top_stag", "south_north", "west_east"))
        ph[:, :, :, :] = 0.0
        phb[:, :, :, :] = np.asarray([[[[100.0]], [[120.0]], [[160.0]]]]) * 9.80665

    wrf = spritzwrf.load_near_surface_wind(path, time_index=0, level_index=0)

    assert wrf.metadata is not None
    assert wrf.metadata["level_meters"] == [10.0]
    assert wrf.metadata["level_meters_kind"] == "height_above_ground"


def test_spritzmet_logs_time_datetime_and_level_meters(caplog: pytest.LogCaptureFixture, tmp_path: Path) -> None:
    if not netcdf_available():
        return
    from netCDF4 import Dataset  # type: ignore

    path = tmp_path / "wrf_4d_wind_logging.nc"
    with Dataset(path, "w") as ds:
        ds.createDimension("Time", 2)
        ds.createDimension("DateStrLen", 19)
        ds.createDimension("bottom_top", 2)
        ds.createDimension("south_north", 2)
        ds.createDimension("west_east", 2)
        times = ds.createVariable("Times", "S1", ("Time", "DateStrLen"))
        times[0, :] = np.asarray(list("2026-05-27_00:00:00"), dtype="S1")
        times[1, :] = np.asarray(list("2026-05-27_01:00:00"), dtype="S1")
        height = ds.createVariable("height_m", "f8", ("bottom_top",))
        height[:] = np.asarray([10.0, 80.0])
        lat_values = np.asarray([[[40.0, 40.0], [40.01, 40.01]], [[40.0, 40.0], [40.01, 40.01]]])
        lon_values = np.asarray([[[14.0, 14.01], [14.0, 14.01]], [[14.0, 14.01], [14.0, 14.01]]])
        for name, values in [("XLAT", lat_values), ("XLONG", lon_values)]:
            var = ds.createVariable(name, "f8", ("Time", "south_north", "west_east"))
            var[:, :, :] = values
        for name in ("U", "V"):
            var = ds.createVariable(name, "f8", ("Time", "bottom_top", "south_north", "west_east"))
            var[:, :, :, :] = np.ones((2, 2, 2, 2), dtype=float)

    wrf = spritzwrf.load_near_surface_wind(path, time_index=None, level_index=None)
    assert wrf.metadata is not None
    assert wrf.metadata["level_meters"] == [10.0, 80.0]

    with caplog.at_level("INFO", logger="sprtz.models.spritzmet"):
        spritzmet.downscale_wrf_to_local_grid(
            wrf,
            center_lat=40.005,
            center_lon=14.005,
            nx=3,
            ny=3,
            dx_m=100.0,
            dy_m=100.0,
        )

    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "time_index=1 datetime_utc=2026-05-27T01:00:00Z" in messages
    assert "level_index=1 level_m=80.000" in messages


def test_wrf_all_levels_prefers_model_wind_over_diagnostic_10m(tmp_path: Path) -> None:
    if not netcdf_available():
        return
    from netCDF4 import Dataset  # type: ignore

    path = tmp_path / "wrf5_d03_20260527Z0000.nc"
    with Dataset(path, "w") as ds:
        ds.createDimension("Time", 1)
        ds.createDimension("DateStrLen", 19)
        ds.createDimension("bottom_top", 2)
        ds.createDimension("south_north", 2)
        ds.createDimension("west_east", 2)
        times = ds.createVariable("Times", "S1", ("Time", "DateStrLen"))
        times[0, :] = np.asarray(list("2026-05-27_00:00:00"), dtype="S1")
        lat_values = np.asarray([[[40.0, 40.0], [40.01, 40.01]]])
        lon_values = np.asarray([[[14.0, 14.01], [14.0, 14.01]]])
        for name, values in [
            ("XLAT", lat_values),
            ("XLONG", lon_values),
            ("U10", np.full((1, 2, 2), -10.0)),
            ("V10", np.full((1, 2, 2), -20.0)),
        ]:
            var = ds.createVariable(name, "f8", ("Time", "south_north", "west_east"))
            var[:, :, :] = values
        u = ds.createVariable("U", "f8", ("Time", "bottom_top", "south_north", "west_east"))
        v = ds.createVariable("V", "f8", ("Time", "bottom_top", "south_north", "west_east"))
        u[0, 0, :, :] = 3.0
        u[0, 1, :, :] = 13.0
        v[0, 0, :, :] = 4.0
        v[0, 1, :, :] = 14.0

    wrf = spritzwrf.load_near_surface_wind(path, time_index=None, level_index=None)

    assert wrf.u.shape == (1, 2, 2, 2)
    np.testing.assert_allclose(wrf.u[0, 0], 3.0)
    np.testing.assert_allclose(wrf.u[0, 1], 13.0)
    assert wrf.u10m is not None
    assert wrf.v10m is not None
    np.testing.assert_allclose(wrf.u10m, -10.0)
    np.testing.assert_allclose(wrf.v10m, -20.0)
    assert wrf.metadata is not None
    assert wrf.metadata["level_index"] == "all"
    assert wrf.metadata.get("level_meters_source") != "diagnostic_10m_wind"


def test_wrf_all_levels_destaggers_standard_u_v_components(tmp_path: Path) -> None:
    if not netcdf_available():
        return
    from netCDF4 import Dataset  # type: ignore

    path = tmp_path / "wrf5_d03_20260527Z0000.nc"
    with Dataset(path, "w") as ds:
        ds.createDimension("Time", 1)
        ds.createDimension("DateStrLen", 19)
        ds.createDimension("bottom_top", 1)
        ds.createDimension("south_north", 2)
        ds.createDimension("west_east", 2)
        ds.createDimension("south_north_stag", 3)
        ds.createDimension("west_east_stag", 3)
        times = ds.createVariable("Times", "S1", ("Time", "DateStrLen"))
        times[0, :] = np.asarray(list("2026-05-27_00:00:00"), dtype="S1")
        lat_values = np.asarray([[[40.0, 40.0], [40.01, 40.01]]])
        lon_values = np.asarray([[[14.0, 14.01], [14.0, 14.01]]])
        for name, values in [
            ("XLAT", lat_values),
            ("XLONG", lon_values),
            ("U10", np.full((1, 2, 2), -10.0)),
            ("V10", np.full((1, 2, 2), -20.0)),
        ]:
            var = ds.createVariable(name, "f8", ("Time", "south_north", "west_east"))
            var[:, :, :] = values
        u = ds.createVariable("U", "f8", ("Time", "bottom_top", "south_north", "west_east_stag"))
        v = ds.createVariable("V", "f8", ("Time", "bottom_top", "south_north_stag", "west_east"))
        u[0, 0, :, :] = np.asarray([[0.0, 2.0, 6.0], [10.0, 12.0, 16.0]])
        v[0, 0, :, :] = np.asarray([[0.0, 10.0], [2.0, 12.0], [6.0, 16.0]])

    wrf = spritzwrf.load_near_surface_wind(path, time_index=None, level_index=None)

    assert wrf.u.shape == (1, 1, 2, 2)
    assert wrf.v.shape == (1, 1, 2, 2)
    np.testing.assert_allclose(wrf.u[0, 0], [[1.0, 4.0], [11.0, 14.0]])
    np.testing.assert_allclose(wrf.v[0, 0], [[1.0, 11.0], [4.0, 14.0]])


def test_high_resolution_wind_entrypoint_without_indices_downscales_all_times_and_levels(tmp_path: Path) -> None:
    if not netcdf_available():
        return
    from netCDF4 import Dataset  # type: ignore

    module = _load_usecase_step("01_high_resolution_wind_field", "step_01_downscale_wind.py")
    wrf_path = tmp_path / "wrf_all_times_levels.nc"
    with Dataset(wrf_path, "w") as ds:
        ds.createDimension("Time", 2)
        ds.createDimension("DateStrLen", 19)
        ds.createDimension("bottom_top", 3)
        ds.createDimension("south_north", 2)
        ds.createDimension("west_east", 2)
        times = ds.createVariable("Times", "S1", ("Time", "DateStrLen"))
        times[0, :] = np.asarray(list("2026-05-27_00:00:00"), dtype="S1")
        times[1, :] = np.asarray(list("2026-05-27_01:00:00"), dtype="S1")
        lat_values = np.asarray([[[40.0, 40.0], [40.01, 40.01]], [[40.0, 40.0], [40.01, 40.01]]])
        lon_values = np.asarray([[[14.0, 14.01], [14.0, 14.01]], [[14.0, 14.01], [14.0, 14.01]]])
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
        rain = ds.createVariable("RAINRATE", "f8", ("Time", "south_north", "west_east"))
        rain[:, :, :] = np.asarray([np.full((2, 2), 0.5), np.full((2, 2), 1.5)])

    out = tmp_path / "local_all.nc"
    stations = tmp_path / "stations.csv"
    stations.write_text(
        "id,x,y,wind_speed,wind_dir,precipitation_rate\nS1,0,0,8,270,2.0\n",
        encoding="utf-8",
    )
    assert (
        module.main(
            [
                "--wrf",
                str(wrf_path),
                "--output",
                str(out),
                "--center-lat",
                "40.005",
                "--center-lon",
                "14.005",
                "--nx",
                "3",
                "--ny",
                "3",
                "--dx",
                "100",
                "--dy",
                "100",
                "--dem",
                "examples/data/highres_dem.asc",
                "--land-cover",
                "examples/data/highres_landcover.asc",
                "--station-measurements",
                str(stations),
            ]
        )
        == 0
    )
    with Dataset(out) as ds:
        assert ds.variables["eastward_wind"].shape == (2, 3, 3, 3)
        assert ds.variables["northward_wind"].shape == (2, 3, 3, 3)
        assert ds.variables["wind_speed"].shape == (2, 3, 3, 3)
        assert ds.variables["precipitation_rate"].shape == (2, 3, 3)
        assert ds.variables["time"].shape == (2,)
        assert str(ds.variables["time_datetime"][1]) == "2026-05-27T01:00:00Z"
        assert ds.spritzmet_downscaling_algorithm == "clean_room_calmet_style_diagnostic"
        assert ds.spritzmet_uses_dem_elevation_m == "true"
        assert ds.spritzmet_uses_land_cover == "true"
        assert ds.spritzmet_station_measurement_improvement == "true"
        assert ds.spritzmet_station_measurement_count == 1
        assert ds.variables["z"].units == "1"
        assert ds.variables["z"].long_name == "vertical level index"


def test_high_resolution_wind_vertical_level_preset_points_to_config() -> None:
    module = _load_usecase_step("01_high_resolution_wind_field", "step_01_downscale_wind_impl.py")
    with pytest.raises(ValueError, match="config.json"):
        module._parse_vertical_levels_m("usecase01-exponential")


def test_wildfire_wind_step_accepts_field_z_levels() -> None:
    _load_usecase_step("02_wildfire_arson_effects", "step_01_downscale_wind.py")
    impl = importlib.import_module("wind_downscaling_cli")
    parser = impl.build_parser()
    args = parser.parse_args(
        [
            "--output",
            "wind.nc",
            "--field-z-levels",
            "2.5,5,10,20",
            "--advanced-physics",
            "--bulk-richardson-number",
            "0.1",
        ]
    )

    assert impl._parse_vertical_levels_m(args.field_z_levels) == [2.5, 5.0, 10.0, 20.0]
    assert args.advanced_physics is True
    assert args.bulk_richardson_number == pytest.approx(0.1)


def test_wind_downscaling_result_supports_wildfire_component(tmp_path: Path) -> None:
    module = _load_usecase_step("01_high_resolution_wind_field", "step_01_downscale_wind_impl.py")
    result = module.WindDownscalingResult(
        tmp_path / "wind.nc",
        3,
        3,
        100.0,
        100.0,
        40.827,
        14.518,
        "wrf.nc",
        "NetCDF-CF",
        component="usecase.02_wildfire_arson_effects",
    )

    assert result.as_dict()["component"] == "usecase.02_wildfire_arson_effects"


def test_high_resolution_wind_step_rejects_removed_vertical_levels_flag() -> None:
    module = _load_usecase_step("01_high_resolution_wind_field", "step_01_downscale_wind_impl.py")
    parser = module.build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["--output", "wind.nc", "--vertical-levels-m", "10,20"])


def test_high_resolution_wind_hourly_resolver_skips_unreadable_netcdf(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    pytest.importorskip("netCDF4")
    module = _load_usecase_step("01_high_resolution_wind_field", "step_01_downscale_wind_impl.py")
    bad_wrf = tmp_path / "wrf5_d03_20240731Z1000.nc"
    bad_wrf.write_bytes(b"not a netcdf file")

    assert module._local_hourly_wrf_path(tmp_path, module.parse_script_datetime("20240731Z1000")) is None
    assert "ignoring unreadable WRF file" in caplog.text


def test_high_resolution_wind_vertical_levels_expand_single_level_wrf() -> None:
    module = _load_usecase_step("01_high_resolution_wind_field", "step_01_downscale_wind_impl.py")
    wrf = module._synthetic_wrf(40.0, 14.0)
    expanded = module._with_vertical_level_metadata(wrf, [10.0, 20.0, 40.0])
    assert expanded.u.shape == (1, 3, 7, 7)
    assert expanded.v.shape == (1, 3, 7, 7)
    assert expanded.metadata["level_meters"] == [10.0, 20.0, 40.0]
    assert expanded.metadata["level_meters_kind"] == "height_above_sea_level"
    assert expanded.metadata["vertical_level_expansion"] == "single_near_surface_level_repeated"
    np.testing.assert_allclose(expanded.u[0, 0], wrf.u)
    np.testing.assert_allclose(expanded.u[0, 1], wrf.u)


def test_high_resolution_wind_vertical_levels_anchor_10m_to_diagnostic_wind() -> None:
    module = _load_usecase_step("01_high_resolution_wind_field", "step_01_downscale_wind_impl.py")
    lat = np.asarray([[40.0, 40.0], [40.01, 40.01]], dtype=float)
    lon = np.asarray([[14.0, 14.01], [14.0, 14.01]], dtype=float)
    u = np.full((2, 2), 1.0, dtype=float)
    v = np.full((2, 2), 2.0, dtype=float)
    u10m = np.full((2, 2), 3.0, dtype=float)
    v10m = np.full((2, 2), 4.0, dtype=float)
    wrf = spritzwrf.WRFWindField(
        lat,
        lon,
        u,
        v,
        Path("wrf_10m.nc"),
        u10m=u10m,
        v10m=v10m,
    )

    expanded = module._with_vertical_level_metadata(wrf, [10.0, 20.0])
    met = spritzmet.downscale_wrf_to_local_grid(
        expanded,
        center_lat=40.005,
        center_lon=14.005,
        nx=2,
        ny=2,
        dx_m=100.0,
        dy_m=100.0,
        neighbours=1,
        land_cover=np.asarray([[80, 50], [80, 50]], dtype=float),
    )
    water = np.asarray([[True, False], [True, False]])
    land = ~water

    np.testing.assert_allclose(expanded.u[0, 0], u)
    np.testing.assert_allclose(expanded.v[0, 0], v)
    np.testing.assert_allclose(met.u[:, 0, water], met.u10m[:, water])
    np.testing.assert_allclose(met.v[:, 0, water], met.v10m[:, water])
    np.testing.assert_allclose(met.wind_speed[:, 0, water], met.wind_speed_10m[:, water])
    assert not np.allclose(met.u[:, 0, land], met.u10m[:, land])
    assert not np.allclose(met.v[:, 0, land], met.v10m[:, land])
    np.testing.assert_allclose(expanded.u[0, 1], u)
    np.testing.assert_allclose(expanded.v[0, 1], v)
    assert met.downscaling_metadata["vertical_level_10m_reference"] == "U10M/V10M"
    assert met.downscaling_metadata["vertical_level_10m_reference_domain"] == "water_land_cover_cells_only"
    assert met.downscaling_metadata["vertical_level_10m_reference_cell_count"] == 2
    assert met.downscaling_metadata["vertical_level_10m_reference_assumption"] == "sea_surface_height_approximately_mean_sea_level"


def test_spritzmet_anchors_10m_diagnostic_to_dem_plus_10m_asl() -> None:
    module = _load_usecase_step("01_high_resolution_wind_field", "step_01_downscale_wind_impl.py")
    lat = np.asarray([[40.0, 40.0], [40.01, 40.01]], dtype=float)
    lon = np.asarray([[14.0, 14.01], [14.0, 14.01]], dtype=float)
    u = np.full((2, 2), 1.0, dtype=float)
    v = np.full((2, 2), 2.0, dtype=float)
    u10m = np.full((2, 2), 3.0, dtype=float)
    v10m = np.full((2, 2), 4.0, dtype=float)
    wrf = spritzwrf.WRFWindField(
        lat,
        lon,
        u,
        v,
        Path("wrf_10m_dem.nc"),
        u10m=u10m,
        v10m=v10m,
    )
    expanded = module._with_vertical_level_metadata(wrf, [100.0, 110.0, 150.0])

    met = spritzmet.downscale_wrf_to_local_grid(
        expanded,
        center_lat=40.005,
        center_lon=14.005,
        nx=2,
        ny=2,
        dx_m=100.0,
        dy_m=100.0,
        neighbours=1,
        dem_elevation_m=np.full((2, 2), 100.0, dtype=float),
    )

    np.testing.assert_allclose(met.u[:, 1], met.u10m)
    np.testing.assert_allclose(met.v[:, 1], met.v10m)
    np.testing.assert_allclose(met.wind_speed[:, 1], met.wind_speed_10m)
    assert met.downscaling_metadata["vertical_level_10m_reference_domain"] == "all_cells_dem_plus_10m_asl"
    assert met.downscaling_metadata["vertical_level_10m_reference_cell_count"] == 4
    assert met.downscaling_metadata["vertical_level_10m_reference_exact_level_indexes"] == [1]
    assert "DEM elevation plus 10 m" in met.downscaling_metadata["vertical_level_10m_reference_assumption"]


def test_spritzmet_anchors_water_cells_to_10m_asl_even_with_dem() -> None:
    module = _load_usecase_step("01_high_resolution_wind_field", "step_01_downscale_wind_impl.py")
    lat = np.asarray([[40.0, 40.0], [40.01, 40.01]], dtype=float)
    lon = np.asarray([[14.0, 14.01], [14.0, 14.01]], dtype=float)
    wrf = spritzwrf.WRFWindField(
        lat,
        lon,
        np.full((2, 2), 1.0, dtype=float),
        np.full((2, 2), 2.0, dtype=float),
        Path("wrf_10m_mixed_water_land.nc"),
        u10m=np.full((2, 2), 3.0, dtype=float),
        v10m=np.full((2, 2), 4.0, dtype=float),
    )
    expanded = module._with_vertical_level_metadata(wrf, [10.0, 110.0])

    met = spritzmet.downscale_wrf_to_local_grid(
        expanded,
        center_lat=40.005,
        center_lon=14.005,
        nx=2,
        ny=2,
        dx_m=100.0,
        dy_m=100.0,
        neighbours=1,
        dem_elevation_m=np.asarray([[0.0, 100.0], [0.0, 100.0]], dtype=float),
        land_cover=np.asarray([[80, 50], [80, 50]], dtype=float),
    )

    water = np.asarray([[True, False], [True, False]])
    land = ~water
    np.testing.assert_allclose(met.wind_speed[:, 0, water], met.wind_speed_10m[:, water])
    np.testing.assert_allclose(met.wind_speed[:, 1, land], met.wind_speed_10m[:, land])
    assert not np.allclose(met.wind_speed[:, 0, land], met.wind_speed_10m[:, land])
    assert met.downscaling_metadata["vertical_level_10m_reference_domain"] == "water_10m_asl_land_dem_plus_10m_asl"
    assert "water land-cover cells use 10 m above mean sea level" in met.downscaling_metadata[
        "vertical_level_10m_reference_assumption"
    ]


def test_spritzmet_masks_asl_wind_levels_below_dem() -> None:
    module = _load_usecase_step("01_high_resolution_wind_field", "step_01_downscale_wind_impl.py")
    lat = np.asarray([[40.0, 40.0], [40.01, 40.01]], dtype=float)
    lon = np.asarray([[14.0, 14.01], [14.0, 14.01]], dtype=float)
    wrf = spritzwrf.WRFWindField(
        lat,
        lon,
        np.full((2, 2), 1.0, dtype=float),
        np.full((2, 2), 2.0, dtype=float),
        Path("wrf_below_ground_mask.nc"),
    )
    expanded = module._with_vertical_level_metadata(wrf, [10.0, 100.0])
    dem = np.asarray([[0.0, 20.0], [100.0, 150.0]], dtype=float)

    met = spritzmet.downscale_wrf_to_local_grid(
        expanded,
        center_lat=40.005,
        center_lon=14.005,
        nx=2,
        ny=2,
        dx_m=100.0,
        dy_m=100.0,
        neighbours=1,
        dem_elevation_m=dem,
    )

    assert np.isfinite(met.wind_speed[:, 0, 0, 0]).all()
    assert np.isnan(met.wind_speed[:, 0, 0, 1]).all()
    assert np.isnan(met.wind_speed[:, 0, 1, 0]).all()
    assert np.isnan(met.wind_speed[:, 0, 1, 1]).all()
    assert np.isfinite(met.wind_speed[:, 1, 0, 0]).all()
    assert np.isfinite(met.wind_speed[:, 1, 0, 1]).all()
    assert np.isfinite(met.wind_speed[:, 1, 1, 0]).all()
    assert np.isnan(met.wind_speed[:, 1, 1, 1]).all()
    assert met.downscaling_metadata["below_ground_wind_mask"] is True
    assert met.downscaling_metadata["below_ground_wind_masked_cell_count"] == 4


def test_spritzmet_vertical_profile_constraint_uses_dem_and_land_cover() -> None:
    lat = np.asarray([[40.0, 40.0], [40.01, 40.01]], dtype=float)
    lon = np.asarray([[14.0, 14.01], [14.0, 14.01]], dtype=float)
    wrf = spritzwrf.WRFWindField(
        lat,
        lon,
        np.full((1, 2, 2, 2), 4.0, dtype=float),
        np.zeros((1, 2, 2, 2), dtype=float),
        Path("wrf_profile_constraint.nc"),
        metadata={
            "time_index": "all",
            "level_index": "all",
            "level_meters": [10.0, 100.0],
            "level_meters_kind": "height_above_sea_level",
        },
        u10m=np.full((2, 2), 4.0, dtype=float),
        v10m=np.zeros((2, 2), dtype=float),
    )

    met = spritzmet.downscale_wrf_to_local_grid(
        wrf,
        center_lat=40.005,
        center_lon=14.005,
        nx=2,
        ny=2,
        dx_m=100.0,
        dy_m=100.0,
        neighbours=1,
        dem_elevation_m=np.zeros((2, 2), dtype=float),
        land_cover=np.asarray([[80, 50], [80, 311]], dtype=float),
    )

    assert met.downscaling_metadata["vertical_wind_profile_constraint"] is True
    assert met.downscaling_metadata["vertical_wind_profile_uses_dem_elevation_m"] is True
    assert met.downscaling_metadata["vertical_wind_profile_uses_land_cover"] is True
    np.testing.assert_allclose(met.wind_speed[:, 0], met.wind_speed_10m)
    water_speed_100m = float(met.wind_speed[0, 1, 0, 0])
    urban_speed_100m = float(met.wind_speed[0, 1, 0, 1])
    forest_speed_100m = float(met.wind_speed[0, 1, 1, 1])
    assert water_speed_100m > urban_speed_100m
    assert water_speed_100m > forest_speed_100m


def test_spritzmet_reuses_projected_idw_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    lat = np.asarray([[40.0, 40.0], [40.01, 40.01]], dtype=float)
    lon = np.asarray([[14.0, 14.01], [14.0, 14.01]], dtype=float)
    wrf = spritzwrf.WRFWindField(
        lat,
        lon,
        np.full((2, 2), 1.0, dtype=float),
        np.full((2, 2), 2.0, dtype=float),
        Path("wrf_plan.nc"),
        precipitation_rate=np.full((2, 2), 0.5, dtype=float),
        u10m=np.full((2, 2), 3.0, dtype=float),
        v10m=np.full((2, 2), 4.0, dtype=float),
    )
    calls = 0
    original = spritzmet._idw_neighbour_plan_from_points

    def counted_plan(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(spritzmet, "_idw_neighbour_plan_from_points", counted_plan)

    met = spritzmet.downscale_wrf_to_local_grid(
        wrf,
        center_lat=40.005,
        center_lon=14.005,
        nx=3,
        ny=3,
        dx_m=100.0,
        dy_m=100.0,
    )

    assert calls == 1
    assert met.downscaling_metadata["spatial_interpolation_coordinates"] == "local_projected_meters"
    assert met.downscaling_metadata["spatial_interpolation_plan_reused"] is True


def test_spritzmet_refines_10m_diagnostic_before_anchor() -> None:
    module = _load_usecase_step("01_high_resolution_wind_field", "step_01_downscale_wind_impl.py")
    lat = np.asarray([[40.0, 40.0], [40.01, 40.01]], dtype=float)
    lon = np.asarray([[14.0, 14.01], [14.0, 14.01]], dtype=float)
    wrf = spritzwrf.WRFWindField(
        lat,
        lon,
        np.full((2, 2), 1.0, dtype=float),
        np.full((2, 2), 2.0, dtype=float),
        Path("wrf_10m_terrain.nc"),
        u10m=np.full((2, 2), 3.0, dtype=float),
        v10m=np.full((2, 2), 4.0, dtype=float),
    )
    expanded = module._with_vertical_level_metadata(wrf, [100.0, 110.0])

    met = spritzmet.downscale_wrf_to_local_grid(
        expanded,
        center_lat=40.005,
        center_lon=14.005,
        nx=2,
        ny=2,
        dx_m=100.0,
        dy_m=100.0,
        neighbours=1,
        dem_elevation_m=np.asarray([[100.0, 120.0], [140.0, 160.0]], dtype=float),
        land_cover=np.asarray([[50, 50], [311, 311]], dtype=float),
    )

    assert met.downscaling_metadata["diagnostic_10m_max_wind_factor"] != pytest.approx(1.0)
    assert not np.allclose(met.u10m, 3.0)
    np.testing.assert_allclose(met.u[:, 1, 0, 0], met.u10m[:, 0, 0])
    np.testing.assert_allclose(met.v[:, 1, 0, 0], met.v10m[:, 0, 0])


def test_high_resolution_wind_vertical_levels_remap_multilevel_wrf() -> None:
    module = _load_usecase_step("01_high_resolution_wind_field", "step_01_downscale_wind_impl.py")
    lat = np.asarray([[40.0, 40.0], [40.01, 40.01]], dtype=float)
    lon = np.asarray([[14.0, 14.01], [14.0, 14.01]], dtype=float)
    u = np.zeros((1, 3, 2, 2), dtype=float)
    v = np.zeros((1, 3, 2, 2), dtype=float)
    u[0, 0, :, :] = 10.0
    u[0, 1, :, :] = 20.0
    u[0, 2, :, :] = 40.0
    v[0, 0, :, :] = 1.0
    v[0, 1, :, :] = 2.0
    v[0, 2, :, :] = 4.0
    wrf = spritzwrf.WRFWindField(
        lat,
        lon,
        u,
        v,
        Path("wrf_4d.nc"),
        metadata={
            "time_index": "all",
            "level_index": "all",
            "level_meters": [100.0, 200.0, 400.0],
            "level_meters_kind": "height_above_sea_level",
        },
    )

    remapped = module._with_vertical_level_metadata(wrf, [150.0, 300.0])

    assert remapped.u.shape == (1, 2, 2, 2)
    assert remapped.v.shape == (1, 2, 2, 2)
    np.testing.assert_allclose(remapped.u[0, 0], 15.0)
    np.testing.assert_allclose(remapped.u[0, 1], 30.0)
    np.testing.assert_allclose(remapped.v[0, 0], 1.5)
    np.testing.assert_allclose(remapped.v[0, 1], 3.0)
    assert remapped.metadata is not None
    assert remapped.metadata["level_meters"] == [150.0, 300.0]
    assert remapped.metadata["vertical_level_remapping"] == "linear_interpolation_from_wrf_levels"
    met = spritzmet.downscale_wrf_to_local_grid(
        remapped,
        center_lat=40.005,
        center_lon=14.005,
        nx=2,
        ny=2,
        dx_m=100.0,
        dy_m=100.0,
    )
    assert met.downscaling_metadata is not None
    assert met.downscaling_metadata["vertical_level_remapping"] == "linear_interpolation_from_wrf_levels"


def test_high_resolution_wind_entrypoint_date_hours_writes_one_multitime_file(tmp_path: Path) -> None:
    if not netcdf_available():
        return
    from netCDF4 import Dataset  # type: ignore

    module = _load_usecase_step("01_high_resolution_wind_field", "step_01_downscale_wind.py")
    wrf_dir = tmp_path / "wrf"
    wrf_dir.mkdir()
    for hour in range(2):
        path = wrf_dir / f"wrf5_d03_20260527Z{hour:02d}00.nc"
        with Dataset(path, "w") as ds:
            ds.createDimension("Time", 1)
            ds.createDimension("DateStrLen", 19)
            ds.createDimension("bottom_top", 2)
            ds.createDimension("south_north", 2)
            ds.createDimension("west_east", 2)
            times = ds.createVariable("Times", "S1", ("Time", "DateStrLen"))
            times[0, :] = np.asarray(list(f"2026-05-27_{hour:02d}:00:00"), dtype="S1")
            lat_values = np.asarray([[[40.0, 40.0], [40.01, 40.01]]])
            lon_values = np.asarray([[[14.0, 14.01], [14.0, 14.01]]])
            for name, values in [("XLAT", lat_values), ("XLONG", lon_values)]:
                var = ds.createVariable(name, "f8", ("Time", "south_north", "west_east"))
                var[:, :, :] = values
            u_values = np.zeros((1, 2, 2, 2), dtype=float)
            v_values = np.zeros((1, 2, 2, 2), dtype=float)
            for level in range(2):
                u_values[0, level, :, :] = 100.0 * hour + 10.0 * level + 3.0
                v_values[0, level, :, :] = 100.0 * hour + 10.0 * level + 4.0
            for name, values in [("U", u_values), ("V", v_values)]:
                var = ds.createVariable(name, "f8", ("Time", "bottom_top", "south_north", "west_east"))
                var[:, :, :, :] = values
            for name, values in [
                ("U10", np.full((1, 2, 2), 10.0 + hour)),
                ("V10", np.full((1, 2, 2), 20.0 + hour)),
                ("T2", np.full((1, 2, 2), 293.15 + hour)),
                ("RH2", np.full((1, 2, 2), 60.0 + hour)),
            ]:
                var = ds.createVariable(name, "f8", ("Time", "south_north", "west_east"))
                var[:, :, :] = values
            rain = ds.createVariable("RAINRATE", "f8", ("Time", "south_north", "west_east"))
            rain[:, :, :] = np.full((1, 2, 2), float(hour + 1))

    out = tmp_path / "wrf_100m_wind_bbox.nc"
    assert (
        module.main(
            [
                "--date",
                "20260527Z0000",
                "--hours",
                "2",
                "--download-dir",
                str(wrf_dir),
                "--output",
                str(out),
                "--center-lat",
                "40.85",
                "--center-lon",
                "14.27",
                "--nx",
                "3",
                "--ny",
                "3",
                "--dx",
                "100",
                "--dy",
                "100",
            ]
        )
        == 0
    )
    with Dataset(out) as ds:
        assert ds.variables["eastward_wind"].dimensions == ("time", "z", "y", "x")
        assert ds.variables["eastward_wind"].shape == (2, 2, 3, 3)
        assert ds.variables["northward_wind"].dimensions == ("time", "z", "y", "x")
        assert ds.variables["northward_wind"].shape == (2, 2, 3, 3)
        assert ds.variables["precipitation_rate"].dimensions == ("time", "y", "x")
        assert ds.variables["precipitation_rate"].shape == (2, 3, 3)
        assert ds.variables["U10M"].dimensions == ("time", "y", "x")
        assert ds.variables["U10M"].shape == (2, 3, 3)
        assert ds.variables["V10M"].dimensions == ("time", "y", "x")
        assert ds.variables["wind_speed_10m"].dimensions == ("time", "y", "x")
        assert ds.variables["temperature_2m_c"].dimensions == ("time", "y", "x")
        assert ds.variables["relative_humidity_2m"].dimensions == ("time", "y", "x")
        np.testing.assert_allclose(ds.variables["U10M"][0], 10.0)
        np.testing.assert_allclose(ds.variables["U10M"][1], 11.0)
        np.testing.assert_allclose(ds.variables["V10M"][0], 20.0)
        np.testing.assert_allclose(ds.variables["V10M"][1], 21.0)
        np.testing.assert_allclose(ds.variables["temperature_2m_c"][0], 20.0)
        np.testing.assert_allclose(ds.variables["temperature_2m_c"][1], 21.0)
        np.testing.assert_allclose(ds.variables["relative_humidity_2m"][0], 0.60)
        np.testing.assert_allclose(ds.variables["relative_humidity_2m"][1], 0.61)
        assert ds.variables["time"].shape == (2,)
        assert str(ds.variables["time_datetime"][0]) == "2026-05-27T00:00:00Z"
        assert str(ds.variables["time_datetime"][1]) == "2026-05-27T01:00:00Z"


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
            ("T2", np.full((1, 2, 2), 293.15)),
            ("RH2", np.full((1, 2, 2), 50.0)),
        ]:
            var = ds.createVariable(name, "f8", ("Time", "south_north", "west_east"))
            var[:, :, :] = values

    wrf = spritzwrf.load_near_surface_wind(path, time_index=0)
    assert wrf.metadata is not None
    assert wrf.metadata["time_datetime"] == "2026-05-27T00:00:00Z"
    np.testing.assert_allclose(wrf.temperature_2m_c, 20.0)
    np.testing.assert_allclose(wrf.relative_humidity_2m, 0.5)
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
        assert ds.variables["U10M"].dimensions == ("time", "y", "x")
        assert ds.variables["V10M"].dimensions == ("time", "y", "x")
        assert ds.variables["wind_speed_10m"].dimensions == ("time", "y", "x")
        assert ds.variables["temperature_2m_c"].dimensions == ("time", "y", "x")
        assert ds.variables["temperature_2m_c"].units == "degree_Celsius"
        assert ds.variables["relative_humidity_2m"].dimensions == ("time", "y", "x")
        assert ds.variables["relative_humidity_2m"].units == "1"
        assert ds.variables["x"].axis == "X"
        assert ds.variables["y"].axis == "Y"
        assert ds.variables["z"].axis == "Z"
        assert ds.variables["latitude"].standard_name == "latitude"
        assert ds.variables["longitude"].standard_name == "longitude"
        assert "latitude longitude" in ds.variables["eastward_wind"].coordinates
        assert "latitude longitude" in ds.variables["precipitation_rate"].coordinates
        np.testing.assert_allclose(ds.variables["U10M"][:], 3.0)
        np.testing.assert_allclose(ds.variables["V10M"][:], 0.0)
        np.testing.assert_allclose(ds.variables["temperature_2m_c"][:], 20.0)
        np.testing.assert_allclose(ds.variables["relative_humidity_2m"][:], 0.5)
        assert ds.variables["time"].standard_name == "time"
        assert ds.variables["time"].units == "seconds since 2026-05-27 00:00:00 UTC"
        assert ds.variables["time"][0] == pytest.approx(0.0)
        assert str(ds.variables["time_datetime"][0]) == "2026-05-27T00:00:00Z"


def test_spritzmet_uses_dem_and_land_cover_for_wind_and_precipitation() -> None:
    lat = np.asarray([[40.0, 40.0], [40.01, 40.01]], dtype=float)
    lon = np.asarray([[14.0, 14.01], [14.0, 14.01]], dtype=float)
    wrf = spritzwrf.WRFWindField(
        latitude=lat,
        longitude=lon,
        u=np.full((2, 2), 4.0),
        v=np.full((2, 2), 1.0),
        source_path=Path("synthetic_wrf.nc"),
        precipitation_rate=np.full((2, 2), 2.0),
    )
    plain = spritzmet.downscale_wrf_to_local_grid(
        wrf,
        center_lat=40.005,
        center_lon=14.005,
        nx=3,
        ny=3,
        dx_m=100.0,
        dy_m=100.0,
    )
    terrain = spritzmet.downscale_wrf_to_local_grid(
        wrf,
        center_lat=40.005,
        center_lon=14.005,
        nx=3,
        ny=3,
        dx_m=100.0,
        dy_m=100.0,
        dem_elevation_m=np.asarray(
            [[0.0, 50.0, 100.0], [25.0, 100.0, 175.0], [50.0, 150.0, 250.0]],
            dtype=float,
        ),
        land_cover=np.asarray([[80, 80, 80], [50, 50, 50], [311, 311, 311]], dtype=float),
    )

    assert terrain.downscaling_metadata is not None
    assert terrain.downscaling_metadata["downscaling_algorithm"] == "clean_room_calmet_style_diagnostic"
    assert terrain.downscaling_metadata["uses_dem_elevation_m"] is True
    assert terrain.downscaling_metadata["uses_land_cover"] is True
    assert terrain.downscaling_metadata["max_precipitation_factor"] > 1.0
    assert not np.allclose(terrain.wind_speed, plain.wind_speed)
    assert not np.allclose(terrain.precipitation_3d, plain.precipitation_3d)
    assert float(terrain.precipitation_3d[0, -1, -1]) > float(plain.precipitation_3d[0, -1, -1])

    with pytest.raises(ValueError, match="dem_elevation_m shape"):
        spritzmet.downscale_wrf_to_local_grid(
            wrf,
            center_lat=40.005,
            center_lon=14.005,
            nx=3,
            ny=3,
            dx_m=100.0,
            dy_m=100.0,
            dem_elevation_m=np.zeros((2, 2)),
            land_cover=np.zeros((3, 3)),
        )


def test_spritzmet_downscales_temperature_and_relative_humidity_with_dem() -> None:
    lat = np.asarray([[40.0, 40.0], [40.01, 40.01]], dtype=float)
    lon = np.asarray([[14.0, 14.01], [14.0, 14.01]], dtype=float)
    wrf = spritzwrf.WRFWindField(
        latitude=lat,
        longitude=lon,
        u=np.full((2, 2), 4.0),
        v=np.zeros((2, 2)),
        source_path=Path("synthetic_wrf.nc"),
        temperature_2m_c=np.full((2, 2), 20.0),
        relative_humidity_2m=np.full((2, 2), 0.50),
    )
    met = spritzmet.downscale_wrf_to_local_grid(
        wrf,
        center_lat=40.005,
        center_lon=14.005,
        nx=2,
        ny=2,
        dx_m=100.0,
        dy_m=100.0,
        dem_elevation_m=np.asarray([[0.0, 100.0], [200.0, 300.0]], dtype=float),
    )

    assert met.temperature_2m_3d is not None
    assert met.relative_humidity_2m_3d is not None
    assert met.downscaling_metadata["temperature_2m_uses_dem_elevation_m"] is True
    assert met.downscaling_metadata["relative_humidity_2m_adjusted_for_temperature_lapse"] is True
    assert float(met.temperature_2m_3d[0, 0, 0]) > float(met.temperature_2m_3d[0, -1, -1])
    assert np.all((met.relative_humidity_2m_3d >= 0.0) & (met.relative_humidity_2m_3d <= 1.0))


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
        module.__file__ = str(tmp_path / "repo" / "usecases" / folder / "demo" / script)
        monkeypatch.setattr(module, "run_workflow", fake_run_workflow)
        assert module.main([]) == 0

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
    plume_met.__file__ = str(
        tmp_path / "repo" / "usecases" / "10_backward_plume_origin" / "demo" / "step_01_prepare_meteorology.py"
    )
    plume_back.__file__ = str(
        tmp_path / "repo" / "usecases" / "10_backward_plume_origin" / "demo" / "step_02_estimate_source.py"
    )
    fire.__file__ = str(
        tmp_path / "repo" / "usecases" / "11_backward_fire_origin" / "demo" / "step_01_estimate_ignition.py"
    )

    assert plume_met.main([]) == 0
    assert plume_back.main([]) == 0
    assert fire.main([]) == 0

    assert ("spritzmet", "meteo.nc", "netcdf") in calls
    assert ("backward", "meteo.nc", "source_likelihood.json", "gaussian") in calls
    assert ("backward", None, "ignition_likelihood.json", "firefront") in calls


def test_usecases_are_not_packaged_as_suite_modules() -> None:
    assert not (Path("src/sprtz/usecases")).exists()

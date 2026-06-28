from __future__ import annotations

import importlib.util
import logging
import sys
from importlib.machinery import SourceFileLoader
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "meteouniparthenope-wrf-download.py"
PLOTTER_SCRIPT = ROOT / "tools" / "plotter.py"


def load_wrf_download_tool():
    loader = SourceFileLoader("meteouniparthenope_wrf_download", str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_plotter_tool():
    loader = SourceFileLoader("sprtz_plotter_tool", str(PLOTTER_SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_wrf_history_url_uses_domain_and_timestamp_path() -> None:
    tool = load_wrf_download_tool()

    url = tool.wrf_history_url(datetime(2026, 5, 27, 6, 30), "d02")

    assert url == (
        "https://data.meteo.uniparthenope.it/files/wrf5/d02/history/2026/05/27/"
        "wrf5_d02_20260527Z0630.nc"
    )


def test_plan_downloads_expands_hourly_duration_under_data_root() -> None:
    tool = load_wrf_download_tool()

    downloads = tool.plan_downloads(
        datetime(2026, 5, 27, 23, 0),
        hours=3,
        domain="d03",
        output_root="data",
    )

    assert [item.timestamp for item in downloads] == [
        datetime(2026, 5, 27, 23, 0),
        datetime(2026, 5, 28, 0, 0),
        datetime(2026, 5, 28, 1, 0),
    ]
    assert downloads[-1].path == Path("data/wrf/d03/wrf5_d03_20260528Z0100.nc")


def test_plan_downloads_rejects_non_positive_hours() -> None:
    tool = load_wrf_download_tool()

    with pytest.raises(ValueError, match="hours"):
        tool.plan_downloads(datetime(2026, 5, 27), hours=0, domain="d01", output_root="data")


def test_validate_domain_rejects_unknown_domain() -> None:
    tool = load_wrf_download_tool()

    with pytest.raises(Exception, match="domain"):
        tool.validate_domain("d04")


def test_run_downloads_rejects_non_positive_workers() -> None:
    tool = load_wrf_download_tool()
    downloads = tool.plan_downloads(
        datetime(2026, 5, 27),
        hours=1,
        domain="d01",
        output_root="data",
    )

    with pytest.raises(ValueError, match="workers"):
        tool.run_downloads(downloads, timeout_s=1.0, force=False, workers=0)


def test_run_downloads_preserves_planned_order(monkeypatch: pytest.MonkeyPatch) -> None:
    tool = load_wrf_download_tool()
    downloads = tool.plan_downloads(
        datetime(2026, 5, 27),
        hours=3,
        domain="d03",
        output_root="data",
    )

    def fake_download(item, *, timeout_s: float, force: bool):
        return item.path

    monkeypatch.setattr(tool, "download_file", fake_download)

    paths = tool.run_downloads(downloads, timeout_s=1.0, force=False, workers=2)

    assert paths == [item.path for item in downloads]


def test_main_uses_data_root_for_dry_run(caplog: pytest.LogCaptureFixture) -> None:
    tool = load_wrf_download_tool()
    caplog.set_level(logging.INFO)

    result = tool.main(
        [
            "20260628Z0000",
            "--hours",
            "1",
            "--domain",
            "d03",
            "--data-root",
            "custom-data",
            "--dry-run",
        ]
    )

    assert result == 0
    assert "custom-data/wrf/d03/wrf5_d03_20260628Z0000.nc" in caplog.text


def test_main_handles_keyboard_interrupt_softly(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = load_wrf_download_tool()
    caplog.set_level(logging.WARNING)

    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(tool, "run_downloads", interrupt)

    result = tool.main(["20260628Z0000", "--hours", "1", "--domain", "d03"])

    assert result == 130
    assert "interrupted; stopping downloads" in caplog.text


def test_plotter_reads_geographic_grid(tmp_path: Path) -> None:
    pytest.importorskip("netCDF4")
    from netCDF4 import Dataset  # type: ignore

    path = tmp_path / "meteo.nc"
    with Dataset(path, "w") as ds:
        ds.createDimension("time", 1)
        ds.createDimension("y", 2)
        ds.createDimension("x", 3)
        lat = ds.createVariable("latitude", "f8", ("y",))
        lon = ds.createVariable("longitude", "f8", ("x",))
        wind = ds.createVariable("eastward_wind", "f8", ("time", "y", "x"))
        north = ds.createVariable("northward_wind", "f8", ("time", "y", "x"))
        wind.units = "m s-1"
        lat[:] = [40.0, 40.1]
        lon[:] = [14.0, 14.1, 14.2]
        wind[0, :, :] = [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]
        north[0, :, :] = [[0.0, 0.0, 0.0], [1.0, 1.0, 0.0]]

    plotter = load_plotter_tool()
    field = plotter.read_map_field(
        path,
        variable_name=None,
        time_index=0,
        level_index=0,
        center_lat=None,
        center_lon=None,
    )

    assert field.name == "eastward_wind"
    assert field.geographic is True
    assert field.values.shape == (2, 3)
    assert field.x[0, 2] == pytest.approx(14.2)
    assert field.y[1, 0] == pytest.approx(40.1)
    assert field.vectors is not None
    assert field.vectors.u[0, 0] == pytest.approx(1.0)
    assert field.vectors.v[1, 2] == pytest.approx(0.0)


def test_plotter_derives_vectors_from_speed_and_direction(tmp_path: Path) -> None:
    pytest.importorskip("netCDF4")
    from netCDF4 import Dataset  # type: ignore

    path = tmp_path / "wind_direction.nc"
    with Dataset(path, "w") as ds:
        ds.createDimension("time", 1)
        ds.createDimension("y", 2)
        ds.createDimension("x", 2)
        ds.createVariable("latitude", "f8", ("y",))[:] = [40.0, 40.1]
        ds.createVariable("longitude", "f8", ("x",))[:] = [14.0, 14.1]
        speed = ds.createVariable("wind_speed", "f8", ("time", "y", "x"))
        direction = ds.createVariable("wind_from_direction", "f8", ("time", "y", "x"))
        speed[:, :, :] = [[[2.0, 2.0], [2.0, 2.0]]]
        direction[:, :, :] = [[[270.0, 270.0], [270.0, 270.0]]]

    plotter = load_plotter_tool()
    field = plotter.read_map_field(
        path,
        variable_name="wind_speed",
        time_index=0,
        level_index=0,
        center_lat=None,
        center_lon=None,
    )

    assert field.vectors is not None
    assert field.vectors.u[0, 0] == pytest.approx(2.0)
    assert field.vectors.v[0, 0] == pytest.approx(0.0)


def test_plotter_uses_time_index_and_utc_label(tmp_path: Path) -> None:
    pytest.importorskip("netCDF4")
    from netCDF4 import Dataset  # type: ignore

    path = tmp_path / "time_series.nc"
    with Dataset(path, "w") as ds:
        ds.createDimension("time", 2)
        ds.createDimension("y", 1)
        ds.createDimension("x", 2)
        ds.createVariable("latitude", "f8", ("y",))[:] = [40.0]
        ds.createVariable("longitude", "f8", ("x",))[:] = [14.0, 14.1]
        time = ds.createVariable("time", "f8", ("time",))
        time.units = "hours since 2026-06-01 00:00:00"
        time[:] = [0.0, 6.0]
        wind = ds.createVariable("wind_speed", "f8", ("time", "y", "x"))
        wind[:, :, :] = [[[1.0, 2.0]], [[3.0, 4.0]]]

    plotter = load_plotter_tool()
    field = plotter.read_map_field(
        path,
        variable_name="wind_speed",
        time_index=1,
        level_index=0,
        center_lat=None,
        center_lon=None,
    )

    assert field.values[0, 0] == pytest.approx(3.0)
    assert field.time_label is not None
    assert "2026-06-01T06:00:00" in field.time_label


def test_plotter_does_not_infer_utc_label_from_wrf_source_filename(tmp_path: Path) -> None:
    pytest.importorskip("netCDF4")
    from netCDF4 import Dataset  # type: ignore

    path = tmp_path / "legacy_local_wind.nc"
    with Dataset(path, "w") as ds:
        ds.createDimension("time", 1)
        ds.createDimension("y", 1)
        ds.createDimension("x", 1)
        ds.source = "data/wrf/wrf5_d03_20260527Z0000.nc"
        ds.createVariable("latitude", "f8", ("y",))[:] = [40.0]
        ds.createVariable("longitude", "f8", ("x",))[:] = [14.0]
        wind = ds.createVariable("wind_speed", "f8", ("time", "y", "x"))
        wind[:, :, :] = [[[1.0]]]

    plotter = load_plotter_tool()
    field = plotter.read_map_field(
        path,
        variable_name="wind_speed",
        time_index=0,
        level_index=0,
        center_lat=None,
        center_lon=None,
    )

    assert field.time_label is None


def test_plotter_rejects_out_of_range_time_index(tmp_path: Path) -> None:
    pytest.importorskip("netCDF4")
    from netCDF4 import Dataset  # type: ignore

    path = tmp_path / "one_time.nc"
    with Dataset(path, "w") as ds:
        ds.createDimension("time", 1)
        ds.createDimension("y", 1)
        ds.createDimension("x", 1)
        ds.createVariable("latitude", "f8", ("y",))[:] = [40.0]
        ds.createVariable("longitude", "f8", ("x",))[:] = [14.0]
        ds.createVariable("time", "f8", ("time",))[:] = [0.0]
        wind = ds.createVariable("wind_speed", "f8", ("time", "y", "x"))
        wind[:, :, :] = [[[1.0]]]

    plotter = load_plotter_tool()

    with pytest.raises(IndexError, match="time index 2"):
        plotter.read_map_field(
            path,
            variable_name="wind_speed",
            time_index=2,
            level_index=0,
            center_lat=None,
            center_lon=None,
        )


def test_plotter_reads_receptor_vector_as_single_row(tmp_path: Path) -> None:
    pytest.importorskip("netCDF4")
    from netCDF4 import Dataset  # type: ignore

    path = tmp_path / "concentration.nc"
    with Dataset(path, "w") as ds:
        ds.createDimension("time", 2)
        ds.createDimension("receptor", 2)
        ds.createVariable("latitude", "f8", ("receptor",))[:] = [40.0, 40.1]
        ds.createVariable("longitude", "f8", ("receptor",))[:] = [14.0, 14.1]
        concentration = ds.createVariable("concentration", "f8", ("time", "receptor"))
        concentration[:, :] = [[1.0, 2.0], [3.0, 4.0]]

    plotter = load_plotter_tool()
    field = plotter.read_map_field(
        path,
        variable_name="concentration",
        time_index=1,
        level_index=0,
        center_lat=None,
        center_lon=None,
    )

    assert field.geographic is True
    assert field.values.shape == (1, 2)
    assert field.values[0, 0] == pytest.approx(3.0)
    assert field.x[0, 1] == pytest.approx(14.1)


def test_plotter_main_reports_missing_variable(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    pytest.importorskip("netCDF4")
    from netCDF4 import Dataset  # type: ignore

    path = tmp_path / "terrain.nc"
    with Dataset(path, "w") as ds:
        ds.createDimension("y", 1)
        ds.createDimension("x", 1)
        ds.createVariable("surface_altitude", "f8", ("y", "x"))[:] = [[10.0]]

    plotter = load_plotter_tool()
    caplog.set_level(logging.ERROR)

    result = plotter.main([str(path), "--variable", "missing", "--output", str(tmp_path / "map.png")])

    assert result == 1
    assert "variable 'missing' is not present" in caplog.text

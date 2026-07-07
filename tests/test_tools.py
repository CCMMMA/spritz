from __future__ import annotations

import importlib.util
import logging
import sys
import types
from io import BytesIO
from importlib.machinery import SourceFileLoader
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "meteouniparthenope-wrf-download.py"
PLOTTER_SCRIPT = ROOT / "tools" / "plotter.py"
PROFILER_SCRIPT = ROOT / "tools" / "profiler.py"
RENDER3D_SCRIPT = ROOT / "tools" / "render3d.py"
COP30_SCRIPT = ROOT / "tools" / "copernicus-cop30-dem-download.py"
LC100_SCRIPT = ROOT / "tools" / "copernicus-lc100-download.py"


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


def load_profiler_tool():
    loader = SourceFileLoader("sprtz_profiler_tool", str(PROFILER_SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_render3d_tool():
    loader = SourceFileLoader("sprtz_render3d_tool", str(RENDER3D_SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_lc100_download_tool():
    loader = SourceFileLoader("copernicus_lc100_download", str(LC100_SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_cop30_download_tool():
    loader = SourceFileLoader("copernicus_cop30_download", str(COP30_SCRIPT))
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
    assert "/history/" in url
    assert "/archive/" not in url


def test_lc100_download_replaces_existing_output_via_temporary_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tool = load_lc100_download_tool()
    output = tmp_path / "landcover" / "lc100.tif"
    output.parent.mkdir()
    output.write_text("old")
    calls: list[list[str]] = []

    def fake_run(command: list[str], check: bool) -> None:
        calls.append(command)
        Path(command[-1]).write_text("new")

    monkeypatch.setattr(tool.shutil, "which", lambda name: "/usr/bin/gdalwarp")
    monkeypatch.setattr(tool.subprocess, "run", fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "copernicus-lc100-download.py",
            "--south",
            "40.0",
            "--north",
            "41.0",
            "--west",
            "14.0",
            "--east",
            "15.0",
            "--output",
            str(output),
        ],
    )

    tool.main()

    assert output.read_text() == "new"
    assert calls
    assert calls[0][-1] != str(output)
    assert calls[0][-1].endswith(".tmp.tif")
    assert not Path(calls[0][-1]).exists()


def test_lc100_download_overwrite_passes_gdal_overwrite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tool = load_lc100_download_tool()
    output = tmp_path / "lc100.tif"
    output.write_text("old")
    calls: list[list[str]] = []

    def fake_run(command: list[str], check: bool) -> None:
        calls.append(command)
        Path(command[-1]).write_text("new")

    monkeypatch.setattr(tool.shutil, "which", lambda name: "/usr/bin/gdalwarp")
    monkeypatch.setattr(tool.subprocess, "run", fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "copernicus-lc100-download.py",
            "--south",
            "40.0",
            "--north",
            "41.0",
            "--west",
            "14.0",
            "--east",
            "15.0",
            "--output",
            str(output),
            "--overwrite",
        ],
    )

    tool.main()

    assert output.read_text() == "new"
    assert calls[0][-1] == str(output)
    assert "-overwrite" in calls[0]


def test_cop30_download_resolves_domain_bbox_with_buffer() -> None:
    tool = load_cop30_download_tool()

    args = types.SimpleNamespace(
        south=None,
        north=None,
        west=None,
        east=None,
        center_lat=40.827,
        center_lon=14.518,
        nx=201,
        ny=201,
        dx=100.0,
        dy=100.0,
        projection="auto-utm",
        buffer_m=1000.0,
    )

    south, north, west, east = tool.resolve_bbox(args)

    assert south < 40.736363
    assert north > 40.917517
    assert west < 14.398597
    assert east > 14.637082


def test_lc100_download_uses_domain_bbox_for_gdalwarp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tool = load_lc100_download_tool()
    output = tmp_path / "lc100.tif"
    calls: list[list[str]] = []

    def fake_run(command: list[str], check: bool) -> None:
        calls.append(command)
        Path(command[-1]).write_text("new")

    monkeypatch.setattr(tool.shutil, "which", lambda name: "/usr/bin/gdalwarp")
    monkeypatch.setattr(tool.subprocess, "run", fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "copernicus-lc100-download.py",
            "--center-lat",
            "40.827",
            "--center-lon",
            "14.518",
            "--nx",
            "201",
            "--ny",
            "201",
            "--dx",
            "100",
            "--dy",
            "100",
            "--buffer-m",
            "1000",
            "--output",
            str(output),
        ],
    )

    tool.main()

    te_index = calls[0].index("-te")
    west, south, east, north = [float(value) for value in calls[0][te_index + 1 : te_index + 5]]
    assert south < 40.736363
    assert north > 40.917517
    assert west < 14.398597
    assert east > 14.637082


def test_plan_downloads_expands_hourly_duration_under_data_root() -> None:
    tool = load_wrf_download_tool()

    downloads = tool.plan_downloads(
        datetime(2026, 5, 27, 23, 0),
        hours=3,
        domain="d03",
        output_root=None,
    )

    assert [item.timestamp for item in downloads] == [
        datetime(2026, 5, 27, 23, 0),
        datetime(2026, 5, 28, 0, 0),
        datetime(2026, 5, 28, 1, 0),
    ]
    assert all("/history/" in item.url and "/archive/" not in item.url for item in downloads)
    assert downloads[-1].path == Path("data/wrf/d03/wrf5_d03_20260528Z0100.nc")


def test_plan_downloads_uses_explicit_data_root_as_destination() -> None:
    tool = load_wrf_download_tool()

    downloads = tool.plan_downloads(
        datetime(2026, 5, 27, 23, 0),
        hours=1,
        domain="d03",
        output_root="data/wrf/d03",
    )

    assert downloads[0].path == Path("data/wrf/d03/wrf5_d03_20260527Z2300.nc")


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
        output_root=None,
    )

    with pytest.raises(ValueError, match="workers"):
        tool.run_downloads(downloads, timeout_s=1.0, force=False, workers=0)


def test_run_downloads_preserves_planned_order(monkeypatch: pytest.MonkeyPatch) -> None:
    tool = load_wrf_download_tool()
    downloads = tool.plan_downloads(
        datetime(2026, 5, 27),
        hours=3,
        domain="d03",
        output_root=None,
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
    assert "custom-data/wrf5_d03_20260628Z0000.nc" in caplog.text


def test_download_file_redownloads_unreadable_existing_netcdf(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    pytest.importorskip("netCDF4")
    tool = load_wrf_download_tool()
    caplog.set_level(logging.WARNING)
    target = tmp_path / "wrf5_d03_20260628Z0000.nc"
    target.write_bytes(b"not a netcdf file")
    item = tool.WRFDownload(
        timestamp=datetime(2026, 6, 28),
        domain="d03",
        url="https://example.test/wrf5_d03_20260628Z0000.nc",
        path=target,
    )

    class FakeResponse(BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            self.close()
            return False

    def fake_urlopen(url: str, timeout: float):
        return FakeResponse(b"replacement")

    monkeypatch.setattr(tool, "urlopen", fake_urlopen)

    assert tool.download_file(item, timeout_s=1.0, force=False) == target
    assert target.read_bytes() == b"replacement"
    assert "not readable NetCDF" in caplog.text


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


def test_plotter_shades_10m_speed_in_knots_with_10m_vectors(tmp_path: Path) -> None:
    pytest.importorskip("netCDF4")
    from netCDF4 import Dataset  # type: ignore

    path = tmp_path / "wind_10m.nc"
    with Dataset(path, "w") as ds:
        ds.createDimension("time", 1)
        ds.createDimension("y", 2)
        ds.createDimension("x", 2)
        ds.createVariable("latitude", "f8", ("y",))[:] = [40.0, 40.1]
        ds.createVariable("longitude", "f8", ("x",))[:] = [14.0, 14.1]
        u10m = ds.createVariable("U10M", "f8", ("time", "y", "x"))
        v10m = ds.createVariable("V10M", "f8", ("time", "y", "x"))
        speed = ds.createVariable("wind_speed_10m", "f8", ("time", "y", "x"))
        u10m.units = "m s-1"
        v10m.units = "m s-1"
        speed.units = "m s-1"
        u10m[:, :, :] = [[[3.0, 3.0], [3.0, 3.0]]]
        v10m[:, :, :] = [[[4.0, 4.0], [4.0, 4.0]]]
        speed[:, :, :] = [[[5.0, 5.0], [5.0, 5.0]]]

    plotter = load_plotter_tool()
    field = plotter.read_map_field(
        path,
        variable_name="wind_speed_10m",
        time_index=0,
        level_index=0,
        center_lat=None,
        center_lon=None,
    )

    np.testing.assert_allclose(field.values, np.full((2, 2), 5.0 * plotter.MPS_TO_KNOTS))
    assert field.label == "Wind speed [kt]"
    assert field.color_levels == tuple(float(level) for level in plotter.WIND_SPEED_KNOT_LEVELS)
    assert field.vectors is not None
    np.testing.assert_allclose(field.vectors.u, np.full((2, 2), 3.0))
    np.testing.assert_allclose(field.vectors.v, np.full((2, 2), 4.0))


def test_plotter_normalizes_wind_vectors_for_quiver() -> None:
    plotter = load_plotter_tool()
    u, v = plotter._unit_vector_components(
        np.asarray([[3.0, 0.0], [5.0, 0.0]], dtype=float),
        np.asarray([[4.0, 0.0], [0.0, -2.0]], dtype=float),
    )

    np.testing.assert_allclose(np.hypot(u, v), np.asarray([[1.0, 0.0], [1.0, 1.0]]))
    np.testing.assert_allclose(u[0, 0], 0.6)
    np.testing.assert_allclose(v[0, 0], 0.8)
    assert np.isfinite(u).all()
    assert np.isfinite(v).all()


def test_plotter_animation_time_indexes_follow_selected_variable(tmp_path: Path) -> None:
    pytest.importorskip("netCDF4")
    from netCDF4 import Dataset  # type: ignore

    path = tmp_path / "plume.nc"
    with Dataset(path, "w") as ds:
        ds.createDimension("time", 3)
        ds.createDimension("field_z", 1)
        ds.createDimension("field_y", 2)
        ds.createDimension("field_x", 2)
        concentration = ds.createVariable("concentration_field", "f8", ("time", "field_z", "field_y", "field_x"))
        concentration[:, :, :, :] = np.zeros((3, 1, 2, 2), dtype=float)

    plotter = load_plotter_tool()

    assert plotter._animation_time_indexes(path, "concentration_field") == [0, 1, 2]


def test_plotter_animation_color_limits_use_all_frames() -> None:
    plotter = load_plotter_tool()
    x = np.asarray([[0.0, 1.0], [0.0, 1.0]])
    y = np.asarray([[0.0, 0.0], [1.0, 1.0]])
    fields = [
        plotter.MapField(
            name="concentration_field",
            values=np.asarray([[0.0, 1.0], [2.0, 3.0]]),
            x=x,
            y=y,
            local_x=None,
            local_y=None,
            geographic=False,
            label="concentration [g m-3]",
            title="Concentration",
        ),
        plotter.MapField(
            name="concentration_field",
            values=np.asarray([[0.0, 4.0], [5.0, 10.0]]),
            x=x,
            y=y,
            local_x=None,
            local_y=None,
            geographic=False,
            label="concentration [g m-3]",
            title="Concentration",
        ),
    ]

    assert plotter._animation_color_limits(fields, log_scale=False) == (0.0, 10.0)
    assert plotter._animation_color_limits(fields, log_scale=True) == (1.0, 10.0)


def test_plotter_animation_passes_fixed_color_limits(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    plotter = load_plotter_tool()
    x = np.asarray([[0.0, 1.0], [0.0, 1.0]])
    y = np.asarray([[0.0, 0.0], [1.0, 1.0]])
    fields = {
        0: plotter.MapField(
            name="concentration_field",
            values=np.asarray([[0.0, 1.0], [2.0, 3.0]]),
            x=x,
            y=y,
            local_x=None,
            local_y=None,
            geographic=False,
            label="concentration [g m-3]",
            title="Concentration",
        ),
        1: plotter.MapField(
            name="concentration_field",
            values=np.asarray([[0.0, 4.0], [5.0, 10.0]]),
            x=x,
            y=y,
            local_x=None,
            local_y=None,
            geographic=False,
            label="concentration [g m-3]",
            title="Concentration",
        ),
    }
    captured_limits: list[tuple[float, float] | None] = []
    captured_warnings: list[bool] = []

    monkeypatch.setattr(plotter, "_animation_time_indexes", lambda *args, **kwargs: [0, 1])
    monkeypatch.setattr(plotter, "read_map_field", lambda *args, time_index, **kwargs: fields[time_index])

    def fake_plot_map(field, output_path, **kwargs):
        captured_limits.append(kwargs["color_limits"])
        captured_warnings.append(kwargs["warn_missing_geographic"])
        Path(output_path).write_bytes(b"PNG")
        return Path(output_path)

    monkeypatch.setattr(plotter, "plot_map", fake_plot_map)
    monkeypatch.setattr(plotter, "_write_gif", lambda frame_paths, output_path, **kwargs: Path(output_path))

    plotter.plot_animation(
        "concentration.nc",
        tmp_path / "plume.gif",
        variable_name="concentration_field",
        level_index=0,
        center_lat=None,
        center_lon=None,
        title=None,
        dpi=100,
        cmap="viridis",
        coastline_source="naturalearth",
        coastline_resolution="10m",
        allow_cartopy_download=False,
        figure_size=(4.0, 3.0),
        log_scale=False,
        vector_overlay=False,
        vector_stride=8,
        vector_density=None,
        vector_scale=None,
        duration_ms=300,
        loop=0,
    )

    assert captured_limits == [(0.0, 10.0), (0.0, 10.0)]
    assert captured_warnings == [False, False]


def test_plotter_main_animates_selected_variable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    plotter = load_plotter_tool()
    output = tmp_path / "plume.gif"
    calls: list[dict[str, object]] = []

    def fake_plot_animation(input_path, output_path, **kwargs):
        calls.append({"input": input_path, "output": output_path, **kwargs})
        Path(output_path).write_bytes(b"GIF89a")
        return Path(output_path)

    monkeypatch.setattr(plotter, "plot_animation", fake_plot_animation)

    result = plotter.main(
        [
            "concentration.nc",
            "--variable",
            "concentration_field",
            "--output",
            str(output),
            "--animate",
            "--frame-duration-ms",
            "125",
            "--gif-loop",
            "2",
        ]
    )

    assert result == 0
    assert output.read_bytes() == b"GIF89a"
    assert calls[0]["variable_name"] == "concentration_field"
    assert calls[0]["duration_ms"] == 125
    assert calls[0]["loop"] == 2


def test_profiler_reads_concentration_profile_data(tmp_path: Path) -> None:
    pytest.importorskip("netCDF4")
    from netCDF4 import Dataset  # type: ignore

    path = tmp_path / "plume.nc"
    with Dataset(path, "w") as ds:
        ds.createDimension("time", 2)
        ds.createDimension("z", 5)
        ds.createDimension("field_z", 3)
        ds.createDimension("field_y", 2)
        ds.createDimension("field_x", 2)
        ds.createVariable("time", "f8", ("time",))[:] = [3600.0, 7200.0]
        ds.createVariable("z", "f8", ("z",))[:] = [100.0, 200.0, 300.0, 400.0, 500.0]
        ds.createVariable("field_z", "f8", ("field_z",))[:] = [1.5, 10.0, 25.0]
        ds.createVariable("field_y", "f8", ("field_y",))[:] = [-50.0, 50.0]
        ds.createVariable("field_x", "f8", ("field_x",))[:] = [-50.0, 50.0]
        ds.createVariable("latitude", "f8", ("field_y",))[:] = [40.0, 40.1]
        ds.createVariable("longitude", "f8", ("field_x",))[:] = [14.0, 14.1]
        ds.createVariable("surface_altitude", "f8", ("field_y", "field_x"))[:, :] = [
            [0.0, 0.0],
            [0.0, 12.0],
        ]
        concentration = ds.createVariable("concentration_field", "f8", ("time", "field_z", "field_y", "field_x"))
        concentration.units = "g m-3"
        concentration.long_name = "gridded mass concentration"
        values = np.zeros((2, 3, 2, 2), dtype=float)
        values[:, :, 1, 1] = [[1.0, 2.0, 3.0], [2.0, 4.0, 6.0]]
        concentration[:, :, :, :] = values

    profiler = load_profiler_tool()
    profile = profiler.read_profile_data(path, variable_name="concentration_field", x_m=40.0, y_m=40.0)

    assert profile.variable_name == "concentration_field"
    assert profile.profiles.shape == (2, 3)
    np.testing.assert_allclose(profile.z_axis, [1.5, 10.0, 25.0])
    np.testing.assert_allclose(profile.profiles[1], [0.0, 0.0, 6.0])
    assert profile.z_reference == "height_above_sea_level"
    assert profile.units == "g m-3"
    assert profile.origin_lat == pytest.approx(40.0)
    assert profile.origin_lon == pytest.approx(14.0)


def test_profiler_emission_label_adds_dem_to_source_z(tmp_path: Path) -> None:
    profiler = load_profiler_tool()
    profile = profiler.ProfileData(
        source_name="concentration.nc",
        variable_name="concentration_field",
        values=np.zeros((1, 1, 1, 1), dtype=float),
        x_axis=np.asarray([0.0], dtype=float),
        y_axis=np.asarray([0.0], dtype=float),
        z_axis=np.asarray([0.0], dtype=float),
        time_axis=np.asarray([0.0], dtype=float),
        time_labels=["t=0"],
        units="g m-3",
        long_name="gridded mass concentration",
        ix=0,
        iy=0,
        terrain_m=np.asarray([[68.0]], dtype=float),
    )
    config = tmp_path / "config.json"
    config.write_text(
        '{"sources": [{"id": "FIRE001", "x": 0.0, "y": 0.0, "z": 0.0, "height_agl_m": 0.0}]}',
        encoding="utf-8",
    )

    points = profiler.read_emission_points(config, profile)

    assert points[0].release_height_asl_m == pytest.approx(68.0)
    assert points[0].release_height_agl_m == pytest.approx(0.0)


def test_profiler_main_animates_selected_profile(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    profiler = load_profiler_tool()
    output = tmp_path / "profiles.gif"
    fake_profile = types.SimpleNamespace(values=np.zeros((2, 1, 1, 1), dtype=float))
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(profiler, "read_profile_data", lambda *args, **kwargs: fake_profile)

    def fake_animation(profile, output_path, **kwargs):
        calls.append({"profile": profile, "output": output_path, **kwargs})
        Path(output_path).write_bytes(b"GIF89a")
        return Path(output_path)

    monkeypatch.setattr(profiler, "plot_profile_animation", fake_animation)

    result = profiler.main(
        [
            "concentration.nc",
            "--variable",
            "concentration_field",
            "--output",
            str(output),
            "--animate",
            "--frame-duration-ms",
            "150",
            "--gif-loop",
            "3",
        ]
    )

    assert result == 0
    assert output.read_bytes() == b"GIF89a"
    assert calls[0]["duration_ms"] == 150
    assert calls[0]["loop"] == 3


def test_render3d_reads_time_varying_volume(tmp_path: Path) -> None:
    pytest.importorskip("netCDF4")
    from netCDF4 import Dataset  # type: ignore

    path = tmp_path / "plume3d.nc"
    with Dataset(path, "w") as ds:
        ds.createDimension("time", 2)
        ds.createDimension("field_z", 3)
        ds.createDimension("field_y", 2)
        ds.createDimension("field_x", 2)
        time = ds.createVariable("time", "f8", ("time",))
        time.units = "seconds"
        time[:] = [0.0, 3600.0]
        ds.createVariable("field_z", "f8", ("field_z",))[:] = [10.0, 40.0, 90.0]
        ds.createVariable("field_y", "f8", ("field_y",))[:] = [-50.0, 50.0]
        ds.createVariable("field_x", "f8", ("field_x",))[:] = [-100.0, 100.0]
        ds.createVariable("latitude", "f8", ("field_y",))[:] = [40.0, 40.1]
        ds.createVariable("longitude", "f8", ("field_x",))[:] = [14.0, 14.2]
        concentration = ds.createVariable("concentration_field", "f8", ("time", "field_z", "field_y", "field_x"))
        concentration.units = "g m-3"
        concentration.long_name = "gridded mass concentration"
        values = np.zeros((2, 3, 2, 2), dtype=float)
        values[1, :, 1, 1] = [1.0, 2.0, 3.0]
        concentration[:, :, :, :] = values

    render3d = load_render3d_tool()
    field = render3d.read_volume_field(path, variable_name="concentration_field", time_index=1)

    assert field.variable_name == "concentration_field"
    assert field.values.shape == (3, 2, 2)
    np.testing.assert_allclose(field.z_axis, [10.0, 40.0, 90.0])
    np.testing.assert_allclose(field.values[:, 1, 1], [1.0, 2.0, 3.0])
    assert field.label == "gridded mass concentration [g m-3]"
    assert field.time_label == "Time: 3600 seconds"
    np.testing.assert_allclose(field.latitude_axis, [40.0, 40.1])
    np.testing.assert_allclose(field.longitude_axis, [14.0, 14.2])


def test_render3d_reads_dem_and_land_cover_terrain(tmp_path: Path) -> None:
    pytest.importorskip("netCDF4")
    from netCDF4 import Dataset  # type: ignore

    path = tmp_path / "geo.nc"
    with Dataset(path, "w") as ds:
        ds.createDimension("y", 2)
        ds.createDimension("x", 3)
        ds.createVariable("x", "f8", ("x",))[:] = [-100.0, 0.0, 100.0]
        ds.createVariable("y", "f8", ("y",))[:] = [-50.0, 50.0]
        ds.createVariable("latitude", "f8", ("y",))[:] = [40.0, 40.1]
        ds.createVariable("longitude", "f8", ("x",))[:] = [14.0, 14.1, 14.2]
        dem = ds.createVariable("surface_altitude", "f8", ("y", "x"))
        dem.units = "m"
        dem[:, :] = [[10.0, 20.0, 30.0], [40.0, 50.0, 60.0]]
        lc = ds.createVariable("land_cover", "i4", ("y", "x"))
        lc[:, :] = [[80, 80, 50], [311, 311, 50]]

    render3d = load_render3d_tool()
    terrain = render3d.read_terrain_field(path)

    assert terrain is not None
    np.testing.assert_allclose(terrain.elevation_m, [[10.0, 20.0, 30.0], [40.0, 50.0, 60.0]])
    np.testing.assert_allclose(terrain.x_axis, [-100.0, 0.0, 100.0])
    np.testing.assert_allclose(terrain.latitude_axis, [40.0, 40.1])
    np.testing.assert_allclose(terrain.longitude_axis, [14.0, 14.1, 14.2])
    np.testing.assert_allclose(terrain.y_axis, [-50.0, 50.0])
    np.testing.assert_allclose(terrain.land_cover, [[80, 80, 50], [311, 311, 50]])


def test_render3d_emission_label_adds_dem_to_source_z(tmp_path: Path) -> None:
    render3d = load_render3d_tool()
    terrain = render3d.TerrainField(
        elevation_m=np.asarray([[68.0]], dtype=float),
        x_axis=np.asarray([0.0], dtype=float),
        y_axis=np.asarray([0.0], dtype=float),
    )
    config = tmp_path / "config.json"
    config.write_text(
        '{"sources": [{"id": "FIRE001", "x": 0.0, "y": 0.0, "z": 0.0, "height_agl_m": 0.0}]}',
        encoding="utf-8",
    )

    points = render3d.read_emission_points(config, terrain)

    assert points[0].release_height_asl_m == pytest.approx(68.0)
    assert points[0].release_height_agl_m == pytest.approx(0.0)


def test_render3d_terrain_colormap_uses_blue_only_for_sea() -> None:
    pytest.importorskip("matplotlib")
    render3d = load_render3d_tool()
    plt = render3d._load_matplotlib()
    elevation = np.asarray([[-3.0, 0.0, 1.0, 25.0]], dtype=float)

    colors = render3d._terrain_facecolors(elevation, plt)

    np.testing.assert_allclose(colors[0, 0, :3], colors[0, 1, :3])
    assert not np.allclose(colors[0, 1, :3], colors[0, 2, :3])
    assert not np.allclose(colors[0, 1, :3], colors[0, 3, :3])


def test_render3d_detects_vertical_reference_and_model_top(tmp_path: Path) -> None:
    pytest.importorskip("netCDF4")
    from netCDF4 import Dataset  # type: ignore

    agl_path = tmp_path / "concentration_agl.nc"
    with Dataset(agl_path, "w") as ds:
        ds.createDimension("time", 1)
        ds.createDimension("field_z", 2)
        ds.createDimension("field_y", 2)
        ds.createDimension("field_x", 2)
        z = ds.createVariable("field_z", "f8", ("field_z",))
        z.units = "m"
        z.long_name = "model grid height above local ground"
        z[:] = [10.0, 200.0]
        concentration = ds.createVariable("concentration_field", "f8", ("time", "field_z", "field_y", "field_x"))
        concentration[:, :, :, :] = np.zeros((1, 2, 2, 2), dtype=float)

    render3d = load_render3d_tool()
    agl = render3d.read_volume_field(agl_path, variable_name="concentration_field", time_index=0)
    z_limits = render3d._vertical_limits(agl, np.asarray([[100.0, 125.0], [150.0, 175.0]], dtype=float))

    assert agl.z_reference == "height_above_ground"
    assert z_limits[0] < 100.0
    assert z_limits[1] > 375.0


def test_render3d_sea_level_heights_mask_below_dem(tmp_path: Path) -> None:
    pytest.importorskip("netCDF4")
    from netCDF4 import Dataset  # type: ignore

    path = tmp_path / "wind_asl.nc"
    with Dataset(path, "w") as ds:
        ds.createDimension("time", 1)
        ds.createDimension("z", 2)
        ds.createDimension("y", 1)
        ds.createDimension("x", 1)
        z = ds.createVariable("z", "f8", ("z",))
        z.units = "m"
        z.long_name = "height above mean sea level"
        z[:] = [50.0, 250.0]
        speed = ds.createVariable("wind_speed", "f8", ("time", "z", "y", "x"))
        speed[:, :, :, :] = np.ones((1, 2, 1, 1), dtype=float)

    render3d = load_render3d_tool()
    field = render3d.read_volume_field(path, variable_name="wind_speed", time_index=0)
    terrain = np.asarray([[[100.0]], [[100.0]]], dtype=float)
    altitude = render3d._plume_altitude(field, field.z_axis[:, np.newaxis, np.newaxis], terrain)

    assert field.z_reference == "height_above_sea_level"
    assert np.isnan(altitude[0, 0, 0])
    assert altitude[1, 0, 0] == 250.0


def test_render3d_ground_level_heights_are_added_to_dem(tmp_path: Path) -> None:
    pytest.importorskip("netCDF4")
    from netCDF4 import Dataset  # type: ignore

    path = tmp_path / "concentration_agl.nc"
    with Dataset(path, "w") as ds:
        ds.spritz_concentration_field_z_reference = "height_above_ground"
        ds.createDimension("time", 1)
        ds.createDimension("field_z", 2)
        ds.createDimension("field_y", 1)
        ds.createDimension("field_x", 1)
        z = ds.createVariable("field_z", "f8", ("field_z",))
        z.units = "m"
        z.long_name = "model grid height above local ground"
        z[:] = [2.5, 50.0]
        concentration = ds.createVariable("concentration_field", "f8", ("time", "field_z", "field_y", "field_x"))
        concentration[:, :, :, :] = np.ones((1, 2, 1, 1), dtype=float)

    render3d = load_render3d_tool()
    field = render3d.read_volume_field(path, variable_name="concentration_field", time_index=0)
    terrain = np.asarray([[[375.0]], [[375.0]]], dtype=float)
    altitude = render3d._plume_altitude(field, field.z_axis[:, np.newaxis, np.newaxis], terrain)

    assert field.z_reference == "height_above_ground"
    np.testing.assert_allclose(altitude[:, 0, 0], [377.5, 425.0])


def test_render3d_uses_concentration_field_asl_reference(tmp_path: Path) -> None:
    pytest.importorskip("netCDF4")
    from netCDF4 import Dataset  # type: ignore

    path = tmp_path / "concentration_asl.nc"
    with Dataset(path, "w") as ds:
        ds.spritz_concentration_field_z_reference = "height_above_sea_level"
        ds.createDimension("time", 1)
        ds.createDimension("field_z", 3)
        ds.createDimension("field_y", 1)
        ds.createDimension("field_x", 1)
        z = ds.createVariable("field_z", "f8", ("field_z",))
        z.units = "m"
        z.long_name = "model grid altitude above mean sea level"
        z[:] = [50.0, 150.0, 300.0]
        concentration = ds.createVariable("concentration_field", "f8", ("time", "field_z", "field_y", "field_x"))
        concentration[:, :, :, :] = np.ones((1, 3, 1, 1), dtype=float)

    render3d = load_render3d_tool()
    field = render3d.read_volume_field(path, variable_name="concentration_field", time_index=0)
    z_limits = render3d._vertical_limits(field, np.asarray([[125.0]], dtype=float))

    assert field.z_reference == "height_above_sea_level"
    np.testing.assert_allclose(render3d._vertical_ticks(field, z_limits), [50.0, 150.0, 300.0])


def test_render3d_vertical_exaggeration_scales_display_only() -> None:
    render3d = load_render3d_tool()

    scaled = render3d._scale_z(np.asarray([100.0, 150.0, 200.0]), 100.0, 3.0)

    np.testing.assert_allclose(scaled, [100.0, 250.0, 400.0])
    assert render3d._display_z_limits((100.0, 200.0), 2.0) == (100.0, 300.0)
    assert render3d._ground_clearance((100.0, 200.0)) >= 0.5


def test_render3d_resamples_larger_terrain_to_volume_grid() -> None:
    render3d = load_render3d_tool()
    terrain = render3d.TerrainField(
        elevation_m=np.asarray(
            [
                [0.0, 10.0, 20.0, 30.0, 40.0],
                [100.0, 110.0, 120.0, 130.0, 140.0],
                [200.0, 210.0, 220.0, 230.0, 240.0],
                [300.0, 310.0, 320.0, 330.0, 340.0],
                [400.0, 410.0, 420.0, 430.0, 440.0],
            ],
            dtype=float,
        ),
        x_axis=np.asarray([-2.0, -1.0, 0.0, 1.0, 2.0]),
        y_axis=np.asarray([-2.0, -1.0, 0.0, 1.0, 2.0]),
        land_cover=np.asarray(
            [
                [20, 20, 30, 30, 30],
                [20, 20, 30, 30, 30],
                [40, 40, 50, 50, 50],
                [40, 40, 50, 50, 50],
                [40, 40, 50, 50, 50],
            ],
            dtype=float,
        ),
    )
    field = render3d.VolumeField(
        "concentration.nc",
        "concentration_field",
        np.zeros((1, 3, 3), dtype=float),
        np.asarray([-1.0, 0.0, 1.0]),
        np.asarray([-1.0, 0.0, 1.0]),
        np.asarray([2.5]),
        "g m-3",
        "gridded mass concentration",
    )

    resampled = render3d._terrain_like_volume(terrain, field)

    assert resampled.elevation_m.shape == (3, 3)
    np.testing.assert_allclose(
        resampled.elevation_m,
        [[110.0, 120.0, 130.0], [210.0, 220.0, 230.0], [310.0, 320.0, 330.0]],
    )
    np.testing.assert_allclose(resampled.land_cover, [[20, 30, 30], [40, 50, 50], [40, 50, 50]])


def test_render3d_animation_time_indexes_follow_selected_variable(tmp_path: Path) -> None:
    pytest.importorskip("netCDF4")
    from netCDF4 import Dataset  # type: ignore

    path = tmp_path / "plume3d.nc"
    with Dataset(path, "w") as ds:
        ds.createDimension("time", 4)
        ds.createDimension("z", 2)
        ds.createDimension("y", 1)
        ds.createDimension("x", 1)
        concentration = ds.createVariable("concentration_field", "f8", ("time", "z", "y", "x"))
        concentration[:, :, :, :] = np.zeros((4, 2, 1, 1), dtype=float)

    render3d = load_render3d_tool()

    assert render3d._animation_time_indexes(path, "concentration_field") == [0, 1, 2, 3]


def test_render3d_main_animates_selected_volume(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    render3d = load_render3d_tool()
    output = tmp_path / "plume3d.gif"
    calls: list[dict[str, object]] = []

    def fake_plot_animation(input_path, output_path, **kwargs):
        calls.append({"input": input_path, "output": output_path, **kwargs})
        Path(output_path).write_bytes(b"GIF89a")
        return Path(output_path)

    monkeypatch.setattr(render3d, "plot_animation", fake_plot_animation)

    result = render3d.main(
        [
            "concentration.nc",
            "--variable",
            "concentration_field",
            "--output",
            str(output),
            "--animate",
            "--mode",
            "voxel",
            "--frame-duration-ms",
            "175",
            "--gif-loop",
            "2",
            "--vertical-exaggeration",
            "2",
            "--ground-color",
            "land-cover",
            "--view",
            "northeast",
        ]
    )

    assert result == 0
    assert output.read_bytes() == b"GIF89a"
    assert calls[0]["variable_name"] == "concentration_field"
    assert calls[0]["mode"] == "voxel"
    assert calls[0]["duration_ms"] == 175
    assert calls[0]["loop"] == 2
    assert calls[0]["vertical_exaggeration"] == 2.0
    assert calls[0]["ground_color"] == "land-cover"
    assert calls[0]["elevation"] == 28.0
    assert calls[0]["azimuth"] == 45.0


def test_render3d_camera_view_presets_can_be_overridden() -> None:
    render3d = load_render3d_tool()

    assert render3d._camera_angles(None, None, None) == (28.0, -55.0)
    assert render3d._camera_angles("top", None, None) == (90.0, -90.0)
    assert render3d._camera_angles("north", 35.0, None) == (35.0, 90.0)
    assert render3d._camera_angles("east", None, -30.0) == (28.0, -30.0)


def test_render3d_rejects_vertical_exaggeration_below_one(tmp_path: Path) -> None:
    render3d = load_render3d_tool()

    result = render3d.main(["concentration.nc", "--output", str(tmp_path / "out.png"), "--vertical-exaggeration", "0.5"])

    assert result == 1


def test_plotter_converts_wind_speed_to_knots_and_uses_palette(tmp_path: Path) -> None:
    pytest.importorskip("netCDF4")
    from netCDF4 import Dataset  # type: ignore

    path = tmp_path / "wind_speed_knots.nc"
    with Dataset(path, "w") as ds:
        ds.createDimension("time", 1)
        ds.createDimension("z", 2)
        ds.createDimension("y", 1)
        ds.createDimension("x", 2)
        height = ds.createVariable("z", "f8", ("z",))
        height.units = "m"
        height[:] = [10.0, 25.0]
        ds.createVariable("latitude", "f8", ("y",))[:] = [40.0]
        ds.createVariable("longitude", "f8", ("x",))[:] = [14.0, 14.1]
        speed = ds.createVariable("wind_speed", "f8", ("time", "z", "y", "x"))
        speed.units = "m s-1"
        speed.long_name = "Wind speed"
        speed[:, :, :, :] = [[[[1.0, 2.0]], [[3.0, 4.0]]]]

    plotter = load_plotter_tool()
    field = plotter.read_map_field(
        path,
        variable_name="wind_speed",
        time_index=0,
        level_index=1,
        center_lat=None,
        center_lon=None,
    )

    np.testing.assert_allclose(field.values, np.asarray([[3.0, 4.0]]) * plotter.MPS_TO_KNOTS)
    assert field.label == "Wind speed [kt]"
    assert field.level_label == "Level index: 1 (25 m)"
    assert field.color_levels == tuple(float(level) for level in plotter.WIND_SPEED_KNOT_LEVELS)
    assert field.color_palette == plotter.WIND_SPEED_KNOT_COLORS


def test_plotter_reads_level_meters_from_global_metadata(tmp_path: Path) -> None:
    pytest.importorskip("netCDF4")
    from netCDF4 import Dataset  # type: ignore

    path = tmp_path / "wind_speed_level_metadata.nc"
    with Dataset(path, "w") as ds:
        ds.createDimension("time", 1)
        ds.createDimension("z", 2)
        ds.createDimension("y", 1)
        ds.createDimension("x", 1)
        ds.spritzmet_level_meters = [10.0, 80.0]
        z = ds.createVariable("z", "f8", ("z",))
        z.units = "1"
        z.long_name = "vertical level index"
        z[:] = [0.0, 1.0]
        ds.createVariable("latitude", "f8", ("y",))[:] = [40.0]
        ds.createVariable("longitude", "f8", ("x",))[:] = [14.0]
        speed = ds.createVariable("wind_speed", "f8", ("time", "z", "y", "x"))
        speed.units = "m s-1"
        speed[:, :, :, :] = [[[[1.0]], [[2.0]]]]

    plotter = load_plotter_tool()
    field = plotter.read_map_field(
        path,
        variable_name="wind_speed",
        time_index=0,
        level_index=1,
        center_lat=None,
        center_lon=None,
    )

    assert field.level_label == "Level index: 1 (80 m)"


def test_plotter_reads_4d_wind_and_3d_precipitation(tmp_path: Path) -> None:
    pytest.importorskip("netCDF4")
    from netCDF4 import Dataset  # type: ignore

    path = tmp_path / "wind_4d_precip_3d.nc"
    with Dataset(path, "w") as ds:
        ds.createDimension("time", 2)
        ds.createDimension("z", 2)
        ds.createDimension("y", 2)
        ds.createDimension("x", 2)
        ds.createVariable("latitude", "f8", ("y",))[:] = [40.0, 40.1]
        ds.createVariable("longitude", "f8", ("x",))[:] = [14.0, 14.1]
        wind = ds.createVariable("eastward_wind", "f8", ("time", "z", "y", "x"))
        north = ds.createVariable("northward_wind", "f8", ("time", "z", "y", "x"))
        precip = ds.createVariable("precipitation_rate", "f8", ("time", "y", "x"))
        wind[:, :, :, :] = np.asarray(
            [
                [[[1.0, 1.0], [1.0, 1.0]], [[2.0, 2.0], [2.0, 2.0]]],
                [[[3.0, 3.0], [3.0, 3.0]], [[4.0, 4.0], [4.0, 4.0]]],
            ]
        )
        north[:, :, :, :] = 0.0
        precip[:, :, :] = [[[0.5, 0.5], [0.5, 0.5]], [[1.5, 1.5], [1.5, 1.5]]]

    plotter = load_plotter_tool()
    wind_field = plotter.read_map_field(
        path,
        variable_name="eastward_wind",
        time_index=1,
        level_index=1,
        center_lat=None,
        center_lon=None,
    )
    precip_field = plotter.read_map_field(
        path,
        variable_name="precipitation_rate",
        time_index=1,
        level_index=0,
        center_lat=None,
        center_lon=None,
    )

    np.testing.assert_allclose(wind_field.values, np.full((2, 2), 4.0))
    assert wind_field.vectors is not None
    np.testing.assert_allclose(wind_field.vectors.u, np.full((2, 2), 4.0))
    np.testing.assert_allclose(precip_field.values, np.full((2, 2), 1.5))


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

    assert field.values[0, 0] == pytest.approx(3.0 * plotter.MPS_TO_KNOTS)
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


def test_plotter_parser_accepts_gshhs_coastline_source() -> None:
    plotter = load_plotter_tool()

    args = plotter.build_parser().parse_args(
        [
            "input.nc",
            "--output",
            "map.png",
            "--coastline-source",
            "gshhs",
            "--coastline-resolution",
            "10m",
        ]
    )

    assert args.coastline_source == "gshhs"
    assert args.coastline_resolution == "10m"


def test_add_cartopy_coastlines_uses_gshhs_feature(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plotter = load_plotter_tool()
    gshhs_path = tmp_path / "shapefiles" / "gshhs" / "f" / "GSHHS_f_L1.shp"
    gshhs_path.parent.mkdir(parents=True)
    gshhs_path.touch()
    added: list[tuple[object, int]] = []
    created: list[dict[str, object]] = []

    class FakeAxes:
        def set_extent(self, extent, *, crs):
            self.extent = extent

        def add_feature(self, feature, zorder):
            added.append((feature, zorder))

    class FakePlateCarree:
        pass

    class FakeReader:
        def __init__(self, path):
            self.path = path

        def geometries(self):
            return ("geometry",)

    def fake_gshhs(**kwargs):
        created.append({"gshhs": kwargs})
        return str(gshhs_path)

    def fake_shapely_feature(*args, **kwargs):
        created.append(kwargs)
        return ("gshhs", args, kwargs)

    cartopy = types.ModuleType("cartopy")
    cartopy.config = {"pre_existing_data_dir": str(tmp_path), "data_dir": ""}
    ccrs = types.ModuleType("cartopy.crs")
    ccrs.PlateCarree = FakePlateCarree
    cfeature = types.ModuleType("cartopy.feature")
    cfeature.ShapelyFeature = fake_shapely_feature
    cartopy_io = types.ModuleType("cartopy.io")
    shpreader = types.ModuleType("cartopy.io.shapereader")
    shpreader.gshhs = fake_gshhs
    shpreader.Reader = FakeReader
    monkeypatch.setitem(sys.modules, "cartopy", cartopy)
    monkeypatch.setitem(sys.modules, "cartopy.crs", ccrs)
    monkeypatch.setitem(sys.modules, "cartopy.feature", cfeature)
    monkeypatch.setitem(sys.modules, "cartopy.io", cartopy_io)
    monkeypatch.setitem(sys.modules, "cartopy.io.shapereader", shpreader)

    plotter._add_cartopy_coastlines(
        FakeAxes(),
        extent=(14.0, 14.1, 40.0, 40.1),
        source="gshhs",
        resolution="10m",
        allow_download=False,
    )

    assert created == [
        {"gshhs": {"scale": "f", "level": 1}},
        {
            "edgecolor": "0.08",
            "facecolor": "none",
            "linewidth": 0.75,
        }
    ]
    assert len(added) == 1
    feature, zorder = added[0]
    assert zorder == 5
    assert feature[0] == "gshhs"
    assert feature[1][0] == ("geometry",)
    assert isinstance(feature[1][1], FakePlateCarree)
    assert feature[2] == created[1]


def test_add_cartopy_coastlines_falls_back_to_soest_gshhs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plotter = load_plotter_tool()
    gshhs_path = tmp_path / "shapefiles" / "gshhs" / "f" / "GSHHS_f_L1.shp"
    added: list[tuple[object, int]] = []
    downloads: list[tuple[str, int]] = []

    class FakeAxes:
        def set_extent(self, extent, *, crs):
            self.extent = extent

        def add_feature(self, feature, zorder):
            added.append((feature, zorder))

    class FakePlateCarree:
        pass

    class FakeReader:
        def __init__(self, path):
            self.path = path

        def geometries(self):
            return ("geometry",)

    def broken_gshhs(**kwargs):
        raise OSError("missing upstream archive")

    def fake_download(config, scale, level):
        downloads.append((scale, level))
        gshhs_path.parent.mkdir(parents=True)
        gshhs_path.touch()
        return gshhs_path

    def fake_shapely_feature(*args, **kwargs):
        return ("gshhs", args, kwargs)

    cartopy = types.ModuleType("cartopy")
    cartopy.config = {"pre_existing_data_dir": "", "data_dir": str(tmp_path)}
    ccrs = types.ModuleType("cartopy.crs")
    ccrs.PlateCarree = FakePlateCarree
    cfeature = types.ModuleType("cartopy.feature")
    cfeature.ShapelyFeature = fake_shapely_feature
    cartopy_io = types.ModuleType("cartopy.io")
    shpreader = types.ModuleType("cartopy.io.shapereader")
    shpreader.gshhs = broken_gshhs
    shpreader.Reader = FakeReader
    monkeypatch.setitem(sys.modules, "cartopy", cartopy)
    monkeypatch.setitem(sys.modules, "cartopy.crs", ccrs)
    monkeypatch.setitem(sys.modules, "cartopy.feature", cfeature)
    monkeypatch.setitem(sys.modules, "cartopy.io", cartopy_io)
    monkeypatch.setitem(sys.modules, "cartopy.io.shapereader", shpreader)
    monkeypatch.setattr(plotter, "_download_soest_gshhs", fake_download)

    plotter._add_cartopy_coastlines(
        FakeAxes(),
        extent=(14.0, 14.1, 40.0, 40.1),
        source="gshhs",
        resolution="10m",
        allow_download=True,
    )

    assert downloads == [("f", 1)]
    assert len(added) == 1

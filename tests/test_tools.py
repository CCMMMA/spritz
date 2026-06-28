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


def load_wrf_download_tool():
    loader = SourceFileLoader("meteouniparthenope_wrf_download", str(SCRIPT))
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

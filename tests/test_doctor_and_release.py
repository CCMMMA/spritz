from __future__ import annotations

import subprocess
import sys

from pypuff.doctor import run_diagnostics


def test_doctor_report_is_deterministic_and_ok_for_required_core_dependencies() -> None:
    report = run_diagnostics()
    assert report["component"] == "pypuff.doctor"
    assert report["ok"] is True
    names = {check["name"] for check in report["checks"]}
    assert {"python_version", "numpy", "pyproj", "typed_package"}.issubset(names)


def test_doctor_cli_json() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "pypuff", "doctor", "--json"],
        check=True,
        text=True,
        capture_output=True,
    )
    assert '"component": "pypuff.doctor"' in completed.stdout


def test_release_check_script_passes_clean_tree() -> None:
    subprocess.run(
        [
            "bash",
            "-lc",
            "find . -type d -name __pycache__ -prune -exec rm -rf {} + && "
            "find . -type f \\( -name \"*.pyc\" -o -name \"*.pyo\" \\) -delete",
        ],
        check=True,
    )
    completed = subprocess.run(
        [sys.executable, "scripts/check_release.py"],
        check=True,
        text=True,
        capture_output=True,
    )
    assert "release check passed" in completed.stdout

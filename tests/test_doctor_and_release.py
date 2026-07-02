from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from sprtz.doctor import run_diagnostics
from scripts.check_release import iter_release_paths

ROOT = Path(__file__).resolve().parents[1]


def _repo_pythonpath_env() -> dict[str, str]:
    env = os.environ.copy()
    src = str(ROOT / "src")
    env["PYTHONPATH"] = (
        src if not env.get("PYTHONPATH") else os.pathsep.join((src, env["PYTHONPATH"]))
    )
    return env


def test_doctor_report_is_deterministic_and_ok_for_required_core_dependencies() -> None:
    report = run_diagnostics()
    assert report["component"] == "sprtz.doctor"
    assert report["ok"] is True
    names = {check["name"] for check in report["checks"]}
    assert {"python_version", "numpy", "pyproj", "typed_package"}.issubset(names)


def test_doctor_cli_json() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "sprtz", "doctor", "--json"],
        check=True,
        text=True,
        capture_output=True,
        env=_repo_pythonpath_env(),
    )
    assert '"component": "sprtz.doctor"' in completed.stdout


def test_release_check_script_passes_clean_tree() -> None:
    for directory in (".pytest_cache", ".mypy_cache", ".ruff_cache", "build", "dist"):
        shutil.rmtree(ROOT / directory, ignore_errors=True)
    for cache_dir in [
        path for path in iter_release_paths(ROOT) if path.is_dir() and path.name == "__pycache__"
    ]:
        shutil.rmtree(cache_dir, ignore_errors=True)
    for bytecode_file in [
        path for path in iter_release_paths(ROOT) if path.suffix in {".pyc", ".pyo"}
    ]:
        bytecode_file.unlink(missing_ok=True)

    completed = subprocess.run(
        [sys.executable, "scripts/check_release.py"],
        check=True,
        text=True,
        capture_output=True,
    )
    assert "release check passed" in completed.stdout
    assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{4} \+\d+ms release check passed", completed.stdout)

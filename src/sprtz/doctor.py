from __future__ import annotations

"""Production readiness diagnostics for Sprtz installations."""

import importlib.util
import json
import logging
import platform
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sprtz import __version__
from sprtz.logging import configure_logging

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "ok": self.ok, "detail": self.detail}


def _has_module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def run_diagnostics(*, require_netcdf: bool = False, require_viz: bool = False, require_mpi: bool = False) -> dict[str, Any]:
    """Return a deterministic production-readiness diagnostic report.

    The checks are intentionally local-only: no internet access, no writes outside
    the current process, and no attempt to contact MPI launchers.  This makes the
    command safe for CI, containers, login nodes, and operational notebooks.
    """
    checks: list[Check] = []
    py_ok = sys.version_info >= (3, 10)
    checks.append(Check("python_version", py_ok, platform.python_version()))

    checks.append(Check("numpy", _has_module("numpy"), "required numerical dependency"))
    checks.append(Check("pyproj", _has_module("pyproj"), "required projection dependency"))

    netcdf_ok = _has_module("netCDF4")
    checks.append(Check("netcdf4", netcdf_ok or not require_netcdf, "optional NetCDF-CF backend"))

    viz_ok = _has_module("matplotlib")
    checks.append(Check("matplotlib", viz_ok or not require_viz, "optional publishing visualization backend"))

    mpi_ok = _has_module("mpi4py")
    checks.append(Check("mpi4py", mpi_ok or not require_mpi, "optional MPI backend"))

    package_root = Path(__file__).resolve().parent
    checks.append(Check("package_import", package_root.exists(), str(package_root)))
    checks.append(Check("typed_package", (package_root / "py.typed").exists(), "PEP 561 marker"))

    ok = all(c.ok for c in checks)
    return {
        "component": "sprtz.doctor",
        "version": __version__,
        "platform": platform.platform(),
        "executable": sys.executable,
        "ok": ok,
        "checks": [c.as_dict() for c in checks],
    }


def format_report(report: dict[str, Any]) -> str:
    lines = [f"Sprtz {report['version']} production diagnostics", f"overall: {'OK' if report['ok'] else 'FAILED'}"]
    for check in report["checks"]:
        mark = "OK" if check["ok"] else "FAIL"
        lines.append(f"- {mark} {check['name']}: {check['detail']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run local Sprtz production-readiness diagnostics")
    parser.add_argument("--require-netcdf", action="store_true", help="fail if netCDF4 is unavailable")
    parser.add_argument("--require-viz", action="store_true", help="fail if matplotlib is unavailable")
    parser.add_argument("--require-mpi", action="store_true", help="fail if mpi4py is unavailable")
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    args = parser.parse_args(argv)

    report = run_diagnostics(
        require_netcdf=args.require_netcdf,
        require_viz=args.require_viz,
        require_mpi=args.require_mpi,
    )
    configure_logging(False)
    if args.json:
        LOGGER.info("%s", json.dumps(report, indent=2, sort_keys=True))
    else:
        LOGGER.info("%s", format_report(report))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

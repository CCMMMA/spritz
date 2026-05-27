from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGGER = logging.getLogger(__name__)
REQUIRED = [
    "README.md",
    "requirements.txt",
    "AGENTS.md",
    "LICENSE",
    "NOTICE",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "docs/production_readiness.md",
    "docs/getting_started.md",
    "docs/parallelization.md",
    "docs/validation.md",
    "docs/usecases.md",
    "docs/pywrf_pymet.md",
    "docs/pyterrel.md",
    "usecases/README.md",
    "usecases/01_high_resolution_wind_field/README.md",
    "usecases/02_wildfire_arson_effects/README.md",
    "usecases/03_satellite_ai_evaluation/README.md",
    "src/pypuff/py.typed",
    "src/pypuff/models/pyterrel.py",
]


def main() -> int:
    errors: list[str] = []
    for item in REQUIRED:
        if not (ROOT / item).exists():
            errors.append(f"missing required release file: {item}")
    for path in ROOT.rglob("*"):
        rel = path.relative_to(ROOT)
        if "__pycache__" in rel.parts:
            errors.append(f"release tree contains __pycache__: {rel}")
        if path.suffix in {".pyc", ".pyo"}:
            errors.append(f"release tree contains bytecode: {rel}")

        if rel.parts and rel.parts[0] in {"build", "dist", ".pytest_cache", ".mypy_cache", ".ruff_cache"}:
            errors.append(f"release tree contains generated artifact/cache: {rel}")
        if path.suffix == ".nc":
            errors.append(f"release tree contains NetCDF data product: {rel}")
        if rel.parts[:2] == ("src", "pypuff") and len(rel.parts) > 2 and rel.parts[2] == "usecases":
            errors.append(f"use cases must not be packaged as suite modules: {rel}")
    if errors:
        logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr, force=True)
        LOGGER.error("release check failed")
        for error in errors:
            LOGGER.error("- %s", error)
        return 1
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout, force=True)
    LOGGER.info("release check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "README.md",
    "AGENTS.md",
    "LICENSE",
    "NOTICE",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "docs/production_readiness.md",
    "docs/validation.md",
    "docs/usecases.md",
    "docs/pywrf_pymet.md",
    "usecases/README.md",
    "usecases/01_high_resolution_wind_field/README.md",
    "usecases/02_wildfire_arson_effects/README.md",
    "usecases/03_satellite_ai_evaluation/README.md",
    "src/pypuff/py.typed",
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
    if errors:
        print("release check failed", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("release check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

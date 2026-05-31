from __future__ import annotations

from collections.abc import Iterator
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGGER = logging.getLogger(__name__)
LOCAL_ONLY_DIRS = {
    ".git",
    ".hg",
    ".idea",
    ".nox",
    ".svn",
    ".tox",
    ".venv",
    ".vscode",
    "__pypackages__",
    "env",
    "venv",
}
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
    "docs/spritzwrf_spritzmet.md",
    "docs/terrain.md",
    "usecases/README.md",
    "usecases/01_high_resolution_wind_field/README.md",
    "usecases/02_wildfire_arson_effects/README.md",
    "usecases/03_satellite_ai_evaluation/README.md",
    "src/sprtz/py.typed",
    "src/sprtz/models/terrain.py",
]


def iter_release_paths(root: Path) -> Iterator[Path]:
    pending = [root]
    while pending:
        current = pending.pop()
        for path in sorted(current.iterdir()):
            if path.is_dir():
                if path.name in LOCAL_ONLY_DIRS:
                    continue
                pending.append(path)
            yield path


def main() -> int:
    errors: list[str] = []
    for item in REQUIRED:
        if not (ROOT / item).exists():
            errors.append(f"missing required release file: {item}")
    for path in iter_release_paths(ROOT):
        rel = path.relative_to(ROOT)
        if "__pycache__" in rel.parts:
            errors.append(f"release tree contains __pycache__: {rel}")
        if path.suffix in {".pyc", ".pyo"}:
            errors.append(f"release tree contains bytecode: {rel}")

        if rel.parts and rel.parts[0] in {"build", "dist", ".pytest_cache", ".mypy_cache", ".ruff_cache"}:
            errors.append(f"release tree contains generated artifact/cache: {rel}")
        if path.suffix == ".nc":
            errors.append(f"release tree contains NetCDF data product: {rel}")
        if rel.parts[:2] == ("src", "sprtz") and len(rel.parts) > 2 and rel.parts[2] == "usecases":
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

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

from sprtz.exceptions import DataFormatError
from sprtz.io.jsonio import write_json


def read_ascii_grid(path: str | Path) -> np.ndarray:
    p = Path(path)
    if not p.exists():
        raise DataFormatError(f"ASCII grid not found: {p}")
    rows: list[list[float]] = []
    expected_width: int | None = None
    for line_number, line in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
        parts = line.split()
        if not parts:
            continue
        try:
            row = [float(part) for part in parts]
        except ValueError:
            continue
        if expected_width is None:
            expected_width = len(row)
        elif len(row) != expected_width:
            raise DataFormatError(f"ragged raster row at {p}:{line_number}")
        rows.append(row)
    if not rows:
        raise DataFormatError(f"no numeric raster rows in {p}")
    arr = np.asarray(rows, dtype=float)
    if not np.isfinite(arr).any():
        raise DataFormatError(f"raster has no finite values: {p}")
    return arr


def aggregate_categories(raster: np.ndarray) -> dict[str, Any]:
    if raster.ndim != 2:
        raise DataFormatError("land-use raster must be two-dimensional")
    counts = Counter(int(v) for v in raster.ravel() if np.isfinite(v))
    total = float(sum(counts.values())) or 1.0
    return {
        "component": "ctgproc",
        "shape": list(raster.shape),
        "categories": {str(k): {"count": int(v), "fraction": v / total} for k, v in sorted(counts.items())},
    }


def run(input_raster: str | Path, output: str | Path) -> dict[str, Any]:
    result = aggregate_categories(read_ascii_grid(input_raster))
    write_json(output, result)
    return result

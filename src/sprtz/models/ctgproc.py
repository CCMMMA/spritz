from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

from sprtz.exceptions import DataFormatError
from sprtz.io.jsonio import write_json

_CORINE_TO_FUEL = {
    111: 0, 112: 0, 121: 0, 122: 0, 123: 0, 124: 0, 131: 0, 132: 0, 133: 0, 141: 0, 142: 0,
    511: 0, 512: 0, 521: 0, 522: 0, 523: 0, 311: 1, 322: 2, 323: 2, 324: 2, 231: 3,
    321: 3, 331: 3, 332: 3, 333: 3, 312: 4, 241: 5, 242: 5, 243: 5, 244: 5, 313: 6,
}
_NLCD_TO_FUEL = {
    11: 0, 12: 0, 21: 0, 22: 0, 23: 0, 24: 0, 41: 1, 42: 4, 43: 6, 52: 2, 71: 3,
    81: 5, 82: 5, 90: 1, 95: 3,
}
FUEL_TABLES = {"corine": _CORINE_TO_FUEL, "nlcd": _NLCD_TO_FUEL}


def landcover_to_fuel(lc_array: np.ndarray, scheme: str = "corine") -> np.ndarray:
    table = FUEL_TABLES[scheme]
    lc = np.asarray(lc_array)
    out = np.zeros(lc.shape, dtype=np.int8)
    for code, fuel_id in table.items():
        out[lc == code] = fuel_id
    unknown = set(int(v) for v in np.unique(lc) if np.isfinite(v)) - set(table)
    if unknown:
        import logging

        logging.getLogger(__name__).warning(
            "landcover_to_fuel: %d unknown %s codes mapped to non-burnable: %s",
            len(unknown),
            scheme,
            sorted(unknown)[:20],
        )
    return out


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

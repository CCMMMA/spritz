from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Any

from sprtz.core.stats import summary
from sprtz.exceptions import DataFormatError
from sprtz.io.jsonio import write_json
from sprtz.io.netcdf_cf import read_cf_concentration


def read_concentrations(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        raise DataFormatError(f"concentration file not found: {p}")
    if p.suffix.lower() in {".nc", ".cdf", ".netcdf", ".json", ".jsn"}:
        return read_cf_concentration(p)
    with p.open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    required = {"receptor", "concentration"}
    if rows and not required.issubset(rows[0]):
        raise DataFormatError("concentration file must include receptor and concentration columns")
    return rows


def read_concentration_csv(path: str | Path) -> list[dict[str, Any]]:
    return read_concentrations(path)


def postprocess(
    rows: list[dict[str, Any]],
    threshold: float | None = None,
    *,
    rank: int = 1,
    average_window: int | None = None,
    average_kind: str = "running",
) -> dict[str, Any]:
    threshold_value = None if threshold is None else float(threshold)
    if threshold_value is not None and threshold_value < 0:
        raise DataFormatError("threshold must be non-negative")
    by_rec: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        try:
            by_rec[str(row["receptor"])].append(float(row["concentration"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise DataFormatError(f"invalid concentration row: {row}") from exc
    out: dict[str, Any] = {"component": "spritzpost", "receptors": {}}
    for receptor, values in sorted(by_rec.items()):
        stats = summary(values, rank=rank, average_window=average_window, average_kind=average_kind)
        if threshold_value is not None:
            stats["exceedances"] = float(sum(v > threshold_value for v in values))
        out["receptors"][receptor] = stats
    return out


def run(
    input_csv: str | Path,
    output: str | Path,
    threshold: float | None = None,
    *,
    rank: int = 1,
    average_window: int | None = None,
    average_kind: str = "running",
) -> dict[str, Any]:
    result = postprocess(
        read_concentrations(input_csv),
        threshold,
        rank=rank,
        average_window=average_window,
        average_kind=average_kind,
    )
    write_json(output, result)
    return result

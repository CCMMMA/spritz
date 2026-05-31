from __future__ import annotations

from pathlib import Path
from typing import Any

from sprtz.io.legacy import parse_legacy_file


def infer_format(path: str | Path, default: str = "auto") -> str:
    suffix = Path(path).suffix.lower()
    if default != "auto":
        return default.lower()
    if suffix in {".nc", ".cdf", ".netcdf"}:
        return "netcdf"
    if suffix in {".json", ".jsn"}:
        return "json"
    if suffix in {".csv"}:
        return "csv"
    return "legacy"


def write_legacy_table(path: str | Path, title: str, rows: list[dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        p.write_text(f"! {title}\n! no rows\n", encoding="utf-8")
        return
    fields = list(rows[0].keys())
    lines = [f"! {title}", "! " + " ".join(fields)]
    for row in rows:
        lines.append(" ".join(str(row.get(field, "")) for field in fields))
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_control(path: str | Path) -> dict[str, str]:
    return parse_legacy_file(path).values

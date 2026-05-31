from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import numpy as np

from sprtz.exceptions import DataFormatError
from sprtz.io.netcdf_cf import read_cf_concentration


def _read_rows(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    if p.suffix.lower() in {".nc", ".cdf", ".netcdf", ".json", ".jsn"}:
        return read_cf_concentration(p)
    with p.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def concentration_scatter(input_path: str | Path, output_path: str | Path, *, title: str = "Concentration field", dpi: int = 300) -> Path:
    """Create a publication-quality receptor scatter plot.

    Matplotlib is imported lazily so production compute deployments do not need
    visualization dependencies unless this module is used.
    """
    rows = _read_rows(input_path)
    if not rows:
        raise DataFormatError("no concentration rows available for plotting")
    x = np.asarray([float(r["x"]) for r in rows], dtype=float)
    y = np.asarray([float(r["y"]) for r in rows], dtype=float)
    c = np.asarray([float(r["concentration"]) for r in rows], dtype=float)
    try:
        import matplotlib.pyplot as plt
    except Exception as exc:  # pragma: no cover - depends on optional extra
        raise DataFormatError("matplotlib is required for visualization; install .[viz]") from exc

    fig, ax = plt.subplots(figsize=(6.8, 5.2), constrained_layout=True)
    marker_size = 70 if len(rows) < 50 else 32
    scatter = ax.scatter(x, y, c=c, s=marker_size, edgecolors="black", linewidths=0.25)
    cbar = fig.colorbar(scatter, ax=ax)
    cbar.set_label("Concentration")
    ax.set_title(title)
    ax.set_xlabel("x [m]")
    ax.set_ylabel("y [m]")
    ax.set_aspect("equal", adjustable="box")
    ax.grid(True, linewidth=0.3, alpha=0.5)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return out

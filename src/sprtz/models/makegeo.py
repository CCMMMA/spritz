from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import numpy as np

from .ctgproc import read_ascii_grid


def build_geo(terrain: np.ndarray, landuse: np.ndarray) -> list[dict[str, float | int]]:
    if terrain.shape != landuse.shape:
        raise ValueError(f"terrain shape {terrain.shape} does not match landuse shape {landuse.shape}")
    rows: list[dict[str, float | int]] = []
    for iy in range(terrain.shape[0]):
        for ix in range(terrain.shape[1]):
            rows.append(
                {
                    "iy": iy,
                    "ix": ix,
                    "terrain_m": float(terrain[iy, ix]),
                    "landuse": int(landuse[iy, ix]),
                }
            )
    return rows


def write_geo_csv(path: str | Path, rows: list[dict[str, float | int]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["iy", "ix", "terrain_m", "landuse"])
        writer.writeheader()
        writer.writerows(rows)


def run(terrain_path: str | Path, landuse_path: str | Path, output: str | Path) -> dict[str, Any]:
    terrain = read_ascii_grid(terrain_path)
    landuse = read_ascii_grid(landuse_path)
    rows = build_geo(terrain, landuse)
    write_geo_csv(output, rows)
    return {"component": "makegeo", "cells": len(rows), "output": str(output)}

from __future__ import annotations

from collections.abc import Iterable

import numpy as np


def running_average(values: Iterable[float], window: int) -> list[float]:
    arr = np.asarray(list(values), dtype=float)
    if window <= 0:
        raise ValueError("window must be positive")
    if arr.size < window:
        return []
    kernel = np.ones(window, dtype=float) / float(window)
    return np.convolve(arr, kernel, mode="valid").astype(float).tolist()


def block_average(values: Iterable[float], block: int) -> list[float]:
    arr = np.asarray(list(values), dtype=float)
    if block <= 0:
        raise ValueError("block must be positive")
    n = (arr.size // block) * block
    if n == 0:
        return []
    return arr[:n].reshape((-1, block)).mean(axis=1).astype(float).tolist()


def ranked(values: Iterable[float], rank: int = 1) -> float:
    arr = np.sort(np.asarray(list(values), dtype=float))[::-1]
    if arr.size == 0:
        return float("nan")
    index = min(max(int(rank), 1), arr.size) - 1
    return float(arr[index])


def summary(values: Iterable[float], *, rank: int = 1, average_window: int | None = None, average_kind: str = "running") -> dict[str, float]:
    raw = list(values)
    series = raw
    if average_window is not None:
        series = running_average(raw, average_window) if average_kind == "running" else block_average(raw, average_window)
    arr = np.asarray(series, dtype=float)
    if arr.size == 0:
        return {"count": 0, "mean": float("nan"), "max": float("nan"), "rank": float("nan"), "p98": float("nan")}
    return {
        "count": float(arr.size),
        "mean": float(np.mean(arr)),
        "max": float(np.max(arr)),
        "rank": ranked(arr, rank),
        "p98": float(np.percentile(arr, 98)),
    }

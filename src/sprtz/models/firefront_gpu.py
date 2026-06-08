from __future__ import annotations

import numpy as np


def _detect_gpu_backend() -> str:
    try:
        import cupy as cp

        cp.asarray([1.0])
        return "cupy"
    except Exception:
        pass
    try:
        import numba.cuda as nc

        if nc.is_available():
            return "numba_cuda"
    except Exception:
        pass
    return "numpy"


class CuPyCAEngine:
    """Minimal CuPy holder used by FireFront backend detection and future CA acceleration."""

    def __init__(self, dem: np.ndarray, fuel: np.ndarray, config: object):
        import cupy as cp

        self._cp = cp
        self.dem = cp.asarray(dem)
        self.fuel = cp.asarray(fuel)
        self.cfg = config

    def initialize(self, n_real: int) -> None:
        cp = self._cp
        ny, nx = self.fuel.shape
        self.burning = cp.zeros((n_real, ny, nx), dtype=cp.bool_)
        self.arrived = cp.full((n_real, ny, nx), cp.inf, dtype=cp.float32)

    def fire_probability(self) -> np.ndarray:
        return self._cp.asnumpy(self.burning.mean(axis=0).astype(self._cp.float32))

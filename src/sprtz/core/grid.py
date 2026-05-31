from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from sprtz.exceptions import ConfigurationError


@dataclass(frozen=True)
class Grid:
    nx: int
    ny: int
    dx: float
    dy: float
    x0: float = 0.0
    y0: float = 0.0
    projection: str = "LOCAL"

    def __post_init__(self) -> None:
        if self.nx <= 0 or self.ny <= 0:
            raise ConfigurationError("grid dimensions must be positive")
        if self.dx <= 0 or self.dy <= 0:
            raise ConfigurationError("grid spacing must be positive")

    @property
    def x(self) -> np.ndarray:
        return self.x0 + np.arange(self.nx, dtype=float) * self.dx

    @property
    def y(self) -> np.ndarray:
        return self.y0 + np.arange(self.ny, dtype=float) * self.dy

    def mesh(self) -> tuple[np.ndarray, np.ndarray]:
        return np.meshgrid(self.x, self.y)

    def nearest_index(self, x: float, y: float) -> tuple[int, int]:
        ix = int(np.clip(round((x - self.x0) / self.dx), 0, self.nx - 1))
        iy = int(np.clip(round((y - self.y0) / self.dy), 0, self.ny - 1))
        return iy, ix

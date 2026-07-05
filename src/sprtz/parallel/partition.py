from __future__ import annotations

from dataclasses import dataclass
from math import ceil


@dataclass(frozen=True)
class Slice1D:
    start: int
    stop: int


@dataclass(frozen=True)
class Tile2D:
    y0: int
    y1: int
    x0: int
    x1: int
    halo: int = 0

    @property
    def interior_slice(self) -> tuple[slice, slice]:
        return (slice(self.y0, self.y1), slice(self.x0, self.x1))


def balanced_slice(n: int, rank: int, size: int) -> Slice1D:
    if n < 0:
        raise ValueError("n must be non-negative")
    if size <= 0:
        raise ValueError("size must be positive")
    if rank < 0 or rank >= size:
        raise ValueError("rank must be in [0, size)")
    base, rem = divmod(n, size)
    start = rank * base + min(rank, rem)
    stop = start + base + (1 if rank < rem else 0)
    return Slice1D(start, stop)


def chunk_slices(n: int, chunks: int) -> list[Slice1D]:
    selected = max(1, min(chunks, n if n else 1))
    return [balanced_slice(n, rank, selected) for rank in range(selected)]


def balanced_tiles_2d(nx: int, ny: int, rank: int, size: int, halo: int = 0) -> Tile2D:
    """Return a deterministic row-major 2-D tile for an MPI rank."""

    if nx < 0 or ny < 0:
        raise ValueError("nx and ny must be non-negative")
    if halo < 0:
        raise ValueError("halo must be non-negative")
    px = max(1, int(round(size**0.5)))
    while px > 1 and size % px != 0:
        px -= 1
    py = ceil(size / px)
    ry = rank // px
    rx = rank % px
    ys = balanced_slice(ny, ry, py)
    xs = balanced_slice(nx, rx, px)
    return Tile2D(ys.start, ys.stop, xs.start, xs.stop, halo)

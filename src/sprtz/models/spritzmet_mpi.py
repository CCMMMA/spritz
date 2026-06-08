from __future__ import annotations

import numpy as np


def _balanced_decomposition(ny: int, nx: int, n_ranks: int) -> tuple[int, int]:
    best = (1, n_ranks)
    best_ratio = float("inf")
    for py in range(1, n_ranks + 1):
        if n_ranks % py:
            continue
        px = n_ranks // py
        ratio = max(ny / py, nx / px) / max(1.0e-12, min(ny / py, nx / px))
        if ratio < best_ratio:
            best_ratio = ratio
            best = (py, px)
    return best


def local_slice(ny: int, nx: int, py: int, px: int, cy: int, cx: int) -> tuple[int, int, int, int]:
    base_y, base_x = ny // py, nx // px
    local_y = base_y + (1 if cy < ny % py else 0)
    local_x = base_x + (1 if cx < nx % px else 0)
    off_y = cy * base_y + min(cy, ny % py)
    off_x = cx * base_x + min(cx, nx % px)
    return local_y, local_x, off_y, off_x


def exchange_halos(local_array: np.ndarray, cart_comm, halo: int = 1) -> np.ndarray:
    rank_n, rank_s = cart_comm.Shift(0, 1)
    rank_w, rank_e = cart_comm.Shift(1, 1)
    arr = local_array
    for send, recv, dest, source in [
        (arr[halo : 2 * halo, :].copy(), arr[:halo, :], rank_n, rank_n),
        (arr[-2 * halo : -halo, :].copy(), arr[-halo:, :], rank_s, rank_s),
        (arr[:, halo : 2 * halo].copy(), arr[:, :halo], rank_w, rank_w),
        (arr[:, -2 * halo : -halo].copy(), arr[:, -halo:], rank_e, rank_e),
    ]:
        if dest != -2 and source != -2:
            cart_comm.Sendrecv(send, senddest=dest, recvbuf=recv, source=source)
    return arr


class SpritzMetMPI:
    def __init__(self, config, comm=None):
        from mpi4py import MPI

        self.comm = comm or MPI.COMM_WORLD
        self.rank = self.comm.Get_rank()
        self.size = self.comm.Get_size()
        self.cfg = config
        py, px = _balanced_decomposition(config.grid.ny, config.grid.nx, self.size)
        self._cart = self.comm.Create_cart(dims=[py, px], periods=[False, False], reorder=True)
        cy, cx = self._cart.Get_coords(self._cart.Get_rank())
        self._local_ny, self._local_nx, self._offset_y, self._offset_x = local_slice(config.grid.ny, config.grid.nx, py, px, cy, cx)

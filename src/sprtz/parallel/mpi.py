from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence, TypeVar

from sprtz.exceptions import ParallelExecutionError

T = TypeVar("T")


def partition_indices(n_items: int, size: int, rank: int) -> range:
    """Return a balanced contiguous slice as a range for an MPI rank.

    The first ``n_items % size`` ranks receive one extra item.  The function is
    pure and is used by both the serial fallback and MPI code paths.
    """
    if n_items < 0:
        raise ValueError("n_items must be non-negative")
    if size <= 0:
        raise ValueError("size must be positive")
    if rank < 0 or rank >= size:
        raise ValueError("rank must be in [0, size)")
    base, rem = divmod(n_items, size)
    start = rank * base + min(rank, rem)
    stop = start + base + (1 if rank < rem else 0)
    return range(start, stop)


@dataclass(frozen=True)
class MPIContext:
    """Small wrapper around an optional mpi4py communicator."""

    comm: Any | None = None
    enabled: bool = False

    @property
    def rank(self) -> int:
        return int(self.comm.Get_rank()) if self.enabled and self.comm is not None else 0

    @property
    def size(self) -> int:
        return int(self.comm.Get_size()) if self.enabled and self.comm is not None else 1

    @property
    def is_root(self) -> bool:
        return self.rank == 0

    def partition(self, n_items: int) -> range:
        return partition_indices(n_items, self.size, self.rank)

    def allgather(self, value: T) -> list[T]:
        if self.enabled and self.comm is not None:
            return list(self.comm.allgather(value))
        return [value]

    def gather_flat(self, rows: Sequence[T]) -> list[T]:
        chunks = self.allgather(list(rows))
        merged: list[T] = []
        for chunk in chunks:
            merged.extend(chunk)
        return merged

    def bcast(self, value: T, root: int = 0) -> T:
        if self.enabled and self.comm is not None:
            return self.comm.bcast(value, root=root)
        return value

    def barrier(self) -> None:
        if self.enabled and self.comm is not None:
            self.comm.Barrier()


def get_mpi_context(mode: str = "auto") -> MPIContext:
    """Return an MPI context.

    ``mode`` may be ``serial``, ``auto``, or ``mpi``.  ``auto`` activates MPI
    only when mpi4py is installed and the communicator has more than one rank.
    ``mpi`` requires mpi4py and raises ParallelExecutionError if it is unavailable.
    """
    normalized = mode.lower().strip()
    if normalized not in {"serial", "auto", "mpi"}:
        raise ParallelExecutionError("parallel mode must be serial, auto, or mpi")
    if normalized == "serial":
        return MPIContext()
    try:
        from mpi4py import MPI  # type: ignore
    except ImportError:
        if normalized == "mpi":
            raise ParallelExecutionError("mpi4py is required for --parallel mpi; install sprtz[mpi]") from None
        return MPIContext()
    comm = MPI.COMM_WORLD
    size = int(comm.Get_size())
    return MPIContext(comm=comm, enabled=(normalized == "mpi" or size > 1))

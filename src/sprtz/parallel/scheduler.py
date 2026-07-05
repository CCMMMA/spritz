from __future__ import annotations

from dataclasses import dataclass

from .gpu import GPUContext, get_gpu_context
from .mpi import MPIContext, get_mpi_context
from .threads import ThreadContext, ThreadMode, get_thread_context


@dataclass(frozen=True)
class ParallelContext:
    """Hierarchical execution context: MPI rank, local workers, and array backend."""

    mpi: MPIContext
    threads: ThreadContext
    gpu: GPUContext

    @property
    def is_root(self) -> bool:
        return self.mpi.is_root


def get_parallel_context(
    parallel: str = "serial",
    thread_mode: ThreadMode = "auto",
    threads_per_rank: int | None = None,
    gpu_backend: str | None = "numpy",
) -> ParallelContext:
    mpi = get_mpi_context(parallel)
    threads = get_thread_context(thread_mode, threads_per_rank)
    gpu = get_gpu_context(gpu_backend or "numpy", rank=mpi.rank)
    return ParallelContext(mpi=mpi, threads=threads, gpu=gpu)

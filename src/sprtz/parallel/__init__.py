"""Optional hierarchical parallel helpers for Spritz.

The public helpers in this package are deliberately small and dependency-light:
serial execution is always available, while MPI, shared-memory, and GPU
execution are enabled only when requested and their optional dependencies are
available.
"""

from .gpu import GPUContext, get_gpu_context
from .mpi import MPIContext, get_mpi_context, partition_indices
from .partition import Slice1D, Tile2D, balanced_slice, balanced_tiles_2d, chunk_slices
from .scheduler import ParallelContext, get_parallel_context
from .threads import ThreadContext, get_thread_context

__all__ = [
    "GPUContext",
    "MPIContext",
    "ParallelContext",
    "Slice1D",
    "ThreadContext",
    "Tile2D",
    "balanced_slice",
    "balanced_tiles_2d",
    "chunk_slices",
    "get_gpu_context",
    "get_mpi_context",
    "get_parallel_context",
    "get_thread_context",
    "partition_indices",
]

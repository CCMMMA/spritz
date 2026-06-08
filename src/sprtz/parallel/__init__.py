"""Optional MPI helpers for Spritz.

The public helpers in this package are deliberately small and dependency-light:
serial execution is always available, while MPI execution is enabled only when
``mpi4py`` is importable and the process is launched by an MPI runtime.
"""

from .gpu import GPUContext, get_gpu_context
from .mpi import MPIContext, get_mpi_context, partition_indices

__all__ = ["GPUContext", "MPIContext", "get_gpu_context", "get_mpi_context", "partition_indices"]

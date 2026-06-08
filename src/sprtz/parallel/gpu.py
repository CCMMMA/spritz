from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class GPUContext:
    """Optional array-accelerator context.

    ``backend`` is ``"numpy"`` unless a CUDA-capable CuPy installation is
    explicitly requested or auto-detected.  The object stores the array module
    so model code can use one implementation for CPU and GPU paths.
    """

    backend: str = "numpy"
    xp: Any = None
    device_id: int = 0

    @property
    def enabled(self) -> bool:
        return self.backend == "cupy"

    def asnumpy(self, value: Any) -> Any:
        if self.enabled:
            return self.xp.asnumpy(value)
        return value


def get_gpu_context(mode: str = "numpy", *, device_id: int = 0, rank: int = 0) -> GPUContext:
    """Return an optional GPU context.

    ``mode`` may be ``numpy``, ``auto``, or ``cupy``.  ``auto`` uses CuPy only
    when CUDA allocation succeeds.  The function never imports CuPy unless GPU
    execution is requested or auto detection is enabled.
    """

    normalized = str(mode or "numpy").strip().lower()
    if normalized not in {"numpy", "auto", "cupy", "cuda"}:
        raise ValueError("gpu backend must be numpy, auto, or cupy")
    if normalized == "numpy":
        import numpy as np

        return GPUContext("numpy", np, device_id)
    try:
        import cupy as cp

        n_devices = int(cp.cuda.runtime.getDeviceCount())
        if n_devices <= 0:
            raise RuntimeError("no CUDA devices available")
        selected = int(device_id if device_id >= 0 else rank % n_devices)
        cp.cuda.Device(selected).use()
        cp.asarray([1.0])
        return GPUContext("cupy", cp, selected)
    except Exception as exc:
        if normalized in {"cupy", "cuda"}:
            raise RuntimeError(f"CuPy/CUDA backend requested but unavailable: {exc}") from exc
        import numpy as np

        LOGGER.debug("GPU auto-detection fell back to NumPy: %s", exc)
        return GPUContext("numpy", np, device_id)

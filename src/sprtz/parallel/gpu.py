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
        return self.backend in {"cupy", "mlx"}

    def asnumpy(self, value: Any) -> Any:
        if self.backend == "cupy":
            return self.xp.asnumpy(value)
        if self.backend == "mlx":
            import numpy as np

            return np.asarray(value)
        return value


def get_gpu_context(mode: str = "numpy", *, device_id: int = -1, rank: int = 0) -> GPUContext:
    """Return an optional GPU context.

    ``mode`` may be ``numpy``, ``auto``, ``cupy``/``cuda``, or ``mlx``.
    ``auto`` prefers CuPy when CUDA allocation succeeds, then MLX on Apple
    Silicon, and finally NumPy. Optional accelerator modules are imported
    lazily.
    """

    normalized = str(mode or "numpy").strip().lower()
    if normalized not in {"numpy", "auto", "cupy", "cuda", "mlx", "metal"}:
        raise ValueError("gpu backend must be numpy, auto, cupy, cuda, mlx, or metal")
    if normalized == "numpy":
        import numpy as np

        return GPUContext("numpy", np, 0 if device_id < 0 else device_id)
    if normalized in {"auto", "cupy", "cuda"}:
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
            LOGGER.debug("CUDA auto-detection failed: %s", exc)

    if normalized in {"auto", "mlx", "metal"}:
        try:
            import mlx.core as mx  # type: ignore

            probe = mx.asarray([1.0])
            mx.eval(probe)
            return GPUContext("mlx", mx, 0)
        except Exception as exc:
            if normalized in {"mlx", "metal"}:
                raise RuntimeError(f"MLX/Metal backend requested but unavailable: {exc}") from exc
            LOGGER.debug("MLX auto-detection failed: %s", exc)

    import numpy as np

    return GPUContext("numpy", np, 0 if device_id < 0 else device_id)

from sprtz.models.firefront_gpu import _detect_gpu_backend


def test_gpu_backend_detection_returns_known_value():
    assert _detect_gpu_backend() in {"cupy", "numba_cuda", "numpy"}

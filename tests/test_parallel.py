from __future__ import annotations

from sprtz.config import load_config
from sprtz.models import spritzmet, spritz, particles
from sprtz.parallel import (
    balanced_slice,
    balanced_tiles_2d,
    chunk_slices,
    get_gpu_context,
    get_mpi_context,
    get_parallel_context,
    get_thread_context,
    partition_indices,
)


def test_partition_indices_balanced():
    parts = [list(partition_indices(10, 3, rank)) for rank in range(3)]
    assert parts == [[0, 1, 2, 3], [4, 5, 6], [7, 8, 9]]


def test_partition_helpers_are_balanced_and_deterministic():
    assert balanced_slice(10, 2, 3).start == 7
    assert balanced_slice(10, 2, 3).stop == 10
    assert chunk_slices(5, 8) == [
        balanced_slice(5, 0, 5),
        balanced_slice(5, 1, 5),
        balanced_slice(5, 2, 5),
        balanced_slice(5, 3, 5),
        balanced_slice(5, 4, 5),
    ]
    tiles = [balanced_tiles_2d(8, 6, rank, 4) for rank in range(4)]
    assert [(tile.y0, tile.y1, tile.x0, tile.x1) for tile in tiles] == [
        (0, 3, 0, 4),
        (0, 3, 4, 8),
        (3, 6, 0, 4),
        (3, 6, 4, 8),
    ]


def test_thread_context_serial_and_threads_map():
    serial = get_thread_context("serial", 4)
    assert serial.map(lambda x: x + 1, [1, 2]) == [2, 3]
    threaded = get_thread_context("threads", 2)
    assert threaded.active
    assert threaded.map(lambda x: x * 2, [1, 2, 3]) == [2, 4, 6]


def test_parallel_context_combines_mpi_threads_and_gpu():
    ctx = get_parallel_context("serial", "threads", 2, "numpy")
    assert ctx.mpi.size == 1
    assert ctx.threads.workers == 2
    assert ctx.gpu.backend == "numpy"
    assert ctx.is_root


def test_auto_parallel_falls_back_to_serial_without_mpi_runtime():
    ctx = get_mpi_context("auto")
    assert ctx.size >= 1
    assert ctx.rank >= 0


def test_gpu_auto_falls_back_or_selects_known_backend():
    ctx = get_gpu_context("auto")
    assert ctx.backend in {"numpy", "cupy"}


def test_gaussian_parallel_serial_equivalence(tmp_path):
    cfg = load_config("examples/minimal.json")
    meteo_path = tmp_path / "meteo.json"
    spritzmet.run(cfg, meteo_path, "json")
    serial = spritz.run(cfg, meteo_path, tmp_path / "serial.csv", "csv", parallel="serial", gpu_backend="numpy")
    auto = spritz.run(cfg, meteo_path, tmp_path / "auto.csv", "csv", parallel="auto", gpu_backend="auto")
    assert auto == serial


def test_particle_parallel_auto_is_deterministic(tmp_path):
    cfg = load_config("examples/minimal.json")
    meteo_path = tmp_path / "meteo.json"
    spritzmet.run(cfg, meteo_path, "json")
    serial = particles.run(cfg, meteo_path, tmp_path / "serial.csv", "csv", seed=11, parallel="serial", gpu_backend="numpy")
    auto = particles.run(cfg, meteo_path, tmp_path / "auto.csv", "csv", seed=11, parallel="auto", gpu_backend="numpy")
    assert auto == serial


def test_spritzmet_gpu_auto_matches_numpy(tmp_path):
    cfg = load_config("examples/minimal.json")
    serial = spritzmet.run(cfg, tmp_path / "meteo_numpy.json", "json", gpu_backend="numpy")
    auto = spritzmet.run(cfg, tmp_path / "meteo_auto.json", "json", gpu_backend="auto")
    assert serial["wind_speed"] == auto["wind_speed"]

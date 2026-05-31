from __future__ import annotations

from sprtz.config import load_config
from sprtz.models import spritzmet, spritz, particles
from sprtz.parallel import get_mpi_context, partition_indices


def test_partition_indices_balanced():
    parts = [list(partition_indices(10, 3, rank)) for rank in range(3)]
    assert parts == [[0, 1, 2, 3], [4, 5, 6], [7, 8, 9]]


def test_auto_parallel_falls_back_to_serial_without_mpi_runtime():
    ctx = get_mpi_context("auto")
    assert ctx.size >= 1
    assert ctx.rank >= 0


def test_gaussian_parallel_serial_equivalence(tmp_path):
    cfg = load_config("examples/minimal.json")
    meteo_path = tmp_path / "meteo.json"
    spritzmet.run(cfg, meteo_path, "json")
    serial = spritz.run(cfg, meteo_path, tmp_path / "serial.csv", "csv", parallel="serial")
    auto = spritz.run(cfg, meteo_path, tmp_path / "auto.csv", "csv", parallel="auto")
    assert auto == serial


def test_particle_parallel_auto_is_deterministic(tmp_path):
    cfg = load_config("examples/minimal.json")
    meteo_path = tmp_path / "meteo.json"
    spritzmet.run(cfg, meteo_path, "json")
    serial = particles.run(cfg, meteo_path, tmp_path / "serial.csv", "csv", seed=11, parallel="serial")
    auto = particles.run(cfg, meteo_path, tmp_path / "auto.csv", "csv", seed=11, parallel="auto")
    assert auto == serial

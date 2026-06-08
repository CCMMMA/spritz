from __future__ import annotations

import numpy as np

from sprtz.config import load_config
from sprtz.models import backward, spritzmet


def test_backward_gaussian_likelihood_normalized(tmp_path):
    cfg = load_config("examples/backward_plume.json")
    meteo_path = tmp_path / "meteo.json"
    spritzmet.run(cfg, meteo_path, "json")
    result = backward.run_backward(cfg, meteo_path, tmp_path / "backward.json", model="gaussian")
    arr = np.asarray(result["source_likelihood"])
    assert arr.shape == (cfg.grid.ny, cfg.grid.nx)
    assert np.isclose(arr.sum(), 1.0)


def test_backward_particles_likelihood_normalized(tmp_path):
    cfg = load_config("examples/backward_plume.json")
    meteo_path = tmp_path / "meteo.json"
    spritzmet.run(cfg, meteo_path, "json")
    result = backward.run_backward(cfg, meteo_path, tmp_path / "backward_particles.csv", model="particles", output_format="csv", seed=4)
    arr = np.asarray(result["source_likelihood"])
    assert arr.shape == (cfg.grid.ny, cfg.grid.nx)
    assert np.isclose(arr.sum(), 1.0)


def test_backward_firefront_likelihood_normalized(tmp_path):
    cfg = load_config("examples/backward_firefront.json")
    result = backward.run_backward(cfg, None, tmp_path / "backward_fire.json", model="firefront")
    arr = np.asarray(result["ignition_likelihood"])
    assert arr.shape == (cfg.grid.ny, cfg.grid.nx)
    assert np.isclose(arr.sum(), 1.0)

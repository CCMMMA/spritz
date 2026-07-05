from __future__ import annotations

import numpy as np

from sprtz.core.physics import random_walk_std_from_k
from sprtz.models.particles import _apply_vertical_boundary


def _constant_k_random_walk_variance(*, k: float, duration_s: float, steps: int, seed: int) -> float:
    rng = np.random.default_rng(seed)
    count = 60000
    dt = duration_s / float(steps)
    x = np.zeros(count, dtype=float)
    for _step in range(steps):
        x += rng.normal(0.0, random_walk_std_from_k(k, dt), count)
    return float(np.var(x))


def test_random_walk_diffusion_is_timestep_invariant():
    k = 10.0
    duration = 600.0
    expected = 2.0 * k * duration
    variances = [
        _constant_k_random_walk_variance(k=k, duration_s=duration, steps=steps, seed=1234 + steps)
        for steps in (10, 20, 40)
    ]

    assert all(abs(value - expected) / expected < 0.04 for value in variances)
    assert max(variances) / min(variances) < 1.08


def test_vertical_boundary_reflects_or_removes_mass():
    z = np.asarray([-5.0, 10.0, 130.0], dtype=float)
    weights = np.ones(3, dtype=float)

    reflected, reflected_mass = _apply_vertical_boundary(
        z,
        weights,
        ground_m=0.0,
        top_m=100.0,
        ground_policy="reflect",
        top_policy="reflect",
    )
    assert np.all(reflected >= 0.0)
    assert np.all(reflected <= 100.0)
    assert np.all(reflected_mass == 1.0)

    bounded, remaining_mass = _apply_vertical_boundary(
        z,
        weights,
        ground_m=0.0,
        top_m=100.0,
        ground_policy="absorb_deposit",
        top_policy="open",
    )
    assert np.all(bounded >= 0.0)
    assert np.all(bounded <= 100.0)
    assert remaining_mass.tolist() == [0.0, 1.0, 0.0]

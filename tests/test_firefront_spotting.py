from __future__ import annotations

import math

import numpy as np

from sprtz.config import SpottingConfig
from sprtz.models.firefront_spotting import RandomFrontSpotting


def test_settling_velocity_positive():
    spot = RandomFrontSpotting(SpottingConfig(), 10.0, np.ones((3, 3), dtype=np.int8))
    assert spot._settling_velocity() > 0


def test_lognormal_mu_below_threshold():
    spot = RandomFrontSpotting(SpottingConfig(), 10.0, np.ones((3, 3), dtype=np.int8))
    assert spot._lognormal_mu(1.0, 10.0, 1000.0) == -math.inf


def test_spotting_does_not_ignite_nonburnable():
    fuel = np.ones((9, 9), dtype=np.int8)
    fuel[:, 5:] = 0
    cfg = SpottingConfig(n_firebrands_per_cell=20, intensity_threshold_kw_m=1.0)
    spot = RandomFrontSpotting(cfg, 1.0, fuel)
    burning = np.zeros((1, 9, 9), dtype=bool)
    arrived = np.full((1, 9, 9), np.inf, dtype=np.float32)
    burning[:, 4, 4] = True
    intensity = np.full((9, 9), 5000.0, dtype=np.float32)
    ws = np.full((9, 9), 20.0, dtype=np.float32)
    wd = np.full((9, 9), np.pi / 2, dtype=np.float32)
    spot.step(burning, arrived, intensity, ws, wd, 1.0, np.random.default_rng(1))
    assert not burning[:, :, 5:].any()

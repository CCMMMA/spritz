from __future__ import annotations

import numpy as np

from sprtz.config import FireConfig
from sprtz.models.firefront import FireFront, byram_intensity, transition_probability


def test_transition_probability_nonburnable_zero():
    assert transition_probability(3, 0, 0.0, 0.0, 5.0, 0.0, 0.08) == 0.0


def test_byram_intensity_positive_for_grass_ros():
    fuel = np.full((2, 2), 3, dtype=np.int8)
    intensity = byram_intensity(fuel, np.full((2, 2), 0.05), np.full((2, 2), 0.08))
    assert np.all(intensity > 0)


def test_firefront_spreads_on_burnable_grid():
    dem = np.zeros((20, 20), dtype=np.float32)
    fuel = np.full((20, 20), 3, dtype=np.int8)
    cfg = FireConfig(realizations=4, t_max_seconds=3000, output_interval_seconds=600, seed=7)
    front = FireFront(dem, fuel, cfg)
    front.set_ignitions([(10, 10)], 0.0)
    result = front.run(np.full((20, 20), 5.0), np.full((20, 20), np.pi / 2))
    assert result["fire_probability"].sum() > 1.0
    assert len(result["snapshots"]) >= 2


def test_non_burnable_barrier_not_ignited():
    dem = np.zeros((10, 10), dtype=np.float32)
    fuel = np.full((10, 10), 3, dtype=np.int8)
    fuel[:, 5] = 0
    front = FireFront(dem, fuel, FireConfig(realizations=2, t_max_seconds=120, seed=3))
    front.set_ignitions([(5, 4)], 0.0)
    front.run(np.full((10, 10), 5.0), np.full((10, 10), np.pi / 2))
    assert not front.burning[:, :, 5].any()

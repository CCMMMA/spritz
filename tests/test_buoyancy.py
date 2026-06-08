from __future__ import annotations

import numpy as np

from sprtz.models.buoyancy import buoyancy_corrected_wind


def test_nc_below_threshold_no_correction():
    ws = np.full((5, 5), 20.0, dtype=np.float32)
    wd = np.ones((5, 5), dtype=np.float32)
    corr, out_dir = buoyancy_corrected_wind(ws, wd, np.ones((5, 5)), np.ones((5, 5)), None)
    assert np.allclose(corr, ws)
    assert np.array_equal(out_dir, wd)


def test_updraft_reduces_and_perimeter_increases():
    ws = np.full((9, 9), 2.0, dtype=np.float32)
    wd = np.ones((9, 9), dtype=np.float32)
    fire = np.zeros((9, 9), dtype=np.float32)
    fire[4, 4] = 1.0
    corr, _ = buoyancy_corrected_wind(ws, wd, np.full((9, 9), 20000.0), fire, None)
    assert corr[4, 4] < ws[4, 4]
    assert corr[4, 5] > ws[4, 5]
    assert np.all(corr >= 0)

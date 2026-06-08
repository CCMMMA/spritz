from __future__ import annotations

import pytest

pd = pytest.importorskip("pandas")

from sprtz.config import FIRMSConfig
from sprtz.terrain.firms import FIRMSDownloader


def test_firms_filter_confidence():
    df = pd.DataFrame({"confidence": ["l", "n", "h"], "frp": [10.0, 0.5, 2.0]})
    out = FIRMSDownloader(FIRMSConfig()).filter(df)
    assert list(out["confidence"]) == ["h"]


def test_firms_to_ignition_points_sorted_by_time():
    df = pd.DataFrame(
        {
            "latitude": [40.0, 41.0],
            "longitude": [14.0, 15.0],
            "acq_date": ["2026-06-02", "2026-06-01"],
            "acq_time": [1200, 1100],
            "confidence": ["h", "h"],
            "frp": [2.0, 2.0],
        }
    )
    pts = FIRMSDownloader(FIRMSConfig(cluster_distance_m=0.0)).to_ignition_points(df)
    assert pts[0].lat == 41.0

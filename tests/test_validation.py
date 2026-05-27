from __future__ import annotations

import json

import pytest

from pypuff.config import ConfigurationError, load_config
from pypuff.models.ctgproc import read_ascii_grid
from pypuff.exceptions import DataFormatError


def test_invalid_grid_rejected(tmp_path):
    cfg = tmp_path / "bad.json"
    cfg.write_text(json.dumps({"grid": {"nx": 0, "ny": 1, "dx": 1, "dy": 1}}), encoding="utf-8")
    with pytest.raises(ConfigurationError):
        load_config(cfg)


def test_ragged_ascii_grid_rejected(tmp_path):
    grid = tmp_path / "ragged.asc"
    grid.write_text("1 2 3\n4 5\n", encoding="utf-8")
    with pytest.raises(DataFormatError):
        read_ascii_grid(grid)

#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

COMMON = Path(__file__).resolve().parents[2] / "common"
sys.path.insert(0, str(COMMON))

from wind_downscaling_cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(component="usecase.03_satellite_ai_evaluation"))

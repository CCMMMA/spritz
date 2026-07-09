#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

COMMON_DIR = Path(__file__).resolve().parents[2] / "common"
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))

from wind_downscaling_cli import main


if __name__ == "__main__":
    raise SystemExit(main())

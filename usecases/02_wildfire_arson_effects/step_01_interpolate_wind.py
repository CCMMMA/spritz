#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

USECASES_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(USECASES_ROOT))

from high_resolution_wind import main


if __name__ == "__main__":
    raise SystemExit(main())

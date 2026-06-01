#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
USECASES_ROOT = THIS_DIR.parent
sys.path.insert(0, str(USECASES_ROOT))

from sailing_forecast import main

if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

USECASES_ROOT = Path(__file__).resolve().parents[2]
COMMON_DIR = USECASES_ROOT / "common"
for path in (COMMON_DIR, USECASES_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from model_evaluation import main


if __name__ == "__main__":
    raise SystemExit(main())

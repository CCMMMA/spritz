#!/usr/bin/env python3
"""Run the satellite/model evaluator used by use case 03."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = ROOT / "usecases" / "03_satellite_ai_evaluation" / "demo"
sys.path[:0] = [str(ROOT / "src"), str(DEMO_DIR)]

from model_evaluation import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())

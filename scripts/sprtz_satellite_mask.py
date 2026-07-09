#!/usr/bin/env python3
"""Run the deterministic mask generator used by use case 03."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = ROOT / "usecases" / "03_satellite_ai_evaluation" / "demo"
sys.path[:0] = [str(ROOT / "src"), str(DEMO_DIR)]

from make_demo_mask import main  # noqa: E402
from sprtz.logging import configure_logging  # noqa: E402


if __name__ == "__main__":
    configure_logging(False)
    raise SystemExit(main())

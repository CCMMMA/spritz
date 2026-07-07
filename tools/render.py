#!/usr/bin/env python3
"""Compatibility wrapper for publication-ready 2-D Sprtz rendering."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if SRC.exists():
    sys.path.insert(0, str(SRC))

from plotter import main


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Command-line wrapper for the unified sprtz workflow CLI."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if SRC.exists():
    sys.path.insert(0, str(SRC))

from sprtz.cli import main


if __name__ == "__main__":
    raise SystemExit(main())

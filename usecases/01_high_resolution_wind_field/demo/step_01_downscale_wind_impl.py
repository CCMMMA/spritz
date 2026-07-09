#!/usr/bin/env python3
"""Compatibility entry point for the shared didactic wind workflow."""

from __future__ import annotations

import sys
from pathlib import Path

COMMON_DIR = Path(__file__).resolve().parents[2] / "common"
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))

import wind_downscaling_cli as _shared

globals().update(
    {
        name: value
        for name, value in vars(_shared).items()
        if name not in {"__name__", "__file__", "__package__", "__spec__"}
    }
)


if __name__ == "__main__":
    raise SystemExit(_shared.main())

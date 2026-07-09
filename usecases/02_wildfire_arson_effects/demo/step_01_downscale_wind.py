#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

COMMON_DIR = Path(__file__).resolve().parents[2] / "common"
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))

from wind_downscaling_cli import main as _main


def main(argv: list[str] | None = None) -> int:
    return _main(
        argv,
        description="Use case 02: SpritzWRF -> SpritzMet wind preparation for arson/wildfire effects",
        component="usecase.02_wildfire_arson_effects",
    )


if __name__ == "__main__":
    raise SystemExit(main())

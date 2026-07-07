#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

USECASE_01_DIR = Path(__file__).resolve().parents[2] / "01_high_resolution_wind_field" / "demo"
if str(USECASE_01_DIR) not in sys.path:
    sys.path.insert(0, str(USECASE_01_DIR))

from step_01_downscale_wind_impl import main as _main


def main(argv: list[str] | None = None) -> int:
    return _main(
        argv,
        description="Use case 02: SpritzWRF -> SpritzMet wind preparation for arson/wildfire effects",
    )


if __name__ == "__main__":
    raise SystemExit(main())

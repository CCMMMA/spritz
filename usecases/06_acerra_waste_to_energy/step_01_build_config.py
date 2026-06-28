#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

USECASES_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(USECASES_ROOT))

from acerra_waste_to_energy import DEFAULT_DURATION_H, DEFAULT_START, build_acerra_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the Acerra waste-to-energy Spritz configuration")
    parser.add_argument("--output", required=True)
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--duration-h", type=float, default=DEFAULT_DURATION_H)
    args = parser.parse_args(argv)
    build_acerra_config(args.output, start_datetime=args.start, duration_h=args.duration_h)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

USECASES_ROOT = Path(__file__).resolve().parents[2]
COMMON_DIR = USECASES_ROOT / "common"
for path in (COMMON_DIR, USECASES_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from production_incidents import DEFAULT_CATALOG, build_incident_config, load_incident_catalog, select_event


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a production-incident Spritz configuration")
    parser.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    parser.add_argument("--code", default="2021_44")
    parser.add_argument("--output", required=True)
    parser.add_argument("--emission-rate-g-s", type=float, default=20.0)
    parser.add_argument("--wind-speed-m-s", type=float, default=3.0)
    parser.add_argument("--wind-from-direction-deg", type=float, default=270.0)
    args = parser.parse_args(argv)
    event = select_event(load_incident_catalog(args.catalog), args.code)
    build_incident_config(
        event,
        args.output,
        emission_rate_g_s=args.emission_rate_g_s,
        wind_speed_m_s=args.wind_speed_m_s,
        wind_from_direction_deg=args.wind_from_direction_deg,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

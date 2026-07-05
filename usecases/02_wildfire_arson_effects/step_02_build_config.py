#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

USECASES_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(USECASES_ROOT))

from datetime_args import script_datetime_to_iso
from wildfire import BURNING_MATERIALS, _load_fire_events, build_wildfire_config


def _parse_field_z_levels(values: list[str] | None) -> list[float] | None:
    if not values:
        return None
    levels: list[float] = []
    for value in values:
        for part in value.split(","):
            text = part.strip()
            if text:
                levels.append(float(text))
    if not levels:
        raise ValueError("--field-z-levels must include at least one non-negative height")
    return levels


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the wildfire/arson Spritz configuration")
    parser.add_argument("--output", required=True)
    parser.add_argument("--center-lat", type=float, required=True)
    parser.add_argument("--center-lon", type=float, required=True)
    parser.add_argument("--nx", type=int, default=None)
    parser.add_argument("--ny", type=int, default=None)
    parser.add_argument("--dx", type=float, default=None)
    parser.add_argument("--dy", type=float, default=None)
    parser.add_argument("--temperature-k", type=float, default=None)
    parser.add_argument("--material", choices=sorted(BURNING_MATERIALS), default="generic")
    parser.add_argument("--start", default=None, help="UTC start datetime as YYYYMMDDZhhmm")
    parser.add_argument("--end", default=None, help="UTC end datetime as YYYYMMDDZhhmm")
    parser.add_argument("--duration-s", type=float, default=3600.0)
    parser.add_argument("--area-m2", type=float, default=2500.0)
    parser.add_argument("--height-agl-m", type=float, default=0.0)
    parser.add_argument("--fire-events-json", default=None)
    parser.add_argument("--weather-start", default=None, help="UTC weather start datetime as YYYYMMDDZhhmm")
    parser.add_argument("--weather-end", default=None, help="UTC weather end datetime as YYYYMMDDZhhmm")
    parser.add_argument("--firefighters-start", default=None, help="UTC firefighter-action start datetime as YYYYMMDDZhhmm")
    parser.add_argument("--firefighters-end", default=None, help="UTC firefighter-action end datetime as YYYYMMDDZhhmm")
    parser.add_argument("--firefighters-emission-factor", type=float, default=1.0)
    parser.add_argument("--precipitation-washout", action="store_true")
    parser.add_argument("--precipitation-rate-mm-h", type=float, default=0.0)
    parser.add_argument("--wind-speed-m-s", type=float, default=4.0)
    parser.add_argument("--wind-from-direction-deg", type=float, default=270.0)
    parser.add_argument(
        "--field-z-levels",
        action="append",
        default=None,
        help="comma-separated concentration field heights in metres AGL; may be repeated",
    )
    args = parser.parse_args(argv)
    try:
        field_z_levels = _parse_field_z_levels(args.field_z_levels)
    except ValueError as exc:
        parser.error(str(exc))
    build_wildfire_config(
        args.output,
        center_lat=args.center_lat,
        center_lon=args.center_lon,
        burning_temperature_k=args.temperature_k,
        burning_material=args.material,
        burning_start=script_datetime_to_iso(args.start),
        burning_end=script_datetime_to_iso(args.end),
        burning_duration_s=args.duration_s,
        burning_area_m2=args.area_m2,
        source_height_agl_m=args.height_agl_m,
        fire_events=_load_fire_events(args.fire_events_json),
        weather_start=script_datetime_to_iso(args.weather_start),
        weather_end=script_datetime_to_iso(args.weather_end),
        firefighters_start=script_datetime_to_iso(args.firefighters_start),
        firefighters_end=script_datetime_to_iso(args.firefighters_end),
        firefighters_emission_factor=args.firefighters_emission_factor,
        precipitation_washout=args.precipitation_washout,
        precipitation_rate_mm_h=args.precipitation_rate_mm_h,
        wind_speed_m_s=args.wind_speed_m_s,
        wind_from_direction_deg=args.wind_from_direction_deg,
        nx=args.nx,
        ny=args.ny,
        dx_m=args.dx,
        dy_m=args.dy,
        field_z_levels=field_z_levels,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

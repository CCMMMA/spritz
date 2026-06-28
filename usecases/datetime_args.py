from __future__ import annotations

import argparse
from datetime import datetime, timezone

SCRIPT_DATETIME_FORMAT = "%Y%m%dZ%H%M"
SCRIPT_DATETIME_FORMAT_TEXT = "YYYYMMDDZhhmm"


def parse_script_datetime(value: str) -> datetime:
    """Parse a script-facing UTC datetime argument."""
    try:
        return datetime.strptime(value, SCRIPT_DATETIME_FORMAT).replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"datetime must use {SCRIPT_DATETIME_FORMAT_TEXT}, e.g. 20260527Z0000"
        ) from exc


def script_datetime_to_iso(value: str | None) -> str | None:
    if value is None:
        return None
    return parse_script_datetime(value).isoformat()


def script_datetime_to_date_and_hour(value: str | None) -> tuple[str | None, int]:
    if value is None:
        return None, 0
    parsed = parse_script_datetime(value)
    return parsed.date().isoformat(), parsed.hour

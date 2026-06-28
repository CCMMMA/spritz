#!/usr/bin/env python3
"""
copernicus-cop30-dem-download.py

Download Copernicus DEM GLO-30 / COP30 for a latitude-longitude bounding box
from OpenTopography as a GeoTIFF.

Example:
    python3 tools/copernicus-cop30-dem-download.py \
        --south 40.40 --north 41.10 \
        --west 13.80 --east 14.80 \
        --api-key YOUR_OPENTOPOGRAPHY_API_KEY \
        --output data/dem/cop30_naples.tif

You can also set the key as an environment variable:

    export OPENTOPO_API_KEY=YOUR_OPENTOPOGRAPHY_API_KEY

Then run:

    python3 tools/copernicus-cop30-dem-download.py \
        --south 40.40 --north 41.10 \
        --west 13.80 --east 14.80 \
        --output data/dem/cop30_naples.tif
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import requests


OPENTOPO_GLOBALDEM_URL = "https://portal.opentopography.org/API/globaldem"


def validate_bbox(south: float, north: float, west: float, east: float) -> None:
    """Validate a WGS84 geographic bounding box."""
    if not (-90.0 <= south <= 90.0):
        raise ValueError("south must be between -90 and 90 degrees")
    if not (-90.0 <= north <= 90.0):
        raise ValueError("north must be between -90 and 90 degrees")
    if not (-180.0 <= west <= 180.0):
        raise ValueError("west must be between -180 and 180 degrees")
    if not (-180.0 <= east <= 180.0):
        raise ValueError("east must be between -180 and 180 degrees")
    if south >= north:
        raise ValueError("south must be smaller than north")
    if west >= east:
        raise ValueError(
            "west must be smaller than east. "
            "This simple script does not handle anti-meridian-crossing boxes."
        )


def download_cop30(
    south: float,
    north: float,
    west: float,
    east: float,
    output: Path,
    api_key: str,
) -> Path:
    """Download COP30 DEM from OpenTopography."""
    validate_bbox(south, north, west, east)

    params = {
        "demtype": "COP30",
        "south": south,
        "north": north,
        "west": west,
        "east": east,
        "outputFormat": "GTiff",
        "API_Key": api_key,
    }

    output.parent.mkdir(parents=True, exist_ok=True)

    with requests.get(
        OPENTOPO_GLOBALDEM_URL,
        params=params,
        stream=True,
        timeout=300,
    ) as response:
        content_type = response.headers.get("Content-Type", "")

        if response.status_code != 200:
            message = response.text[:1000]
            raise RuntimeError(
                f"OpenTopography request failed with HTTP {response.status_code}.\n"
                f"Response:\n{message}"
            )

        # Error responses may sometimes come back as text/html or JSON.
        if "text" in content_type.lower() or "json" in content_type.lower():
            message = response.text[:1000]
            raise RuntimeError(
                "OpenTopography did not return a GeoTIFF.\n"
                f"Content-Type: {content_type}\n"
                f"Response:\n{message}"
            )

        total = int(response.headers.get("Content-Length", 0))
        downloaded = 0

        with output.open("wb") as f:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue

                f.write(chunk)
                downloaded += len(chunk)

                if total:
                    percent = 100.0 * downloaded / total
                    print(
                        f"\rDownloaded {downloaded / 1e6:.1f} MB "
                        f"of {total / 1e6:.1f} MB ({percent:.1f}%)",
                        end="",
                        file=sys.stderr,
                    )
                else:
                    print(
                        f"\rDownloaded {downloaded / 1e6:.1f} MB",
                        end="",
                        file=sys.stderr,
                    )

        print(file=sys.stderr)

    if output.stat().st_size == 0:
        raise RuntimeError("Downloaded file is empty")

    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download Copernicus DEM GLO-30 / COP30 from OpenTopography."
    )

    parser.add_argument("--south", type=float, required=True, help="Minimum latitude")
    parser.add_argument("--north", type=float, required=True, help="Maximum latitude")
    parser.add_argument("--west", type=float, required=True, help="Minimum longitude")
    parser.add_argument("--east", type=float, required=True, help="Maximum longitude")

    parser.add_argument(
        "--output",
        type=Path,
        default=Path("cop30_dem.tif"),
        help="Output GeoTIFF path",
    )

    parser.add_argument(
        "--api-key",
        default=os.environ.get("OPENTOPO_API_KEY"),
        help="OpenTopography API key. Can also be set with OPENTOPO_API_KEY.",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not args.api_key:
        print(
            "Error: OpenTopography API key is required. "
            "Pass --api-key or set OPENTOPO_API_KEY.",
            file=sys.stderr,
        )
        return 2

    try:
        path = download_cop30(
            south=args.south,
            north=args.north,
            west=args.west,
            east=args.east,
            output=args.output,
            api_key=args.api_key,
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Saved COP30 DEM to: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

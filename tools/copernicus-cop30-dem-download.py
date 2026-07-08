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
import math
import os
import sys
from pathlib import Path

import requests
from pyproj import CRS, Transformer

from sprtz.terrain.regrid import DomainDefinition, aoi_bounds


OPENTOPO_GLOBALDEM_URL = "https://portal.opentopography.org/API/globaldem"


def _domain_from_bbox(args: argparse.Namespace) -> DomainDefinition:
    if (args.center_lat is None) != (args.center_lon is None):
        raise ValueError("--center-lat and --center-lon must be supplied together")
    if args.dx is None:
        raise ValueError("--dx is required when deriving a terrain domain from bounds")
    if (args.nx is None) != (args.ny is None):
        raise ValueError("--nx and --ny must be supplied together")

    south = float(args.south)
    north = float(args.north)
    west = float(args.west)
    east = float(args.east)
    center_lat = (south + north) / 2.0 if args.center_lat is None else float(args.center_lat)
    center_lon = (west + east) / 2.0 if args.center_lon is None else float(args.center_lon)
    dx_m = float(args.dx)
    dy_m = float(args.dy if args.dy is not None else args.dx)
    nx = int(args.nx) if args.nx is not None else None
    ny = int(args.ny) if args.ny is not None else None

    if nx is None or ny is None:
        # Compute the smallest symmetric local AEQD grid whose snapped spacing
        # fully covers the requested geographic bounds.
        local_crs = CRS.from_proj4(
            f"+proj=aeqd +lat_0={center_lat:.12f} +lon_0={center_lon:.12f} "
            "+datum=WGS84 +units=m +no_defs"
        )
        to_local = Transformer.from_crs(CRS.from_epsg(4326), local_crs, always_xy=True)
        corner_x, corner_y = to_local.transform(
            [west, west, east, east],
            [south, north, south, north],
        )
        half_width_m = max(abs(float(value)) for value in corner_x)
        half_height_m = max(abs(float(value)) for value in corner_y)
        nx = int(math.ceil((2.0 * half_width_m) / dx_m)) + 1
        ny = int(math.ceil((2.0 * half_height_m) / dy_m)) + 1
        if nx % 2 == 0:
            nx += 1
        if ny % 2 == 0:
            ny += 1

    return DomainDefinition(
        center_lat=center_lat,
        center_lon=center_lon,
        nx=nx,
        ny=ny,
        dx_m=dx_m,
        dy_m=dy_m,
        projection=str(args.projection),
        buffer_m=float(args.buffer_m),
    )


def resolve_bbox(args: argparse.Namespace) -> tuple[float, float, float, float]:
    explicit = [args.south, args.north, args.west, args.east]
    if all(value is not None for value in explicit):
        south = float(args.south)
        north = float(args.north)
        west = float(args.west)
        east = float(args.east)
        validate_bbox(south, north, west, east)
        grid = [args.nx, args.ny, args.dx, args.dy, args.center_lat, args.center_lon]
        if any(value is not None for value in grid):
            west, south, east, north = aoi_bounds(
                _domain_from_bbox(args)
            )
            validate_bbox(south, north, west, east)
        return south, north, west, east
    if any(value is not None for value in explicit):
        raise ValueError(
            "--south, --north, --west, and --east must be supplied together"
        )
    required = [args.center_lat, args.center_lon, args.nx, args.ny, args.dx]
    if any(value is None for value in required):
        raise ValueError(
            "supply either --south/--north/--west/--east or "
            "--center-lat/--center-lon/--nx/--ny/--dx"
        )
    west, south, east, north = aoi_bounds(
        DomainDefinition(
            center_lat=float(args.center_lat),
            center_lon=float(args.center_lon),
            nx=int(args.nx),
            ny=int(args.ny),
            dx_m=float(args.dx),
            dy_m=float(args.dy if args.dy is not None else args.dx),
            projection=str(args.projection),
            buffer_m=float(args.buffer_m),
        )
    )
    validate_bbox(south, north, west, east)
    return south, north, west, east


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

    parser.add_argument("--south", type=float, default=None, help="Minimum latitude")
    parser.add_argument("--north", type=float, default=None, help="Maximum latitude")
    parser.add_argument("--west", type=float, default=None, help="Minimum longitude")
    parser.add_argument("--east", type=float, default=None, help="Maximum longitude")
    parser.add_argument("--center-lat", type=float, default=None, help="Terrain domain center latitude")
    parser.add_argument("--center-lon", type=float, default=None, help="Terrain domain center longitude")
    parser.add_argument("--nx", type=int, default=None, help="Terrain grid node count in x")
    parser.add_argument("--ny", type=int, default=None, help="Terrain grid node count in y")
    parser.add_argument("--dx", type=float, default=None, help="Terrain grid x spacing in metres")
    parser.add_argument("--dy", type=float, default=None, help="Terrain grid y spacing in metres; defaults to --dx")
    parser.add_argument("--projection", default="auto-utm", help="Terrain grid projection")
    parser.add_argument(
        "--buffer-m",
        type=float,
        default=1000.0,
        help="Extra source-raster buffer around the terrain grid in metres when using domain arguments",
    )

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
        south, north, west, east = resolve_bbox(args)
        path = download_cop30(
            south=south,
            north=north,
            west=west,
            east=east,
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

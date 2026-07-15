#!/usr/bin/env python3
"""
Download/crop Copernicus Global Land Cover 100 m discrete classification
for a latitude/longitude bounding box.

Example:
    python3 tools/copernicus-lc100-download.py \
      --south 40.40 \
      --north 41.10 \
      --west 13.80 \
      --east 14.80 \
      --output data/landcover/lc100_naples.tif

Requirements:
    GDAL command-line tools must be installed, especially gdalwarp.

Ubuntu/Debian:
    sudo apt install gdal-bin

Conda:
    conda install -c conda-forge gdal
"""

import argparse
import math
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

from pyproj import CRS, Transformer

from sprtz.terrain.regrid import DomainDefinition, aoi_bounds

COPERNICUS_LC100_2019_URL = (
    "https://zenodo.org/api/records/3939050/files/"
    "PROBAV_LC100_global_v3.0.1_2019-nrt_"
    "Discrete-Classification-map_EPSG-4326.tif/content"
)


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Crop Copernicus Global Land Cover 100 m discrete classification "
            "to a WGS84 latitude/longitude bounding box."
        )
    )

    parser.add_argument("--south", type=float, default=None, help="Southern latitude")
    parser.add_argument("--north", type=float, default=None, help="Northern latitude")
    parser.add_argument("--west", type=float, default=None, help="Western longitude")
    parser.add_argument("--east", type=float, default=None, help="Eastern longitude")
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
    parser.add_argument("--output", required=True, help="Output GeoTIFF path")

    parser.add_argument(
        "--source-url",
        default=COPERNICUS_LC100_2019_URL,
        help="Remote Copernicus LC100 GeoTIFF URL",
    )

    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite output file if it already exists",
    )

    return parser.parse_args()


def validate_bbox(south, north, west, east):
    if south >= north:
        raise ValueError("--south must be smaller than --north")

    if west >= east:
        raise ValueError("--west must be smaller than --east")

    if not (-90 <= south <= 90 and -90 <= north <= 90):
        raise ValueError("Latitude values must be between -90 and 90")

    if not (-180 <= west <= 180 and -180 <= east <= 180):
        raise ValueError("Longitude values must be between -180 and 180")


def _domain_from_bbox(args) -> DomainDefinition:
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


def resolve_bbox(args):
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


def main():
    args = parse_args()
    south, north, west, east = resolve_bbox(args)

    if shutil.which("gdalwarp") is None:
        print(
            "ERROR: gdalwarp was not found. Install GDAL first.",
            file=sys.stderr,
        )
        sys.exit(1)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    target = output
    replace_target = False
    if output.exists() and not args.overwrite:
        target = output.with_name(f".{output.name}.{uuid.uuid4().hex}.tmp{output.suffix}")
        replace_target = True

    source = f"/vsicurl/{args.source_url}"

    command = [
        "gdalwarp",
        "-te",
        str(west),
        str(south),
        str(east),
        str(north),
        "-te_srs",
        "EPSG:4326",
        "-t_srs",
        "EPSG:4326",
        "-r",
        "near",
        "-co",
        "COMPRESS=DEFLATE",
        "-co",
        "TILED=YES",
        "-co",
        "BIGTIFF=IF_SAFER",
    ]

    if args.overwrite:
        command.append("-overwrite")

    command.extend(
        [
            source,
            str(target),
        ]
    )

    print("Running:")
    print(" ".join(command))

    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as exc:
        if replace_target and target.exists():
            target.unlink()
        print(
            f"ERROR: gdalwarp failed with exit code {exc.returncode}",
            file=sys.stderr,
        )
        sys.exit(exc.returncode)

    if replace_target:
        target.replace(output)

    print(f"Written: {output}")


if __name__ == "__main__":
    main()

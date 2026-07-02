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
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

COPERNICUS_LC100_2019_URL = (
    "https://zenodo.org/records/3939050/files/"
    "PROBAV_LC100_global_v3.0.1_2019-nrt_"
    "Discrete-Classification-map_EPSG-4326.tif?download=1"
)


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Crop Copernicus Global Land Cover 100 m discrete classification "
            "to a WGS84 latitude/longitude bounding box."
        )
    )

    parser.add_argument("--south", type=float, required=True, help="Southern latitude")
    parser.add_argument("--north", type=float, required=True, help="Northern latitude")
    parser.add_argument("--west", type=float, required=True, help="Western longitude")
    parser.add_argument("--east", type=float, required=True, help="Eastern longitude")
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


def validate_bbox(args):
    if args.south >= args.north:
        raise ValueError("--south must be smaller than --north")

    if args.west >= args.east:
        raise ValueError("--west must be smaller than --east")

    if not (-90 <= args.south <= 90 and -90 <= args.north <= 90):
        raise ValueError("Latitude values must be between -90 and 90")

    if not (-180 <= args.west <= 180 and -180 <= args.east <= 180):
        raise ValueError("Longitude values must be between -180 and 180")


def main():
    args = parse_args()
    validate_bbox(args)

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
        str(args.west),
        str(args.south),
        str(args.east),
        str(args.north),
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

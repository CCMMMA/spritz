#!/usr/bin/env python3
"""Download a Sentinel-5P L2 atmospheric subset from Copernicus Data Space."""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path

import requests

from sprtz.logging import configure_logging

LOGGER = logging.getLogger(__name__)
TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
PROCESS_URL = "https://sh.dataspace.copernicus.eu/api/v1/process"


class EmptySentinel5PSubsetError(RuntimeError):
    """Raised when Sentinel Hub returns a raster with no usable pixels."""


def main(argv: list[str] | None = None, *, prog: str | None = None) -> int:
    parser = argparse.ArgumentParser(prog=prog, description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--bbox", nargs=4, type=float, required=True, metavar=("WEST", "SOUTH", "EAST", "NORTH"))
    parser.add_argument("--time-start", required=True, help="ISO-8601 UTC start")
    parser.add_argument("--time-end", required=True, help="ISO-8601 UTC end")
    parser.add_argument("--width", type=int, default=256)
    parser.add_argument("--height", type=int, default=256)
    parser.add_argument(
        "--band",
        choices=("AER_AI_340_380", "AER_AI_354_388", "NO2", "CO"),
        default="AER_AI_340_380",
        help="Sentinel-5P L2 band; aerosol index is the smoke-plume default",
    )
    parser.add_argument(
        "--min-qa",
        type=int,
        default=None,
        help="Sentinel Hub minimum QA filter; defaults to 75 for NO2 and 50 for aerosol index/CO",
    )
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help=(
            "write the GeoTIFF even when post-download validation finds no finite "
            "pixels; intended only for negative-provenance/debug downloads"
        ),
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    configure_logging(args.verbose)

    min_qa = args.min_qa if args.min_qa is not None else (75 if args.band == "NO2" else 50)
    if not 0 <= min_qa <= 100:
        parser.error("--min-qa must be between 0 and 100")

    request_body = {
        "input": {
            "bounds": {"bbox": args.bbox, "properties": {"crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84"}},
            "data": [{
                "type": "sentinel-5p-l2",
                "dataFilter": {
                    "timeRange": {"from": args.time_start, "to": args.time_end},
                    "timeliness": "OFFL",
                },
                "processing": {"minQa": int(min_qa)},
            }],
        },
        "output": {
            "width": args.width,
            "height": args.height,
            "responses": [{"identifier": "default", "format": {"type": "image/tiff"}}],
        },
        "evalscript": (
            "//VERSION=3\n"
            f"function setup(){{return {{input:[{{bands:[\"{args.band}\",\"dataMask\"]}}],"
            "output:{bands:1,sampleType:\"FLOAT32\"}};}\n"
            f"function evaluatePixel(s){{return [s.dataMask ? s.{args.band} : NaN];}}\n"
        ),
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.with_suffix(output.suffix + ".request.json").write_text(
        json.dumps(request_body, indent=2) + "\n", encoding="utf-8"
    )
    if args.dry_run:
        LOGGER.info("Wrote request plan for %s", output)
        return 0

    client_id = os.environ.get("CDSE_CLIENT_ID")
    client_secret = os.environ.get("CDSE_CLIENT_SECRET")
    if not client_id or not client_secret:
        parser.error("CDSE_CLIENT_ID and CDSE_CLIENT_SECRET are required unless --dry-run is used")
    token_response = requests.post(
        TOKEN_URL,
        data={"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret},
        timeout=60,
    )
    token_response.raise_for_status()
    token = token_response.json()["access_token"]
    response = requests.post(
        PROCESS_URL,
        json=request_body,
        headers={"Authorization": f"Bearer {token}"},
        timeout=300,
    )
    response.raise_for_status()
    temporary = output.with_suffix(output.suffix + ".part")
    temporary.write_bytes(response.content)
    try:
        finite_pixels = _validate_downloaded_raster(
            temporary,
            band=args.band,
            allow_empty=args.allow_empty,
        )
    except EmptySentinel5PSubsetError as exc:
        temporary.unlink(missing_ok=True)
        parser.exit(2, f"{parser.prog}: error: {exc}\n")
    temporary.replace(output)
    LOGGER.info(
        "Wrote Sentinel-5P L2 %s subset to %s finite_pixels=%s",
        args.band,
        output,
        finite_pixels if finite_pixels is not None else "unchecked",
    )
    return 0


def _validate_downloaded_raster(
    path: Path,
    *,
    band: str,
    allow_empty: bool = False,
) -> int | None:
    """Return the finite-pixel count for a downloaded GeoTIFF.

    Sentinel Hub can validly return HTTP 200 and a syntactically valid GeoTIFF
    whose requested band is entirely masked for the selected product, bbox, time
    range, and QA filter. That file is useful as negative provenance, but it is
    not useful as satellite evidence for the use-case alignment stage.
    """

    try:
        import numpy as np
        import rasterio
    except Exception as exc:  # pragma: no cover - depends on optional geo stack
        LOGGER.warning(
            "Could not validate downloaded Sentinel-5P raster because rasterio/numpy "
            "is unavailable: %s",
            exc,
        )
        return None

    with rasterio.open(path) as dataset:
        values = dataset.read(1).astype(float)
        if dataset.nodata is not None:
            values[values == dataset.nodata] = np.nan
        finite_pixels = int(np.isfinite(values).sum())

    if finite_pixels == 0 and not allow_empty:
        raise EmptySentinel5PSubsetError(
            f"Sentinel-5P L2 {band} download produced a GeoTIFF with zero finite pixels. "
            "The HTTP request succeeded, but Sentinel Hub returned only masked/NaN "
            "samples for this bbox, time range, band, and QA filter. Retry with a "
            "wider scientifically justified bbox/time window, or keep this file only "
            "as negative provenance by passing --allow-empty. Do not use an all-empty "
            "raster for satellite alignment or validation."
        )
    if finite_pixels == 0:
        LOGGER.warning(
            "Sentinel-5P L2 %s raster has zero finite pixels; keeping it because "
            "--allow-empty was supplied",
            band,
        )
    return finite_pixels


if __name__ == "__main__":
    raise SystemExit(main())

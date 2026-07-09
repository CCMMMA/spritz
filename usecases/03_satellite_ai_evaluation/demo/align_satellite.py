#!/usr/bin/env python3
"""Conservatively downscale Sentinel-5P aerosol index to the Spritz domain."""

from __future__ import annotations

import argparse
import logging
import math
from pathlib import Path

import numpy as np

from sprtz.config import load_config
from sprtz.io.jsonio import write_json
from sprtz.logging import configure_logging

LOGGER = logging.getLogger(__name__)


def _coarse_labels(source_shape: tuple[int, int], target_shape: tuple[int, int]) -> tuple[np.ndarray, np.ndarray]:
    """Map target-cell centres to source pixels on the same bounding box."""
    sy, sx = source_shape
    ty, tx = target_shape
    rows = np.minimum((np.arange(ty) + 0.5) * sy / ty, sy - 1).astype(int)
    cols = np.minimum((np.arange(tx) + 0.5) * sx / tx, sx - 1).astype(int)
    return np.meshgrid(rows, cols, indexing="ij")


def conservative_downscale(
    coarse: np.ndarray,
    target_shape: tuple[int, int],
    weights: np.ndarray,
    *,
    smoothing_iterations: int = 2,
) -> tuple[np.ndarray, dict[str, float]]:
    """Allocate coarse values with positive weights and exact coarse-cell means."""
    if coarse.ndim != 2 or weights.shape != target_shape:
        raise ValueError("coarse and target weights must be two-dimensional")
    labels_y, labels_x = _coarse_labels(coarse.shape, target_shape)
    valid = np.isfinite(coarse)
    field = np.zeros(target_shape, dtype=float)
    positive_weights = np.maximum(np.asarray(weights, dtype=float), 1.0e-12)

    # Each coarse observation is an areal constraint. Distribute it only among
    # target cells assigned to that footprint, then normalize their mean back
    # to the observed value.
    for row in range(coarse.shape[0]):
        for col in range(coarse.shape[1]):
            members = (labels_y == row) & (labels_x == col)
            if not members.any() or not valid[row, col]:
                field[members] = np.nan
                continue
            local = positive_weights[members]
            field[members] = float(coarse[row, col]) * local / float(np.mean(local))

    # A small seamless regularization reduces block edges. Hard normalization
    # after every pass prevents smoothing from changing coarse-pixel means.
    for _ in range(max(0, smoothing_iterations)):
        padded = np.pad(field, 1, mode="edge")
        neighbours = np.stack((
            padded[1:-1, 1:-1],
            padded[:-2, 1:-1],
            padded[2:, 1:-1],
            padded[1:-1, :-2],
            padded[1:-1, 2:],
        ))
        kernel = np.asarray([4.0, 1.0, 1.0, 1.0, 1.0])[:, None, None]
        finite = np.isfinite(neighbours)
        smooth = np.sum(np.where(finite, neighbours, 0.0) * kernel, axis=0) / np.maximum(
            np.sum(finite * kernel, axis=0), 1.0
        )
        smooth[~np.isfinite(field)] = np.nan
        for row in range(coarse.shape[0]):
            for col in range(coarse.shape[1]):
                members = (labels_y == row) & (labels_x == col)
                if not members.any() or not valid[row, col]:
                    continue
                local_mean = float(np.nanmean(smooth[members]))
                if abs(local_mean) > np.finfo(float).eps:
                    smooth[members] *= float(coarse[row, col]) / local_mean
        field = smooth

    errors = []
    for row in range(coarse.shape[0]):
        for col in range(coarse.shape[1]):
            members = (labels_y == row) & (labels_x == col)
            if members.any() and valid[row, col]:
                errors.append(abs(float(np.nanmean(field[members])) - float(coarse[row, col])))
    return field, {
        "maximum_coarse_mean_error": max(errors, default=0.0),
        "mean_coarse_mean_error": float(np.mean(errors)) if errors else 0.0,
    }


def _spritz_domain_bbox(cfg) -> tuple[float, float, float, float]:
    """Return an approximate lon/lat bbox for the Spritz concentration field."""
    if not cfg.sources:
        raise ValueError("configuration must contain at least one source with longitude/latitude")
    source = cfg.sources[0]
    lon0 = float(source.longitude)
    lat0 = float(source.latitude)
    metres_per_degree_lat = 111_320.0
    metres_per_degree_lon = metres_per_degree_lat * math.cos(math.radians(lat0))
    if abs(metres_per_degree_lon) < 1.0:
        raise ValueError("cannot derive local longitude scale near the pole")

    x_min = float(cfg.grid.x0) - 0.5 * float(cfg.grid.dx)
    x_max = float(cfg.grid.x0) + (int(cfg.grid.nx) - 1) * float(cfg.grid.dx) + 0.5 * float(cfg.grid.dx)
    y_min = float(cfg.grid.y0) - 0.5 * float(cfg.grid.dy)
    y_max = float(cfg.grid.y0) + (int(cfg.grid.ny) - 1) * float(cfg.grid.dy) + 0.5 * float(cfg.grid.dy)
    west = lon0 + x_min / metres_per_degree_lon
    east = lon0 + x_max / metres_per_degree_lon
    south = lat0 + y_min / metres_per_degree_lat
    north = lat0 + y_max / metres_per_degree_lat
    return min(west, east), min(south, north), max(west, east), max(south, north)


def _read_domain_subset(dataset, bbox: tuple[float, float, float, float]) -> tuple[np.ndarray, dict[str, object]]:
    """Read the satellite subset overlapping the Spritz domain bbox."""
    import rasterio.windows

    west, south, east, north = bbox
    bounds = dataset.bounds
    overlap_west = max(west, bounds.left)
    overlap_south = max(south, bounds.bottom)
    overlap_east = min(east, bounds.right)
    overlap_north = min(north, bounds.top)
    if overlap_west >= overlap_east or overlap_south >= overlap_north:
        raise ValueError(
            "satellite raster does not overlap the Spritz domain bbox "
            f"{bbox}; raster bounds are {tuple(bounds)}"
        )

    window = rasterio.windows.from_bounds(
        overlap_west,
        overlap_south,
        overlap_east,
        overlap_north,
        transform=dataset.transform,
    ).round_offsets().round_lengths()
    window = window.intersection(rasterio.windows.Window(0, 0, dataset.width, dataset.height))
    coarse = np.asarray(dataset.read(1, window=window), dtype=float)
    transform = dataset.window_transform(window)
    metadata = {
        "domain_bbox_wgs84": list(bbox),
        "source_bounds": [bounds.left, bounds.bottom, bounds.right, bounds.top],
        "subset_bounds": [
            overlap_west,
            overlap_south,
            overlap_east,
            overlap_north,
        ],
        "source_window": [
            int(window.col_off),
            int(window.row_off),
            int(window.width),
            int(window.height),
        ],
        "subset_transform": tuple(transform)[:6],
    }
    return coarse, metadata


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--satellite", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--satellite-time", required=True)
    parser.add_argument("--event-end", required=True)
    parser.add_argument("--wind-from-deg", type=float, default=270.0)
    parser.add_argument("--smoothing-iterations", type=int, default=2)
    args = parser.parse_args(argv)
    configure_logging(False)
    try:
        import rasterio
    except ImportError as exc:
        parser.error(f"satellite downscaling requires the geo optional dependencies: {exc}")

    cfg = load_config(args.config)
    with rasterio.open(args.satellite) as dataset:
        domain_bbox = _spritz_domain_bbox(cfg)
        coarse, subset_metadata = _read_domain_subset(dataset, domain_bbox)
        if dataset.nodata is not None:
            coarse[coarse == dataset.nodata] = np.nan
        source_crs = str(dataset.crs)
        source_transform = tuple(dataset.transform)[:6]
    if not np.isfinite(coarse).any():
        parser.error(
            "satellite raster contains no valid aerosol-index pixels. "
            "The Sentinel Hub request returned only NaN/dataMask=0 samples for "
            "this bbox, time window, band, and QA filter. Re-download with a "
            "larger output grid such as --width 32 --height 32, inspect the "
            ".request.json file, and if needed relax the downloader QA filter "
            "with --min-qa 0 or widen the time/bbox window. Do not treat an "
            "all-NaN raster as satellite validation."
        )

    ny, nx = cfg.grid.ny, cfg.grid.nx
    x = cfg.grid.x0 + np.arange(nx) * cfg.grid.dx
    y = cfg.grid.y0 + np.arange(ny) * cfg.grid.dy
    xx, yy = np.meshgrid(x, y)
    theta = np.deg2rad((270.0 - args.wind_from_deg) % 360.0)
    along = xx * np.cos(theta) + yy * np.sin(theta)
    cross = -xx * np.sin(theta) + yy * np.cos(theta)
    domain_scale = max(nx * cfg.grid.dx, ny * cfg.grid.dy, 1.0)
    plume_weight = 1.0 + 0.35 * np.exp(
        -0.5 * (cross / (0.22 * domain_scale)) ** 2
    ) * np.exp(-np.maximum(along, 0.0) / domain_scale)
    field, conservation = conservative_downscale(
        coarse,
        (ny, nx),
        plume_weight,
        smoothing_iterations=args.smoothing_iterations,
    )

    valid = np.isfinite(field)
    low, high = np.nanpercentile(field, [5.0, 95.0])
    scale = max(float(high - low), np.finfo(float).eps)
    probability = np.clip((field - low) / scale, 0.0, 1.0)
    probability[~valid] = 0.0
    receptor_rows = []
    for receptor in cfg.receptors:
        col = int(round((receptor.x - cfg.grid.x0) / cfg.grid.dx))
        row = int(round((receptor.y - cfg.grid.y0) / cfg.grid.dy))
        if not (0 <= row < ny and 0 <= col < nx):
            parser.error(f"receptor {receptor.id} lies outside the target grid")
        receptor_rows.append(float(probability[row, col]))

    write_json(args.output, {
        "mask": [receptor_rows],
        "downscaled_field": probability.tolist(),
        "raw_downscaled_aerosol_index": [
            [None if not np.isfinite(value) else float(value) for value in row]
            for row in field
        ],
        "provenance": {
            "source": "Copernicus Sentinel-5P TROPOMI L2 AER_AI_340_380",
            "satellite_path": str(Path(args.satellite)),
            "satellite_time_utc": args.satellite_time,
            "event_end_utc": args.event_end,
            "source_crs": source_crs,
            "source_transform": source_transform,
            **subset_metadata,
            "source_shape": list(coarse.shape),
            "target_shape": [ny, nx],
            "method": "clean-room conservative ancillary-weight allocation",
            "weighting": "bounded downwind plume-coordinate weight",
            "smoothing_iterations": args.smoothing_iterations,
            "normalization": "target-field valid-sample 5th-to-95th percentile",
            **conservation,
        },
    })
    LOGGER.info(
        "Downscaled aerosol index to %dx%d; maximum conservation error %.3g",
        ny, nx, conservation["maximum_coarse_mean_error"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

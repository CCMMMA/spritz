#!/usr/bin/env python3
"""Conservatively downscale Sentinel-5P aerosol index to the Spritz domain."""

from __future__ import annotations

import argparse
import csv
import logging
import math
from pathlib import Path

import numpy as np

from sprtz.config import load_config
from sprtz.io.jsonio import write_json
from sprtz.logging import configure_logging
from sprtz.terrain.landuse import derive_surface_parameters, land_cover_mapping, remap_land_cover

LOGGER = logging.getLogger(__name__)


def _robust_standardize(values: np.ndarray) -> np.ndarray:
    """Return a bounded, robustly standardized finite grid."""
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        raise ValueError("ancillary raster contains no finite target-grid values")
    median = float(np.median(finite))
    low, high = np.percentile(finite, [10.0, 90.0])
    scale = max(float(high - low), np.finfo(float).eps)
    return np.clip((np.where(np.isfinite(values), values, median) - median) / scale, -2.0, 2.0)


def _read_ancillary_on_grid(path: str | Path, cfg, *, categorical: bool) -> tuple[np.ndarray, np.ndarray]:
    """Reproject an ancillary raster to the exact south-to-north Spritz grid."""
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.transform import from_bounds
    from rasterio.warp import reproject

    west, south, east, north = _spritz_domain_bbox(cfg)
    # Raster rows conventionally run north-to-south. Reproject in that native
    # orientation, then flip once so row zero agrees with Spritz y0 (south).
    destination = np.full((cfg.grid.ny, cfg.grid.nx), np.nan, dtype=float)
    destination_transform = from_bounds(west, south, east, north, cfg.grid.nx, cfg.grid.ny)
    with rasterio.open(path) as dataset:
        source = np.asarray(dataset.read(1), dtype=float)
        if dataset.nodata is not None:
            source[source == dataset.nodata] = np.nan
        reproject(
            source=source,
            destination=destination,
            src_transform=dataset.transform,
            src_crs=dataset.crs,
            src_nodata=np.nan,
            dst_transform=destination_transform,
            dst_crs="EPSG:4326",
            dst_nodata=np.nan,
            resampling=Resampling.nearest if categorical else Resampling.bilinear,
        )
    result = np.flipud(destination)
    coverage = np.isfinite(result)
    # Buffered ancillary downloads can end a few cells short of an expanded
    # target bbox. Extend the nearest valid edge instead of introducing an
    # artificial constant-fill boundary into the downscaled field.
    columns = np.arange(result.shape[1])
    for row in range(result.shape[0]):
        valid = np.isfinite(result[row])
        if valid.any():
            result[row] = np.interp(columns, columns[valid], result[row, valid])
    rows = np.arange(result.shape[0])
    for col in range(result.shape[1]):
        valid = np.isfinite(result[:, col])
        if valid.any():
            result[:, col] = np.interp(rows, rows[valid], result[valid, col])
    return (np.rint(result) if categorical else result), coverage


def _terrain_land_cover_weight(
    dem_path: str | Path,
    land_cover_path: str | Path,
    cfg,
) -> tuple[np.ndarray, dict[str, object]]:
    """Build bounded 100 m terrain and surface-roughness allocation weights."""
    dem, dem_coverage = _read_ancillary_on_grid(dem_path, cfg, categorical=False)
    source_land_cover, land_cover_coverage = _read_ancillary_on_grid(land_cover_path, cfg, categorical=True)
    if not np.isfinite(source_land_cover).any():
        raise ValueError("land-cover raster contains no valid target-grid cells")
    fill_class = int(np.nanmedian(source_land_cover))
    source_classes = np.rint(np.where(np.isfinite(source_land_cover), source_land_cover, fill_class)).astype(int)
    landuse = remap_land_cover(source_classes, land_cover_mapping("copernicus-lc100"))
    roughness = derive_surface_parameters(landuse)["roughness_length_m"]

    # Elevation, local slope, and land-cover roughness contribute independent
    # bounded anomalies. These are allocation covariates, not a retrieval or a
    # claim that terrain changes the satellite column measurement itself.
    dem_filled = np.where(np.isfinite(dem), dem, np.nanmedian(dem))
    gradient_y, gradient_x = np.gradient(dem_filled, cfg.grid.dy, cfg.grid.dx)
    slope = np.hypot(gradient_x, gradient_y)
    feature = (
        0.20 * _robust_standardize(dem_filled)
        + 0.30 * _robust_standardize(slope)
        + 0.35 * _robust_standardize(np.log(np.maximum(roughness, 1.0e-4)))
    )
    weight = np.clip(np.exp(feature), 0.35, 2.85)
    # Feather ancillary influence to neutral across uncovered edge cells. This
    # avoids extending the final valid DEM/LC row as artificial stripes.
    feather = (dem_coverage & land_cover_coverage).astype(float)
    for _ in range(30):
        padded = np.pad(feather, 1, mode="edge")
        feather = (
            4.0 * padded[1:-1, 1:-1]
            + padded[:-2, 1:-1]
            + padded[2:, 1:-1]
            + padded[1:-1, :-2]
            + padded[1:-1, 2:]
        ) / 8.0
    weight = 1.0 + feather * (weight - 1.0)
    return weight, {
        "dem_path": str(Path(dem_path)),
        "land_cover_path": str(Path(land_cover_path)),
        "dem_used_for_satellite_downscaling": True,
        "land_cover_used_for_satellite_downscaling": True,
        "land_cover_mapping": "copernicus-lc100",
        "ancillary_resampling_dem": "bilinear",
        "ancillary_resampling_land_cover": "nearest",
        "terrain_weight_min": float(np.min(weight)),
        "terrain_weight_max": float(np.max(weight)),
        "ancillary_joint_coverage_fraction": float(np.mean(dem_coverage & land_cover_coverage)),
    }


def seamless_regularize(field: np.ndarray, radius_cells: int = 10, blend: float = 0.85) -> np.ndarray:
    """Suppress coarse-pixel seams with a finite-aware square low-pass blend."""
    if radius_cells < 1 or not 0.0 <= blend <= 1.0:
        raise ValueError("deblocking radius must be positive and blend must be between zero and one")

    def box_sum(values: np.ndarray, radius: int, axis: int) -> np.ndarray:
        padded = np.pad(values, ((radius, radius), (0, 0)) if axis == 0 else ((0, 0), (radius, radius)))
        cumulative = np.cumsum(padded, axis=axis, dtype=float)
        zero_shape = list(cumulative.shape)
        zero_shape[axis] = 1
        cumulative = np.concatenate((np.zeros(zero_shape), cumulative), axis=axis)
        width = 2 * radius + 1
        if axis == 0:
            return cumulative[width:, :] - cumulative[:-width, :]
        return cumulative[:, width:] - cumulative[:, :-width]

    valid = np.isfinite(field)
    values = np.where(valid, field, 0.0)
    numerator = box_sum(box_sum(values, radius_cells, 0), radius_cells, 1)
    denominator = box_sum(box_sum(valid.astype(float), radius_cells, 0), radius_cells, 1)
    smooth = np.divide(numerator, denominator, out=np.zeros_like(field), where=denominator > 0.0)
    result = (1.0 - blend) * values + blend * smooth
    result[~valid] = np.nan
    # Preserve the domain-wide finite mean while intentionally relaxing exact
    # per-Sentinel-pixel means; exact footprint projection would recreate seams.
    result += float(np.nanmean(field) - np.nanmean(result))
    return result


def _station_correction(
    path: str | Path,
    base_field: np.ndarray,
    cfg,
    *,
    alpha: float = 0.65,
    radius_m: float = 20_000.0,
    power: float = 2.0,
) -> tuple[np.ndarray, dict[str, object]]:
    """Build a bounded IDW correction from station-pattern residuals.

    Station NO2 and satellite aerosol index are different physical quantities,
    so only their independently robust-scaled spatial anomalies are compared.
    The result modifies fine-grid allocation weights; the subsequent
    conservative normalization still preserves every satellite-pixel mean.
    """
    if not 0.0 <= alpha <= 1.0:
        raise ValueError("station alpha must be between zero and one")
    if radius_m <= 0.0 or power <= 0.0:
        raise ValueError("station radius and power must be positive")
    source = cfg.sources[0]
    lat0, lon0 = float(source.latitude), float(source.longitude)
    metres_per_degree_lat = 111_320.0
    metres_per_degree_lon = metres_per_degree_lat * math.cos(math.radians(lat0))
    stations: list[tuple[str, float, float, float, float]] = []
    with Path(path).open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        columns = {str(name).strip().upper(): name for name in (reader.fieldnames or [])}
        missing = {"LAT", "LON", "NO2"} - columns.keys()
        if missing:
            raise ValueError(f"station CSV is missing columns: {', '.join(sorted(missing))}")
        id_column = columns.get("ID")
        for index, row in enumerate(reader, start=2):
            try:
                lat = float(row[columns["LAT"]])
                lon = float(row[columns["LON"]])
                value = float(row[columns["NO2"]])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"invalid station value on CSV row {index}") from exc
            x = (lon - lon0) * metres_per_degree_lon
            y = (lat - lat0) * metres_per_degree_lat
            col = int(round((x - cfg.grid.x0) / cfg.grid.dx))
            row_index = int(round((y - cfg.grid.y0) / cfg.grid.dy))
            if np.isfinite(value) and 0 <= row_index < cfg.grid.ny and 0 <= col < cfg.grid.nx:
                station_id = str(row[id_column]).strip() if id_column else f"row_{index}"
                predicted = float(base_field[row_index, col])
                if np.isfinite(predicted):
                    stations.append((station_id, x, y, value, predicted))
    if not stations:
        return np.ones(base_field.shape), {
            "station_observations_used": 0,
            "station_correction_status": "no_valid_in_domain_overlap",
        }

    observed = np.asarray([station[3] for station in stations], dtype=float)
    predicted = np.asarray([station[4] for station in stations], dtype=float)

    def robust01(values: np.ndarray) -> np.ndarray:
        low, high = np.percentile(values, [5.0, 95.0])
        span = max(float(high - low), np.finfo(float).eps)
        return np.clip((values - low) / span, 0.0, 1.0)

    residuals = robust01(observed) - robust01(predicted)
    x = cfg.grid.x0 + np.arange(cfg.grid.nx) * cfg.grid.dx
    y = cfg.grid.y0 + np.arange(cfg.grid.ny) * cfg.grid.dy
    xx, yy = np.meshgrid(x, y)
    numerator = np.zeros(base_field.shape, dtype=float)
    denominator = np.zeros(base_field.shape, dtype=float)
    for station, residual in zip(stations, residuals):
        distance = np.hypot(xx - station[1], yy - station[2])
        influence = np.maximum(1.0 - distance / radius_m, 0.0)
        weight = influence / np.maximum(distance, max(cfg.grid.dx, cfg.grid.dy) * 0.5) ** power
        numerator += weight * residual
        denominator += weight
    residual_field = np.divide(numerator, denominator, out=np.zeros_like(numerator), where=denominator > 0.0)
    correction = np.clip(np.exp(alpha * residual_field), 0.5, 2.0)
    return correction, {
        "station_observations_used": len(stations),
        "station_ids_used": [station[0] for station in stations],
        "station_correction_status": "applied",
        "station_correction_method": "clean-room robust-anomaly residual IDW",
        "station_observation_field": "NO2",
        "station_alpha": alpha,
        "station_idw_radius_m": radius_m,
        "station_idw_power": power,
        "station_correction_min": float(np.min(correction)),
        "station_correction_max": float(np.max(correction)),
        "cross_quantity_note": "NO2 and aerosol index are scaled independently; stations constrain spatial pattern only",
    }


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


def _coarse_mean_errors(coarse: np.ndarray, field: np.ndarray) -> dict[str, float]:
    labels_y, labels_x = _coarse_labels(coarse.shape, field.shape)
    errors: list[float] = []
    for row in range(coarse.shape[0]):
        for col in range(coarse.shape[1]):
            members = (labels_y == row) & (labels_x == col)
            if members.any() and np.isfinite(coarse[row, col]):
                errors.append(abs(float(np.nanmean(field[members])) - float(coarse[row, col])))
    return {
        "maximum_coarse_mean_error": max(errors, default=0.0),
        "mean_coarse_mean_error": float(np.mean(errors)) if errors else 0.0,
    }


def _guided_seamless_downscale(coarse: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Interpolate the coarse field smoothly, then add fine ancillary structure."""
    sy, sx = coarse.shape
    ty, tx = weights.shape
    source_x = np.arange(sx, dtype=float)
    source_y = np.arange(sy, dtype=float)
    target_x = np.linspace(0.0, max(sx - 1, 0), tx)
    target_y = np.linspace(0.0, max(sy - 1, 0), ty)

    # Fill gaps only along valid samples before separable bilinear interpolation;
    # preserve an all-missing source row for the subsequent column pass.
    horizontal = np.full((sy, tx), np.nan, dtype=float)
    for row in range(sy):
        valid = np.isfinite(coarse[row])
        if valid.any():
            horizontal[row] = np.interp(target_x, source_x[valid], coarse[row, valid])
    baseline = np.full((ty, tx), np.nan, dtype=float)
    for col in range(tx):
        valid = np.isfinite(horizontal[:, col])
        if valid.any():
            baseline[:, col] = np.interp(target_y, source_y[valid], horizontal[valid, col])

    field = baseline * np.maximum(weights, 1.0e-12)
    # Retain the source-domain mean without reinstating individual source-pixel
    # rectangles. Terrain and LC100 therefore control sub-pixel spatial detail.
    field *= float(np.nanmean(coarse) / np.nanmean(field))
    return field


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
    parser.add_argument("--station-observations", help="Optional CSV with ID,LAT,LON,NO2 observations")
    parser.add_argument("--station-alpha", type=float, default=0.65)
    parser.add_argument("--station-idw-radius-m", type=float, default=20_000.0)
    parser.add_argument("--station-idw-power", type=float, default=2.0)
    parser.add_argument("--dem", help="High-resolution DEM GeoTIFF used as an allocation covariate")
    parser.add_argument("--land-cover", help="Copernicus LC100 raster used as an allocation covariate")
    parser.add_argument("--deblocking-radius-cells", type=int, default=12)
    parser.add_argument("--deblocking-blend", type=float, default=0.65)
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
    # GeoTIFF row zero is north, whereas the Spritz y axis starts in the south.
    # Flip exactly once before allocating source pixels to the target grid.
    coarse = np.flipud(coarse)
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
    terrain_metadata: dict[str, object] = {
        "dem_used_for_satellite_downscaling": False,
        "land_cover_used_for_satellite_downscaling": False,
    }
    if bool(args.dem) != bool(args.land_cover):
        parser.error("--dem and --land-cover must be supplied together")
    if args.dem and args.land_cover:
        try:
            terrain_weight, terrain_metadata = _terrain_land_cover_weight(args.dem, args.land_cover, cfg)
        except (OSError, ValueError) as exc:
            parser.error(str(exc))
        plume_weight *= terrain_weight
    field = _guided_seamless_downscale(coarse, plume_weight)
    station_metadata: dict[str, object] = {
        "station_observations_used": 0,
        "station_correction_status": "not_requested",
    }
    if args.station_observations:
        try:
            correction, station_metadata = _station_correction(
                args.station_observations,
                field,
                cfg,
                alpha=args.station_alpha,
                radius_m=args.station_idw_radius_m,
                power=args.station_idw_power,
            )
        except (OSError, ValueError) as exc:
            parser.error(str(exc))
        plume_weight *= correction
        field = _guided_seamless_downscale(coarse, plume_weight)

    try:
        field = seamless_regularize(
            field,
            radius_cells=args.deblocking_radius_cells,
            blend=args.deblocking_blend,
        )
    except ValueError as exc:
        parser.error(str(exc))
    conservation = _coarse_mean_errors(coarse, field)

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
            "source_row_orientation": "flipped from north-to-south GeoTIFF into south-to-north Spritz y",
            "method": "clean-room terrain-guided seamless ancillary-weight allocation",
            "weighting": "bounded downwind, DEM, LC100 roughness, and station residual covariates",
            **terrain_metadata,
            "station_observations_path": str(Path(args.station_observations)) if args.station_observations else None,
            **station_metadata,
            "smoothing_iterations": args.smoothing_iterations,
            "deblocking_radius_cells": args.deblocking_radius_cells,
            "deblocking_blend": args.deblocking_blend,
            "coarse_constraint_policy": "domain-mean preserving; per-pixel constraints relaxed by seamless deblocking",
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

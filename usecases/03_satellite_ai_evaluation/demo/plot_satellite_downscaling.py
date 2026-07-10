#!/usr/bin/env python3
"""Plot original and downscaled satellite fields with shared colors."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np

from sprtz.config import load_config
from sprtz.logging import configure_logging

LOGGER = logging.getLogger(__name__)


def shared_color_limits(original: np.ndarray, downscaled: np.ndarray) -> tuple[float, float]:
    """Return robust limits shared by both Aerosol Index fields."""
    values = np.concatenate((original[np.isfinite(original)], downscaled[np.isfinite(downscaled)]))
    if values.size == 0:
        raise ValueError("original and downscaled satellite fields contain no finite values")
    low, high = np.percentile(values, [2.0, 98.0])
    if high <= low:
        high = low + max(abs(float(low)) * 1.0e-6, np.finfo(float).eps)
    return float(low), float(high)


def _smooth_outline(values: np.ndarray, iterations: int = 16) -> np.ndarray:
    """Regularize model-grid noise before extracting a plume outline."""
    result = np.asarray(values, dtype=float).copy()
    for _ in range(iterations):
        padded = np.pad(result, 1, mode="edge")
        result = (
            4.0 * padded[1:-1, 1:-1]
            + padded[:-2, 1:-1]
            + padded[2:, 1:-1]
            + padded[1:-1, :-2]
            + padded[1:-1, 2:]
        ) / 8.0
    return result


def _read_model_plume(path: str | Path, time_index: int, level_index: int) -> np.ndarray:
    """Read one Spritz concentration slice as a normalized plume field."""
    try:
        from netCDF4 import Dataset
    except ImportError as exc:
        raise RuntimeError(f"model plume overlays require netCDF4: {exc}") from exc
    with Dataset(path) as dataset:
        if "concentration_field" not in dataset.variables:
            raise ValueError(f"{path} has no concentration_field variable")
        variable = dataset.variables["concentration_field"]
        if variable.ndim != 4:
            raise ValueError(f"{path} concentration_field must have time,z,y,x dimensions")
        if not 0 <= time_index < variable.shape[0] or not 0 <= level_index < variable.shape[1]:
            raise ValueError(f"model plume index is outside {path} shape {variable.shape}")
        field = np.asarray(variable[time_index, level_index], dtype=float)
    field = _smooth_outline(np.maximum(np.where(np.isfinite(field), field, 0.0), 0.0))
    maximum = float(np.max(field))
    if maximum <= 0.0:
        raise ValueError(f"{path} selected concentration slice has no positive plume")
    return field / maximum


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--satellite", required=True, help="Original satellite GeoTIFF")
    parser.add_argument("--downscaled", required=True, help="Aligned satellite JSON")
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--gaussian", required=True, help="Spritz Gaussian concentration NetCDF")
    parser.add_argument("--particles", required=True, help="Spritz particles concentration NetCDF")
    parser.add_argument("--model-time-index", type=int, default=1)
    parser.add_argument("--model-level-index", type=int, default=0)
    parser.add_argument("--plume-threshold", type=float, default=0.05, help="Fraction of each model plume maximum")
    parser.add_argument("--dpi", type=int, default=300)
    args = parser.parse_args(argv)
    configure_logging(False)
    try:
        import matplotlib.pyplot as plt
        import rasterio
        import rasterio.windows
    except ImportError as exc:
        parser.error(f"satellite plotting requires the geo and viz optional dependencies: {exc}")

    with Path(args.downscaled).open(encoding="utf-8") as stream:
        payload = json.load(stream)
    provenance = payload.get("provenance", {})
    try:
        window_values = provenance["source_window"]
        bbox = tuple(float(value) for value in provenance["domain_bbox_wgs84"])
        subset_bounds = tuple(float(value) for value in provenance["subset_bounds"])
        downscaled = np.asarray(payload["raw_downscaled_aerosol_index"], dtype=float)
    except (KeyError, TypeError, ValueError) as exc:
        parser.error(f"downscaled JSON lacks satellite plotting data: {exc}")
    if downscaled.ndim != 2:
        parser.error("downscaled Aerosol Index must be a 2-D array")

    window = rasterio.windows.Window(*window_values)
    with rasterio.open(args.satellite) as dataset:
        original = np.asarray(dataset.read(1, window=window), dtype=float)
        if dataset.nodata is not None:
            original[original == dataset.nodata] = np.nan

    cfg = load_config(args.config)
    source = cfg.sources[0]
    west, south, east, north = bbox
    extent = (west, east, south, north)
    original_extent = (subset_bounds[0], subset_bounds[2], subset_bounds[1], subset_bounds[3])
    vmin, vmax = shared_color_limits(original, downscaled)
    try:
        gaussian_plume = _read_model_plume(args.gaussian, args.model_time_index, args.model_level_index)
        particle_plume = _read_model_plume(args.particles, args.model_time_index, args.model_level_index)
    except (OSError, RuntimeError, ValueError) as exc:
        parser.error(str(exc))
    if gaussian_plume.shape != downscaled.shape or particle_plume.shape != downscaled.shape:
        parser.error("model plume grids must match the downscaled satellite grid")
    plume_x = np.linspace(west, east, downscaled.shape[1])
    plume_y = np.linspace(south, north, downscaled.shape[0])
    figure, axes = plt.subplots(1, 2, figsize=(13.0, 5.4), constrained_layout=True, sharex=True, sharey=True)
    images = []
    for axis, field, image_extent, title, origin in (
        (axes[0], original, original_extent, "Original Sentinel-5P Aerosol Index", "upper"),
        (axes[1], downscaled, extent, "Station-assisted downscaled Aerosol Index", "lower"),
    ):
        images.append(axis.imshow(field, extent=image_extent, origin=origin, cmap="magma", vmin=vmin, vmax=vmax))
        axis.contour(
            plume_x,
            plume_y,
            gaussian_plume,
            levels=[args.plume_threshold],
            colors="cyan",
            linewidths=1.5,
        )
        axis.contour(
            plume_x,
            plume_y,
            particle_plume,
            levels=[args.plume_threshold],
            colors="lime",
            linewidths=1.3,
            linestyles="--",
        )
        axis.scatter(
            [float(source.longitude)],
            [float(source.latitude)],
            marker="*",
            s=110,
            c="lime",
            edgecolors="black",
            linewidths=0.6,
            zorder=4,
            label="Emission source",
        )
        axis.set_title(title)
        axis.set_xlabel("Longitude [degrees east]")
        axis.grid(alpha=0.18)
    axes[0].set_ylabel("Latitude [degrees north]")
    from matplotlib.lines import Line2D
    axes[0].legend(handles=[
        Line2D([0], [0], marker="*", color="none", markerfacecolor="lime", markeredgecolor="black", markersize=11, label="Emission source"),
        Line2D([0], [0], color="cyan", linewidth=1.5, label="Spritz Gaussian plume"),
        Line2D([0], [0], color="lime", linewidth=1.3, linestyle="--", label="Spritz particles plume"),
    ], loc="upper right")
    figure.colorbar(images[0], ax=axes, label="UV Aerosol Index (340–380 nm)", shrink=0.88)
    figure.suptitle(
        f"Model plume outlines at time index {args.model_time_index}: "
        f"{args.plume_threshold:g} of each model maximum"
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=args.dpi)
    plt.close(figure)
    LOGGER.info("Wrote shared-scale satellite comparison to %s", output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

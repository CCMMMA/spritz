#!/usr/bin/env python3
"""Compare a vertically integrated Spritz NO2 plume with native TROPOMI NO2 pixels."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np

from sprtz.config import load_config
from sprtz.io.jsonio import write_json
from sprtz.logging import configure_logging

LOGGER = logging.getLogger(__name__)
NO2_MOLAR_MASS_G_MOL = 46.0055


def _statistics(model: np.ndarray, satellite: np.ndarray, *, suffix: str) -> dict[str, float | int | None]:
    valid = np.isfinite(model) & np.isfinite(satellite)
    if not valid.any():
        raise ValueError("model and satellite NO2 have no finite overlapping pixels")
    predicted = model[valid]
    observed = satellite[valid]
    difference = predicted - observed
    return {
        "count": int(valid.sum()),
        "model_positive_count": int(np.count_nonzero(predicted > 0.0)),
        "satellite_positive_count": int(np.count_nonzero(observed > 0.0)),
        "joint_positive_count": int(np.count_nonzero((predicted > 0.0) & (observed > 0.0))),
        f"bias_{suffix}": float(np.mean(difference)),
        f"mean_absolute_error_{suffix}": float(np.mean(np.abs(difference))),
        f"root_mean_square_error_{suffix}": float(np.sqrt(np.mean(difference**2))),
        "pearson_correlation": (
            float(np.corrcoef(predicted, observed)[0, 1])
            if predicted.size > 1 and np.std(predicted) > 0.0 and np.std(observed) > 0.0
            else None
        ),
    }


def _normalized(values: np.ndarray) -> np.ndarray:
    finite = values[np.isfinite(values)]
    low, high = np.percentile(finite, [5.0, 95.0])
    return np.clip((values - low) / max(float(high - low), np.finfo(float).eps), 0.0, 1.0)


def _integrated_model_column(path: str | Path, time_index: int) -> tuple[np.ndarray, np.ndarray]:
    try:
        from netCDF4 import Dataset
    except ImportError as exc:
        raise RuntimeError(f"NO2 column evaluation requires netCDF4: {exc}") from exc
    with Dataset(path) as dataset:
        if "concentration_field" not in dataset.variables or "field_z" not in dataset.variables:
            raise ValueError("Spritz NetCDF must contain concentration_field and field_z")
        variable = dataset.variables["concentration_field"]
        if variable.ndim != 4 or variable.shape[1] < 2:
            raise ValueError("NO2 column evaluation requires at least two model field_z levels")
        if not 0 <= time_index < variable.shape[0]:
            raise ValueError(f"time index {time_index} is outside model time dimension {variable.shape[0]}")
        concentration_g_m3 = np.ma.filled(variable[time_index], np.nan).astype(float)
        levels_m = np.asarray(dataset["field_z"][:], dtype=float)
        units = str(getattr(variable, "units", ""))
    if units not in {"g m-3", "g/m3", "g m^-3"}:
        raise ValueError(f"expected Spritz concentration in g m-3, found {units!r}")
    if np.any(np.diff(levels_m) <= 0.0):
        raise ValueError("field_z levels must increase strictly for column integration")
    # Trapezoidal integration produces g m-2. Dividing by molecular mass in
    # g mol-1 produces mol m-2, matching the Sentinel Hub NO2 band contract.
    column_g_m2 = np.trapezoid(concentration_g_m3, levels_m, axis=0)
    return column_g_m2 / NO2_MOLAR_MASS_G_MOL, levels_m


def _aggregate_to_shape(field: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    """Area-average a south-to-north model grid into north-to-south satellite pixels."""
    target_y, target_x = shape
    labels_y = np.minimum((np.arange(field.shape[0]) + 0.5) * target_y / field.shape[0], target_y - 1).astype(int)
    labels_x = np.minimum((np.arange(field.shape[1]) + 0.5) * target_x / field.shape[1], target_x - 1).astype(int)
    out = np.full(shape, np.nan, dtype=float)
    for row in range(target_y):
        row_values = field[labels_y == row]
        for col in range(target_x):
            values = row_values[:, labels_x == col]
            if np.isfinite(values).any():
                out[target_y - 1 - row, col] = float(np.nanmean(values))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--concentration", required=True)
    parser.add_argument("--satellite-no2", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--time-index", type=int, default=1)
    args = parser.parse_args(argv)
    configure_logging(False)
    try:
        import rasterio
        import rasterio.windows
    except ImportError as exc:
        parser.error(f"NO2 column evaluation requires rasterio: {exc}")

    # Reuse the exact domain bounds used by the satellite alignment workflow.
    from align_satellite import _spritz_domain_bbox

    config = load_config(args.config)
    bbox = _spritz_domain_bbox(config)
    with rasterio.open(args.satellite_no2) as dataset:
        window = rasterio.windows.from_bounds(*bbox, transform=dataset.transform).round_offsets().round_lengths()
        window = window.intersection(rasterio.windows.Window(0, 0, dataset.width, dataset.height))
        satellite = np.asarray(dataset.read(1, window=window), dtype=float)
        if dataset.nodata is not None:
            satellite[satellite == dataset.nodata] = np.nan
        satellite_bounds = rasterio.windows.bounds(window, dataset.transform)
    try:
        model_column, levels = _integrated_model_column(args.concentration, args.time_index)
        model_native = _aggregate_to_shape(model_column, satellite.shape)
        raw_stats = _statistics(model_native, satellite, suffix="mol_m2")
        pattern_stats = _statistics(_normalized(model_native), _normalized(satellite), suffix="normalized")
    except (OSError, RuntimeError, ValueError) as exc:
        parser.error(str(exc))

    write_json(args.output, {
        "component": "usecase03.tropomi_no2_column_evaluation",
        "primary_observable": "tropospheric_NO2_column",
        "unit": "mol m-2",
        "model_concentration_path": str(Path(args.concentration)),
        "satellite_no2_path": str(Path(args.satellite_no2)),
        "selected_model_time_index": args.time_index,
        "model_vertical_levels_m": levels.tolist(),
        "model_vertical_integration": "trapezoidal concentration integration followed by 46.0055 g mol-1 conversion",
        "satellite_native_subset_shape": list(satellite.shape),
        "satellite_native_subset_bounds": list(satellite_bounds),
        "raw_column_statistics": raw_stats,
        "normalized_pattern_statistics": pattern_stats,
        "model_column_mol_m2": model_native.tolist(),
        "satellite_column_mol_m2": [
            [None if not np.isfinite(value) else float(value) for value in row]
            for row in satellite
        ],
        "limitations": [
            "The Sentinel Hub GeoTIFF does not expose the TROPOMI averaging kernel, so it is not applied.",
            "Spritz uses a passive NO2 tracer without atmospheric chemistry or a background NO2 column.",
            "Raw-column metrics are screening diagnostics; normalized metrics assess spatial pattern only.",
        ],
    })
    LOGGER.info("Wrote native-pixel TROPOMI NO2 column evaluation to %s", args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

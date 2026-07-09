"""Deterministic validation metrics for meteorological fields."""

from __future__ import annotations

import numpy as np


def field_metrics(predicted: np.ndarray, observed: np.ndarray) -> dict[str, float]:
    error = np.asarray(predicted, dtype=float) - np.asarray(observed, dtype=float)
    return {
        "rmse": float(np.sqrt(np.nanmean(error * error))),
        "mae": float(np.nanmean(np.abs(error))),
        "bias": float(np.nanmean(error)),
    }


def wind_metrics(
    predicted_u: np.ndarray,
    predicted_v: np.ndarray,
    observed_u: np.ndarray,
    observed_v: np.ndarray,
) -> dict[str, float]:
    du = np.asarray(predicted_u, dtype=float) - np.asarray(observed_u, dtype=float)
    dv = np.asarray(predicted_v, dtype=float) - np.asarray(observed_v, dtype=float)
    predicted_direction = np.degrees(np.arctan2(-predicted_u, -predicted_v)) % 360.0
    observed_direction = np.degrees(np.arctan2(-observed_u, -observed_v)) % 360.0
    direction_delta = (predicted_direction - observed_direction + 180.0) % 360.0 - 180.0
    return {
        "vector_rmse": float(np.sqrt(np.nanmean(du * du + dv * dv))),
        "wind_direction_mae_degrees": float(np.nanmean(np.abs(direction_delta))),
    }

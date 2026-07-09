"""Pressure reconstruction using the hypsometric equation."""

from __future__ import annotations

import numpy as np

GRAVITY_M_S2 = 9.80665
DRY_AIR_GAS_CONSTANT_J_KG_K = 287.05


def hypsometric_pressure(
    reference_pressure_pa: np.ndarray,
    reference_temperature_c: np.ndarray,
    elevation_delta_m: np.ndarray,
    *,
    target_temperature_c: np.ndarray | None = None,
) -> np.ndarray:
    """Return pressure at a new elevation from layer-mean virtual-free temperature."""
    pressure = np.asarray(reference_pressure_pa, dtype=float)
    source_k = np.asarray(reference_temperature_c, dtype=float) + 273.15
    target_k = source_k if target_temperature_c is None else np.asarray(target_temperature_c, dtype=float) + 273.15
    mean_k = np.maximum(0.5 * (source_k + target_k), 150.0)
    delta = np.asarray(elevation_delta_m, dtype=float)
    while delta.ndim < pressure.ndim:
        delta = delta[np.newaxis, ...]
    return pressure * np.exp(-GRAVITY_M_S2 * delta / (DRY_AIR_GAS_CONSTANT_J_KG_K * mean_k))

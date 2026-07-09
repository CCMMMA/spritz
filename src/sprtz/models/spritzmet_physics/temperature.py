"""Terrain-aware temperature reconstruction."""

from __future__ import annotations

import numpy as np

DRY_ADIABATIC_LAPSE_RATE_K_PER_M = 0.0098
DEFAULT_ENVIRONMENTAL_LAPSE_RATE_K_PER_M = 0.0065
DEFAULT_MOIST_LAPSE_RATE_K_PER_M = 0.0050


def correct_temperature(
    temperature_c: np.ndarray,
    elevation_delta_m: np.ndarray,
    *,
    method: str = "constant",
    lapse_rate_k_per_m: float = DEFAULT_ENVIRONMENTAL_LAPSE_RATE_K_PER_M,
    bulk_richardson_number: np.ndarray | None = None,
) -> np.ndarray:
    """Correct temperature for elevation while preserving input dimensions.

    ``elevation_delta_m`` is target minus source/reference elevation. The
    stability method reduces the lapse rate in stable air and increases it in
    unstable air, with explicit physical bounds. The moist method uses a named
    configurable approximation rather than a full parcel model.
    """
    temperature = np.asarray(temperature_c, dtype=float)
    delta = np.asarray(elevation_delta_m, dtype=float)
    if method == "constant":
        lapse: float | np.ndarray = float(lapse_rate_k_per_m)
    elif method == "moist":
        lapse = min(max(float(lapse_rate_k_per_m), 0.0), DEFAULT_MOIST_LAPSE_RATE_K_PER_M)
    elif method == "stability":
        if bulk_richardson_number is None:
            lapse = float(lapse_rate_k_per_m)
        else:
            ri = np.asarray(bulk_richardson_number, dtype=float)
            lapse = np.clip(
                float(lapse_rate_k_per_m) * (1.0 - 0.5 * np.clip(ri, -1.0, 1.0)),
                DEFAULT_MOIST_LAPSE_RATE_K_PER_M,
                DRY_ADIABATIC_LAPSE_RATE_K_PER_M,
            )
    else:
        raise ValueError("temperature method must be constant, stability, or moist")
    while delta.ndim < temperature.ndim:
        delta = delta[np.newaxis, ...]
    if isinstance(lapse, np.ndarray):
        while lapse.ndim < temperature.ndim:
            lapse = lapse[np.newaxis, ...]
    return temperature - lapse * delta

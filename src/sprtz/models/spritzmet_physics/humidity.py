"""Thermodynamically consistent humidity reconstruction."""

from __future__ import annotations

import numpy as np


def saturation_vapor_pressure_pa(temperature_c: np.ndarray) -> np.ndarray:
    temperature = np.asarray(temperature_c, dtype=float)
    return 611.2 * np.exp(17.67 * temperature / np.maximum(temperature + 243.5, 1.0e-6))


def vapor_pressure_from_relative_humidity(
    relative_humidity: np.ndarray, temperature_c: np.ndarray
) -> np.ndarray:
    return np.clip(np.asarray(relative_humidity, dtype=float), 0.0, 1.0) * saturation_vapor_pressure_pa(
        temperature_c
    )


def relative_humidity_from_vapor_pressure(
    vapor_pressure_pa: np.ndarray, corrected_temperature_c: np.ndarray
) -> np.ndarray:
    saturation = np.maximum(saturation_vapor_pressure_pa(corrected_temperature_c), 1.0e-12)
    return np.clip(np.asarray(vapor_pressure_pa, dtype=float) / saturation, 0.0, 1.0)

"""Composable optional wind corrections."""

from __future__ import annotations

from typing import Any

import numpy as np

from .massconsistency import minimize_divergence


def apply_wind_operators(
    u: np.ndarray,
    v: np.ndarray,
    *,
    dx_m: float,
    dy_m: float,
    options: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """Apply explicitly enabled wind operators in documented sequence."""
    corrected_u = np.asarray(u, dtype=float)
    corrected_v = np.asarray(v, dtype=float)
    metadata: dict[str, Any] = {"physics_wind_operators_enabled": True}
    stability = options.get("stability")
    if stability:
        ri = np.asarray(stability.get("bulk_richardson_number", 0.0), dtype=float)
        factor = np.clip(1.0 - 0.20 * np.clip(ri, -1.0, 1.0), 0.8, 1.2)
        while factor.ndim < corrected_u.ndim:
            factor = factor[np.newaxis, ...]
        corrected_u, corrected_v = corrected_u * factor, corrected_v * factor
        metadata["stability_correction"] = "bounded_bulk_richardson"
    mass = options.get("mass_consistency")
    if mass:
        corrected_u, corrected_v, diagnostics = minimize_divergence(
            corrected_u,
            corrected_v,
            dx_m,
            dy_m,
            iterations=int(mass.get("iterations", 80)),
            relaxation=float(mass.get("relaxation", 0.8)),
        )
        metadata.update({f"mass_consistency_{key}": value for key, value in diagnostics.items()})
    return corrected_u, corrected_v, metadata

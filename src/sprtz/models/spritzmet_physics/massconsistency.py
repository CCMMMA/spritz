"""Lightweight diagnostic horizontal divergence minimization."""

from __future__ import annotations

import numpy as np


def divergence(u: np.ndarray, v: np.ndarray, dx_m: float, dy_m: float) -> np.ndarray:
    """Compute horizontal divergence over the final two array axes."""
    return np.gradient(np.asarray(u, dtype=float), dx_m, axis=-1) + np.gradient(
        np.asarray(v, dtype=float), dy_m, axis=-2
    )


def minimize_divergence(
    u: np.ndarray,
    v: np.ndarray,
    dx_m: float,
    dy_m: float,
    *,
    iterations: int = 80,
    relaxation: float = 0.8,
) -> tuple[np.ndarray, np.ndarray, dict[str, float | int]]:
    """Project horizontal wind toward a divergence-free field.

    A bounded Jacobi solve estimates a velocity potential under zero-gradient
    boundary conditions. This diagnostic operator does not impose full
    three-dimensional anelastic mass conservation.
    """
    if dx_m <= 0.0 or dy_m <= 0.0 or iterations < 0 or not 0.0 < relaxation <= 1.0:
        raise ValueError("spacing, iterations, and relaxation must be positive and bounded")
    uu = np.asarray(u, dtype=float)
    vv = np.asarray(v, dtype=float)
    if uu.shape != vv.shape or uu.ndim < 2:
        raise ValueError("u and v must have equal shapes with at least two dimensions")
    before = divergence(uu, vv, dx_m, dy_m)
    phi = np.zeros_like(before)
    dx2, dy2 = dx_m * dx_m, dy_m * dy_m
    denominator = 2.0 / dx2 + 2.0 / dy2
    for _ in range(iterations):
        padded = np.pad(phi, [(0, 0)] * (phi.ndim - 2) + [(1, 1), (1, 1)], mode="edge")
        estimate = (
            (padded[..., 1:-1, 2:] + padded[..., 1:-1, :-2]) / dx2
            + (padded[..., 2:, 1:-1] + padded[..., :-2, 1:-1]) / dy2
            - before
        ) / denominator
        phi = (1.0 - relaxation) * phi + relaxation * estimate
    corrected_u = uu - np.gradient(phi, dx_m, axis=-1)
    corrected_v = vv - np.gradient(phi, dy_m, axis=-2)
    after = divergence(corrected_u, corrected_v, dx_m, dy_m)
    return corrected_u, corrected_v, {
        "iterations": int(iterations),
        "divergence_rms_before_s-1": float(np.sqrt(np.nanmean(before * before))),
        "divergence_rms_after_s-1": float(np.sqrt(np.nanmean(after * after))),
    }

from __future__ import annotations

import numpy as np

RHO_AIR_DEFAULT = 1.2
C_P = 1005.0
T_SURFACE = 293.0
NC_WIND_DOMINATED = 2.0
NC_PLUME_DOMINATED = 10.0
ALPHA_INFLOW_MAX = 0.35
INFLOW_RADIUS_CELLS = 3
BETA_UPDRAFT_MAX = 0.50


def _binary_dilation(mask: np.ndarray, radius: int) -> np.ndarray:
    try:
        from scipy.ndimage import binary_dilation

        return np.asarray(binary_dilation(mask, structure=np.ones((2 * radius + 1, 2 * radius + 1), dtype=bool)))
    except Exception:
        padded = np.pad(mask, radius, mode="constant", constant_values=False)
        out = np.zeros_like(mask, dtype=bool)
        for dy in range(2 * radius + 1):
            for dx in range(2 * radius + 1):
                out |= padded[dy : dy + mask.shape[0], dx : dx + mask.shape[1]]
        return out


def buoyancy_corrected_wind(
    wind_speed: np.ndarray,
    wind_dir: np.ndarray,
    intensity: np.ndarray,
    fire_prob: np.ndarray,
    temp_k: np.ndarray | None,
    prob_threshold: float = 0.5,
) -> tuple[np.ndarray, np.ndarray]:
    ws = np.asarray(wind_speed, dtype=np.float32)
    wd = np.asarray(wind_dir, dtype=np.float32)
    temp = np.asarray(temp_k, dtype=np.float32) if temp_k is not None else np.full_like(ws, T_SURFACE)
    fire = np.asarray(fire_prob, dtype=np.float32) >= prob_threshold
    nc = np.where(fire, np.asarray(intensity, dtype=np.float32) * 1000.0 / (RHO_AIR_DEFAULT * C_P * temp * np.maximum(ws, 0.1) ** 3), 0.0)
    if float(np.nanmax(nc)) < NC_WIND_DOMINATED:
        return ws.copy(), wd
    weight = np.clip((nc - NC_WIND_DOMINATED) / (NC_PLUME_DOMINATED - NC_WIND_DOMINATED), 0.0, 1.0)
    perimeter = _binary_dilation(fire, INFLOW_RADIUS_CELLS) & ~fire
    perimeter_weight = _binary_dilation(weight > 0.0, INFLOW_RADIUS_CELLS) & perimeter
    ws_corr = ws.copy()
    ws_corr[fire] *= 1.0 - weight[fire] * BETA_UPDRAFT_MAX
    ws_corr[perimeter_weight] *= 1.0 + float(np.nanmax(weight)) * ALPHA_INFLOW_MAX
    return np.maximum(ws_corr, 0.0).astype(np.float32), wd

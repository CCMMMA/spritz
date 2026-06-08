from __future__ import annotations

import math

import numpy as np

from sprtz.config import SpottingConfig

RHO_FIREBRAND = 700.0
RHO_AIR = 1.2
G = 9.81
C_DRAG = 1.0
P_PERCENTILE = 0.995
SIGMA_SPOTTING = 0.70
SIGMA_ANGULAR = math.pi / 4.0
DEFAULT_FIREBRAND_RADIUS_M = 0.010
DEFAULT_ABL_HEIGHT_M = 1000.0
DEFAULT_N_FIREBRANDS = 5
INTENSITY_THRESHOLD_KW_M = 100.0


def _normal_ppf(p: float) -> float:
    try:
        from scipy import stats

        return float(stats.norm.ppf(p))
    except Exception:
        return 2.5758293035489004 if abs(p - 0.995) < 1e-9 else float(math.sqrt(2.0) * _erfinv(2.0 * p - 1.0))


def _erfinv(x: float) -> float:
    a = 0.147
    s = 1.0 if x >= 0 else -1.0
    y = 1.0 - x * x
    return s * math.sqrt(math.sqrt((2.0 / (math.pi * a) + math.log(y) / 2.0) ** 2 - math.log(y) / a) - (2.0 / (math.pi * a) + math.log(y) / 2.0))


class RandomFrontSpotting:
    """Post-processing fire-spotting module implementing RandomFront 2.3."""

    def __init__(self, config: SpottingConfig, dx: float, fuel: np.ndarray, abl_height_grid: np.ndarray | None = None):
        self.cfg = config
        self.dx = float(dx)
        self.fuel = np.asarray(fuel, dtype=np.int8)
        self.ny, self.nx = self.fuel.shape
        self.abl = (
            np.asarray(abl_height_grid, dtype=np.float32)
            if abl_height_grid is not None
            else np.full((self.ny, self.nx), config.abl_height_m, dtype=np.float32)
        )

    def _settling_velocity(self) -> float:
        r = self.cfg.firebrand_radius_m
        ratio = RHO_FIREBRAND / RHO_AIR - 1.0
        return math.sqrt((4.0 / 3.0) * G * r * ratio / C_DRAG)

    def _lognormal_mu(self, intensity_kw_m: float, wind_speed: float, abl_h: float) -> float:
        if intensity_kw_m < self.cfg.intensity_threshold_kw_m:
            return -math.inf
        h_max = min(5.963e-4 * (intensity_kw_m / self.cfg.firebrand_radius_m) ** 0.4326, abl_h)
        settling = self._settling_velocity()
        if settling < 1e-6:
            return -math.inf
        transport = h_max * max(0.0, wind_speed) / settling
        if transport < self.dx:
            return -math.inf
        return math.log(transport) - self.cfg.sigma_spotting * _normal_ppf(self.cfg.p_percentile)

    def step(
        self,
        burning: np.ndarray,
        arrived: np.ndarray,
        intensity: np.ndarray,
        wind_speed: np.ndarray,
        wind_dir: np.ndarray,
        t_now: float,
        rng: np.random.Generator,
    ) -> int:
        n_spot = 0
        for real in range(burning.shape[0]):
            burn_r, burn_c = np.where(burning[real])
            for r, c in zip(burn_r, burn_c):
                mu = self._lognormal_mu(float(intensity[r, c]), float(wind_speed[r, c]), float(self.abl[r, c]))
                if not math.isfinite(mu):
                    continue
                dists = rng.lognormal(mu, self.cfg.sigma_spotting, self.cfg.n_firebrands_per_cell)
                azimuths = rng.normal(float(wind_dir[r, c]), self.cfg.sigma_angular_rad, self.cfg.n_firebrands_per_cell)
                for dist, az in zip(dists, azimuths):
                    dr = int(round(-dist * math.cos(az) / self.dx))
                    dc = int(round(dist * math.sin(az) / self.dx))
                    nr, nc = int(r + dr), int(c + dc)
                    if 0 <= nr < self.ny and 0 <= nc < self.nx and not burning[real, nr, nc] and self.fuel[nr, nc] != 0:
                        burning[real, nr, nc] = True
                        arrived[real, nr, nc] = t_now
                        n_spot += 1
        return n_spot

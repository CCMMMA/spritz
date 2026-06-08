from __future__ import annotations

from dataclasses import replace
import logging
import math
from pathlib import Path
from typing import Any

import numpy as np

from sprtz.config import FireConfig

FUEL_ID_NAMES = {
    0: "Non-burnable",
    1: "Broadleaves",
    2: "Shrubs",
    3: "Grasslands",
    4: "Fire-prone conifers",
    5: "Agro-forestry",
    6: "Non-fire-prone forest",
}
NOMINAL_ROS = np.array([0.000, 0.025, 0.042, 0.058, 0.075, 0.017, 0.008], dtype=np.float64)
NOMINAL_FUEL_LOAD = np.array([0.0, 4.0, 5.0, 3.0, 6.0, 2.0, 1.5], dtype=np.float64)
P_NOM = np.array(
    [
        [0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00],
        [0.00, 0.30, 0.35, 0.25, 0.40, 0.20, 0.15],
        [0.00, 0.40, 0.55, 0.45, 0.60, 0.35, 0.25],
        [0.00, 0.35, 0.45, 0.50, 0.50, 0.30, 0.20],
        [0.00, 0.55, 0.65, 0.55, 0.75, 0.45, 0.35],
        [0.00, 0.25, 0.30, 0.25, 0.35, 0.20, 0.15],
        [0.00, 0.15, 0.20, 0.15, 0.25, 0.12, 0.10],
    ],
    dtype=np.float64,
)
NEIGHBOR_DR = np.array([-1, -1, 0, 1, 1, 1, 0, -1], dtype=np.int8)
NEIGHBOR_DC = np.array([0, 1, 1, 1, 0, -1, -1, -1], dtype=np.int8)
NEIGHBOR_BEARING = np.array(
    [0, np.pi / 4, np.pi / 2, 3 * np.pi / 4, np.pi, 5 * np.pi / 4, 3 * np.pi / 2, 7 * np.pi / 4],
    dtype=np.float64,
)
IS_DIAGONAL = np.array([False, True, False, True, False, True, False, True])
C_WIND_WANG = 0.1783
C_WIND_CLASSIC = 0.045
C_SLOPE = 3.533
C_MOISTURE = -0.014
HEAT_OF_COMBUSTION_KJ_KG = 18_000.0


FireFrontConfig = FireConfig


def f_wind_wang(bearing_ij_rad: float, wind_dir_rad: float, wind_speed_ms: float) -> float:
    return float(np.exp(C_WIND_WANG * wind_speed_ms * np.cos(bearing_ij_rad - wind_dir_rad)))


def f_wind_classic(bearing_ij_rad: float, wind_dir_rad: float, wind_speed_ms: float) -> float:
    return float(1.0 + C_WIND_CLASSIC * wind_speed_ms * max(0.0, math.cos(bearing_ij_rad - wind_dir_rad)))


def f_slope(slope_deg: float) -> float:
    return float(max(0.1, 1.0 + C_SLOPE * math.tan(math.radians(slope_deg)) ** 2))


def f_moisture(fmc_fraction: float) -> float:
    return float(np.exp(C_MOISTURE * fmc_fraction * 100.0))


def ros(
    fuel_j: int,
    wind_speed: float,
    wind_dir_rad: float,
    bearing_ij_rad: float,
    slope_deg: float,
    fmc_frac: float,
    ros_model: str = "wang",
) -> float:
    ros_n = float(NOMINAL_ROS[int(fuel_j)])
    if ros_n < 1e-9:
        return 0.0
    fw = (
        f_wind_wang(bearing_ij_rad, wind_dir_rad, wind_speed)
        if ros_model == "wang"
        else f_wind_classic(bearing_ij_rad, wind_dir_rad, wind_speed)
    )
    return max(1e-5, ros_n * fw * f_slope(slope_deg) * f_moisture(fmc_frac))


def transition_time(ros_ms: float, dx: float, is_diagonal: bool) -> float:
    return dx * (math.sqrt(2.0) if is_diagonal else 1.0) / max(ros_ms, 1e-5)


def transition_probability(
    fuel_i: int,
    fuel_j: int,
    bearing: float,
    wind_dir_rad: float,
    wind_speed: float,
    slope_deg: float,
    fmc_frac: float,
    ros_model: str = "wang",
) -> float:
    base = float(P_NOM[int(fuel_i), int(fuel_j)])
    if base <= 0.0:
        return 0.0
    fw = f_wind_wang(bearing, wind_dir_rad, wind_speed) if ros_model == "wang" else f_wind_classic(bearing, wind_dir_rad, wind_speed)
    return min(1.0, base * fw * f_slope(slope_deg) * f_moisture(fmc_frac))


def byram_intensity(fuel_id_grid: np.ndarray, ros_grid: np.ndarray, fmc_grid: np.ndarray) -> np.ndarray:
    fuel = np.clip(np.asarray(fuel_id_grid, dtype=np.int16), 0, len(NOMINAL_FUEL_LOAD) - 1)
    available = NOMINAL_FUEL_LOAD[fuel] * (1.0 - np.asarray(fmc_grid, dtype=float))
    return (available * HEAT_OF_COMBUSTION_KJ_KG * np.asarray(ros_grid, dtype=float)).astype(np.float32)


class FireFront:
    """PROPAGATOR-inspired stochastic cellular-automaton wildfire spread model."""

    def __init__(self, dem: np.ndarray, fuel: np.ndarray, config: FireFrontConfig | None = None):
        self.dem = np.asarray(dem, dtype=np.float32)
        self.fuel = np.asarray(fuel, dtype=np.int8)
        self.cfg = config or FireFrontConfig()
        self.ny, self.nx = self.dem.shape
        if self.fuel.shape != (self.ny, self.nx):
            raise ValueError("dem and fuel must have same shape")
        self._rng = np.random.default_rng(self.cfg.seed)
        self._slope = self._precompute_slopes()
        self._log = logging.getLogger(__name__)
        self._spotting = None
        self._gpu_backend = "numpy"
        self._reset_state()
        if self.cfg.gpu.backend in {"auto", "cupy", "numba_cuda"}:
            from sprtz.models.firefront_gpu import _detect_gpu_backend

            detected = _detect_gpu_backend() if self.cfg.gpu.backend == "auto" else self.cfg.gpu.backend
            self._gpu_backend = detected if detected != "numpy" else "numpy"
        if self.cfg.spotting and self.cfg.spotting_config.model == "randomfront":
            from sprtz.models.firefront_spotting import RandomFrontSpotting

            self._spotting = RandomFrontSpotting(self.cfg.spotting_config, self.cfg_dx, self.fuel)

    @property
    def cfg_dx(self) -> float:
        return float(getattr(self.cfg, "dx", 100.0))

    def _reset_state(self) -> None:
        self.burning = np.zeros((self.cfg.realizations, self.ny, self.nx), dtype=bool)
        self.arrived = np.full((self.cfg.realizations, self.ny, self.nx), np.inf, dtype=np.float32)
        self._pending_arrival = np.full((self.cfg.realizations, self.ny, self.nx), np.inf, dtype=np.float32)
        self.snapshots: list[dict[str, Any]] = []
        self._current_intensity = np.zeros((self.ny, self.nx), dtype=np.float32)

    def _precompute_slopes(self) -> np.ndarray:
        padded = np.pad(self.dem, 1, mode="edge")
        slope = np.zeros((self.ny, self.nx, 8), dtype=np.float32)
        for k, (dr, dc) in enumerate(zip(NEIGHBOR_DR, NEIGHBOR_DC)):
            neigh = padded[1 + dr : 1 + dr + self.ny, 1 + dc : 1 + dc + self.nx]
            dist = self.cfg_dx * (math.sqrt(2.0) if IS_DIAGONAL[k] else 1.0)
            slope[:, :, k] = np.degrees(np.arctan2(neigh - self.dem, dist)).astype(np.float32)
        return slope

    def set_ignitions(self, ignitions: Any, t0: float = 0.0) -> None:
        if isinstance(ignitions, np.ndarray) and ignitions.dtype == bool:
            rr, cc = np.where(ignitions)
        else:
            rr, cc = zip(*[(int(r), int(c)) for r, c in ignitions]) if ignitions else ([], [])
        for r, c in zip(rr, cc):
            if 0 <= r < self.ny and 0 <= c < self.nx and self.fuel[r, c] != 0:
                self.burning[:, r, c] = True
                self.arrived[:, r, c] = t0

    def run(self, wind_speed: np.ndarray, wind_dir: np.ndarray, moisture: np.ndarray | None = None, t_start: float = 0.0) -> dict[str, Any]:
        ws = self._as_time_array(wind_speed)
        wd = self._as_time_array(wind_dir)
        mst = self._as_time_array(moisture if moisture is not None else np.full((self.ny, self.nx), self.cfg.moisture_default))
        if not self.burning.any():
            self.set_ignitions([(self.ny // 2, self.nx // 2)], t_start)
        dt_step = min(60.0, max(1.0, self.cfg.t_max_seconds / 200.0))
        next_out = t_start
        t = float(t_start)
        while t <= t_start + self.cfg.t_max_seconds + 1e-9:
            idx = min(int((t - t_start) / max(self.cfg.output_interval_seconds, 1.0)), ws.shape[0] - 1)
            self._ca_step(ws[idx], wd[idx], mst[min(idx, mst.shape[0] - 1)], t, dt_step)
            if self._spotting is not None:
                n = self._spotting.step(self.burning, self.arrived, self._current_intensity, ws[idx], wd[idx], t, self._rng)
                if n:
                    self._log.debug("t=%.0f: RandomFront spotted %d new ignitions", t, n)
            if t >= next_out - 1e-9:
                self._record_snapshot(t)
                next_out += self.cfg.output_interval_seconds
            t += dt_step
        return self._result()

    def _as_time_array(self, value: np.ndarray) -> np.ndarray:
        arr = np.asarray(value, dtype=np.float32)
        if arr.ndim == 2:
            arr = arr[np.newaxis, :, :]
        if arr.shape[-2:] != (self.ny, self.nx):
            raise ValueError("meteorology arrays must match fire grid")
        return arr

    def _ca_step(self, wind_speed: np.ndarray, wind_dir: np.ndarray, moisture: np.ndarray, t: float, dt: float) -> None:
        ros_grid = np.zeros((self.ny, self.nx), dtype=np.float32)
        for real in range(self.cfg.realizations):
            rows, cols = np.where(self.burning[real])
            for r, c in zip(rows, cols):
                fuel_i = int(self.fuel[r, c])
                for k in range(8):
                    nr = int(r + NEIGHBOR_DR[k])
                    nc = int(c + NEIGHBOR_DC[k])
                    if nr < 0 or nr >= self.ny or nc < 0 or nc >= self.nx or self.burning[real, nr, nc]:
                        continue
                    if self._pending_arrival[real, nr, nc] <= t + dt:
                        continue
                    fuel_j = int(self.fuel[nr, nc])
                    if fuel_j == 0:
                        continue
                    p = transition_probability(
                        fuel_i,
                        fuel_j,
                        float(NEIGHBOR_BEARING[k]),
                        float(wind_dir[nr, nc]),
                        float(wind_speed[nr, nc]),
                        float(self._slope[r, c, k]),
                        float(moisture[nr, nc]),
                        self.cfg.ros_model,
                    )
                    if self._rng.random() >= p:
                        continue
                    rj = ros(fuel_j, float(wind_speed[nr, nc]), float(wind_dir[nr, nc]), float(NEIGHBOR_BEARING[k]), float(self._slope[r, c, k]), float(moisture[nr, nc]), self.cfg.ros_model)
                    ros_grid[nr, nc] = max(ros_grid[nr, nc], rj)
                    self._pending_arrival[real, nr, nc] = min(
                        self._pending_arrival[real, nr, nc],
                        t + transition_time(rj, self.cfg_dx, bool(IS_DIAGONAL[k])),
                    )
        commit = (self._pending_arrival <= t + dt) & ~self.burning
        self.burning |= commit
        self.arrived = np.where(commit, np.minimum(self.arrived, self._pending_arrival), self.arrived).astype(np.float32)
        self._current_intensity = byram_intensity(self.fuel, ros_grid, moisture)

    def _record_snapshot(self, t: float) -> None:
        self.snapshots.append({"t": float(t), "fire_probability": self.fire_probability(), "intensity": self._current_intensity.copy()})

    def fire_probability(self) -> np.ndarray:
        return self.burning.mean(axis=0).astype(np.float32)

    def mean_arrival_time(self) -> np.ndarray:
        arr = self.arrived.copy()
        arr[~np.isfinite(arr)] = np.nan
        valid = np.isfinite(arr)
        count = valid.sum(axis=0)
        total = np.nansum(arr, axis=0)
        out = np.divide(total, count, out=np.full((self.ny, self.nx), np.nan, dtype=np.float32), where=count > 0)
        return out.astype(np.float32)

    def _result(self) -> dict[str, Any]:
        return {
            "component": "firefront",
            "fire_probability": self.fire_probability(),
            "arrival_time": self.mean_arrival_time(),
            "intensity": self._current_intensity.copy(),
            "snapshots": self.snapshots,
        }

    def to_netcdf(self, path: str | Path, grid_info: dict[str, Any] | None = None) -> None:
        from sprtz.models.firefront_io import write_netcdf

        write_netcdf(path, self._result(), grid_info or {}, self.cfg, "simulation start")

    def to_geojson_perimeters(self, threshold: float = 0.5) -> dict[str, Any]:
        from sprtz.models.firefront_io import geojson_perimeters

        return geojson_perimeters(self.snapshots, threshold=threshold)

    def to_csv(self, path: str | Path) -> None:
        from sprtz.models.firefront_io import write_csv

        write_csv(path, self._result())


def demo_firefront_from_config(config: Any, *, realizations: int | None = None) -> FireFront:
    fire_cfg = config.fire or FireFrontConfig()
    if realizations is not None:
        fire_cfg = replace(fire_cfg, realizations=realizations)
    dem = np.zeros((config.grid.ny, config.grid.nx), dtype=np.float32)
    fuel = np.full((config.grid.ny, config.grid.nx), 3, dtype=np.int8)
    return FireFront(dem, fuel, fire_cfg)

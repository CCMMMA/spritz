from __future__ import annotations

from dataclasses import asdict
import csv
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import numpy as np

from sprtz.config import SuiteConfig
from sprtz.core.grid import Grid
from sprtz.io.jsonio import write_json
from sprtz.models.spritz import _mean_wind, read_meteorology


def _grid_xy(config: SuiteConfig) -> tuple[np.ndarray, np.ndarray]:
    grid = Grid(**asdict(config.grid))
    return np.meshgrid(grid.x, grid.y)


def _normalize(score: np.ndarray) -> np.ndarray:
    arr = np.asarray(score, dtype=np.float64)
    arr[~np.isfinite(arr)] = 0.0
    total = float(arr.sum())
    if total > 0.0:
        arr = arr / total
    return arr.astype(np.float32)


def _receptor_weights(config: SuiteConfig) -> dict[str, float]:
    raw = config.run.get("observations", config.run.get("OBSERVATIONS", {}))
    if isinstance(raw, dict):
        return {str(k): max(float(v), 0.0) for k, v in raw.items()}
    return {rec.id: 1.0 for rec in config.receptors}


def backward_gaussian(config: SuiteConfig, meteo: dict[str, Any]) -> dict[str, Any]:
    """Estimate an upwind source likelihood field with an adjoint-style Gaussian footprint."""
    config.validate()
    xx, yy = _grid_xy(config)
    u, v, speed = _mean_wind(meteo)
    ex, ey = u / speed, v / speed
    weights = _receptor_weights(config)
    sigma_cross = float(config.run.get("backward_sigma_cross_m", max(config.grid.dx, config.grid.dy) * 2.0))
    min_downwind = float(config.run.get("backward_min_downwind_m", max(config.grid.dx, config.grid.dy)))
    score = np.zeros_like(xx, dtype=np.float64)
    for rec in config.receptors:
        obs = weights.get(rec.id, 1.0)
        dx = rec.x - xx
        dy = rec.y - yy
        xdown = dx * ex + dy * ey
        ycross = -dx * ey + dy * ex
        upstream = xdown >= min_downwind
        footprint = np.exp(-0.5 * (ycross / max(sigma_cross, 1.0)) ** 2) / np.maximum(xdown, min_downwind)
        score += obs * np.where(upstream, footprint, 0.0)
    return {
        "component": "spritz.backward.gaussian",
        "x": xx[0].astype(float).tolist(),
        "y": yy[:, 0].astype(float).tolist(),
        "source_likelihood": _normalize(score).tolist(),
        "metadata": {
            "method": "steady adjoint Gaussian footprint",
            "wind_u": u,
            "wind_v": v,
            "wind_speed": speed,
            "sigma_cross_m": sigma_cross,
        },
    }


def backward_particles(config: SuiteConfig, meteo: dict[str, Any], *, seed: int | None = None) -> dict[str, Any]:
    """Estimate source likelihood by releasing particles backward from observations."""
    config.validate()
    xx, yy = _grid_xy(config)
    u, v, speed = _mean_wind(meteo)
    rng = np.random.default_rng(seed if seed is not None else int(config.run.get("seed", 42)))
    n_particles = int(config.run.get("backward_particles", 5000))
    duration = float(config.run.get("backward_duration_s", 3600.0))
    sigma_h = float(config.run.get("particle_sigma_h", 250.0))
    weights = _receptor_weights(config)
    score = np.zeros(xx.shape, dtype=np.float64)
    x_edges = np.concatenate([xx[0] - config.grid.dx / 2.0, [xx[0, -1] + config.grid.dx / 2.0]])
    y_edges = np.concatenate([yy[:, 0] - config.grid.dy / 2.0, [yy[-1, 0] + config.grid.dy / 2.0]])
    total_obs = sum(weights.get(rec.id, 1.0) for rec in config.receptors) or 1.0
    for rec in config.receptors:
        count = max(1, int(round(n_particles * weights.get(rec.id, 1.0) / total_obs)))
        travel = rng.uniform(0.0, duration, count)
        px = rec.x - u * travel + rng.normal(0.0, sigma_h, count)
        py = rec.y - v * travel + rng.normal(0.0, sigma_h, count)
        hist, _, _ = np.histogram2d(py, px, bins=[y_edges, x_edges])
        score += hist
    return {
        "component": "spritz.backward.particles",
        "x": xx[0].astype(float).tolist(),
        "y": yy[:, 0].astype(float).tolist(),
        "source_likelihood": _normalize(score).tolist(),
        "metadata": {
            "method": "backward particle residence histogram",
            "wind_u": u,
            "wind_v": v,
            "wind_speed": speed,
            "particles": n_particles,
            "duration_s": duration,
        },
    }


def backward_firefront(config: SuiteConfig) -> dict[str, Any]:
    """Estimate ignition likelihood from observed burned/fire points.

    Observed fire points are read from ``fire.ignitions`` when row/col are
    present.  If none are configured, the grid center is used as a documented
    didactic fallback.
    """
    config.validate()
    xx, yy = _grid_xy(config)
    fire = config.fire
    observed: list[tuple[int, int]] = []
    if fire is not None:
        for point in fire.ignitions:
            if point.row is not None and point.col is not None:
                observed.append((int(point.row), int(point.col)))
    if not observed:
        observed = [(config.grid.ny // 2, config.grid.nx // 2)]
    wind_dir = float(config.run.get("default_fire_wind_dir_rad", np.pi / 2.0))
    ex = np.sin(wind_dir)
    ey = -np.cos(wind_dir)
    spread_sigma = float(config.run.get("backward_fire_sigma_m", max(config.grid.dx, config.grid.dy) * 3.0))
    score = np.zeros(xx.shape, dtype=np.float64)
    for row, col in observed:
        row = min(max(row, 0), config.grid.ny - 1)
        col = min(max(col, 0), config.grid.nx - 1)
        ox = xx[row, col]
        oy = yy[row, col]
        dx = ox - xx
        dy = oy - yy
        downwind = dx * ex + dy * ey
        cross = -dx * ey + dy * ex
        # Candidate ignitions must be upwind of the observed burned point; the
        # exponential distance term keeps nearby plausible starts preferred.
        candidate = downwind >= 0
        distance = np.hypot(dx, dy)
        footprint = np.exp(-distance / max(spread_sigma, 1.0)) * np.exp(-0.5 * (cross / max(spread_sigma, 1.0)) ** 2)
        score += np.where(candidate, footprint, 0.0)
    return {
        "component": "spritz.backward.firefront",
        "x": xx[0].astype(float).tolist(),
        "y": yy[:, 0].astype(float).tolist(),
        "ignition_likelihood": _normalize(score).tolist(),
        "metadata": {
            "method": "reverse anisotropic fire spread footprint",
            "observed_fire_points": [{"row": r, "col": c} for r, c in observed],
            "wind_dir_rad": wind_dir,
        },
    }


def write_backward_csv(path: str | Path, result: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    key = "ignition_likelihood" if "ignition_likelihood" in result else "source_likelihood"
    arr = np.asarray(result[key], dtype=float)
    xs = list(result["x"])
    ys = list(result["y"])
    with NamedTemporaryFile("w", newline="", encoding="utf-8", dir=p.parent, delete=False) as handle:
        writer = csv.DictWriter(handle, fieldnames=["row", "col", "x", "y", key])
        writer.writeheader()
        for r, y in enumerate(ys):
            for c, x in enumerate(xs):
                writer.writerow({"row": r, "col": c, "x": x, "y": y, key: arr[r, c]})
        tmp = handle.name
    Path(tmp).replace(p)


def run_backward(
    config: SuiteConfig,
    meteo_path: str | Path | None,
    output: str | Path,
    *,
    model: str = "gaussian",
    output_format: str = "json",
    seed: int | None = None,
) -> dict[str, Any]:
    model_key = model.strip().lower()
    if model_key in {"gaussian", "spritz"}:
        if meteo_path is None:
            raise ValueError("Gaussian backward simulation requires --meteo")
        result = backward_gaussian(config, read_meteorology(meteo_path))
    elif model_key in {"particle", "particles"}:
        if meteo_path is None:
            raise ValueError("Particle backward simulation requires --meteo")
        result = backward_particles(config, read_meteorology(meteo_path), seed=seed)
    elif model_key in {"firefront", "fire"}:
        result = backward_firefront(config)
    else:
        raise ValueError("backward model must be gaussian, particles, or firefront")
    if output_format == "csv":
        write_backward_csv(output, result)
    else:
        write_json(output, result)
    return result

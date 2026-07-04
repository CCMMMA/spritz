from __future__ import annotations

import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

import numpy as np

from sprtz.config import SuiteConfig
from sprtz.core.grid import Grid
from sprtz.core.physics import exponential_loss_factor, random_walk_std_from_k, stack_tip_downwash
from sprtz.exceptions import DataFormatError
from sprtz.io.calpuff import write_calpuff_concentration_dat
from sprtz.io.legacy_outputs import infer_format, write_legacy_table
from sprtz.io.netcdf_cf import write_cf_concentration
from sprtz.models.spritz import (
    _firefighters_emission_factor,
    _grid_receptors,
    _source_active,
    concentration_output_mode,
    field_z_levels,
    model_receptors,
    output_times,
    precipitation_washout_rate,
    read_meteorology,
    sample_datetime,
    terrain_fields_for_grid,
    _terrain_row_fields_for_receptor,
    WindSampler,
    write_csv,
)
from sprtz.parallel import get_gpu_context, get_mpi_context

LOGGER = logging.getLogger(__name__)


def _run_float(config: SuiteConfig, *names: str, default: float) -> float:
    for name in names:
        value = config.run.get(name, config.run.get(name.upper()))
        if value is not None:
            return float(value)
    return float(default)


def _run_text(config: SuiteConfig, *names: str, default: str) -> str:
    for name in names:
        value = config.run.get(name, config.run.get(name.upper()))
        if value is not None:
            return str(value).strip().lower()
    return default


def _particle_diffusivities(config: SuiteConfig, duration_s: float, legacy_sigma_h: float) -> tuple[float, float, float]:
    """Resolve constant particle eddy diffusivities in m2/s.

    Explicit ``particle_k*`` keys use the random-walk convention directly.  If
    old configurations only set ``particle_sigma_h``, treat it as a target
    one-dimensional spread over the particle sampling duration rather than as a
    per-step displacement.
    """
    legacy_k = legacy_sigma_h**2 / max(2.0 * duration_s, 1.0)
    kx = _run_float(config, "particle_kx_m2_s", "particle_k_m2_s", default=legacy_k)
    ky = _run_float(config, "particle_ky_m2_s", "particle_k_m2_s", default=legacy_k)
    kz = _run_float(config, "particle_kz_m2_s", default=1.0)
    return max(kx, 0.0), max(ky, 0.0), max(kz, 0.0)


def _apply_vertical_boundary(
    z: np.ndarray,
    weights: np.ndarray,
    *,
    ground_m: float,
    top_m: float,
    ground_policy: str,
    top_policy: str,
) -> tuple[np.ndarray, np.ndarray]:
    """Apply deterministic vertical boundary handling to particle positions."""
    bounded = np.asarray(z, dtype=float).copy()
    mass = np.asarray(weights, dtype=float).copy()
    ground = float(ground_m)
    top = max(float(top_m), ground + 1.0)
    below = bounded < ground
    if np.any(below):
        if ground_policy == "absorb_deposit":
            mass[below] = 0.0
            bounded[below] = ground
        else:
            bounded[below] = ground + (ground - bounded[below])
    above = bounded > top
    if np.any(above):
        if top_policy == "open":
            mass[above] = 0.0
            bounded[above] = top
        else:
            bounded[above] = top - (bounded[above] - top)
            bounded = np.clip(bounded, ground, top)
    return bounded, mass


def _wind(meteo: dict[str, Any]) -> tuple[float, float]:
    try:
        u = float(np.nanmean(np.asarray(meteo.get("u", [[2.0]]), dtype=float)))
        v = float(np.nanmean(np.asarray(meteo.get("v", [[0.0]]), dtype=float)))
    except (TypeError, ValueError) as exc:
        raise DataFormatError("particle model meteorology u/v must be numeric") from exc
    return u, v


def _particle_effective_release_heights(
    src: Any,
    *,
    wind_speed: float,
    downwind_distances: np.ndarray,
    ambient_temperature: float,
    downwash: bool,
) -> np.ndarray:
    """Return effective release heights for particle-age travel distances."""
    u = max(float(wind_speed), 0.1)
    diameter = max(float(src.stack_diameter), 0.1)
    delta_t = max(float(src.exit_temperature) - float(ambient_temperature), 0.0)
    buoyancy = 9.80665 * float(src.exit_velocity) * diameter**2 * delta_t / (
        4.0 * max(float(ambient_temperature), 1.0)
    )
    if src.heat_release > 0.0:
        buoyancy += 8.8e-6 * float(src.heat_release)
    x = np.maximum(np.asarray(downwind_distances, dtype=float), 1.0)
    if buoyancy > 0.0:
        buoyant_rise = 1.6 * (buoyancy ** (1.0 / 3.0)) * (x ** (2.0 / 3.0)) / u
    else:
        buoyant_rise = np.zeros_like(x)
    momentum = max(float(src.exit_velocity), 0.0) * diameter / u
    rise = np.maximum(buoyant_rise, 3.0 * momentum)
    penalty = (
        stack_tip_downwash(float(src.stack_height), diameter, float(src.exit_velocity), u)
        if downwash
        else 0.0
    )
    return np.maximum(float(src.z) + float(src.stack_height) + rise - penalty, 0.0)


def simulate_particles(
    config: SuiteConfig,
    meteo: dict[str, Any],
    *,
    n_particles: int | None = None,
    seed: int | None = None,
    terrain_fields: dict[str, np.ndarray] | None = None,
    parallel: str = "serial",
    gpu_backend: str | None = None,
    progress_callback: Callable[[int, float], None] | None = None,
) -> list[dict[str, float | str]]:
    """Run a deterministic Lagrangian particle screening alternative to Spritz.

    The module accepts the same SuiteConfig and meteorology files as the Gaussian
    Spritz kernel and emits the same receptor concentration table.
    It is designed for interoperability, not regulatory equivalence.
    """
    config.validate()
    if n_particles is None:
        n_particles = int(config.run.get("particles", config.run.get("PARTICLES", 2000)))
    if n_particles <= 0:
        raise DataFormatError("n_particles must be positive")
    base_seed = (
        seed
        if seed is not None
        else int(config.run.get("particle_random_seed", config.run.get("seed", config.run.get("SEED", 42))))
    )
    duration = float(config.run.get("particle_duration_s", config.run.get("PARTICLE_DURATION_S", 3600.0)))
    advection_steps = max(1, int(config.run.get("particle_advection_steps", config.run.get("PARTICLE_ADVECTION_STEPS", 8))))
    sigma_h = float(config.run.get("particle_sigma_h", 250.0))
    sigma_z = float(config.run.get("particle_sigma_z", 80.0))
    diffusion_model = _run_text(config, "particle_diffusion_model", default="constant")
    if diffusion_model != "constant":
        raise DataFormatError("run.particle_diffusion_model currently supports constant")
    kx, ky, kz = _particle_diffusivities(config, duration, sigma_h)
    vertical_boundary = _run_text(config, "particle_vertical_boundary", default="reflect")
    top_boundary = _run_text(config, "particle_top_boundary", default="reflect")
    if vertical_boundary not in {"reflect", "absorb_deposit"}:
        raise DataFormatError("run.particle_vertical_boundary must be reflect or absorb_deposit")
    if top_boundary not in {"reflect", "open"}:
        raise DataFormatError("run.particle_top_boundary must be reflect or open")
    top_m = _run_float(config, "particle_top_m", "model_top_m", default=1000.0)
    receptor_radius = float(config.run.get("particle_receptor_radius", 400.0))
    washout_rate = precipitation_washout_rate(config, meteo)
    ambient_temperature = float(np.nanmean(np.asarray(meteo.get("temperature", [[293.15]]), dtype=float)))
    receptors = model_receptors(config)
    output_mode = concentration_output_mode(config)
    field_levels = field_z_levels(config)
    field_receptors = _grid_receptors(config, field_levels) if output_mode in {"grid", "both"} else ()
    field_ids = {rec.id for rec in field_receptors}
    sampled_terrain = terrain_fields or {}
    point_receptors = tuple(rec for rec in receptors if rec.id not in field_ids)
    grid = Grid(**asdict(config.grid))
    wind_sampler = WindSampler(meteo, grid_dx=config.grid.dx, grid_dy=config.grid.dy)
    x_edges = np.concatenate(
        (
            [grid.x[0] - 0.5 * grid.dx],
            0.5 * (grid.x[:-1] + grid.x[1:]),
            [grid.x[-1] + 0.5 * grid.dx],
        )
    )
    y_edges = np.concatenate(
        (
            [grid.y[0] - 0.5 * grid.dy],
            0.5 * (grid.y[:-1] + grid.y[1:]),
            [grid.y[-1] + 0.5 * grid.dy],
        )
    )
    total_emission = sum(src.emission_rate for src in config.sources) or 1.0

    ctx = get_mpi_context(parallel)
    gpu = get_gpu_context(gpu_backend or str(config.run.get("gpu_backend", "numpy")), rank=ctx.rank)
    xp = gpu.xp
    local_sources = [(i, config.sources[i]) for i in ctx.partition(len(config.sources))]
    rows: list[dict[str, float | str]] = []
    for time_index, time_value in enumerate(output_times(config), start=1):
        sample_dt = sample_datetime(config, time_value)
        firefighter_factor = _firefighters_emission_factor(config, sample_dt)
        receptor_values = {rec.id: {"concentration": 0.0, "dry_flux": 0.0, "wet_flux": 0.0} for rec in receptors}
        local_values = {rec.id: {"concentration": 0.0, "dry_flux": 0.0, "wet_flux": 0.0} for rec in receptors}
        sample_window = min(duration, max(float(time_value), 0.0))
        if sample_window <= 0.0:
            sample_window = min(duration, float(config.run.get("output_interval_s", duration)))
        for source_index, src in local_sources:
            if not _source_active(config, src, sample_dt):
                continue
            seed_i = base_seed + source_index * 1000003 + int(round(float(time_value) * 10.0))
            rng = np.random.default_rng(seed_i)
            count = max(1, int(round(n_particles * src.emission_rate / total_emission)))
            if gpu.enabled:
                grng = xp.random.default_rng(seed_i)
                travel = grng.uniform(0.0, sample_window, count)
                px = xp.full(count, src.x, dtype=float)
                py = xp.full(count, src.y, dtype=float)
                pz = src.z + src.stack_height + grng.normal(0.0, sigma_z, count)
            else:
                travel = rng.uniform(0.0, sample_window, count)
                px = np.full(count, src.x, dtype=float)
                py = np.full(count, src.y, dtype=float)
                pz = src.z + src.stack_height + rng.normal(0.0, sigma_z, count)
            if src.width > 0 or src.length > 0:
                if gpu.enabled:
                    px += grng.uniform(-0.5 * src.length, 0.5 * src.length, count)
                    py += grng.uniform(-0.5 * src.width, 0.5 * src.width, count)
                else:
                    px += rng.uniform(-0.5 * src.length, 0.5 * src.length, count)
                    py += rng.uniform(-0.5 * src.width, 0.5 * src.width, count)
            if src.source_type.lower() == "flare":
                pz += max(src.heat_release, 0.0) ** (1.0 / 3.0) * 0.01
            travel_np = gpu.asnumpy(travel) if gpu.enabled else travel
            px_np = gpu.asnumpy(px) if gpu.enabled else px
            py_np = gpu.asnumpy(py) if gpu.enabled else py
            pz_np = gpu.asnumpy(pz) if gpu.enabled else pz
            release_time = np.maximum(float(time_value) - travel_np, 0.0)
            step_dt = travel_np / float(advection_steps)
            plume_u, plume_v, plume_speed = wind_sampler.vector(
                src.x,
                src.y,
                max(src.z + src.stack_height, 0.0),
                max(float(time_value), 0.0),
            )
            del plume_u, plume_v
            plume_distances = np.maximum(plume_speed * np.maximum(travel_np, 1.0), 1.0)
            plume_heights = _particle_effective_release_heights(
                src,
                wind_speed=plume_speed,
                downwind_distances=plume_distances,
                ambient_temperature=ambient_temperature,
                downwash=bool(config.run.get("stack_tip_downwash", True)),
            )
            pz_np += plume_heights - (src.z + src.stack_height)
            boundary_weights = np.ones(count, dtype=float)
            for step in range(advection_steps):
                current_time = release_time + (step + 0.5) * step_dt
                u_step, v_step = wind_sampler.sample(
                    px_np,
                    py_np,
                    pz_np,
                    current_time,
                )
                px_np = px_np + u_step * step_dt + rng.normal(0.0, random_walk_std_from_k(kx, step_dt), count)
                py_np = py_np + v_step * step_dt + rng.normal(0.0, random_walk_std_from_k(ky, step_dt), count)
                pz_np = pz_np + rng.normal(0.0, random_walk_std_from_k(kz, step_dt), count)
                if src.settling_velocity > 0.0:
                    pz_np = pz_np - float(src.settling_velocity) * step_dt
                pz_np, _boundary_mass = _apply_vertical_boundary(
                    pz_np,
                    np.ones(count, dtype=float),
                    ground_m=0.0,
                    top_m=top_m,
                    ground_policy=vertical_boundary,
                    top_policy=top_boundary,
                )
                boundary_weights *= _boundary_mass
            loss_rate = max(src.decay_rate, 0.0) + max(src.wet_scavenging, 0.0) + washout_rate
            loss_rate += max(src.deposition_velocity + src.settling_velocity, 0.0) / max(
                sigma_z * 10.0, 1.0
            )
            weights_np = np.asarray(exponential_loss_factor(loss_rate, travel_np), dtype=float) * boundary_weights
            pz_np, weights_np = _apply_vertical_boundary(
                pz_np,
                weights_np,
                ground_m=0.0,
                top_m=top_m,
                ground_policy=vertical_boundary,
                top_policy=top_boundary,
            )
            particle_mass = src.emission_rate * sample_window / count
            point_volume = max(np.pi * receptor_radius**2 * max(sigma_z, 1.0), 1.0)
            for rec in point_receptors:
                dist2 = (px_np - rec.x) ** 2 + (py_np - rec.y) ** 2 + ((pz_np - rec.z) * 0.2) ** 2
                hits = dist2 <= receptor_radius**2
                value = float(np.sum(weights_np[hits])) * particle_mass / point_volume * firefighter_factor
                local_values[rec.id]["concentration"] += value
                local_values[rec.id]["dry_flux"] += value * max(src.deposition_velocity, 0.0)
                local_values[rec.id]["wet_flux"] += value * (max(src.wet_scavenging, 0.0) + washout_rate)
            if field_receptors:
                cell_volume = max(grid.dx * grid.dy * max(sigma_z, 1.0), 1.0)
                for level_index, level in enumerate(field_levels):
                    vertical_weight = np.exp(-0.5 * ((pz_np - level) / max(sigma_z, 1.0)) ** 2)
                    mass_grid, _, _ = np.histogram2d(
                        py_np,
                        px_np,
                        bins=(y_edges, x_edges),
                        weights=weights_np * vertical_weight,
                    )
                    conc_grid = mass_grid * particle_mass / cell_volume * firefighter_factor
                    for iy in range(grid.ny):
                        for ix in range(grid.nx):
                            rec_id = f"G{iy}_{ix}" if len(field_levels) == 1 else f"G{level_index}_{iy}_{ix}"
                            value = float(conc_grid[iy, ix])
                            local_values[rec_id]["concentration"] += value
                            local_values[rec_id]["dry_flux"] += value * max(src.deposition_velocity, 0.0)
                            local_values[rec_id]["wet_flux"] += value * (max(src.wet_scavenging, 0.0) + washout_rate)
        gathered = ctx.allgather(local_values)
        for partial in gathered:
            for rec_id, values in partial.items():
                receptor_values[rec_id]["concentration"] += float(values["concentration"])
                receptor_values[rec_id]["dry_flux"] += float(values["dry_flux"])
                receptor_values[rec_id]["wet_flux"] += float(values["wet_flux"])
        for rec in receptors:
            total = 0.0
            dry_flux = 0.0
            wet_flux = 0.0
            total += receptor_values[rec.id]["concentration"]
            dry_flux += receptor_values[rec.id]["dry_flux"]
            wet_flux += receptor_values[rec.id]["wet_flux"]
            row: dict[str, float | str] = {
                "time": time_value,
                **({} if sample_dt is None else {"datetime": sample_dt.isoformat()}),
                "receptor": rec.id,
                "output_kind": "field" if rec.id in field_ids else "receptor",
                "x": rec.x,
                "y": rec.y,
                "z": rec.z,
                **_terrain_row_fields_for_receptor(sampled_terrain, rec.id),
                "concentration": total,
                "dry_flux": dry_flux,
                "wet_flux": wet_flux,
            }
            if rec.latitude is not None and rec.longitude is not None:
                row["latitude"] = float(rec.latitude)
                row["longitude"] = float(rec.longitude)
            rows.append(row)
        if ctx.is_root:
            if progress_callback is not None:
                progress_callback(time_index, time_value)
            else:
                LOGGER.info(
                    "Spritz particles: concentration output interval reached index=%d output_time_s=%.0f",
                    time_index,
                    time_value,
                )
    return rows


def write_particle_output(path: str | Path, rows: list[dict[str, float | str]], output_format: str = "auto") -> None:
    fmt = infer_format(path, output_format)
    if fmt == "netcdf":
        write_cf_concentration(path, rows)
    elif fmt == "calpuff":
        write_calpuff_concentration_dat(path, rows)
    elif fmt == "legacy":
        write_legacy_table(path, "Spritz particle concentration and deposition table", rows)
    else:
        write_csv(path, rows)


def run(
    config: SuiteConfig,
    meteo_path: str | Path,
    output: str | Path,
    output_format: str = "auto",
    seed: int | None = None,
    *,
    terrain_input: str | Path | None = None,
    parallel: str = "serial",
    gpu_backend: str | None = None,
    progress_callback: Callable[[int, float], None] | None = None,
) -> list[dict[str, float | str]]:
    ctx = get_mpi_context(parallel)
    terrain_fields = terrain_fields_for_grid(terrain_input, config)
    rows = simulate_particles(
        config,
        read_meteorology(meteo_path),
        seed=seed,
        terrain_fields=terrain_fields,
        parallel=parallel,
        gpu_backend=gpu_backend,
        progress_callback=progress_callback,
    )
    if ctx.is_root:
        write_particle_output(output, rows, output_format)
    ctx.barrier()
    return rows

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from sprtz.config import SuiteConfig
from sprtz.exceptions import DataFormatError
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
    write_csv,
)
from sprtz.parallel import get_gpu_context, get_mpi_context


def _wind(meteo: dict[str, Any]) -> tuple[float, float]:
    try:
        u = float(np.nanmean(np.asarray(meteo.get("u", [[2.0]]), dtype=float)))
        v = float(np.nanmean(np.asarray(meteo.get("v", [[0.0]]), dtype=float)))
    except (TypeError, ValueError) as exc:
        raise DataFormatError("particle model meteorology u/v must be numeric") from exc
    return u, v


def simulate_particles(
    config: SuiteConfig,
    meteo: dict[str, Any],
    *,
    n_particles: int | None = None,
    seed: int | None = None,
    parallel: str = "serial",
    gpu_backend: str | None = None,
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
    base_seed = seed if seed is not None else int(config.run.get("seed", config.run.get("SEED", 42)))
    u, v = _wind(meteo)
    duration = float(config.run.get("particle_duration_s", config.run.get("PARTICLE_DURATION_S", 3600.0)))
    sigma_h = float(config.run.get("particle_sigma_h", 250.0))
    sigma_z = float(config.run.get("particle_sigma_z", 80.0))
    receptor_radius = float(config.run.get("particle_receptor_radius", 400.0))
    washout_rate = precipitation_washout_rate(config, meteo)
    receptors = model_receptors(config)
    output_mode = concentration_output_mode(config)
    field_ids = (
        {rec.id for rec in _grid_receptors(config, field_z_levels(config))}
        if output_mode in {"grid", "both"}
        else set()
    )
    total_emission = sum(src.emission_rate for src in config.sources) or 1.0

    ctx = get_mpi_context(parallel)
    gpu = get_gpu_context(gpu_backend or str(config.run.get("gpu_backend", "numpy")), rank=ctx.rank)
    xp = gpu.xp
    local_sources = [(i, config.sources[i]) for i in ctx.partition(len(config.sources))]
    local_source_totals: dict[str, dict[str, float]] = {}

    for source_index, src in local_sources:
        source_totals = {rec.id: 0.0 for rec in receptors}
        # Per-source seed keeps results deterministic regardless of MPI size.
        seed_i = base_seed + source_index * 1000003
        rng = np.random.default_rng(seed_i)
        count = max(1, int(round(n_particles * src.emission_rate / total_emission)))
        if gpu.enabled:
            grng = xp.random.default_rng(seed_i)
            travel = grng.uniform(0.0, duration, count)
            px = src.x + u * travel + grng.normal(0.0, sigma_h, count)
            py = src.y + v * travel + grng.normal(0.0, sigma_h, count)
            pz = src.z + src.stack_height + grng.normal(0.0, sigma_z, count)
        else:
            travel = rng.uniform(0.0, duration, count)
            px = src.x + u * travel + rng.normal(0.0, sigma_h, count)
            py = src.y + v * travel + rng.normal(0.0, sigma_h, count)
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
        loss_rate = max(src.decay_rate, 0.0) + max(src.wet_scavenging, 0.0) + washout_rate
        loss_rate += max(src.deposition_velocity + src.settling_velocity, 0.0) / max(
            sigma_z * 10.0, 1.0
        )
        weights = xp.exp(-loss_rate * travel) if gpu.enabled else np.exp(-loss_rate * travel)
        particle_mass = src.emission_rate * duration / count
        for rec in receptors:
            dist2 = (px - rec.x) ** 2 + (py - rec.y) ** 2 + ((pz - rec.z) * 0.2) ** 2
            hits = dist2 <= receptor_radius**2
            hit_mass = float(gpu.asnumpy(xp.sum(weights[hits])) if gpu.enabled else np.sum(weights[hits])) * particle_mass
            # Convert hit density to a stable screening concentration proxy.
            volume = max(np.pi * receptor_radius**2 * max(sigma_z, 1.0), 1.0)
            source_totals[rec.id] += hit_mass / volume
        local_source_totals[src.id] = source_totals

    source_concentrations = {src.id: {rec.id: 0.0 for rec in receptors} for src in config.sources}
    gathered = ctx.allgather(local_source_totals)
    for partial in gathered:
        for source_id, values in partial.items():
            for rec_id, value in values.items():
                source_concentrations[source_id][rec_id] += float(value)

    rows: list[dict[str, float | str]] = []
    for time_value in output_times(config):
        sample_dt = sample_datetime(config, time_value)
        firefighter_factor = _firefighters_emission_factor(config, sample_dt)
        for rec in receptors:
            total = 0.0
            dry_flux = 0.0
            wet_flux = 0.0
            for src in config.sources:
                if not _source_active(config, src, sample_dt):
                    continue
                value = source_concentrations[src.id][rec.id] * firefighter_factor
                total += value
                dry_flux += value * max(src.deposition_velocity, 0.0)
                wet_flux += value * (max(src.wet_scavenging, 0.0) + washout_rate)
            rows.append(
                {
                    "time": time_value,
                    **({} if sample_dt is None else {"datetime": sample_dt.isoformat()}),
                    "receptor": rec.id,
                    "output_kind": "field" if rec.id in field_ids else "receptor",
                    "x": rec.x,
                    "y": rec.y,
                    "z": rec.z,
                    "concentration": total,
                    "dry_flux": dry_flux,
                    "wet_flux": wet_flux,
                }
            )
    return rows


def write_particle_output(path: str | Path, rows: list[dict[str, float | str]], output_format: str = "auto") -> None:
    fmt = infer_format(path, output_format)
    if fmt == "netcdf":
        write_cf_concentration(path, rows)
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
    parallel: str = "serial",
    gpu_backend: str | None = None,
) -> list[dict[str, float | str]]:
    ctx = get_mpi_context(parallel)
    rows = simulate_particles(
        config,
        read_meteorology(meteo_path),
        seed=seed,
        parallel=parallel,
        gpu_backend=gpu_backend,
    )
    if ctx.is_root:
        write_particle_output(output, rows, output_format)
    ctx.barrier()
    return rows

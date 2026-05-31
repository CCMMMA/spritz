from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np

from sprtz.config import Receptor, SuiteConfig
from sprtz.core.grid import Grid
from sprtz.exceptions import DataFormatError
from sprtz.io.legacy_outputs import infer_format, write_legacy_table
from sprtz.io.netcdf_cf import write_cf_concentration
from sprtz.models.spritz import read_meteorology, write_csv
from sprtz.parallel import get_mpi_context


def _grid_receptors(config: SuiteConfig) -> tuple[Receptor, ...]:
    grid = Grid(**asdict(config.grid))
    return tuple(
        Receptor(id=f"G{iy}_{ix}", x=float(x), y=float(y), z=0.0)
        for iy, y in enumerate(grid.y)
        for ix, x in enumerate(grid.x)
    )


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
    receptors = config.receptors or _grid_receptors(config)
    totals = {rec.id: 0.0 for rec in receptors}
    total_emission = sum(src.emission_rate for src in config.sources) or 1.0

    ctx = get_mpi_context(parallel)
    local_sources = [(i, config.sources[i]) for i in ctx.partition(len(config.sources))]
    local_totals = {rec.id: 0.0 for rec in receptors}

    for source_index, src in local_sources:
        # Per-source seed keeps results deterministic regardless of MPI size.
        rng = np.random.default_rng(base_seed + source_index * 1000003)
        count = max(1, int(round(n_particles * src.emission_rate / total_emission)))
        travel = rng.uniform(0.0, duration, count)
        px = src.x + u * travel + rng.normal(0.0, sigma_h, count)
        py = src.y + v * travel + rng.normal(0.0, sigma_h, count)
        pz = src.z + src.stack_height + rng.normal(0.0, sigma_z, count)
        if src.width > 0 or src.length > 0:
            px += rng.uniform(-0.5 * src.length, 0.5 * src.length, count)
            py += rng.uniform(-0.5 * src.width, 0.5 * src.width, count)
        if src.source_type.lower() == "flare":
            pz += max(src.heat_release, 0.0) ** (1.0 / 3.0) * 0.01
        loss_rate = max(src.decay_rate, 0.0) + max(src.wet_scavenging, 0.0)
        loss_rate += max(src.deposition_velocity + src.settling_velocity, 0.0) / max(sigma_z * 10.0, 1.0)
        weights = np.exp(-loss_rate * travel)
        particle_mass = src.emission_rate * duration / count
        for rec in receptors:
            dist2 = (px - rec.x) ** 2 + (py - rec.y) ** 2 + ((pz - rec.z) * 0.2) ** 2
            hits = dist2 <= receptor_radius**2
            hit_mass = float(np.sum(weights[hits])) * particle_mass
            # Convert hit density to a stable screening concentration proxy.
            volume = max(np.pi * receptor_radius**2 * max(sigma_z, 1.0), 1.0)
            local_totals[rec.id] += hit_mass / volume

    gathered = ctx.allgather(local_totals)
    for partial in gathered:
        for rec_id, value in partial.items():
            totals[rec_id] += float(value)

    return [
        {
            "time": 0.0,
            "receptor": rec.id,
            "x": rec.x,
            "y": rec.y,
            "concentration": totals[rec.id],
            "dry_flux": totals[rec.id] * sum(max(s.deposition_velocity, 0.0) for s in config.sources),
            "wet_flux": totals[rec.id] * sum(max(s.wet_scavenging, 0.0) for s in config.sources),
        }
        for rec in receptors
    ]


def write_particle_output(path: str | Path, rows: list[dict[str, float | str]], output_format: str = "auto") -> None:
    fmt = infer_format(path, output_format)
    if fmt == "netcdf":
        write_cf_concentration(path, rows)
    elif fmt == "legacy":
        write_legacy_table(path, "Sprtz particle concentration and deposition table", rows)
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
) -> list[dict[str, float | str]]:
    ctx = get_mpi_context(parallel)
    rows = simulate_particles(config, read_meteorology(meteo_path), seed=seed, parallel=parallel)
    if ctx.is_root:
        write_particle_output(output, rows, output_format)
    ctx.barrier()
    return rows

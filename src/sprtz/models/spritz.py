from __future__ import annotations

import csv
from dataclasses import asdict
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import numpy as np

from sprtz.config import Receptor, SuiteConfig
from sprtz.core.grid import Grid
from sprtz.core.physics import (
    depletion_factor,
    dispersion_parameters,
    effective_release_height,
    gaussian_plume,
    gaussian_puff,
)
from sprtz.exceptions import DataFormatError
from sprtz.io.jsonio import read_json
from sprtz.io.legacy_outputs import infer_format, write_legacy_table
from sprtz.io.netcdf_cf import read_cf_meteorology, write_cf_concentration
from sprtz.parallel import get_mpi_context


def _mean_wind(meteo: dict[str, Any]) -> tuple[float, float, float]:
    try:
        u = np.asarray(meteo.get("u", meteo.get("eastward_wind", [[2.0]])), dtype=float)
        v = np.asarray(meteo.get("v", meteo.get("northward_wind", [[0.0]])), dtype=float)
    except (TypeError, ValueError) as exc:
        raise DataFormatError("meteorology u/v fields must be numeric arrays") from exc
    if u.shape != v.shape:
        raise DataFormatError(f"meteorology u/v shape mismatch: {u.shape} vs {v.shape}")
    if u.size == 0:
        raise DataFormatError("meteorology fields must not be empty")
    um = float(np.nanmean(u))
    vm = float(np.nanmean(v))
    speed = max(float(np.hypot(um, vm)), 0.1)
    return um, vm, speed


def _down_cross(dx: float, dy: float, u: float, v: float, speed: float) -> tuple[float, float]:
    ex, ey = u / speed, v / speed
    xdown = dx * ex + dy * ey
    ycross = -dx * ey + dy * ex
    return xdown, ycross


def _grid_receptors(config: SuiteConfig) -> tuple[Receptor, ...]:
    grid = Grid(**asdict(config.grid))
    return tuple(
        Receptor(id=f"G{iy}_{ix}", x=float(x), y=float(y), z=0.0)
        for iy, y in enumerate(grid.y)
        for ix, x in enumerate(grid.x)
    )


def read_meteorology(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if p.suffix.lower() in {".nc", ".cdf", ".netcdf"}:
        return read_cf_meteorology(p)
    return read_json(p)


def output_times(config: SuiteConfig) -> tuple[float, ...]:
    """Resolve optional concentration output times in seconds.

    The default remains the historical single output at ``time=0``. When
    ``run.output_interval_s`` is present, Spritz emits rows at that interval
    independently from the meteorological input cadence. The default duration is
    ``run.averaging_time_s`` so existing one-hour examples can request, for
    example, 600-second outputs without changing meteorology.
    """
    interval_value = config.run.get("output_interval_s", config.run.get("OUTPUT_INTERVAL_S"))
    if interval_value is None:
        return (0.0,)
    interval = float(interval_value)
    if interval <= 0:
        raise DataFormatError("run.output_interval_s must be positive")
    duration = float(
        config.run.get(
            "output_duration_s",
            config.run.get(
                "OUTPUT_DURATION_S",
                config.run.get("averaging_time_s", config.run.get("AVERAGING_TIME_S", interval)),
            ),
        )
    )
    if duration <= 0:
        raise DataFormatError("run.output_duration_s must be positive")
    start = float(config.run.get("output_start_s", config.run.get("OUTPUT_START_S", interval)))
    if start < 0:
        raise DataFormatError("run.output_start_s must be non-negative")
    values = np.arange(start, duration + interval * 1.0e-9, interval, dtype=float)
    if values.size == 0:
        values = np.asarray([duration], dtype=float)
    return tuple(float(np.round(value, 9)) for value in values)


def compute_concentrations(
    config: SuiteConfig,
    meteo: dict[str, Any],
    *,
    parallel: str = "serial",
) -> list[dict[str, float | str]]:
    config.validate()
    u, v, speed = _mean_wind(meteo)
    rows: list[dict[str, float | str]] = []
    receptors = config.receptors or _grid_receptors(config)
    stability = str(config.run.get("stability", config.run.get("STABILITY", "D")))
    numerical_mode = str(config.run.get("numerical_mode", config.run.get("NUMERICAL_MODE", "puff"))).lower()
    averaging_time = float(config.run.get("averaging_time_s", config.run.get("AVERAGING_TIME_S", 3600.0)))
    times = output_times(config)
    output_interval = config.run.get("output_interval_s", config.run.get("OUTPUT_INTERVAL_S"))
    interval_mass_time = float(output_interval) if output_interval is not None else averaging_time
    legacy_steady_output = output_interval is None
    ambient_temperature = float(np.nanmean(np.asarray(meteo.get("temperature", [[293.15]]), dtype=float)))
    mixing_height = float(np.nanmean(np.asarray(meteo.get("mixing_height", [[1000.0]]), dtype=float)))
    ctx = get_mpi_context(parallel)
    local_receptors = [receptors[i] for i in ctx.partition(len(receptors))]
    local_rows: list[dict[str, float | str]] = []
    for rec in local_receptors:
        for sample_time in times:
            total = 0.0
            dry_total = 0.0
            wet_total = 0.0
            for src in config.sources:
                xdown, ycross = _down_cross(rec.x - src.x, rec.y - src.y, u, v, speed)
                if xdown <= 0:
                    continue
                travel_time = xdown / speed
                elapsed_s = travel_time if legacy_steady_output else max(sample_time, 1.0)
                puff_center_x = xdown if legacy_steady_output else speed * sample_time
                eff_h = effective_release_height(
                    stack_height=src.stack_height,
                    source_z=src.z,
                    receptor_z=rec.z,
                    wind_speed=speed,
                    downwind_distance=max(puff_center_x, xdown, 1.0),
                    stack_diameter=src.stack_diameter,
                    exit_velocity=src.exit_velocity,
                    exit_temperature=src.exit_temperature,
                    ambient_temperature=ambient_temperature,
                    heat_release=src.heat_release,
                    downwash=bool(config.run.get("stack_tip_downwash", True)),
                )
                depletion = depletion_factor(
                    travel_time_s=elapsed_s,
                    decay_rate_s=src.decay_rate,
                    deposition_velocity_m_s=src.deposition_velocity,
                    mixing_height_m=mixing_height,
                    wet_scavenging_s=src.wet_scavenging,
                    settling_velocity_m_s=src.settling_velocity,
                )
                if numerical_mode == "plume":
                    conc = gaussian_plume(
                        q=src.emission_rate * depletion,
                        wind_speed=speed,
                        x_downwind=xdown,
                        y_crosswind=ycross,
                        z=0.0,
                        h=eff_h,
                        stability=stability,
                    )
                else:
                    # Time-resolved puff output advects the puff center with the
                    # mean wind. This lets output cadence differ from the
                    # meteorological cadence while the default path below keeps
                    # the legacy steady representative concentration unchanged.
                    sigmas = dispersion_parameters(
                        max(puff_center_x, 1.0),
                        stability,
                        elapsed_s=elapsed_s,
                        source_width=src.width,
                        source_length=src.length,
                        source_height=max(src.height, 0.0),
                    )
                    emission_window = min(interval_mass_time, max(elapsed_s, 1.0))
                    mass = src.emission_rate * emission_window * depletion
                    conc = gaussian_puff(
                        mass=mass,
                        x_receptor=xdown,
                        y_receptor=ycross,
                        z_receptor=0.0,
                        x_center=puff_center_x,
                        y_center=0.0,
                        z_center=eff_h,
                        sigmas=sigmas,
                    )
                    conc = conc / max(emission_window, 1.0)
                total += conc
                dry_total += conc * max(src.deposition_velocity, 0.0)
                wet_total += conc * max(src.wet_scavenging, 0.0) * mixing_height
            row: dict[str, float | str] = {
                "time": sample_time,
                "receptor": rec.id,
                "x": rec.x,
                "y": rec.y,
                "concentration": total,
                "dry_flux": dry_total,
                "wet_flux": wet_total,
            }
            if rec.latitude is not None and rec.longitude is not None:
                row["latitude"] = float(rec.latitude)
                row["longitude"] = float(rec.longitude)
            local_rows.append(row)
    return ctx.gather_flat(local_rows)


def write_csv(path: str | Path, rows: list[dict[str, float | str]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fields = ["time", "receptor", "x", "y", "concentration", "dry_flux", "wet_flux"]
    if any("latitude" in row and "longitude" in row for row in rows):
        fields.extend(["latitude", "longitude"])
    with NamedTemporaryFile("w", newline="", encoding="utf-8", dir=p.parent, delete=False) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)
        tmp_name = handle.name
    Path(tmp_name).replace(p)


def write_concentration(path: str | Path, rows: list[dict[str, float | str]], output_format: str = "auto") -> None:
    fmt = infer_format(path, output_format)
    if fmt == "netcdf":
        write_cf_concentration(path, rows)
    elif fmt == "legacy":
        write_legacy_table(path, "Sprtz concentration and deposition table", rows)
    else:
        write_csv(path, rows)


def run(
    config: SuiteConfig,
    meteo_path: str | Path,
    output: str | Path,
    output_format: str = "auto",
    *,
    parallel: str = "serial",
) -> list[dict[str, float | str]]:
    ctx = get_mpi_context(parallel)
    meteo = read_meteorology(meteo_path)
    rows = compute_concentrations(config, meteo, parallel=parallel)
    if ctx.is_root:
        write_concentration(output, rows, output_format)
    ctx.barrier()
    return rows

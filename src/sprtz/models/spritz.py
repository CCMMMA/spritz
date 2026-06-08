from __future__ import annotations

import csv
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import numpy as np

from sprtz.config import Receptor, Source, SuiteConfig, parse_datetime_value, parse_field_z_levels, run_datetime
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
from sprtz.parallel import get_gpu_context, get_mpi_context


def wildfire_plume_rise(intensity_kw_per_m: float, perimeter_m: float, u_ms: float) -> float:
    """Effective smoke release height using a Briggs buoyancy-dominated estimate."""
    q_heat_w = max(0.0, intensity_kw_per_m) * max(0.0, perimeter_m) * 1000.0
    g, cp, rho, t0 = 9.81, 1005.0, 1.2, 293.0
    fb = (g / (cp * rho * t0)) * q_heat_w
    u_safe = max(float(u_ms), 0.5)
    if fb > 55.0:
        return float(1.6 * fb**0.333 * (10.0 * max(perimeter_m, 1.0)) ** 0.667 / u_safe)
    return float(21.425 * fb**0.75 / u_safe)


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


def _mean_precipitation_rate(meteo: dict[str, Any]) -> float:
    try:
        precipitation = np.asarray(meteo.get("precipitation_rate", [[0.0]]), dtype=float)
    except (TypeError, ValueError) as exc:
        raise DataFormatError("meteorology precipitation_rate field must be numeric") from exc
    if precipitation.size == 0:
        return 0.0
    return max(float(np.nanmean(precipitation)), 0.0)


def _down_cross(dx: float, dy: float, u: float, v: float, speed: float) -> tuple[float, float]:
    ex, ey = u / speed, v / speed
    xdown = dx * ex + dy * ey
    ycross = -dx * ey + dy * ex
    return xdown, ycross


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _run_value(config: SuiteConfig, *names: str, default: Any = None) -> Any:
    for name in names:
        value = config.run.get(name, config.run.get(name.upper()))
        if value is not None:
            return value
    return default


def weather_start_datetime(config: SuiteConfig) -> datetime | None:
    return run_datetime(config.run, "weather_start_datetime", "simulation_start_datetime")


def sample_datetime(config: SuiteConfig, sample_time_s: float) -> datetime | None:
    start = weather_start_datetime(config)
    if start is None:
        return None
    return start + timedelta(seconds=float(sample_time_s))


def _source_window(config: SuiteConfig, source: Source) -> tuple[datetime | None, datetime | None]:
    start = parse_datetime_value(source.start_datetime, field_name=f"source {source.id} start_datetime")
    end = parse_datetime_value(source.end_datetime, field_name=f"source {source.id} end_datetime")
    if start is None:
        start = run_datetime(config.run, "event_start_datetime", "fire_start_datetime")
    if end is None:
        end = run_datetime(config.run, "event_end_datetime", "fire_end_datetime")
    return start, end


def _source_active(config: SuiteConfig, source: Source, when: datetime | None) -> bool:
    if when is None:
        return True
    start, end = _source_window(config, source)
    if start is not None and when < start:
        return False
    if end is not None and when > end:
        return False
    return True


def _firefighters_emission_factor(config: SuiteConfig, when: datetime | None) -> float:
    if when is None:
        return 1.0
    start = run_datetime(config.run, "firefighters_start_datetime")
    end = run_datetime(config.run, "firefighters_end_datetime")
    if start is None or end is None or not (start <= when <= end):
        return 1.0
    return float(_run_value(config, "firefighters_emission_factor", default=1.0))


def precipitation_washout_rate(config: SuiteConfig, meteo: dict[str, Any]) -> float:
    enabled = _truthy(
        _run_value(
            config,
            "precipitation_washout",
            "use_precipitation_washout",
            default=False,
        )
    )
    if not enabled:
        return 0.0
    coefficient = float(
        _run_value(
            config,
            "precipitation_washout_coefficient_s_per_mm_h",
            default=1.0e-5,
        )
    )
    return max(coefficient, 0.0) * _mean_precipitation_rate(meteo)


def concentration_output_mode(config: SuiteConfig) -> str:
    """Resolve receptor-table, grid-field, or combined concentration output."""
    mode_value = config.run.get("concentration_output", config.run.get("CONCENTRATION_OUTPUT"))
    if mode_value is None:
        field_requested = _truthy(
            config.run.get(
                "output_field",
                config.run.get("OUTPUT_FIELD", config.run.get("concentration_field", False)),
            )
        )
        if field_requested:
            return "both" if config.receptors else "grid"
        return "receptors" if config.receptors else "grid"
    mode = str(mode_value).strip().lower()
    aliases = {
        "receptor": "receptors",
        "receptors": "receptors",
        "grid": "grid",
        "field": "grid",
        "grid_field": "grid",
        "both": "both",
    }
    try:
        return aliases[mode]
    except KeyError as exc:
        raise DataFormatError("run.concentration_output must be receptors, grid, or both") from exc


def field_z_levels(config: SuiteConfig) -> tuple[float, ...]:
    """Return vertical levels used when a gridded concentration field is requested."""
    return parse_field_z_levels(
        config.run.get(
            "field_z_levels",
            config.run.get("FIELD_Z_LEVELS", config.run.get("z_levels", config.run.get("Z_LEVELS"))),
        )
    )


def _grid_receptors(config: SuiteConfig, z_levels: tuple[float, ...] | None = None) -> tuple[Receptor, ...]:
    grid = Grid(**asdict(config.grid))
    levels = z_levels if z_levels is not None else (0.0,)
    receptors: list[Receptor] = []
    for iz, z_value in enumerate(levels):
        for iy, y in enumerate(grid.y):
            for ix, x in enumerate(grid.x):
                receptor_id = f"G{iy}_{ix}" if len(levels) == 1 else f"G{iz}_{iy}_{ix}"
                receptors.append(Receptor(id=receptor_id, x=float(x), y=float(y), z=float(z_value)))
    return tuple(receptors)


def model_receptors(config: SuiteConfig) -> tuple[Receptor, ...]:
    """Return the receptor set implied by the concentration output mode."""
    mode = concentration_output_mode(config)
    if mode == "receptors":
        return config.receptors or _grid_receptors(config)
    grid = _grid_receptors(config, field_z_levels(config))
    if mode == "grid":
        return grid
    return tuple(config.receptors) + grid


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
    weather_start = weather_start_datetime(config)
    weather_end = run_datetime(config.run, "weather_end_datetime", "simulation_end_datetime")
    if weather_start is not None and weather_end is not None:
        default_duration = max((weather_end - weather_start).total_seconds(), interval)
    else:
        default_duration = config.run.get("averaging_time_s", config.run.get("AVERAGING_TIME_S", interval))
    duration = float(
        config.run.get(
            "output_duration_s",
            config.run.get("OUTPUT_DURATION_S", default_duration),
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
    gpu_backend: str | None = None,
) -> list[dict[str, float | str]]:
    config.validate()
    u, v, speed = _mean_wind(meteo)
    rows: list[dict[str, float | str]] = []
    receptors = model_receptors(config)
    output_mode = concentration_output_mode(config)
    field_ids = (
        {rec.id for rec in _grid_receptors(config, field_z_levels(config))}
        if output_mode in {"grid", "both"}
        else set()
    )
    stability = str(config.run.get("stability", config.run.get("STABILITY", "D")))
    numerical_mode = str(config.run.get("numerical_mode", config.run.get("NUMERICAL_MODE", "puff"))).lower()
    averaging_time = float(config.run.get("averaging_time_s", config.run.get("AVERAGING_TIME_S", 3600.0)))
    times = output_times(config)
    output_interval = config.run.get("output_interval_s", config.run.get("OUTPUT_INTERVAL_S"))
    interval_mass_time = float(output_interval) if output_interval is not None else averaging_time
    legacy_steady_output = output_interval is None
    ambient_temperature = float(np.nanmean(np.asarray(meteo.get("temperature", [[293.15]]), dtype=float)))
    mixing_height = float(np.nanmean(np.asarray(meteo.get("mixing_height", [[1000.0]]), dtype=float)))
    washout_rate = precipitation_washout_rate(config, meteo)
    ctx = get_mpi_context(parallel)
    gpu = get_gpu_context(gpu_backend or str(config.run.get("gpu_backend", "numpy")), rank=ctx.rank)
    xp = gpu.xp
    source_x = xp.asarray([src.x for src in config.sources], dtype=float)
    source_y = xp.asarray([src.y for src in config.sources], dtype=float)
    local_receptors = [receptors[i] for i in ctx.partition(len(receptors))]
    local_rows: list[dict[str, float | str]] = []
    for rec in local_receptors:
        for sample_time in times:
            sample_dt = sample_datetime(config, sample_time)
            firefighter_factor = _firefighters_emission_factor(config, sample_dt)
            total = 0.0
            dry_total = 0.0
            wet_total = 0.0
            dx_all = rec.x - source_x
            dy_all = rec.y - source_y
            xdown_all = dx_all * (u / speed) + dy_all * (v / speed)
            ycross_all = -dx_all * (v / speed) + dy_all * (u / speed)
            xdown_values = np.asarray(gpu.asnumpy(xdown_all), dtype=float)
            ycross_values = np.asarray(gpu.asnumpy(ycross_all), dtype=float)
            for src_index, src in enumerate(config.sources):
                if not _source_active(config, src, sample_dt):
                    continue
                xdown = float(xdown_values[src_index])
                ycross = float(ycross_values[src_index])
                if xdown <= 0:
                    continue
                source_wet_rate = max(src.wet_scavenging, 0.0) + washout_rate
                emission_rate = src.emission_rate * firefighter_factor
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
                    wet_scavenging_s=source_wet_rate,
                    settling_velocity_m_s=src.settling_velocity,
                )
                if numerical_mode == "plume":
                    conc = gaussian_plume(
                        q=emission_rate * depletion,
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
                    mass = emission_rate * emission_window * depletion
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
                wet_total += conc * source_wet_rate * mixing_height
            row: dict[str, float | str] = {
                "time": sample_time,
                "receptor": rec.id,
                "output_kind": "field" if rec.id in field_ids else "receptor",
                "x": rec.x,
                "y": rec.y,
                "z": rec.z,
                "concentration": total,
                "dry_flux": dry_total,
                "wet_flux": wet_total,
            }
            if rec.latitude is not None and rec.longitude is not None:
                row["latitude"] = float(rec.latitude)
                row["longitude"] = float(rec.longitude)
            if sample_dt is not None:
                row["datetime"] = sample_dt.isoformat()
            local_rows.append(row)
    return ctx.gather_flat(local_rows)


def write_csv(path: str | Path, rows: list[dict[str, float | str]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "time",
        "datetime",
        "receptor",
        "output_kind",
        "x",
        "y",
        "z",
        "concentration",
        "dry_flux",
        "wet_flux",
    ]
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
        write_legacy_table(path, "Spritz concentration and deposition table", rows)
    else:
        write_csv(path, rows)


def run(
    config: SuiteConfig,
    meteo_path: str | Path,
    output: str | Path,
    output_format: str = "auto",
    *,
    parallel: str = "serial",
    gpu_backend: str | None = None,
) -> list[dict[str, float | str]]:
    ctx = get_mpi_context(parallel)
    meteo = read_meteorology(meteo_path)
    rows = compute_concentrations(config, meteo, parallel=parallel, gpu_backend=gpu_backend)
    if ctx.is_root:
        write_concentration(output, rows, output_format)
    ctx.barrier()
    return rows

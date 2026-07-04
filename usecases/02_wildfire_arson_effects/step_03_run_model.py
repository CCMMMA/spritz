#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from sprtz.workflow import run_workflow
from sprtz.io.jsonio import read_json, write_json
from sprtz.logging import configure_logging

USECASES_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(USECASES_ROOT))

from plotting import plot_3d_volume_if_available, plot_concentration_vertical_profiles_if_available
from wildfire import (
    DEFAULT_WILDFIRE_FIELD_Z_LEVELS,
    DEFAULT_WILDFIRE_PARTICLE_ADVECTION_STEPS,
    DEFAULT_WILDFIRE_PARTICLE_COUNT,
    DEFAULT_WILDFIRE_PARTICLE_SIGMA_H_M,
    DEFAULT_WILDFIRE_PARTICLE_SIGMA_Z_M,
    ensure_wildfire_receptor_coordinates,
)


LOGGER = logging.getLogger(__name__)


def _default_meteo_path(config_path: str | Path) -> Path | None:
    candidate = Path(config_path).parent / "wrf_100m_wind.nc"
    return candidate if candidate.exists() else None


def _default_terrain_path(config_path: str | Path) -> Path | None:
    candidate = Path(config_path).parent / "geo.nc"
    return candidate if candidate.exists() else None


def _infer_output_interval_s(meteo_path: str | Path | None) -> float | None:
    if meteo_path is None:
        return None
    try:
        from netCDF4 import Dataset  # type: ignore
    except Exception:
        return None
    with Dataset(meteo_path) as ds:
        if "time" not in ds.variables:
            return None
        values = list(float(value) for value in ds.variables["time"][:])
    deltas = [b - a for a, b in zip(values, values[1:]) if b > a]
    if not deltas:
        return None
    return float(deltas[0])


def _ensure_time_dependent_plume_config(config_path: str | Path, meteo_path: str | Path | None) -> tuple[dict, float | None, bool]:
    config = read_json(config_path)
    run = dict(config.get("run", {}))
    changed = False
    if "output_interval_s" not in run:
        interval = _infer_output_interval_s(meteo_path) or 3600.0
        run["output_interval_s"] = float(interval)
        changed = True
    else:
        interval = float(run["output_interval_s"])
    if "concentration_output" not in run:
        run["concentration_output"] = "both"
        changed = True
    if "field_z_levels" not in run:
        run["field_z_levels"] = list(DEFAULT_WILDFIRE_FIELD_Z_LEVELS)
        changed = True
    particle_defaults = {
        "particles": DEFAULT_WILDFIRE_PARTICLE_COUNT,
        "particle_duration_s": 3600.0,
        "particle_sigma_h": DEFAULT_WILDFIRE_PARTICLE_SIGMA_H_M,
        "particle_sigma_z": DEFAULT_WILDFIRE_PARTICLE_SIGMA_Z_M,
        "particle_advection_steps": DEFAULT_WILDFIRE_PARTICLE_ADVECTION_STEPS,
    }
    for key, value in particle_defaults.items():
        if key not in run:
            run[key] = value
            changed = True
    if changed:
        config = {**config, "run": run}
        write_json(config_path, config)
    return config, interval, changed


def _compare_concentration_outputs(particle_path: str | Path, gaussian_path: str | Path, output_path: str | Path) -> dict:
    try:
        from netCDF4 import Dataset  # type: ignore
        import numpy as np
    except Exception:
        return {"available": False, "reason": "netCDF4/numpy unavailable"}
    with Dataset(particle_path) as particle_ds, Dataset(gaussian_path) as gaussian_ds:
        for axis in ("time", "field_x", "field_y", "field_z"):
            if axis not in particle_ds.variables or axis not in gaussian_ds.variables:
                raise ValueError(f"cannot compare concentration fields: missing {axis!r} coordinate")
            particle_axis = np.asarray(particle_ds.variables[axis][:], dtype=float)
            gaussian_axis = np.asarray(gaussian_ds.variables[axis][:], dtype=float)
            if particle_axis.shape != gaussian_axis.shape or not np.allclose(particle_axis, gaussian_axis, rtol=1.0e-9, atol=1.0e-9):
                raise ValueError(f"particle/Gaussian {axis} coordinates differ")
        variable = "concentration_field" if "concentration_field" in particle_ds.variables and "concentration_field" in gaussian_ds.variables else "concentration"
        particle_values = np.asarray(particle_ds.variables[variable][:], dtype=float)
        gaussian_values = np.asarray(gaussian_ds.variables[variable][:], dtype=float)
    common_shape = tuple(min(a, b) for a, b in zip(particle_values.shape, gaussian_values.shape))
    slices = tuple(slice(0, size) for size in common_shape)
    particle_common = particle_values[slices]
    gaussian_common = gaussian_values[slices]
    diff = particle_common - gaussian_common
    report = {
        "available": True,
        "variable": variable,
        "shape": list(common_shape),
        "grid_consistent": True,
        "particle_min": float(np.nanmin(particle_common)),
        "particle_max": float(np.nanmax(particle_common)),
        "gaussian_min": float(np.nanmin(gaussian_common)),
        "gaussian_max": float(np.nanmax(gaussian_common)),
        "mean_absolute_difference": float(np.nanmean(np.abs(diff))),
        "root_mean_square_difference": float(np.sqrt(np.nanmean(diff * diff))),
        "max_absolute_difference": float(np.nanmax(np.abs(diff))),
    }
    write_json(output_path, report)
    return report


def _concentration_output_times(concentration_path: str | Path) -> list[float]:
    try:
        from netCDF4 import Dataset  # type: ignore
    except Exception:
        return []
    path = Path(concentration_path)
    if path.suffix.lower() != ".nc" or not path.exists():
        return []
    with Dataset(path) as ds:
        if "time" not in ds.variables:
            return []
        return [float(value) for value in ds.variables["time"][:]]


def _log_backend_hourly_performance(
    *,
    backend: str,
    workflow: dict,
    elapsed_s: float,
    output_interval_s: float | None,
) -> None:
    concentration = workflow.get("concentration")
    output_times = _concentration_output_times(concentration) if concentration else []
    interval_s = float(output_interval_s or workflow.get("output_interval_s") or 3600.0)
    simulated_hours = max(len(output_times) * interval_s / 3600.0, 1.0)
    seconds_per_hour = elapsed_s / simulated_hours
    LOGGER.info(
        "step 3/3 performance: backend=%s elapsed_s=%.3f simulated_hours=%.3f seconds_per_simulated_hour=%.3f",
        backend,
        elapsed_s,
        simulated_hours,
        seconds_per_hour,
    )
    if not output_times:
        LOGGER.info(
            "step 3/3 progress: backend=%s computed_hour=1 output_time_s=unknown cumulative_simulated_hours=%.3f estimated_seconds_for_hour=%.3f",
            backend,
            simulated_hours,
            seconds_per_hour,
        )


def _run_workflow_with_performance_log(
    *,
    config_path: str | Path,
    output_dir: str | Path,
    backend: str,
    interchange: str,
    output_interval_s: float | None,
    meteo_input: Path | None,
    terrain_input: Path | None,
    calpuff_binary: bool,
) -> dict:
    LOGGER.info("step 3/3 workflow: running Sprtz workflow backend=%s", backend)
    started = time.perf_counter()

    def _log_concentration_progress(index: int, output_time_s: float) -> None:
        elapsed_s = time.perf_counter() - started
        interval_s = float(output_interval_s or 3600.0)
        cumulative_simulated_hours = index * interval_s / 3600.0
        seconds_per_hour = elapsed_s / max(cumulative_simulated_hours, 1.0e-9)
        LOGGER.info(
            "step 3/3 progress: backend=%s computed_hour=%d output_time_s=%.0f cumulative_simulated_hours=%.3f estimated_seconds_for_hour=%.3f elapsed_s=%.3f",
            backend,
            index,
            output_time_s,
            cumulative_simulated_hours,
            seconds_per_hour,
            elapsed_s,
        )

    workflow = run_workflow(
        config_path,
        output_dir,
        backend=backend,
        interchange=interchange,
        parallel="serial",
        output_interval_s=output_interval_s,
        meteo_input=meteo_input,
        terrain_input=terrain_input,
        calpuff_binary=calpuff_binary,
        concentration_progress_callback=_log_concentration_progress,
    )
    elapsed_s = time.perf_counter() - started
    _log_backend_hourly_performance(
        backend=backend,
        workflow=workflow,
        elapsed_s=elapsed_s,
        output_interval_s=output_interval_s,
    )
    return workflow


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Spritz for a prepared wildfire/arson configuration")
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--backend", choices=["gaussian", "particles", "both"], default="both")
    parser.add_argument("--interchange", choices=["json", "netcdf"], default="netcdf")
    parser.add_argument("--meteo", default=None, help="prepared meteorology file; defaults to wrf_100m_wind.nc beside the config")
    parser.add_argument("--terrain", default=None, help="prepared GEO/terrain file; defaults to geo.nc beside the config")
    parser.add_argument("--output-interval-s", type=float, default=None, help="concentration output interval in seconds")
    parser.add_argument("--calpuff-binary", action="store_true", help="write clean-room CALPUFF-style binary concentration sidecars")
    parser.add_argument("--verbose", action="store_true", help="enable debug logging")
    args = parser.parse_args(argv)
    configure_logging(args.verbose)
    LOGGER.info("step 3/3 input: config=%s output_dir=%s", args.config, args.output_dir)
    LOGGER.info("step 3/3 model: backend=%s interchange=%s parallel=serial", args.backend, args.interchange)
    upgraded = ensure_wildfire_receptor_coordinates(args.config)
    if upgraded:
        LOGGER.info("step 3/3 config: added receptor latitude/longitude coordinates to %s", args.config)
    meteo_input = Path(args.meteo) if args.meteo else _default_meteo_path(args.config)
    terrain_input = Path(args.terrain) if args.terrain else _default_terrain_path(args.config)
    if meteo_input is not None:
        LOGGER.info("step 3/3 meteo: using prepared meteorology %s", meteo_input)
    if terrain_input is not None:
        LOGGER.info("step 3/3 terrain: using prepared GEO/terrain %s", terrain_input)
    config, inferred_interval_s, plume_upgraded = _ensure_time_dependent_plume_config(args.config, meteo_input)
    output_interval_s = args.output_interval_s if args.output_interval_s is not None else inferred_interval_s
    if plume_upgraded:
        LOGGER.info("step 3/3 config: enabled time-dependent gridded plume output in %s", args.config)
    if output_interval_s is not None:
        LOGGER.info("step 3/3 timing: concentration output interval %.0f s", output_interval_s)
    workflows: dict[str, dict] = {}
    if args.backend == "both":
        for backend in ("particles", "gaussian"):
            backend_dir = Path(args.output_dir) / backend
            workflows[backend] = _run_workflow_with_performance_log(
                config_path=args.config,
                output_dir=backend_dir,
                backend=backend,
                interchange=args.interchange,
                output_interval_s=output_interval_s,
                meteo_input=meteo_input,
                terrain_input=terrain_input,
                calpuff_binary=args.calpuff_binary,
            )
            LOGGER.info(
                "step 3/3 workflow: backend=%s wrote meteo=%s concentration=%s post=%s",
                backend,
                workflows[backend].get("meteo"),
                workflows[backend].get("concentration"),
                workflows[backend].get("post"),
            )
        workflow = workflows["particles"]
        comparison_path = Path(args.output_dir) / "particle_gaussian_comparison.json"
        comparison = _compare_concentration_outputs(
            workflows["particles"]["concentration"],
            workflows["gaussian"]["concentration"],
            comparison_path,
        )
        LOGGER.info("step 3/3 comparison: wrote %s metrics=%s", comparison_path, comparison)
    else:
        workflow = _run_workflow_with_performance_log(
            config_path=args.config,
            output_dir=args.output_dir,
            backend=args.backend,
            interchange=args.interchange,
            output_interval_s=output_interval_s,
            meteo_input=meteo_input,
            terrain_input=terrain_input,
            calpuff_binary=args.calpuff_binary,
        )
        workflows[args.backend] = workflow
        LOGGER.info("step 3/3 workflow: wrote meteo=%s concentration=%s post=%s", workflow.get("meteo"), workflow.get("concentration"), workflow.get("post"))
    plots: dict[str, str] = {}
    for backend, backend_workflow in workflows.items():
        backend_output_dir = Path(args.output_dir) / backend if args.backend == "both" else Path(args.output_dir)
        plume_profile = plot_concentration_vertical_profiles_if_available(
            backend_workflow.get("concentration"),
            backend_output_dir / f"{backend}_concentration_vertical_profiles.png",
        )
        if plume_profile is not None:
            plots[f"{backend}_plume_vertical_profiles"] = str(plume_profile)
        plume_3d = plot_3d_volume_if_available(
            backend_workflow.get("concentration"),
            backend_output_dir / f"{backend}_concentration_3d.png",
            terrain_path=backend_workflow.get("terrain") or backend_workflow.get("meteo") or meteo_input,
            title=f"{backend.title()} concentration 3D",
        )
        if plume_3d is not None:
            plots[f"{backend}_plume_3d"] = str(plume_3d)
    if plots:
        LOGGER.info("step 3/3 plotting: wrote %s", plots)
    else:
        LOGGER.info("step 3/3 plotting: no vertical profile figures were generated")
    LOGGER.info("step 3/3 complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

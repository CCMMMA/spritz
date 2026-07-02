#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from sprtz.workflow import run_workflow
from sprtz.io.jsonio import read_json, write_json
from sprtz.logging import configure_logging

USECASES_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(USECASES_ROOT))

from plotting import plot_workflow_netcdfs
from wildfire import ensure_wildfire_receptor_coordinates


LOGGER = logging.getLogger(__name__)


def _default_meteo_path(config_path: str | Path) -> Path | None:
    candidate = Path(config_path).parent / "wrf_100m_wind.nc"
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
        run["field_z_levels"] = [1.5]
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Spritz for a prepared wildfire/arson configuration")
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--backend", choices=["gaussian", "particles", "both"], default="both")
    parser.add_argument("--interchange", choices=["json", "netcdf"], default="netcdf")
    parser.add_argument("--meteo", default=None, help="prepared meteorology file; defaults to wrf_100m_wind.nc beside the config")
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
    if meteo_input is not None:
        LOGGER.info("step 3/3 meteo: using prepared meteorology %s", meteo_input)
    config, inferred_interval_s, plume_upgraded = _ensure_time_dependent_plume_config(args.config, meteo_input)
    output_interval_s = args.output_interval_s if args.output_interval_s is not None else inferred_interval_s
    if plume_upgraded:
        LOGGER.info("step 3/3 config: enabled time-dependent gridded plume output in %s", args.config)
    if output_interval_s is not None:
        LOGGER.info("step 3/3 timing: concentration output interval %.0f s", output_interval_s)
    metadata = config.get("metadata", {})
    center_lat = metadata.get("center_lat")
    center_lon = metadata.get("center_lon")
    if center_lat is not None and center_lon is not None:
        LOGGER.info("step 3/3 plotting: using geographic center lat=%s lon=%s", center_lat, center_lon)
    workflows: dict[str, dict] = {}
    if args.backend == "both":
        for backend in ("particles", "gaussian"):
            backend_dir = Path(args.output_dir) / backend
            LOGGER.info("step 3/3 workflow: running Sprtz workflow backend=%s", backend)
            workflows[backend] = run_workflow(
                args.config,
                backend_dir,
                backend=backend,
                interchange=args.interchange,
                parallel="serial",
                output_interval_s=output_interval_s,
                meteo_input=meteo_input,
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
        LOGGER.info("step 3/3 workflow: running Sprtz workflow backend=%s", args.backend)
        workflow = run_workflow(
            args.config,
            args.output_dir,
            backend=args.backend,
            interchange=args.interchange,
            parallel="serial",
                output_interval_s=output_interval_s,
                meteo_input=meteo_input,
                calpuff_binary=args.calpuff_binary,
        )
        workflows[args.backend] = workflow
        LOGGER.info("step 3/3 workflow: wrote meteo=%s concentration=%s post=%s", workflow.get("meteo"), workflow.get("concentration"), workflow.get("post"))
    plots: dict[str, str] = {}
    for backend, backend_workflow in workflows.items():
        backend_output_dir = Path(args.output_dir) / backend if args.backend == "both" else Path(args.output_dir)
        plots.update(
            {
                f"{backend}_{key}": value
                for key, value in plot_workflow_netcdfs(
                    backend_workflow,
                    backend_output_dir,
                    center_lat=None if center_lat is None else float(center_lat),
                    center_lon=None if center_lon is None else float(center_lon),
                ).items()
            }
        )
    if plots:
        LOGGER.info("step 3/3 plotting: wrote %s", plots)
    else:
        LOGGER.info("step 3/3 plotting: no NetCDF maps were generated")
    LOGGER.info("step 3/3 complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path
from typing import Any

import numpy as np

LOGGER = logging.getLogger(__name__)

NETCDF_SUFFIXES = {".nc", ".nc4", ".cdf", ".netcdf"}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_plotter() -> Any:
    path = _repo_root() / "tools" / "plotter.py"
    spec = importlib.util.spec_from_file_location("sprtz_tools_plotter", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load plotter tool from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def plot_netcdf_if_available(
    input_path: str | Path | None,
    output_path: str | Path,
    *,
    variable: str | None = None,
    title: str | None = None,
    center_lat: float | None = None,
    center_lon: float | None = None,
    dpi: int = 600,
) -> Path | None:
    if input_path is None:
        return None
    source = Path(input_path)
    if source.suffix.lower() not in NETCDF_SUFFIXES or not source.exists():
        return None
    try:
        plotter = _load_plotter()
        try:
            field = plotter.read_map_field(
                source,
                variable_name=variable,
                time_index=0,
                level_index=0,
                center_lat=center_lat,
                center_lon=center_lon,
            )
        except Exception:
            if variable is None:
                raise
            field = plotter.read_map_field(
                source,
                variable_name=None,
                time_index=0,
                level_index=0,
                center_lat=center_lat,
                center_lon=center_lon,
            )
        return plotter.plot_map(
            field,
            output_path,
            title=title,
            dpi=dpi,
            cmap="viridis",
            coastline_resolution="10m",
            allow_cartopy_download=False,
            figure_size=(7.2, 5.4),
            log_scale=False,
            vector_overlay=True,
            vector_stride=8,
            vector_scale=None,
        )
    except Exception as exc:
        LOGGER.warning("could not plot %s with tools/plotter.py: %s", source, exc)
        return None


def plot_workflow_netcdfs(
    workflow: dict[str, Any] | None,
    output_dir: str | Path,
    *,
    center_lat: float | None = None,
    center_lon: float | None = None,
    prefix: str = "",
) -> dict[str, str]:
    if not workflow:
        return {}
    out = Path(output_dir)
    products: dict[str, str] = {}
    variables = {
        "terrain": "surface_altitude",
        "meteo": "wind_speed",
        "concentration": "concentration",
        "firefront": "fire_probability",
        "puff": "concentration",
    }
    for key, variable in variables.items():
        path = workflow.get(key)
        figure = out / f"{prefix}{key}_map.png"
        plotted = plot_netcdf_if_available(
            path,
            figure,
            variable=variable,
            title=f"{key.replace('_', ' ').title()}",
            center_lat=center_lat,
            center_lon=center_lon,
        )
        if plotted is not None:
            products[key] = str(plotted)
    return products


def write_grid_result_netcdf_if_available(
    result: dict[str, Any],
    output_path: str | Path,
    *,
    variable: str,
    long_name: str,
    units: str = "1",
) -> Path | None:
    if variable not in result or "x" not in result or "y" not in result:
        return None
    try:
        from netCDF4 import Dataset  # type: ignore
    except Exception:
        LOGGER.warning("netCDF4 is unavailable; skipping NetCDF sidecar for %s", variable)
        return None
    values = np.asarray(result[variable], dtype=float)
    x = np.asarray(result["x"], dtype=float)
    y = np.asarray(result["y"], dtype=float)
    if values.ndim != 2 or values.shape != (y.size, x.size):
        LOGGER.warning("cannot write %s NetCDF sidecar: grid shape does not match x/y axes", variable)
        return None
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with Dataset(out, "w") as ds:
        ds.createDimension("y", y.size)
        ds.createDimension("x", x.size)
        ds.Conventions = "CF-1.8"
        ds.title = long_name
        x_var = ds.createVariable("x", "f8", ("x",))
        y_var = ds.createVariable("y", "f8", ("y",))
        x_var.units = y_var.units = "m"
        x_var.standard_name = "projection_x_coordinate"
        y_var.standard_name = "projection_y_coordinate"
        x_var[:] = x
        y_var[:] = y
        field = ds.createVariable(variable, "f8", ("y", "x"), zlib=True)
        field.long_name = long_name
        field.units = units
        field[:, :] = values
    return out

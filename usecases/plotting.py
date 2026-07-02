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
    time_index: int = 0,
    level_index: int = 0,
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
                time_index=time_index,
                level_index=level_index,
                center_lat=center_lat,
                center_lon=center_lon,
            )
        except Exception:
            if time_index != 0:
                field = plotter.read_map_field(
                    source,
                    variable_name=variable,
                    time_index=0,
                    level_index=level_index,
                    center_lat=center_lat,
                    center_lon=center_lon,
                )
            elif variable is None:
                raise
            else:
                field = plotter.read_map_field(
                    source,
                    variable_name=None,
                    time_index=time_index,
                    level_index=level_index,
                    center_lat=center_lat,
                    center_lon=center_lon,
                )
        return plotter.plot_map(
            field,
            output_path,
            title=title,
            dpi=dpi,
            cmap="viridis",
            coastline_source="naturalearth",
            coastline_resolution="10m",
            allow_cartopy_download=False,
            figure_size=(7.2, 5.4),
            log_scale=False,
            vector_overlay=True,
            vector_stride=8,
            vector_density=None,
            vector_scale=None,
        )
    except Exception as exc:
        LOGGER.warning("could not plot %s with tools/plotter.py: %s", source, exc)
        return None


def _decode_time_labels(values: Any) -> list[str]:
    labels: list[str] = []
    for value in values:
        text = str(value)
        labels.append(text.replace("+00:00", "Z"))
    return labels


def _with_diagnostic_10m_profile_layer(ds: Any, values: np.ndarray, z_axis: np.ndarray, variable: str) -> tuple[np.ndarray, np.ndarray, bool]:
    if values.ndim != 4 or z_axis.size == 0 or float(np.nanmin(z_axis)) <= 10.0 + 1.0e-6:
        return values, z_axis, False
    diagnostic: np.ndarray | None = None
    if variable == "wind_speed" and "wind_speed_10m" in ds.variables:
        diagnostic = np.asarray(ds.variables["wind_speed_10m"][:], dtype=float)
    elif variable in {"eastward_wind", "u"} and "U10M" in ds.variables:
        diagnostic = np.asarray(ds.variables["U10M"][:], dtype=float)
    elif variable in {"northward_wind", "v"} and "V10M" in ds.variables:
        diagnostic = np.asarray(ds.variables["V10M"][:], dtype=float)
    elif variable == "wind_speed" and "U10M" in ds.variables and "V10M" in ds.variables:
        diagnostic = np.hypot(
            np.asarray(ds.variables["U10M"][:], dtype=float),
            np.asarray(ds.variables["V10M"][:], dtype=float),
        )
    if diagnostic is None:
        return values, z_axis, False
    if diagnostic.ndim == 2:
        diagnostic = diagnostic[np.newaxis, :, :]
    if diagnostic.shape != (values.shape[0], values.shape[2], values.shape[3]):
        return values, z_axis, False
    z_aug = np.concatenate(([10.0], z_axis.astype(float)))
    values_aug = np.concatenate((diagnostic[:, np.newaxis, :, :], values), axis=1)
    order = np.argsort(z_aug)
    return values_aug[:, order, :, :], z_aug[order], True


def plot_vertical_profiles_if_available(
    input_path: str | Path | None,
    output_path: str | Path,
    *,
    variable: str = "wind_speed",
    x_m: float = 0.0,
    y_m: float = 0.0,
    dpi: int = 300,
) -> Path | None:
    if input_path is None:
        return None
    source = Path(input_path)
    if source.suffix.lower() not in NETCDF_SUFFIXES or not source.exists():
        return None
    try:
        from netCDF4 import Dataset  # type: ignore
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:
        LOGGER.warning("could not plot vertical profiles for %s: %s", source, exc)
        return None
    try:
        with Dataset(source) as ds:
            if variable in ds.variables:
                values = np.asarray(ds.variables[variable][:], dtype=float)
                units = str(getattr(ds.variables[variable], "units", ""))
                long_name = str(getattr(ds.variables[variable], "long_name", variable))
            elif "eastward_wind" in ds.variables and "northward_wind" in ds.variables:
                u = np.asarray(ds.variables["eastward_wind"][:], dtype=float)
                v = np.asarray(ds.variables["northward_wind"][:], dtype=float)
                values = np.hypot(u, v)
                units = "m s-1"
                long_name = "wind speed"
            else:
                return None
            if values.ndim != 4:
                return None
            x_axis = np.asarray(ds.variables["x"][:], dtype=float) if "x" in ds.variables else np.arange(values.shape[-1])
            y_axis = np.asarray(ds.variables["y"][:], dtype=float) if "y" in ds.variables else np.arange(values.shape[-2])
            z_axis = np.asarray(ds.variables["z"][:], dtype=float) if "z" in ds.variables else np.arange(values.shape[1])
            values, z_axis, used_diagnostic_10m = _with_diagnostic_10m_profile_layer(ds, values, z_axis, variable)
            time_axis = np.asarray(ds.variables["time"][:], dtype=float) if "time" in ds.variables else np.arange(values.shape[0])
            if "time_datetime" in ds.variables:
                time_labels = _decode_time_labels(ds.variables["time_datetime"][:])
            else:
                time_labels = [f"{float(value):g} s" for value in time_axis]
            z_label = str(getattr(ds.variables["z"], "long_name", "vertical level")) if "z" in ds.variables else "vertical level"
            if used_diagnostic_10m:
                z_label = "diagnostic 10 m AGL plus model vertical levels"
            z_units = str(getattr(ds.variables["z"], "units", "")) if "z" in ds.variables else ""
        ix = int(np.argmin(np.abs(x_axis - float(x_m))))
        iy = int(np.argmin(np.abs(y_axis - float(y_m))))
        profiles = values[:, :, iy, ix]
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        fig, (ax_heat, ax_profiles) = plt.subplots(1, 2, figsize=(10.5, 5.2), dpi=dpi, constrained_layout=True)
        mesh = ax_heat.pcolormesh(np.arange(profiles.shape[0]), z_axis, profiles.T, shading="auto", cmap="viridis")
        cbar = fig.colorbar(mesh, ax=ax_heat)
        cbar.set_label(f"{long_name}{f' [{units}]' if units else ''}")
        ax_heat.set_title("Time-height section")
        ax_heat.set_xlabel("time index")
        ax_heat.set_ylabel(f"{z_label}{f' [{z_units}]' if z_units else ''}")
        sample_count = min(6, profiles.shape[0])
        sample_indexes = np.linspace(0, profiles.shape[0] - 1, sample_count, dtype=int)
        cmap = plt.get_cmap("viridis")
        for order, time_index in enumerate(sample_indexes):
            color = cmap(0.0 if sample_count == 1 else order / (sample_count - 1))
            label = time_labels[time_index] if time_index < len(time_labels) else f"t={time_index}"
            ax_profiles.plot(profiles[time_index, :], z_axis, color=color, linewidth=1.7, label=label)
        ax_profiles.set_title(f"Vertical profiles at x={x_axis[ix]:.0f} m, y={y_axis[iy]:.0f} m")
        ax_profiles.set_xlabel(f"{long_name}{f' [{units}]' if units else ''}")
        ax_profiles.set_ylabel(f"{z_label}{f' [{z_units}]' if z_units else ''}")
        ax_profiles.grid(True, alpha=0.25)
        ax_profiles.legend(fontsize=6, loc="best")
        fig.suptitle(f"{source.name}: time-varying vertical {long_name}")
        fig.savefig(out)
        plt.close(fig)
        return out
    except Exception as exc:
        LOGGER.warning("could not plot vertical profiles for %s: %s", source, exc)
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
        "meteo": "wind_speed_10m",
        "concentration": "concentration_field",
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
            time_index=1 if key == "concentration" else 0,
        )
        if plotted is not None:
            products[key] = str(plotted)
        if key == "meteo":
            profile = plot_vertical_profiles_if_available(
                path,
                out / f"{prefix}{key}_vertical_profiles.png",
                variable="wind_speed",
            )
            if profile is not None:
                products[f"{key}_vertical_profiles"] = str(profile)
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

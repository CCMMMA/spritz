#!/usr/bin/env python3
"""Render academic-quality 3-D views from Sprtz NetCDF products."""

from __future__ import annotations

import argparse
import logging
import math
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from sprtz.logging import LOG_DATE_FORMAT, LOG_FORMAT_VERBOSE

LOGGER = logging.getLogger("sprtz.render3d")

TIME_DIMENSION_TOKENS = ("time", "date")
Z_NAMES = ("z", "field_z", "level", "height", "altitude", "bottom_top", "lev")
Y_NAMES = ("y", "field_y", "south_north")
X_NAMES = ("x", "field_x", "west_east")
TIME_NAMES = ("time",)
DATETIME_NAMES = ("time_datetime", "Times")
LATITUDE_NAMES = ("field_latitude", "latitude", "lat", "XLAT", "XLAT_M")
LONGITUDE_NAMES = ("field_longitude", "longitude", "lon", "long", "lng", "XLONG", "XLONG_M")
VARIABLE_CANDIDATES = (
    "concentration_field",
    "wind_speed",
    "temperature",
    "relative_humidity",
    "eastward_wind",
    "northward_wind",
)
DEM_NAMES = ("surface_altitude", "elevation_m", "dem_elevation_m", "terrain_m", "terrain")
LAND_COVER_NAMES = ("land_cover", "landuse_class", "landuse", "land_use")


@dataclass(frozen=True)
class TerrainField:
    elevation_m: np.ndarray
    x_axis: np.ndarray
    y_axis: np.ndarray
    land_cover: np.ndarray | None = None
    source_name: str | None = None
    longitude_axis: np.ndarray | None = None
    latitude_axis: np.ndarray | None = None


@dataclass(frozen=True)
class VolumeField:
    source_name: str
    variable_name: str
    values: np.ndarray
    x_axis: np.ndarray
    y_axis: np.ndarray
    z_axis: np.ndarray
    units: str
    long_name: str
    time_label: str | None = None
    longitude_axis: np.ndarray | None = None
    latitude_axis: np.ndarray | None = None

    @property
    def label(self) -> str:
        return f"{self.long_name or self.variable_name}{f' [{self.units}]' if self.units else ''}"

    @property
    def title(self) -> str:
        detail = f" | {self.time_label}" if self.time_label else ""
        return f"{self.source_name}: {self.long_name or self.variable_name}{detail}"


def _load_netcdf4() -> Any:
    try:
        from netCDF4 import Dataset
    except Exception as exc:  # pragma: no cover - depends on optional extra
        raise RuntimeError("netCDF4 is required to read NetCDF files; install sprtz[netcdf]") from exc
    return Dataset


def _load_matplotlib() -> Any:
    try:
        import matplotlib

        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt
    except Exception as exc:  # pragma: no cover - depends on optional extra
        raise RuntimeError("matplotlib is required for 3-D rendering; install sprtz[viz]") from exc
    return plt


def _decode_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").strip()
    if isinstance(value, np.ndarray):
        if value.dtype.kind in {"S", "U"}:
            return b"".join(np.asarray(value, dtype="S1").ravel()).decode("utf-8", errors="replace").strip()
        if value.size == 1:
            return _decode_text(value.item())
    return str(value).strip()


def _find_variable(ds: Any, names: Sequence[str]) -> Any | None:
    lowered = {name.lower(): name for name in ds.variables}
    for name in names:
        actual = lowered.get(str(name).lower())
        if actual is not None:
            return ds.variables[actual]
    return None


def _variable_array(variable: Any) -> np.ndarray:
    values = np.asarray(variable[:])
    if np.ma.isMaskedArray(values):
        values = np.asarray(values.filled(np.nan))
    return np.asarray(values, dtype=float)


def _take_checked(arr: np.ndarray, index: int, axis: int, *, name: str) -> np.ndarray:
    if index < 0 or index >= arr.shape[axis]:
        raise IndexError(f"{name} index {index} is out of range for size {arr.shape[axis]}")
    return np.take(arr, index, axis=axis)


def _candidate_variable_name(ds: Any, requested: str | None) -> str:
    if requested:
        lowered = {name.lower(): name for name in ds.variables}
        actual = lowered.get(requested.lower())
        if actual is None:
            raise ValueError(f"variable {requested!r} not found")
        return actual
    for name in VARIABLE_CANDIDATES:
        variable = _find_variable(ds, (name,))
        if variable is not None and len(getattr(variable, "shape", ())) >= 3:
            return str(variable.name)
    for name, variable in ds.variables.items():
        if getattr(variable, "dtype", None) is not None and variable.dtype.kind in "fiu":
            if len(getattr(variable, "shape", ())) >= 3:
                return str(name)
    raise ValueError("no 3-D gridded variable found; pass --variable explicitly")


def _axis_values(ds: Any, names: Sequence[str], size: int, dimension_name: str | None = None) -> np.ndarray:
    if dimension_name is not None:
        exact = ds.variables.get(dimension_name)
        if exact is not None:
            values = np.asarray(exact[:], dtype=float)
            if values.ndim == 1 and values.size == size:
                return values
    variable = _find_variable(ds, names)
    if variable is None:
        return np.arange(size, dtype=float)
    values = np.asarray(variable[:], dtype=float)
    if values.ndim == 1 and values.size == size:
        return values
    return np.arange(size, dtype=float)


def _geographic_axis_values(ds: Any, names: Sequence[str], size: int, axis: str) -> np.ndarray | None:
    variable = _find_variable(ds, names)
    if variable is None:
        return None
    values = np.asarray(variable[:], dtype=float)
    while values.ndim > 2:
        values = _take_checked(values, 0, 0, name="time")
    if values.ndim == 1 and values.size == size:
        return values
    if values.ndim == 2:
        line = values[values.shape[0] // 2, :] if axis == "x" else values[:, values.shape[1] // 2]
        if line.size == size:
            return np.asarray(line, dtype=float)
    return None


def _select_2d(values: np.ndarray, *, time_index: int = 0) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    while arr.ndim > 2:
        arr = _take_checked(arr, min(time_index, arr.shape[0] - 1), 0, name="time")
    if arr.ndim != 2:
        raise ValueError("terrain variables must be two-dimensional")
    return arr


def _terrain_from_dataset(ds: Any, *, source_name: str, time_index: int = 0) -> TerrainField | None:
    dem_var = _find_variable(ds, DEM_NAMES)
    if dem_var is None:
        return None
    dem = _select_2d(_variable_array(dem_var), time_index=time_index)
    dimensions = tuple(str(dim) for dim in getattr(dem_var, "dimensions", ()))
    y_dim = dimensions[-2] if len(dimensions) >= 2 else None
    x_dim = dimensions[-1] if len(dimensions) >= 1 else None
    y_axis = _axis_values(ds, Y_NAMES, dem.shape[0], y_dim)
    x_axis = _axis_values(ds, X_NAMES, dem.shape[1], x_dim)
    lon_axis = _geographic_axis_values(ds, LONGITUDE_NAMES, dem.shape[1], "x")
    lat_axis = _geographic_axis_values(ds, LATITUDE_NAMES, dem.shape[0], "y")
    land_cover = None
    land_var = _find_variable(ds, LAND_COVER_NAMES)
    if land_var is not None:
        try:
            candidate = _select_2d(_variable_array(land_var), time_index=time_index)
            if candidate.shape == dem.shape:
                land_cover = candidate
        except Exception:
            land_cover = None
    return TerrainField(dem, x_axis, y_axis, land_cover, source_name=source_name, longitude_axis=lon_axis, latitude_axis=lat_axis)


def read_terrain_field(input_path: str | Path, *, time_index: int = 0) -> TerrainField | None:
    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(
            f"terrain NetCDF {input_path} does not exist; create it with "
            "sprtz-terrain fetch using the matching DEM and land-cover rasters, "
            "or omit --terrain to render over a flat reference plane"
        )
    Dataset = _load_netcdf4()
    with Dataset(input_path) as ds:
        return _terrain_from_dataset(ds, source_name=input_path.name, time_index=time_index)


def _as_z_y_x(ds: Any, variable_name: str, *, time_index: int) -> tuple[np.ndarray, tuple[str | None, str | None, str | None], str, str]:
    variable = ds.variables[variable_name]
    values = _variable_array(variable)
    dimensions = tuple(str(dim) for dim in getattr(variable, "dimensions", ()))
    dims = [dim.lower() for dim in dimensions]
    if values.ndim == 4:
        time_axis = next((axis for axis, dim in enumerate(dims) if any(token in dim for token in TIME_DIMENSION_TOKENS)), 0)
        values = _take_checked(values, time_index, time_axis, name="time")
        dimensions = tuple(dim for axis, dim in enumerate(dimensions) if axis != time_axis)
        dims = [dim.lower() for dim in dimensions]
    elif values.ndim == 2:
        values = values[np.newaxis, :, :]
        dimensions = (None, dimensions[0] if len(dimensions) > 0 else None, dimensions[1] if len(dimensions) > 1 else None)
        return values, dimensions, str(getattr(variable, "units", "")), str(getattr(variable, "long_name", variable_name))
    if values.ndim != 3:
        raise ValueError(f"variable {variable_name!r} must be shaped as z,y,x or time,z,y,x")
    order: list[int] = []
    for tokens in (Z_NAMES, Y_NAMES, X_NAMES):
        match = next((axis for axis, dim in enumerate(dims) if any(token in dim for token in tokens)), None)
        if match is not None and match not in order:
            order.append(match)
    if len(order) == 3:
        values = np.transpose(values, order)
        dimensions = tuple(dimensions[index] for index in order)
    return values, dimensions, str(getattr(variable, "units", "")), str(getattr(variable, "long_name", variable_name))


def _time_label(ds: Any, *, time_index: int) -> str | None:
    for name in DATETIME_NAMES:
        variable = _find_variable(ds, (name,))
        if variable is not None and np.asarray(variable[:]).size:
            text = _decode_text(np.asarray(variable[:])[time_index])
            return f"UTC: {text.replace('+00:00', 'Z').replace('_', ' ')}"
    time_var = _find_variable(ds, TIME_NAMES)
    if time_var is None:
        return None
    values = np.asarray(time_var[:], dtype=float)
    if values.size == 0:
        return None
    return f"Time: {float(values[time_index]):g} {str(getattr(time_var, 'units', '')).strip()}".strip()


def read_volume_field(input_path: str | Path, *, variable_name: str | None, time_index: int) -> VolumeField:
    Dataset = _load_netcdf4()
    with Dataset(input_path) as ds:
        actual = _candidate_variable_name(ds, variable_name)
        values, dimensions, units, long_name = _as_z_y_x(ds, actual, time_index=time_index)
        z_count, y_count, x_count = values.shape
        z_axis = _axis_values(ds, Z_NAMES, z_count, dimensions[0])
        y_axis = _axis_values(ds, Y_NAMES, y_count, dimensions[1])
        x_axis = _axis_values(ds, X_NAMES, x_count, dimensions[2])
        lon_axis = _geographic_axis_values(ds, LONGITUDE_NAMES, x_count, "x")
        lat_axis = _geographic_axis_values(ds, LATITUDE_NAMES, y_count, "y")
        label = _time_label(ds, time_index=time_index)
    return VolumeField(Path(input_path).name, actual, values, x_axis, y_axis, z_axis, units, long_name, label, lon_axis, lat_axis)


def _terrain_like_volume(terrain: TerrainField | None, field: VolumeField) -> TerrainField:
    if terrain is None or terrain.elevation_m.shape != (field.y_axis.size, field.x_axis.size):
        return TerrainField(
            np.zeros((field.y_axis.size, field.x_axis.size), dtype=float),
            field.x_axis,
            field.y_axis,
            None,
            source_name=None,
            longitude_axis=field.longitude_axis,
            latitude_axis=field.latitude_axis,
        )
    return TerrainField(
        np.asarray(terrain.elevation_m, dtype=float),
        np.asarray(terrain.x_axis, dtype=float),
        np.asarray(terrain.y_axis, dtype=float),
        None if terrain.land_cover is None else np.asarray(terrain.land_cover, dtype=float),
        source_name=terrain.source_name,
        longitude_axis=terrain.longitude_axis if terrain.longitude_axis is not None else field.longitude_axis,
        latitude_axis=terrain.latitude_axis if terrain.latitude_axis is not None else field.latitude_axis,
    )


def _land_cover_facecolors(land_cover: np.ndarray | None, shape: tuple[int, int], plt: Any) -> np.ndarray:
    if land_cover is None or land_cover.shape != shape:
        return np.full((*shape, 4), (0.72, 0.68, 0.58, 1.0), dtype=float)
    palette = {
        1: (0.08, 0.38, 0.16, 1.0),
        2: (0.42, 0.58, 0.23, 1.0),
        3: (0.72, 0.74, 0.38, 1.0),
        4: (0.80, 0.66, 0.30, 1.0),
        5: (0.26, 0.52, 0.20, 1.0),
        6: (0.70, 0.70, 0.64, 1.0),
        7: (0.86, 0.84, 0.76, 1.0),
        8: (0.17, 0.40, 0.72, 1.0),
        9: (0.31, 0.58, 0.54, 1.0),
        10: (0.92, 0.92, 0.88, 1.0),
        50: (0.70, 0.70, 0.64, 1.0),
        80: (0.17, 0.40, 0.72, 1.0),
        311: (0.08, 0.38, 0.16, 1.0),
    }
    rounded = np.rint(land_cover).astype(int)
    colors = np.empty((*shape, 4), dtype=float)
    fallback = plt.get_cmap("tab20")
    for index in np.ndindex(shape):
        code = int(rounded[index])
        colors[index] = palette.get(code, fallback((abs(code) % 20) / 19.0))
        colors[index + (3,)] = 1.0
    return colors


def _animation_time_indexes(input_path: str | Path, variable_name: str | None) -> list[int]:
    Dataset = _load_netcdf4()
    with Dataset(input_path) as ds:
        actual = _candidate_variable_name(ds, variable_name)
        variable = ds.variables[actual]
        dims = tuple(str(dim).lower() for dim in getattr(variable, "dimensions", ()))
        shape = tuple(int(size) for size in getattr(variable, "shape", ()))
        for axis, dim in enumerate(dims):
            if any(token in dim for token in TIME_DIMENSION_TOKENS):
                return list(range(max(1, shape[axis])))
    return [0]


def _color_limits(fields: Sequence[VolumeField], *, log_scale: bool) -> tuple[float, float] | None:
    samples: list[np.ndarray] = []
    for field in fields:
        values = np.asarray(field.values, dtype=float)
        sample = values[np.isfinite(values) & (values > 0.0)] if log_scale else values[np.isfinite(values)]
        if sample.size:
            samples.append(sample)
    if not samples:
        return None
    combined = np.concatenate(samples)
    low = float(np.nanmin(combined))
    high = float(np.nanmax(combined))
    if not log_scale and low >= 0.0:
        low = 0.0
    if high <= low:
        pad = max(abs(low) * 0.01, 1.0)
        return low - pad, high + pad
    return low, high


def _subsample_axis(axis: np.ndarray, max_points: int) -> np.ndarray:
    if axis.size <= max_points:
        return np.arange(axis.size)
    return np.unique(np.linspace(0, axis.size - 1, max_points, dtype=int))


def _surface_z(values: np.ndarray, z_axis: np.ndarray, threshold: float) -> np.ndarray:
    mask = np.isfinite(values) & (values >= threshold)
    indexes = np.argmax(mask, axis=0)
    has_value = np.any(mask, axis=0)
    surface = z_axis[indexes]
    return np.where(has_value, surface, np.nan)


def _is_concentration_field(field: VolumeField) -> bool:
    text = f"{field.variable_name} {field.long_name}".lower()
    return "concentration" in text or "mass" in text


def _positive_render_values(field: VolumeField, values: np.ndarray) -> np.ndarray:
    if not _is_concentration_field(field):
        return values
    return np.where(np.asarray(values, dtype=float) > 0.0, values, np.nan)


def _threshold(values: np.ndarray, quantile: float) -> float | None:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return None
    return float(np.nanquantile(finite, quantile))


def _format_axis_tick(value: float) -> str:
    return f"{value:.0f}" if math.isfinite(value) and abs(value - round(value)) < 1.0e-6 else f"{value:.1f}"


def _apply_dual_horizontal_ticks(ax: Any, field: VolumeField, terrain: TerrainField) -> None:
    lon_axis = terrain.longitude_axis if terrain.longitude_axis is not None else field.longitude_axis
    lat_axis = terrain.latitude_axis if terrain.latitude_axis is not None else field.latitude_axis
    ax.set_xticks(np.linspace(float(np.nanmin(field.x_axis)), float(np.nanmax(field.x_axis)), min(4, field.x_axis.size)))
    ax.set_yticks(np.linspace(float(np.nanmin(field.y_axis)), float(np.nanmax(field.y_axis)), min(4, field.y_axis.size)))
    if lon_axis is not None and lon_axis.size == field.x_axis.size:
        xticks = ax.get_xticks()
        lon_values = np.interp(xticks, field.x_axis, lon_axis)
        ax.set_xticks(xticks)
        ax.set_xticklabels([f"{_format_axis_tick(x)}\n{lon:.5f} degE" for x, lon in zip(xticks, lon_values)], fontsize=7)
        ax.set_xlabel("x [m] / longitude")
    else:
        ax.set_xlabel("x [m]")
    if lat_axis is not None and lat_axis.size == field.y_axis.size:
        yticks = ax.get_yticks()
        lat_values = np.interp(yticks, field.y_axis, lat_axis)
        ax.set_yticks(yticks)
        ax.set_yticklabels([f"{_format_axis_tick(y)}\n{lat:.5f} degN" for y, lat in zip(yticks, lat_values)], fontsize=7)
        ax.set_ylabel("y [m] / latitude")
    else:
        ax.set_ylabel("y [m]")


def _nanmax_or_nan(values: np.ndarray, axis: int) -> np.ndarray:
    with np.errstate(invalid="ignore"):
        valid = np.isfinite(values)
        filled = np.where(valid, values, -np.inf)
        maximum = np.max(filled, axis=axis)
    return np.where(np.isfinite(maximum), maximum, np.nan)


def plot_volume(
    field: VolumeField,
    output_path: str | Path,
    *,
    terrain: TerrainField | None,
    title: str | None,
    dpi: int,
    cmap: str,
    figure_size: tuple[float, float],
    log_scale: bool,
    mode: str,
    threshold_quantile: float,
    max_points: int,
    elevation: float,
    azimuth: float,
    color_limits: tuple[float, float] | None = None,
) -> Path:
    plt = _load_matplotlib()
    from matplotlib.colors import LogNorm, Normalize

    if log_scale and not np.any(np.isfinite(field.values) & (field.values > 0.0)):
        raise ValueError("--log-scale requires at least one positive value")
    finite = field.values[np.isfinite(field.values)]
    if finite.size == 0:
        raise ValueError("selected variable has no finite values")
    if color_limits is None:
        color_limits = _color_limits((field,), log_scale=log_scale)
    norm = LogNorm(vmin=color_limits[0], vmax=color_limits[1]) if log_scale and color_limits else Normalize(*(color_limits or (None, None)))
    x_idx = _subsample_axis(field.x_axis, max_points)
    y_idx = _subsample_axis(field.y_axis, max_points)
    z_idx = np.arange(field.z_axis.size)
    terrain_field = _terrain_like_volume(terrain, field)
    terrain_sample = terrain_field.elevation_m[np.ix_(y_idx, x_idx)]

    fig = plt.figure(figsize=figure_size, dpi=dpi)
    ax = fig.add_subplot(1, 1, 1, projection="3d")
    plot_cmap = plt.get_cmap(cmap)
    xx, yy = np.meshgrid(field.x_axis[x_idx], field.y_axis[y_idx])
    terrain_colors = _land_cover_facecolors(
        None if terrain_field.land_cover is None else terrain_field.land_cover[np.ix_(y_idx, x_idx)],
        terrain_sample.shape,
        plt,
    )
    ax.plot_surface(
        xx,
        yy,
        terrain_sample,
        facecolors=terrain_colors,
        linewidth=0.0,
        antialiased=True,
        shade=True,
        alpha=0.96,
        zorder=1,
    )
    if mode == "voxel":
        sampled = _positive_render_values(field, field.values[np.ix_(z_idx, y_idx, x_idx)])
        threshold = _threshold(sampled, threshold_quantile)
        occupied = np.isfinite(sampled) & (sampled >= threshold) if threshold is not None else np.zeros(sampled.shape, dtype=bool)
        if np.any(occupied):
            zz, yy3, xx3 = np.meshgrid(field.z_axis[z_idx], field.y_axis[y_idx], field.x_axis[x_idx], indexing="ij")
            terrain3 = np.broadcast_to(terrain_sample, sampled.shape)
            colors = plot_cmap(norm(sampled[occupied]))
            colors[:, 3] = 0.62
            ax.scatter(
                xx3[occupied],
                yy3[occupied],
                terrain3[occupied] + zz[occupied],
                c=colors,
                s=18.0,
                marker="s",
                linewidths=0.0,
                depthshade=False,
                zorder=3,
            )
        ax.set_box_aspect((np.ptp(field.x_axis[x_idx]) or 1.0, np.ptp(field.y_axis[y_idx]) or 1.0, (np.ptp(terrain_sample) + np.ptp(field.z_axis[z_idx])) or 1.0))
    else:
        sampled = _positive_render_values(field, field.values[:, :, x_idx][:, y_idx, :])
        threshold = _threshold(sampled, threshold_quantile)
        surface = terrain_sample + _surface_z(sampled, field.z_axis, threshold) if threshold is not None else np.full_like(terrain_sample, np.nan)
        colors = plot_cmap(norm(_nanmax_or_nan(sampled, axis=0)))
        colors[..., 3] = np.where(np.isfinite(surface), 0.68, 0.0)
        ax.plot_surface(xx, yy, surface, facecolors=colors, linewidth=0.0, antialiased=True, shade=False)
        ax.set_box_aspect((np.ptp(field.x_axis[x_idx]) or 1.0, np.ptp(field.y_axis[y_idx]) or 1.0, (np.ptp(terrain_sample) + np.ptp(field.z_axis)) or 1.0))
    mappable = plt.cm.ScalarMappable(norm=norm, cmap=plot_cmap)
    mappable.set_array([])
    fig.colorbar(mappable, ax=ax, shrink=0.72, pad=0.08, label=field.label)
    _apply_dual_horizontal_ticks(ax, field, terrain_field)
    ax.set_zlabel("elevation / plume height [m]")
    ax.view_init(elev=elevation, azim=azimuth)
    ax.set_title(title or field.title, fontsize=11)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return out


def _write_gif(frame_paths: Sequence[Path], output_path: str | Path, *, duration_ms: int, loop: int) -> Path:
    if not frame_paths:
        raise ValueError("animation requires at least one frame")
    try:
        from PIL import Image
    except Exception as exc:  # pragma: no cover - depends on optional extra
        raise RuntimeError("Pillow is required to write animated GIFs; install matplotlib with Pillow support") from exc
    frames = [Image.open(path).convert("P", palette=Image.ADAPTIVE) for path in frame_paths]
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(out, save_all=True, append_images=frames[1:], duration=max(1, int(duration_ms)), loop=max(0, int(loop)), optimize=False)
    for frame in frames:
        frame.close()
    return out


def plot_animation(input_path: str | Path, output_path: str | Path, **kwargs: Any) -> Path:
    variable_name = kwargs.pop("variable_name")
    terrain_path = kwargs.pop("terrain_path", None)
    duration_ms = kwargs.pop("duration_ms")
    loop = kwargs.pop("loop")
    time_indexes = _animation_time_indexes(input_path, variable_name)
    fields = [read_volume_field(input_path, variable_name=variable_name, time_index=index) for index in time_indexes]
    color_limits = _color_limits(fields, log_scale=kwargs["log_scale"])
    terrain = read_terrain_field(terrain_path or input_path, time_index=0) if terrain_path or Path(input_path).exists() else None
    with tempfile.TemporaryDirectory(prefix="sprtz_render3d_frames_") as tmp:
        frame_paths: list[Path] = []
        for index, field in zip(time_indexes, fields):
            frame_path = Path(tmp) / f"render3d_{index:05d}.png"
            plot_volume(field, frame_path, terrain=terrain, color_limits=color_limits, **kwargs)
            frame_paths.append(frame_path)
            LOGGER.info("animation frame %d/%d time_index=%d", len(frame_paths), len(time_indexes), index)
        return _write_gif(frame_paths, output_path, duration_ms=duration_ms, loop=loop)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render academic-quality 3-D views from Sprtz NetCDF-CF products.")
    parser.add_argument("input", help="input NetCDF file produced by a Sprtz module")
    parser.add_argument("-o", "--output", required=True, help="output figure path, e.g. render3d.png or render3d.gif")
    parser.add_argument("-v", "--variable", default=None, help="NetCDF variable to render; auto-detected by default")
    parser.add_argument("--time-index", type=int, default=0, help="time index for multidimensional variables")
    parser.add_argument("--level-index", type=int, default=0, help="accepted for CLI parity; 3-D rendering uses all vertical levels")
    parser.add_argument("--terrain", default=None, help="optional terrain/GEO NetCDF with surface_altitude and land_cover variables")
    parser.add_argument("--title", default=None, help="figure title")
    parser.add_argument("--dpi", type=int, default=600, help="output raster DPI")
    parser.add_argument("--cmap", default="viridis", help="matplotlib colormap")
    parser.add_argument("--log-scale", action="store_true", help="use logarithmic color normalization")
    parser.add_argument("--mode", choices=("surface", "voxel"), default="surface", help="3-D rendering style")
    parser.add_argument("--threshold-quantile", type=float, default=0.85, help="quantile threshold used for 3-D extraction")
    parser.add_argument("--max-points", type=int, default=56, help="maximum sampled points per axis for responsive rendering")
    parser.add_argument("--elevation", type=float, default=28.0, help="3-D camera elevation in degrees")
    parser.add_argument("--azimuth", type=float, default=-55.0, help="3-D camera azimuth in degrees")
    parser.add_argument("--animate", action="store_true", help="write an animated GIF using every time frame of the selected variable")
    parser.add_argument("--frame-duration-ms", type=int, default=300, help="animated GIF frame duration in milliseconds")
    parser.add_argument("--gif-loop", type=int, default=0, help="animated GIF loop count; 0 loops forever")
    parser.add_argument("--width", type=float, default=7.2, help="figure width in inches")
    parser.add_argument("--height", type=float, default=5.6, help="figure height in inches")
    parser.add_argument("--verbose", action="store_true", help="enable debug logging")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format=LOG_FORMAT_VERBOSE,
        datefmt=LOG_DATE_FORMAT,
    )
    try:
        common = {
            "title": args.title,
            "dpi": args.dpi,
            "cmap": args.cmap,
            "figure_size": (args.width, args.height),
            "log_scale": args.log_scale,
            "mode": args.mode,
            "threshold_quantile": min(1.0, max(0.0, args.threshold_quantile)),
            "max_points": max(2, args.max_points),
            "elevation": args.elevation,
            "azimuth": args.azimuth,
            "duration_ms": args.frame_duration_ms,
            "loop": args.gif_loop,
        }
        if args.animate:
            out = plot_animation(args.input, args.output, variable_name=args.variable, terrain_path=args.terrain, **common)
        else:
            field = read_volume_field(args.input, variable_name=args.variable, time_index=args.time_index)
            terrain = read_terrain_field(args.terrain or args.input, time_index=args.time_index)
            common.pop("duration_ms")
            common.pop("loop")
            out = plot_volume(field, args.output, terrain=terrain, **common)
    except KeyboardInterrupt:
        LOGGER.warning("interrupted; stopping 3-D render generation")
        return 130
    except Exception as exc:
        LOGGER.error("%s", exc)
        return 1
    LOGGER.info("wrote %s", out)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

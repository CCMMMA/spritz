#!/usr/bin/env python3
"""Render time-varying vertical profiles from Sprtz NetCDF products."""

from __future__ import annotations

import argparse
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from sprtz.logging import LOG_DATE_FORMAT, LOG_FORMAT_VERBOSE

LOGGER = logging.getLogger("sprtz.profiler")

TIME_DIMENSION_TOKENS = ("time", "date")
X_NAMES = ("x", "field_x", "west_east")
Y_NAMES = ("y", "field_y", "south_north")
Z_NAMES = ("z", "field_z", "level", "height", "bottom_top", "lev")
TIME_NAMES = ("time",)
DATETIME_NAMES = ("time_datetime", "Times")
PROFILE_VARIABLE_CANDIDATES = (
    "concentration_field",
    "wind_speed",
    "wind_speed_10m",
    "eastward_wind",
    "northward_wind",
)


@dataclass(frozen=True)
class ProfileData:
    source_name: str
    variable_name: str
    values: np.ndarray
    x_axis: np.ndarray
    y_axis: np.ndarray
    z_axis: np.ndarray
    time_axis: np.ndarray
    time_labels: list[str]
    units: str
    long_name: str
    ix: int
    iy: int

    @property
    def profiles(self) -> np.ndarray:
        return self.values[:, :, self.iy, self.ix]


def _load_netcdf4() -> Any:
    try:
        from netCDF4 import Dataset
    except Exception as exc:  # pragma: no cover - depends on optional extra
        raise RuntimeError("netCDF4 is required to read NetCDF files; install sprtz[netcdf]") from exc
    return Dataset


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
        actual = lowered.get(name.lower())
        if actual is not None:
            return ds.variables[actual]
    return None


def _variable_array(variable: Any) -> np.ndarray:
    values = np.asarray(variable[:])
    if np.ma.isMaskedArray(values):
        values = np.asarray(values.filled(np.nan))
    return np.asarray(values, dtype=float)


def _candidate_variable_name(ds: Any, requested: str | None) -> str:
    if requested:
        lowered = {name.lower(): name for name in ds.variables}
        actual = lowered.get(requested.lower())
        if actual is None:
            raise ValueError(f"variable {requested!r} not found")
        return actual
    for name in PROFILE_VARIABLE_CANDIDATES:
        variable = _find_variable(ds, (name,))
        if variable is not None and len(getattr(variable, "shape", ())) >= 3:
            return str(variable.name)
    for name, variable in ds.variables.items():
        if len(getattr(variable, "shape", ())) >= 3:
            return str(name)
    raise ValueError("no time-varying gridded variable found")


def _time_labels(ds: Any, count: int, time_axis: np.ndarray) -> list[str]:
    for name in DATETIME_NAMES:
        variable = _find_variable(ds, (name,))
        if variable is None:
            continue
        labels = [_decode_text(value).replace("+00:00", "Z") for value in np.asarray(variable[:])]
        if labels:
            return labels[:count]
    return [f"{float(value):g} s" for value in time_axis[:count]]


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


def _as_time_z_y_x(ds: Any, variable_name: str) -> tuple[np.ndarray, tuple[str | None, str | None, str | None, str | None], str, str]:
    variable = ds.variables[variable_name]
    values = _variable_array(variable)
    variable_dimensions = tuple(str(dim) for dim in getattr(variable, "dimensions", ()))
    if values.ndim == 4:
        dims = [dim.lower() for dim in variable_dimensions]
        if dims:
            order: list[int] = []
            for tokens in (TIME_DIMENSION_TOKENS, Z_NAMES, Y_NAMES, X_NAMES):
                match = next((axis for axis, dim in enumerate(dims) if any(token in dim for token in tokens)), None)
                if match is not None and match not in order:
                    order.append(match)
            if len(order) == 4:
                values = np.transpose(values, order)
                variable_dimensions = tuple(variable_dimensions[index] for index in order)
        return values, variable_dimensions, str(getattr(variable, "units", "")), str(getattr(variable, "long_name", variable_name))
    if values.ndim == 3:
        dims = [dim.lower() for dim in variable_dimensions]
        ordered_dimensions: tuple[str | None, str | None, str | None, str | None] = (
            variable_dimensions[0] if len(variable_dimensions) > 0 else None,
            None,
            variable_dimensions[1] if len(variable_dimensions) > 1 else None,
            variable_dimensions[2] if len(variable_dimensions) > 2 else None,
        )
        if len(dims) == 3:
            time_axis = next((axis for axis, dim in enumerate(dims) if any(token in dim for token in TIME_DIMENSION_TOKENS)), 0)
            y_axis = next((axis for axis, dim in enumerate(dims) if any(token in dim for token in Y_NAMES)), None)
            x_axis = next((axis for axis, dim in enumerate(dims) if any(token in dim for token in X_NAMES)), None)
            order = [axis for axis in (time_axis, y_axis, x_axis) if axis is not None]
            if len(order) == 3 and len(set(order)) == 3:
                values = np.transpose(values, order)
                ordered_dimensions = (
                    variable_dimensions[order[0]],
                    None,
                    variable_dimensions[order[1]],
                    variable_dimensions[order[2]],
                )
        return values[:, np.newaxis, :, :], ordered_dimensions, str(getattr(variable, "units", "")), str(getattr(variable, "long_name", variable_name))
    raise ValueError(f"variable {variable_name!r} must be shaped as time,z,y,x or time,y,x")


def read_profile_data(
    input_path: str | Path,
    *,
    variable_name: str | None,
    x_m: float,
    y_m: float,
) -> ProfileData:
    Dataset = _load_netcdf4()
    with Dataset(input_path) as ds:
        actual = _candidate_variable_name(ds, variable_name)
        values, dimensions, units, long_name = _as_time_z_y_x(ds, actual)
        time_count, z_count, y_count, x_count = values.shape
        x_axis = _axis_values(ds, X_NAMES, x_count, dimensions[3])
        y_axis = _axis_values(ds, Y_NAMES, y_count, dimensions[2])
        z_axis = _axis_values(ds, Z_NAMES, z_count, dimensions[1])
        time_axis = _axis_values(ds, TIME_NAMES, time_count, dimensions[0])
        labels = _time_labels(ds, time_count, time_axis)
    ix = int(np.argmin(np.abs(x_axis - float(x_m))))
    iy = int(np.argmin(np.abs(y_axis - float(y_m))))
    selected = values[:, :, iy, ix]
    global_max = float(np.nanmax(values)) if np.isfinite(values).any() else 0.0
    if (not np.isfinite(selected).any() or float(np.nanmax(selected)) <= 0.0) and global_max > 0.0:
        column_max = np.nanmax(values, axis=(0, 1))
        iy, ix = (int(index) for index in np.unravel_index(int(np.nanargmax(column_max)), column_max.shape))
    return ProfileData(
        source_name=Path(input_path).name,
        variable_name=actual,
        values=values,
        x_axis=x_axis,
        y_axis=y_axis,
        z_axis=z_axis,
        time_axis=time_axis,
        time_labels=labels,
        units=units,
        long_name=long_name,
        ix=ix,
        iy=iy,
    )


def _load_matplotlib() -> Any:
    try:
        import matplotlib

        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt
    except Exception as exc:  # pragma: no cover - depends on optional extra
        raise RuntimeError("matplotlib is required for profile plotting; install sprtz[viz]") from exc
    return plt


def _profile_color_limits(profiles: np.ndarray) -> dict[str, float]:
    finite = profiles[np.isfinite(profiles)]
    maximum = float(np.nanmax(finite)) if finite.size else 0.0
    return {"vmin": 0.0, "vmax": maximum if maximum > 0.0 else 1.0}


def plot_profile(
    profile: ProfileData,
    output_path: str | Path,
    *,
    title: str | None,
    dpi: int,
    time_index: int | None = None,
) -> Path:
    plt = _load_matplotlib()
    profiles = profile.profiles
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig, (ax_heat, ax_profiles) = plt.subplots(1, 2, figsize=(10.5, 5.2), dpi=dpi, constrained_layout=True)
    mesh = ax_heat.pcolormesh(
        np.arange(profiles.shape[0]),
        profile.z_axis,
        profiles.T,
        shading="auto",
        cmap="viridis",
        **_profile_color_limits(profiles),
    )
    cbar = fig.colorbar(mesh, ax=ax_heat)
    label = f"{profile.long_name}{f' [{profile.units}]' if profile.units else ''}"
    cbar.set_label(label)
    ax_heat.set_title("Time-height section")
    ax_heat.set_xlabel("time index")
    ax_heat.set_ylabel("vertical level [m]")
    if time_index is not None:
        ax_heat.axvline(time_index, color="white", linewidth=1.6)
        indexes = [time_index]
    else:
        sample_count = min(6, profiles.shape[0])
        indexes = list(np.linspace(0, profiles.shape[0] - 1, sample_count, dtype=int))
    cmap = plt.get_cmap("viridis")
    for order, index in enumerate(indexes):
        color = cmap(0.0 if len(indexes) == 1 else order / (len(indexes) - 1))
        label_text = profile.time_labels[index] if index < len(profile.time_labels) else f"t={index}"
        ax_profiles.plot(profiles[index, :], profile.z_axis, color=color, linewidth=1.7, label=label_text)
    ax_profiles.set_title(f"Vertical profile at x={profile.x_axis[profile.ix]:.0f} m, y={profile.y_axis[profile.iy]:.0f} m")
    ax_profiles.set_xlabel(label)
    ax_profiles.set_ylabel("vertical level [m]")
    finite = profiles[np.isfinite(profiles)]
    maximum = float(np.nanmax(finite)) if finite.size else 0.0
    if maximum > 0.0:
        ax_profiles.set_xlim(left=0.0, right=maximum * 1.05)
    ax_profiles.grid(True, alpha=0.25)
    ax_profiles.legend(fontsize=6, loc="best")
    fig.suptitle(title or f"{profile.source_name}: time-varying vertical {profile.long_name}")
    fig.savefig(out)
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
    frames[0].save(
        out,
        save_all=True,
        append_images=frames[1:],
        duration=max(1, int(duration_ms)),
        loop=max(0, int(loop)),
        optimize=False,
    )
    for frame in frames:
        frame.close()
    return out


def plot_profile_animation(
    profile: ProfileData,
    output_path: str | Path,
    *,
    title: str | None,
    dpi: int,
    duration_ms: int,
    loop: int,
) -> Path:
    with tempfile.TemporaryDirectory(prefix="sprtz_profiler_frames_") as tmp:
        frame_paths: list[Path] = []
        for time_index in range(profile.values.shape[0]):
            frame_path = Path(tmp) / f"profile_{time_index:05d}.png"
            plot_profile(profile, frame_path, title=title, dpi=dpi, time_index=time_index)
            frame_paths.append(frame_path)
            LOGGER.info("animation frame %d/%d time_index=%d", len(frame_paths), profile.values.shape[0], time_index)
        return _write_gif(frame_paths, output_path, duration_ms=duration_ms, loop=loop)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render time-varying vertical profiles from Sprtz NetCDF-CF products.")
    parser.add_argument("input", help="input NetCDF file produced by a Sprtz module")
    parser.add_argument("-o", "--output", required=True, help="output figure path, e.g. profile.png or profile.gif")
    parser.add_argument("-v", "--variable", default=None, help="NetCDF variable to profile; auto-detected by default")
    parser.add_argument("--x", "--x-m", dest="x_m", type=float, default=0.0, help="local x coordinate for the sampled column")
    parser.add_argument("--y", "--y-m", dest="y_m", type=float, default=0.0, help="local y coordinate for the sampled column")
    parser.add_argument("--time-index", type=int, default=None, help="single time index to highlight in a static profile")
    parser.add_argument("--title", default=None, help="figure title")
    parser.add_argument("--dpi", type=int, default=300, help="output raster DPI")
    parser.add_argument("--animate", action="store_true", help="write an animated GIF with every simulation time frame")
    parser.add_argument("--frame-duration-ms", type=int, default=300, help="animated GIF frame duration in milliseconds")
    parser.add_argument("--gif-loop", type=int, default=0, help="animated GIF loop count; 0 loops forever")
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
        profile = read_profile_data(args.input, variable_name=args.variable, x_m=args.x_m, y_m=args.y_m)
        if args.animate:
            out = plot_profile_animation(
                profile,
                args.output,
                title=args.title,
                dpi=args.dpi,
                duration_ms=args.frame_duration_ms,
                loop=args.gif_loop,
            )
        else:
            if args.time_index is not None and (args.time_index < 0 or args.time_index >= profile.values.shape[0]):
                raise IndexError(f"time index {args.time_index} is out of range for size {profile.values.shape[0]}")
            out = plot_profile(profile, args.output, title=args.title, dpi=args.dpi, time_index=args.time_index)
    except KeyboardInterrupt:
        LOGGER.warning("interrupted; stopping profile generation")
        return 130
    except Exception as exc:
        LOGGER.error("%s", exc)
        return 1
    LOGGER.info("wrote %s", out)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

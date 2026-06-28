#!/usr/bin/env python3
"""Plot publication-ready maps from Sprtz NetCDF products.

The tool is intentionally optional-dependency friendly: it requires netCDF4 and
matplotlib for plotting, uses Cartopy for coastlines when installed, and never
opts into network-backed Cartopy data acquisition unless requested explicitly.
"""

from __future__ import annotations

import argparse
import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np

LOGGER = logging.getLogger("sprtz.plotter")

LATITUDE_NAMES = ("latitude", "lat", "XLAT", "XLAT_M")
LONGITUDE_NAMES = ("longitude", "lon", "long", "lng", "XLONG", "XLONG_M")
X_NAMES = ("x", "field_x", "west_east")
Y_NAMES = ("y", "field_y", "south_north")
U_WIND_NAMES = ("eastward_wind", "u", "U", "U10")
V_WIND_NAMES = ("northward_wind", "v", "V", "V10")
WIND_SPEED_NAMES = ("wind_speed", "WSPD10", "wspd10", "speed")
WIND_FROM_DIRECTION_NAMES = ("wind_from_direction", "WDIR10", "wdir10", "wind_dir", "wind_direction")
SKIP_VARIABLES = {
    "time",
    "time_datetime",
    "receptor",
    "receptor_id",
    "output_kind",
    "x",
    "y",
    "z",
    "field_x",
    "field_y",
    "field_z",
    "latitude",
    "longitude",
    "lat",
    "lon",
}

TIME_DIMENSION_TOKENS = ("time", "date")
LEVEL_DIMENSION_TOKENS = ("z", "level", "height", "altitude", "bottom_top", "lev")
@dataclass(frozen=True)
class VectorField:
    u: np.ndarray
    v: np.ndarray
    label: str = "Wind vector"


@dataclass(frozen=True)
class MapField:
    name: str
    values: np.ndarray
    x: np.ndarray
    y: np.ndarray
    geographic: bool
    label: str
    title: str
    vectors: VectorField | None = None
    time_label: str | None = None


def _decode_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").strip()
    if isinstance(value, np.ndarray):
        if value.dtype.kind in {"S", "U"}:
            return b"".join(np.asarray(value, dtype="S1").ravel()).decode("utf-8", errors="replace").strip()
        if value.size == 1:
            return _decode_text(value.item())
    return str(value).strip()


def _load_netcdf4() -> Any:
    try:
        from netCDF4 import Dataset
    except Exception as exc:  # pragma: no cover - depends on optional extra
        raise RuntimeError("netCDF4 is required to read NetCDF files; install sprtz[netcdf]") from exc
    return Dataset


def _variable_array(variable: Any) -> np.ndarray:
    values = np.asarray(variable[:])
    if np.ma.isMaskedArray(values):
        values = np.asarray(values.filled(np.nan))
    return np.asarray(values)


def _take_checked(arr: np.ndarray, index: int, axis: int, *, name: str) -> np.ndarray:
    if index < 0 or index >= arr.shape[axis]:
        raise IndexError(f"{name} index {index} is out of range for size {arr.shape[axis]}")
    return np.take(arr, index, axis=axis)


def _find_variable(ds: Any, names: Sequence[str]) -> Any | None:
    lowered = {name.lower(): name for name in ds.variables}
    for name in names:
        actual = lowered.get(name.lower())
        if actual is not None:
            return ds.variables[actual]
    return None


def _select_2d(
    values: np.ndarray,
    *,
    dimensions: Sequence[str] = (),
    time_index: int,
    level_index: int,
) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    dims = [dim.lower() for dim in dimensions]
    while arr.ndim > 2:
        if dims:
            if any(token in dims[0] for token in TIME_DIMENSION_TOKENS):
                index = time_index
                name = "time"
            elif any(token in dims[0] for token in LEVEL_DIMENSION_TOKENS):
                index = level_index
                name = "level"
            else:
                index = 0
                name = dims[0]
            dims.pop(0)
        else:
            index = time_index if arr.ndim > 3 else level_index
            name = "time" if arr.ndim > 3 else "level"
        arr = _take_checked(arr, index, 0, name=name)
    if arr.ndim == 2 and dims:
        lowered = [dim.lower() for dim in dims]
        for axis, dim in enumerate(lowered[:2]):
            if any(token in dim for token in TIME_DIMENSION_TOKENS):
                arr = _take_checked(arr, time_index, axis, name="time")
                break
            if any(token in dim for token in LEVEL_DIMENSION_TOKENS):
                arr = _take_checked(arr, level_index, axis, name="level")
                break
    if arr.ndim != 2:
        if arr.ndim == 1:
            return arr.reshape(1, arr.size)
        raise ValueError("selected variable is not one- or two-dimensional")
    return arr


def _select_1d_or_2d(values: np.ndarray, *, time_index: int = 0) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    while arr.ndim > 2:
        arr = _take_checked(arr, time_index, 0, name="time")
    if arr.ndim == 2 and 1 in arr.shape:
        arr = arr.reshape(max(arr.shape))
    return arr


def _select_like_variable(variable: Any, *, time_index: int, level_index: int) -> np.ndarray:
    return _select_2d(
        _variable_array(variable),
        dimensions=getattr(variable, "dimensions", ()),
        time_index=time_index,
        level_index=level_index,
    )


def _candidate_variables(ds: Any) -> list[str]:
    candidates: list[str] = []
    for name, variable in ds.variables.items():
        if name in SKIP_VARIABLES:
            continue
        if getattr(variable, "dtype", None) is not None and variable.dtype.kind not in "fiu":
            continue
        if len(getattr(variable, "dimensions", ())) < 1:
            continue
        candidates.append(name)
    return candidates


def _resolve_value_variable(ds: Any, requested: str | None) -> Any:
    if requested:
        if requested not in ds.variables:
            raise ValueError(f"variable {requested!r} is not present in the NetCDF file")
        return ds.variables[requested]
    for name in _candidate_variables(ds):
        values = np.asarray(ds.variables[name][:])
        if values.ndim >= 2 or values.size > 1:
            return ds.variables[name]
    raise ValueError("no numeric plottable variable found; pass --variable explicitly")


def _coordinate_mesh(
    ds: Any,
    shape: tuple[int, int],
    *,
    time_index: int,
    center_lat: float | None,
    center_lon: float | None,
) -> tuple[np.ndarray, np.ndarray, bool]:
    lat_var = _find_variable(ds, LATITUDE_NAMES)
    lon_var = _find_variable(ds, LONGITUDE_NAMES)
    if lat_var is not None and lon_var is not None:
        lat = _select_1d_or_2d(_variable_array(lat_var), time_index=time_index)
        lon = _select_1d_or_2d(_variable_array(lon_var), time_index=time_index)
        if lat.ndim == lon.ndim == 1:
            if lat.size == shape[0] and lon.size == shape[1]:
                lon_grid, lat_grid = np.meshgrid(lon, lat)
                return lon_grid, lat_grid, True
            if lat.size == lon.size == shape[0] * shape[1]:
                return lon.reshape(shape), lat.reshape(shape), True
        if lat.shape == shape and lon.shape == shape:
            return lon, lat, True

    x_var = _find_variable(ds, X_NAMES)
    y_var = _find_variable(ds, Y_NAMES)
    if x_var is not None and y_var is not None:
        x = _select_1d_or_2d(_variable_array(x_var), time_index=time_index)
        y = _select_1d_or_2d(_variable_array(y_var), time_index=time_index)
        if x.ndim == y.ndim == 1:
            if x.size == y.size == shape[0] * shape[1]:
                x_grid, y_grid = x.reshape(shape), y.reshape(shape)
            else:
                x_grid, y_grid = np.meshgrid(x, y)
        elif x.shape == y.shape == shape:
            x_grid, y_grid = x, y
        else:
            x_grid, y_grid = np.meshgrid(np.arange(shape[1]), np.arange(shape[0]))
        if center_lat is not None and center_lon is not None:
            return _local_to_lat_lon(x_grid, y_grid, center_lat=center_lat, center_lon=center_lon)
        return x_grid, y_grid, False

    x_grid, y_grid = np.meshgrid(np.arange(shape[1], dtype=float), np.arange(shape[0], dtype=float))
    return x_grid, y_grid, False


def _wind_from_speed_direction(speed: np.ndarray, direction_from_deg: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    theta = np.deg2rad(270.0 - direction_from_deg)
    return speed * np.cos(theta), speed * np.sin(theta)


def _read_vectors(ds: Any, shape: tuple[int, int], *, time_index: int, level_index: int) -> VectorField | None:
    u_var = _find_variable(ds, U_WIND_NAMES)
    v_var = _find_variable(ds, V_WIND_NAMES)
    if u_var is not None and v_var is not None:
        u = _select_like_variable(u_var, time_index=time_index, level_index=level_index)
        v = _select_like_variable(v_var, time_index=time_index, level_index=level_index)
        if u.shape == v.shape == shape:
            return VectorField(u, v, "Wind vector [m s-1]")

    speed_var = _find_variable(ds, WIND_SPEED_NAMES)
    direction_var = _find_variable(ds, WIND_FROM_DIRECTION_NAMES)
    if speed_var is not None and direction_var is not None:
        speed = _select_like_variable(speed_var, time_index=time_index, level_index=level_index)
        direction = _select_like_variable(direction_var, time_index=time_index, level_index=level_index)
        if speed.shape == direction.shape == shape:
            u, v = _wind_from_speed_direction(speed, direction)
            return VectorField(u, v, "Wind vector from speed/direction [m s-1]")
    return None


def _read_time_label(ds: Any, *, time_index: int) -> str | None:
    time_datetime = _find_variable(ds, ("time_datetime",))
    if time_datetime is not None:
        values = np.asarray(time_datetime[:])
        if values.size:
            text = _decode_text(values[min(time_index, values.shape[0] - 1)])
            if text:
                return f"UTC: {text.replace('+00:00', 'Z')}"

    wrf_times = _find_variable(ds, ("Times",))
    if wrf_times is not None:
        values = np.asarray(wrf_times[:])
        if values.size:
            text = _decode_text(values[min(time_index, values.shape[0] - 1)])
            if text:
                return f"UTC: {text.replace('_', ' ')}"

    time_var = _find_variable(ds, ("time",))
    if time_var is None:
        return None
    values = np.asarray(time_var[:])
    if values.size == 0:
        return None
    if time_index < 0 or time_index >= values.shape[0]:
        raise IndexError(f"time index {time_index} is out of range for size {values.shape[0]}")
    units = str(getattr(time_var, "units", "")).strip()
    calendar = str(getattr(time_var, "calendar", "standard")).strip()
    value = float(values[time_index])
    if "since" in units.lower():
        try:
            from netCDF4 import num2date  # type: ignore

            dt = num2date(value, units=units, calendar=calendar, only_use_cftime_datetimes=False)
            text = dt.isoformat()
            if text.endswith("+00:00"):
                text = text[:-6] + "Z"
            elif getattr(dt, "tzinfo", None) is None:
                text = f"{text}Z"
            return f"UTC: {text}"
        except Exception:
            pass
    return f"Time: {value:g} {units}".strip()


def _local_to_lat_lon(
    x: np.ndarray,
    y: np.ndarray,
    *,
    center_lat: float,
    center_lon: float,
) -> tuple[np.ndarray, np.ndarray, bool]:
    try:
        from pyproj import CRS, Transformer
    except Exception as exc:  # pragma: no cover - pyproj is a core dependency
        raise RuntimeError("pyproj is required to transform local coordinates") from exc
    local = CRS.from_proj4(
        f"+proj=aeqd +lat_0={center_lat:.12f} +lon_0={center_lon:.12f} "
        "+datum=WGS84 +units=m +no_defs"
    )
    transformer = Transformer.from_crs(local, CRS.from_epsg(4326), always_xy=True)
    lon, lat = transformer.transform(x, y)
    return np.asarray(lon, dtype=float), np.asarray(lat, dtype=float), True


def read_map_field(
    input_path: str | Path,
    *,
    variable_name: str | None,
    time_index: int,
    level_index: int,
    center_lat: float | None,
    center_lon: float | None,
) -> MapField:
    Dataset = _load_netcdf4()
    with Dataset(input_path) as ds:
        variable = _resolve_value_variable(ds, variable_name)
        values_raw = _variable_array(variable)
        values = _select_2d(
            values_raw,
            dimensions=getattr(variable, "dimensions", ()),
            time_index=time_index,
            level_index=level_index,
        )
        x, y, geographic = _coordinate_mesh(
            ds,
            values.shape,
            time_index=time_index,
            center_lat=center_lat,
            center_lon=center_lon,
        )
        units = getattr(variable, "units", "")
        long_name = getattr(variable, "long_name", "") or getattr(variable, "standard_name", "")
        label = f"{long_name or variable.name}{f' [{units}]' if units else ''}"
        title = f"{Path(input_path).name}: {long_name or variable.name}"
        vectors = _read_vectors(ds, values.shape, time_index=time_index, level_index=level_index)
        time_label = _read_time_label(ds, time_index=time_index)
        return MapField(variable.name, values, x, y, geographic, label, title, vectors=vectors, time_label=time_label)


def _extent(x: np.ndarray, y: np.ndarray, margin_fraction: float) -> tuple[float, float, float, float]:
    west = float(np.nanmin(x))
    east = float(np.nanmax(x))
    south = float(np.nanmin(y))
    north = float(np.nanmax(y))
    dx = max(east - west, 1.0e-9)
    dy = max(north - south, 1.0e-9)
    return (
        west - dx * margin_fraction,
        east + dx * margin_fraction,
        south - dy * margin_fraction,
        north + dy * margin_fraction,
    )


def _add_cartopy_coastlines(
    ax: Any,
    *,
    extent: tuple[float, float, float, float],
    resolution: str,
    allow_download: bool,
) -> None:
    try:
        import cartopy
        import cartopy.crs as ccrs
        import cartopy.feature as cfeature
        import cartopy.io.shapereader as shpreader
    except Exception:
        LOGGER.warning("cartopy is not installed; skipping high-resolution coastlines")
        return
    if not allow_download:
        cartopy.config["downloaders"] = {}
    west, east, south, north = extent
    ax.set_extent((west, east, south, north), crs=ccrs.PlateCarree())

    def add_natural_earth(
        category: str,
        name: str,
        *,
        zorder: int,
        edgecolor: str,
        facecolor: str,
        linewidth: float,
    ) -> None:
        try:
            shpreader.natural_earth(resolution=resolution, category=category, name=name)
        except Exception as exc:
            LOGGER.warning(
                "Cartopy Natural Earth %s/%s at %s is unavailable (%s); "
                "install local Natural Earth data or pass --allow-cartopy-download",
                category,
                name,
                resolution,
                exc,
            )
            return
        feature = cfeature.NaturalEarthFeature(
            category,
            name,
            resolution,
            edgecolor=edgecolor,
            facecolor=facecolor,
            linewidth=linewidth,
        )
        ax.add_feature(feature, zorder=zorder)

    add_natural_earth("physical", "ocean", zorder=0, edgecolor="none", facecolor="0.985", linewidth=0.0)
    add_natural_earth("physical", "land", zorder=0, edgecolor="none", facecolor="0.94", linewidth=0.0)
    add_natural_earth("physical", "coastline", zorder=5, edgecolor="0.08", facecolor="none", linewidth=0.65)
    add_natural_earth(
        "cultural",
        "admin_0_boundary_lines_land",
        zorder=5,
        edgecolor="0.25",
        facecolor="none",
        linewidth=0.3,
    )


def plot_map(
    field: MapField,
    output_path: str | Path,
    *,
    title: str | None,
    dpi: int,
    cmap: str,
    coastline_resolution: str,
    allow_cartopy_download: bool,
    figure_size: tuple[float, float],
    log_scale: bool,
    vector_overlay: bool,
    vector_stride: int,
    vector_density: int | None,
    vector_scale: float | None,
) -> Path:
    try:
        import matplotlib

        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt
        from matplotlib.colors import LogNorm
    except Exception as exc:  # pragma: no cover - depends on optional extra
        raise RuntimeError("matplotlib is required for plotting; install sprtz[viz]") from exc

    projection = None
    transform = None
    if field.geographic:
        try:
            import cartopy.crs as ccrs

            projection = ccrs.PlateCarree()
            transform = ccrs.PlateCarree()
        except Exception:
            projection = None
            transform = None

    fig = plt.figure(figsize=figure_size, constrained_layout=True)
    ax = fig.add_subplot(1, 1, 1, projection=projection)
    norm = None
    if log_scale:
        positive = field.values[np.isfinite(field.values) & (field.values > 0)]
        if positive.size == 0:
            raise ValueError("--log-scale requires at least one positive value")
        norm = LogNorm(vmin=float(np.nanmin(positive)), vmax=float(np.nanmax(positive)))

    if min(field.values.shape) == 1:
        scatter_kwargs: dict[str, Any] = {
            "c": field.values.ravel(),
            "cmap": cmap,
            "norm": norm,
            "s": 34.0,
            "edgecolors": "black",
            "linewidths": 0.25,
        }
        if transform is not None:
            scatter_kwargs["transform"] = transform
        artist = ax.scatter(field.x.ravel(), field.y.ravel(), **scatter_kwargs)
    else:
        mesh_kwargs: dict[str, Any] = {"cmap": cmap, "shading": "auto", "norm": norm}
        if transform is not None:
            mesh_kwargs["transform"] = transform
        artist = ax.pcolormesh(field.x, field.y, field.values, **mesh_kwargs)
    cbar = fig.colorbar(artist, ax=ax, shrink=0.88, pad=0.025)
    cbar.set_label(field.label)

    if vector_overlay and field.vectors is not None and min(field.values.shape) > 1:
        if vector_density is not None:
            if vector_density <= 0:
                raise ValueError("--vector-density must be positive")
            stride = max(1, int(math.ceil(max(field.values.shape) / float(vector_density))))
        else:
            stride = max(1, int(vector_stride))
        vector_kwargs: dict[str, Any] = {
            "angles": "uv",
            "scale_units": "width",
            "scale": vector_scale,
            "width": 0.0022,
            "headwidth": 3.4,
            "headlength": 4.2,
            "headaxislength": 3.8,
            "color": "0.08",
            "alpha": 0.88,
            "zorder": 6,
        }
        if transform is not None:
            vector_kwargs["transform"] = transform
        ax.quiver(
            field.x[::stride, ::stride],
            field.y[::stride, ::stride],
            field.vectors.u[::stride, ::stride],
            field.vectors.v[::stride, ::stride],
            **vector_kwargs,
        )

    west, east, south, north = _extent(field.x, field.y, 0.04)
    if field.geographic:
        _add_cartopy_coastlines(
            ax,
            extent=(west, east, south, north),
            resolution=coastline_resolution,
            allow_download=allow_cartopy_download,
        )
        ax.set_xlabel("Longitude [deg]")
        ax.set_ylabel("Latitude [deg]")
        try:
            gl = ax.gridlines(draw_labels=True, linewidth=0.25, color="0.35", alpha=0.45)
            gl.top_labels = False
            gl.right_labels = False
        except Exception:
            ax.grid(True, linewidth=0.25, alpha=0.45)
    else:
        ax.set_xlim(west, east)
        ax.set_ylim(south, north)
        ax.set_aspect("equal", adjustable="box")
        ax.set_xlabel("x [m]")
        ax.set_ylabel("y [m]")
        ax.grid(True, linewidth=0.25, alpha=0.45)
        LOGGER.warning("geographic coordinates unavailable; coastlines require latitude/longitude")

    title_text = title or field.title
    if field.time_label:
        title_text = f"{title_text}\n{field.time_label}"
    ax.set_title(title_text, fontsize=11)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return out


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Plot publication-ready maps from Sprtz NetCDF-CF products."
    )
    parser.add_argument("input", help="input NetCDF file produced by a Sprtz module")
    parser.add_argument("-o", "--output", required=True, help="output figure path, e.g. map.png or map.pdf")
    parser.add_argument("-v", "--variable", default=None, help="NetCDF variable to plot; auto-detected by default")
    parser.add_argument("--time-index", type=int, default=0, help="time index for multidimensional variables")
    parser.add_argument("--level-index", type=int, default=0, help="vertical/level index for 3-D or 4-D fields")
    parser.add_argument("--center-lat", type=float, default=None, help="grid origin latitude for local x/y products")
    parser.add_argument("--center-lon", type=float, default=None, help="grid origin longitude for local x/y products")
    parser.add_argument("--title", default=None, help="figure title")
    parser.add_argument("--dpi", type=int, default=600, help="output raster DPI")
    parser.add_argument("--cmap", default="viridis", help="matplotlib colormap")
    parser.add_argument("--log-scale", action="store_true", help="use logarithmic color normalization")
    parser.add_argument("--no-vectors", action="store_true", help="disable automatic wind-vector overlay")
    parser.add_argument("--vector-stride", type=int, default=8, help="plot every Nth wind vector")
    parser.add_argument("--vector-density", type=int, default=None, help="target number of wind vectors along the longest grid axis")
    parser.add_argument("--vector-scale", type=float, default=None, help="matplotlib quiver scale for wind vectors")
    parser.add_argument(
        "--coastline-resolution",
        choices=("10m", "50m", "110m"),
        default="10m",
        help="Natural Earth coastline resolution used by Cartopy",
    )
    parser.add_argument(
        "--allow-cartopy-download",
        action="store_true",
        help="allow Cartopy to download missing Natural Earth coastline data",
    )
    parser.add_argument("--width", type=float, default=7.2, help="figure width in inches")
    parser.add_argument("--height", type=float, default=5.4, help="figure height in inches")
    parser.add_argument("--verbose", action="store_true", help="enable debug logging")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )
    try:
        field = read_map_field(
            args.input,
            variable_name=args.variable,
            time_index=args.time_index,
            level_index=args.level_index,
            center_lat=args.center_lat,
            center_lon=args.center_lon,
        )
        out = plot_map(
            field,
            args.output,
            title=args.title,
            dpi=args.dpi,
            cmap=args.cmap,
            coastline_resolution=args.coastline_resolution,
            allow_cartopy_download=args.allow_cartopy_download,
            figure_size=(args.width, args.height),
            log_scale=args.log_scale,
            vector_overlay=not args.no_vectors,
            vector_stride=args.vector_stride,
            vector_density=args.vector_density,
            vector_scale=args.vector_scale,
        )
    except KeyboardInterrupt:
        LOGGER.warning("interrupted; stopping plot generation")
        return 130
    except Exception as exc:
        LOGGER.error("%s", exc)
        return 1
    LOGGER.info("wrote %s", out)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

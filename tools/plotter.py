#!/usr/bin/env python3
"""Plot publication-ready maps, profiles, and 3-D views from Sprtz NetCDF products.

The tool is intentionally optional-dependency friendly: it requires netCDF4 and
matplotlib for plotting, uses Cartopy for coastlines when installed, and never
opts into network-backed Cartopy data acquisition unless requested explicitly.
"""

from __future__ import annotations

import argparse
import logging
import math
import ast
import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from sprtz.logging import LOG_DATE_FORMAT, LOG_FORMAT_VERBOSE

LOGGER = logging.getLogger("sprtz.plotter")
PLOTTER_MODES = ("map", "profile", "profiler", "render3d", "3d")

LATITUDE_NAMES = ("field_latitude", "latitude", "lat", "XLAT", "XLAT_M")
LONGITUDE_NAMES = ("field_longitude", "longitude", "lon", "long", "lng", "XLONG", "XLONG_M")
X_NAMES = ("x", "field_x", "west_east")
Y_NAMES = ("y", "field_y", "south_north")
U_WIND_NAMES = ("eastward_wind", "u", "U", "U10", "U10M")
V_WIND_NAMES = ("northward_wind", "v", "V", "V10", "V10M")
WIND_SPEED_NAMES = ("wind_speed", "wind_speed_10m", "WSPD10", "wspd10", "speed")
WIND_FROM_DIRECTION_NAMES = (
    "wind_from_direction",
    "wind_from_direction_10m",
    "WDIR10",
    "wdir10",
    "wind_dir",
    "wind_direction",
)
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
MPS_TO_KNOTS = 1.9438444924406048
WIND_SPEED_KNOT_LEVELS = (
    0,
    1,
    2,
    3,
    4,
    5,
    6,
    7,
    8,
    9,
    10,
    11,
    12,
    13,
    14,
    15,
    16,
    17,
    18,
    19,
    20,
    21,
    22,
    23,
    24,
    25,
    26,
    27,
    28,
    29,
    30,
    32,
    34,
    36,
    38,
    40,
    42,
    44,
    46,
    48,
    50,
)
WIND_SPEED_KNOT_COLOR_ANCHORS = (
    (0, 0, 51, 255),
    (1, 23, 186, 255),
    (1, 31, 243, 255),
    (5, 51, 252, 255),
    (25, 87, 255, 255),
    (59, 139, 244, 255),
    (79, 189, 248, 255),
    (104, 245, 231, 255),
    (119, 254, 198, 255),
    (146, 251, 158, 255),
    (168, 254, 125, 255),
    (202, 254, 90, 255),
    (237, 253, 77, 255),
    (245, 208, 58, 255),
    (239, 169, 57, 255),
    (250, 115, 46, 255),
    (231, 83, 38, 255),
    (238, 48, 33, 255),
    (187, 32, 24, 255),
    (122, 22, 16, 255),
    (100, 22, 16, 255),
)
WIND_SPEED_KNOT_COLOR_ANCHOR_LEVELS = (0, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21, 23, 25, 27, 30, 35, 40, 45, 50, 52)
WIND_SPEED_KNOT_COLORS = tuple(
    tuple(
        int(round(float(np.interp(level, WIND_SPEED_KNOT_COLOR_ANCHOR_LEVELS, channel_values))))
        for channel_values in zip(*WIND_SPEED_KNOT_COLOR_ANCHORS)
    )
    for level in WIND_SPEED_KNOT_LEVELS
)


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
    local_x: np.ndarray | None
    local_y: np.ndarray | None
    geographic: bool
    label: str
    title: str
    vectors: VectorField | None = None
    time_label: str | None = None
    level_label: str | None = None
    color_levels: tuple[float, ...] | None = None
    color_palette: tuple[tuple[int, int, int, int], ...] | None = None
    terrain_m: np.ndarray | None = None


@dataclass(frozen=True)
class EmissionPoint:
    id: str
    x: float
    y: float
    release_height_agl_m: float
    release_height_asl_m: float
    longitude: float | None = None
    latitude: float | None = None

    @property
    def label(self) -> str:
        return (
            f"{self.id}\n"
            f"z ASL {_format_meters(self.release_height_asl_m)}\n"
            f"z AGL {_format_meters(self.release_height_agl_m)}"
        )


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
) -> tuple[np.ndarray, np.ndarray, np.ndarray | None, np.ndarray | None, bool]:
    local_x: np.ndarray | None = None
    local_y: np.ndarray | None = None
    for x_name, y_name in (("field_x", "field_y"), ("x", "y")):
        if x_name in ds.variables and y_name in ds.variables:
            x = _select_1d_or_2d(_variable_array(ds.variables[x_name]), time_index=time_index)
            y = _select_1d_or_2d(_variable_array(ds.variables[y_name]), time_index=time_index)
            if x.ndim == y.ndim == 1 and x.size == shape[1] and y.size == shape[0]:
                local_x, local_y = np.meshgrid(x, y)
                break
            if x.shape == y.shape == shape:
                local_x, local_y = x, y
                break
    lat_var = _find_variable(ds, LATITUDE_NAMES)
    lon_var = _find_variable(ds, LONGITUDE_NAMES)
    if lat_var is not None and lon_var is not None:
        lat = _select_1d_or_2d(_variable_array(lat_var), time_index=time_index)
        lon = _select_1d_or_2d(_variable_array(lon_var), time_index=time_index)
        if lat.ndim == lon.ndim == 1:
            if lat.size == shape[0] and lon.size == shape[1]:
                lon_grid, lat_grid = np.meshgrid(lon, lat)
                return lon_grid, lat_grid, local_x, local_y, True
            if lat.size == lon.size == shape[0] * shape[1]:
                return lon.reshape(shape), lat.reshape(shape), local_x, local_y, True
        if lat.shape == shape and lon.shape == shape:
            return lon, lat, local_x, local_y, True

    for x_name, y_name in (("field_x", "field_y"), ("x", "y"), ("lon", "lat")):
        if x_name in ds.variables and y_name in ds.variables:
            x = _select_1d_or_2d(_variable_array(ds.variables[x_name]), time_index=time_index)
            y = _select_1d_or_2d(_variable_array(ds.variables[y_name]), time_index=time_index)
            if x.ndim == y.ndim == 1 and x.size == shape[1] and y.size == shape[0]:
                x_grid, y_grid = np.meshgrid(x, y)
                if x_name == "lon" and y_name == "lat":
                    return x_grid, y_grid, local_x, local_y, True
                if center_lat is not None and center_lon is not None:
                    lon_grid, lat_grid, _ = _local_to_lat_lon(x_grid, y_grid, center_lat=center_lat, center_lon=center_lon)
                    return lon_grid, lat_grid, x_grid, y_grid, True
                return x_grid, y_grid, local_x, local_y, False
            if x.shape == y.shape == shape:
                if x_name == "lon" and y_name == "lat":
                    return x, y, local_x, local_y, True
                if center_lat is not None and center_lon is not None:
                    lon_grid, lat_grid, _ = _local_to_lat_lon(x, y, center_lat=center_lat, center_lon=center_lon)
                    return lon_grid, lat_grid, x, y, True
                return x, y, local_x, local_y, False

    x_var = _find_variable(ds, X_NAMES)
    y_var = _find_variable(ds, Y_NAMES)
    if x_var is not None and y_var is not None:
        x = _select_1d_or_2d(_variable_array(x_var), time_index=time_index)
        y = _select_1d_or_2d(_variable_array(y_var), time_index=time_index)
        if x.ndim == y.ndim == 1:
            if x.size == y.size == shape[0] * shape[1]:
                x_grid, y_grid = x.reshape(shape), y.reshape(shape)
            elif x.size == shape[1] and y.size == shape[0]:
                x_grid, y_grid = np.meshgrid(x, y)
            else:
                x_grid, y_grid = np.meshgrid(np.arange(shape[1]), np.arange(shape[0]))
        elif x.shape == y.shape == shape:
            x_grid, y_grid = x, y
        else:
            x_grid, y_grid = np.meshgrid(np.arange(shape[1]), np.arange(shape[0]))
        if center_lat is not None and center_lon is not None:
            lon_grid, lat_grid, _ = _local_to_lat_lon(x_grid, y_grid, center_lat=center_lat, center_lon=center_lon)
            return lon_grid, lat_grid, x_grid, y_grid, True
        return x_grid, y_grid, local_x, local_y, False

    x_grid, y_grid = np.meshgrid(np.arange(shape[1], dtype=float), np.arange(shape[0], dtype=float))
    return x_grid, y_grid, local_x, local_y, False


def _wind_from_speed_direction(speed: np.ndarray, direction_from_deg: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    theta = np.deg2rad(270.0 - direction_from_deg)
    return speed * np.cos(theta), speed * np.sin(theta)


def _unit_vector_components(u: np.ndarray, v: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    u_arr = np.asarray(u, dtype=float)
    v_arr = np.asarray(v, dtype=float)
    magnitude = np.hypot(u_arr, v_arr)
    with np.errstate(divide="ignore", invalid="ignore"):
        unit_u = np.divide(u_arr, magnitude, out=np.zeros_like(u_arr), where=magnitude > 0.0)
        unit_v = np.divide(v_arr, magnitude, out=np.zeros_like(v_arr), where=magnitude > 0.0)
    return unit_u, unit_v


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


def _read_surface_altitude(ds: Any, shape: tuple[int, int], *, time_index: int) -> np.ndarray | None:
    variable = _find_variable(ds, ("surface_altitude", "terrain_m", "dem_elevation_m", "elevation_m"))
    if variable is None:
        return None
    try:
        values = _select_2d(
            _variable_array(variable),
            dimensions=getattr(variable, "dimensions", ()),
            time_index=time_index,
            level_index=0,
        )
    except Exception:
        return None
    return values if values.shape == shape else None


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


def _is_level_dimension(name: str) -> bool:
    lowered = name.lower()
    return any(token in lowered for token in LEVEL_DIMENSION_TOKENS)


def _format_meters(value: float) -> str:
    if math.isfinite(value) and abs(value - round(value)) < 1.0e-6:
        return f"{value:.0f} m"
    return f"{value:.2f} m"


def _format_geographic_coordinate(value: float, positive_suffix: str, negative_suffix: str, coordinate_format: str) -> str:
    suffix = positive_suffix if value >= 0.0 else negative_suffix
    absolute = abs(float(value))
    if coordinate_format == "decimal":
        return f"{absolute:.5f} deg{suffix}"
    degrees = int(math.floor(absolute))
    minutes_total = (absolute - degrees) * 60.0
    if coordinate_format == "dms":
        minutes = int(math.floor(minutes_total))
        seconds = (minutes_total - minutes) * 60.0
        return f"{degrees:02d}°{minutes:02d}'{seconds:04.1f}\"{suffix}"
    return f"{degrees:02d}°{minutes_total:05.2f}'{suffix}"


def _format_longitude(value: float, coordinate_format: str) -> str:
    return _format_geographic_coordinate(value, "E", "W", coordinate_format)


def _format_latitude(value: float, coordinate_format: str) -> str:
    return _format_geographic_coordinate(value, "N", "S", coordinate_format)


def _nearest_grid_value(values: np.ndarray, x_grid: np.ndarray | None, y_grid: np.ndarray | None, x: float, y: float) -> float | None:
    if values.shape != getattr(x_grid, "shape", None) or values.shape != getattr(y_grid, "shape", None):
        return None
    distance2 = (np.asarray(x_grid, dtype=float) - float(x)) ** 2 + (np.asarray(y_grid, dtype=float) - float(y)) ** 2
    if not np.isfinite(distance2).any():
        return None
    iy, ix = (int(index) for index in np.unravel_index(int(np.nanargmin(distance2)), distance2.shape))
    value = float(values[iy, ix])
    return value if math.isfinite(value) else None


def _source_ground_asl_m(
    source: dict[str, Any],
    terrain: np.ndarray | None,
    x_grid: np.ndarray | None,
    y_grid: np.ndarray | None,
    x: float,
    y: float,
) -> float:
    terrain_ground = _nearest_grid_value(terrain, x_grid, y_grid, x, y) if terrain is not None else None
    return float(terrain_ground if terrain_ground is not None else 0.0) + float(source.get("z", 0.0))


def _source_json_candidates(config_path: str | Path | None, input_path: str | Path | None) -> list[Path]:
    if config_path is not None:
        return [Path(config_path)]
    if input_path is None:
        return []
    input_parent = Path(input_path).resolve().parent
    candidates: list[Path] = []
    for directory in (input_parent, *input_parent.parents[:4]):
        candidates.extend(directory.glob("config.json"))
        candidates.extend(directory.glob("*event*.json"))
    return list(dict.fromkeys(candidates))


def _source_records_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(payload.get("sources"), list):
        return [record for record in payload["sources"] if isinstance(record, dict)]
    metadata = payload.get("metadata")
    if isinstance(metadata, dict) and isinstance(metadata.get("fire_events"), list):
        return [record for record in metadata["fire_events"] if isinstance(record, dict)]
    return []


def _nearest_local_from_geographic(field: MapField, latitude: float, longitude: float) -> tuple[float, float] | None:
    if not field.geographic:
        return None
    distance2 = (np.asarray(field.y, dtype=float) - float(latitude)) ** 2 + (np.asarray(field.x, dtype=float) - float(longitude)) ** 2
    if not np.isfinite(distance2).any():
        return None
    iy, ix = (int(index) for index in np.unravel_index(int(np.nanargmin(distance2)), distance2.shape))
    x = float(field.local_x[iy, ix]) if field.local_x is not None else float(field.x[iy, ix])
    y = float(field.local_y[iy, ix]) if field.local_y is not None else float(field.y[iy, ix])
    return x, y


def read_emission_points(config_path: str | Path | None, field: MapField, *, input_path: str | Path | None = None) -> tuple[EmissionPoint, ...]:
    config = None
    for candidate in _source_json_candidates(config_path, input_path):
        try:
            with candidate.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError):
            continue
        if _source_records_from_payload(payload):
            config = payload
            break
    if config is None:
        return ()
    terrain = field.terrain_m
    if terrain is None and field.name.lower() in {"surface_altitude", "terrain_m", "dem_elevation_m", "elevation_m"}:
        terrain = np.asarray(field.values, dtype=float)
    points: list[EmissionPoint] = []
    for index, source in enumerate(_source_records_from_payload(config)):
        lat = float(source["latitude"]) if source.get("latitude") is not None else None
        lon = float(source["longitude"]) if source.get("longitude") is not None else None
        local_from_geo = _nearest_local_from_geographic(field, lat, lon) if lat is not None and lon is not None else None
        x = float(source.get("x", local_from_geo[0] if local_from_geo is not None else 0.0))
        y = float(source.get("y", local_from_geo[1] if local_from_geo is not None else 0.0))
        agl = float(source.get("height_agl_m", source.get("stack_height", 0.0)))
        ground_m = _source_ground_asl_m(
            source,
            terrain,
            field.local_x if field.local_x is not None else field.x,
            field.local_y if field.local_y is not None else field.y,
            x,
            y,
        )
        points.append(
            EmissionPoint(
                id=str(source.get("id", f"S{index + 1}")),
                x=x,
                y=y,
                release_height_agl_m=agl,
                release_height_asl_m=ground_m + agl,
                longitude=lon,
                latitude=lat,
            )
        )
    return tuple(points)


def _parse_float_list(value: Any) -> list[float]:
    if value is None:
        return []
    if isinstance(value, np.ndarray):
        return [float(item) for item in value.ravel()]
    if isinstance(value, (list, tuple)):
        return [float(item) for item in value]
    if isinstance(value, (int, float, np.integer, np.floating)):
        return [float(value)]
    text = str(value).strip()
    if not text:
        return []
    try:
        parsed = ast.literal_eval(text)
    except (SyntaxError, ValueError):
        try:
            return [float(text)]
        except ValueError:
            return []
    return _parse_float_list(parsed)


def _height_to_meters(value: float, units: str) -> float | None:
    lowered = units.strip().lower()
    if lowered in {"", "m", "meter", "meters", "metre", "metres"}:
        return value
    if lowered in {"km", "kilometer", "kilometers", "kilometre", "kilometres"}:
        return value * 1000.0
    if lowered in {"cm", "centimeter", "centimeters", "centimetre", "centimetres"}:
        return value / 100.0
    return None


def _read_level_label(ds: Any, variable: Any, *, level_index: int) -> str | None:
    level_dim = next((dim for dim in getattr(variable, "dimensions", ()) if _is_level_dimension(dim)), None)
    if level_dim is None:
        return None
    level_prefix = f"Level index: {level_index}"
    for attr_name in ("spritzmet_level_meters", "level_meters"):
        levels = _parse_float_list(getattr(ds, attr_name, None))
        if level_index < len(levels):
            return f"{level_prefix} ({_format_meters(levels[level_index])})"
    candidates = [level_dim, "height_m", "height", "z", "level", "bottom_top"]
    lowered = {name.lower(): name for name in ds.variables}
    for candidate in candidates:
        actual = lowered.get(candidate.lower())
        if actual is None:
            continue
        coord = ds.variables[actual]
        if len(getattr(coord, "dimensions", ())) != 1:
            continue
        coord_dims = tuple(getattr(coord, "dimensions", ()))
        if coord_dims and coord_dims[0] != level_dim:
            continue
        values = np.asarray(coord[:], dtype=float).reshape(-1)
        if values.size == 0 or level_index < 0 or level_index >= values.size:
            continue
        meters = _height_to_meters(float(values[level_index]), str(getattr(coord, "units", "")))
        if meters is not None:
            return f"{level_prefix} ({_format_meters(meters)})"
    return f"{level_prefix} (meters unavailable)"


def _is_wind_speed_variable(variable: Any) -> bool:
    name = str(getattr(variable, "name", "")).lower()
    standard_name = str(getattr(variable, "standard_name", "")).lower()
    long_name = str(getattr(variable, "long_name", "")).lower()
    return (
        name in {candidate.lower() for candidate in WIND_SPEED_NAMES}
        or standard_name == "wind_speed"
        or "wind speed" in long_name
    )


def _values_to_knots(values: np.ndarray, units: str) -> np.ndarray:
    lowered = units.strip().lower()
    if lowered in {"kt", "kts", "knot", "knots"}:
        return values
    if lowered in {"m s-1", "m/s", "meter s-1", "meters s-1", "metre s-1", "metres s-1"}:
        return values * MPS_TO_KNOTS
    return values * MPS_TO_KNOTS


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
        x, y, local_x, local_y, geographic = _coordinate_mesh(
            ds,
            values.shape,
            time_index=time_index,
            center_lat=center_lat,
            center_lon=center_lon,
        )
        units = getattr(variable, "units", "")
        long_name = getattr(variable, "long_name", "") or getattr(variable, "standard_name", "")
        color_levels: tuple[float, ...] | None = None
        color_palette: tuple[tuple[int, int, int, int], ...] | None = None
        if _is_wind_speed_variable(variable):
            values = _values_to_knots(values, str(units))
            units = "kt"
            long_name = long_name or "Wind speed"
            color_levels = tuple(float(level) for level in WIND_SPEED_KNOT_LEVELS)
            color_palette = WIND_SPEED_KNOT_COLORS
        label = f"{long_name or variable.name}{f' [{units}]' if units else ''}"
        title = f"{Path(input_path).name}: {long_name or variable.name}"
        vectors = _read_vectors(ds, values.shape, time_index=time_index, level_index=level_index)
        time_label = _read_time_label(ds, time_index=time_index)
        level_label = _read_level_label(ds, variable, level_index=level_index)
        terrain_m = _read_surface_altitude(ds, values.shape, time_index=time_index)
        return MapField(
            variable.name,
            values,
            x,
            y,
            local_x,
            local_y,
            geographic,
            label,
            title,
            vectors=vectors,
            time_label=time_label,
            level_label=level_label,
            color_levels=color_levels,
            color_palette=color_palette,
            terrain_m=terrain_m,
        )


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


def _is_concentration_field(field: MapField) -> bool:
    text = f"{field.name} {field.label}".lower()
    return "concentration" in text or "mass" in text


def _transparent_zero_values(field: MapField) -> np.ndarray:
    values = np.asarray(field.values, dtype=float)
    if not _is_concentration_field(field):
        return values
    return np.ma.masked_where(np.isfinite(values) & (values <= 0.0), values)


def _transparent_zero_cmap(plt: Any, cmap: Any, *, transparent: bool) -> Any:
    if not transparent:
        return cmap
    resolved = plt.get_cmap(cmap) if isinstance(cmap, str) else cmap
    copied = resolved.copy()
    copied.set_bad((0.0, 0.0, 0.0, 0.0))
    return copied


def _emission_summary_text(emission_points: Sequence[EmissionPoint]) -> str | None:
    if not emission_points:
        return None
    return "\n".join(point.label.replace("\n", " | ") for point in emission_points[:4])


def _axis_center_line(grid: np.ndarray | None, axis: str) -> np.ndarray | None:
    if grid is None or grid.ndim != 2:
        return None
    if axis == "x":
        return np.asarray(grid[grid.shape[0] // 2, :], dtype=float)
    return np.asarray(grid[:, grid.shape[1] // 2], dtype=float)


def _format_axis_tick(value: float) -> str:
    rounded = round(float(value))
    if math.isclose(float(value), rounded, rel_tol=0.0, abs_tol=1.0e-9):
        return f"{rounded:d}"
    return f"{float(value):.1f}"


def _mapped_axis_ticks(
    source: np.ndarray,
    target: np.ndarray,
    *,
    count: int = 7,
) -> tuple[np.ndarray, list[str]]:
    source_arr = np.asarray(source, dtype=float)
    target_arr = np.asarray(target, dtype=float)
    finite = np.isfinite(source_arr) & np.isfinite(target_arr)
    if np.count_nonzero(finite) < 2:
        return np.asarray([], dtype=float), []
    source_arr = source_arr[finite]
    target_arr = target_arr[finite]
    order = np.argsort(source_arr)
    source_arr = source_arr[order]
    target_arr = target_arr[order]
    if float(np.nanmin(source_arr)) == float(np.nanmax(source_arr)):
        return np.asarray([], dtype=float), []
    source_ticks = np.linspace(float(source_arr[0]), float(source_arr[-1]), max(2, int(count)))
    target_ticks = np.interp(source_ticks, source_arr, target_arr)
    labels = [_format_axis_tick(value) for value in target_ticks]
    return source_ticks, labels


def _add_overlay_axis(ax: Any, *, kind: str) -> Any:
    figure = getattr(ax, "figure", None)
    if figure is None or not hasattr(figure, "add_axes") or not hasattr(ax, "get_position"):
        return ax.twiny() if kind == "x" else ax.twinx()
    overlay = figure.add_axes(ax.get_position(), frameon=False)
    overlay.patch.set_alpha(0.0)
    if kind == "x":
        overlay.set_xlim(ax.get_xlim())
        overlay.xaxis.set_ticks_position("top")
        overlay.xaxis.set_label_position("top")
        overlay.yaxis.set_visible(False)
    else:
        overlay.set_ylim(ax.get_ylim())
        overlay.yaxis.set_ticks_position("right")
        overlay.yaxis.set_label_position("right")
        overlay.xaxis.set_visible(False)
    return overlay


def _add_local_secondary_axes(ax: Any, field: MapField) -> None:
    if not field.geographic or field.local_x is None or field.local_y is None:
        return
    lon_line = _axis_center_line(field.x, "x")
    x_line = _axis_center_line(field.local_x, "x")
    lat_line = _axis_center_line(field.y, "y")
    y_line = _axis_center_line(field.local_y, "y")
    if lon_line is None or x_line is None or lat_line is None or y_line is None:
        return
    if np.ptp(lon_line) > 0.0 and np.ptp(x_line) > 0.0:
        top = _add_overlay_axis(ax, kind="x")
        top.set_xlim(ax.get_xlim())
        x_ticks, x_labels = _mapped_axis_ticks(lon_line, x_line)
        if x_labels:
            top.set_xticks(x_ticks)
            top.set_xticklabels(x_labels)
        top.set_xlabel("x [m]")
    if np.ptp(lat_line) > 0.0 and np.ptp(y_line) > 0.0:
        right = _add_overlay_axis(ax, kind="y")
        right.set_ylim(ax.get_ylim())
        y_ticks, y_labels = _mapped_axis_ticks(lat_line, y_line)
        if y_labels:
            right.set_yticks(y_ticks)
            right.set_yticklabels(y_labels)
        right.set_ylabel("y [m]")


def _download_soest_gshhs(cartopy_config: Any, scale: str, level: int) -> Path:
    from io import BytesIO
    from urllib.request import urlopen
    from zipfile import ZipFile

    data_dir = Path(cartopy_config["data_dir"])
    target_dir = data_dir / "shapefiles" / "gshhs" / scale
    target = target_dir / f"GSHHS_{scale}_L{level}.shp"
    if target.exists():
        return target

    url = "https://www.soest.hawaii.edu/pwessel/gshhg/gshhg-shp-2.3.7.zip"
    LOGGER.warning("Cartopy GSHHS download failed; downloading GSHHG from %s", url)
    with urlopen(url, timeout=60) as response:
        archive = BytesIO(response.read())

    target_dir.mkdir(parents=True, exist_ok=True)
    prefix = Path("GSHHS_shp") / scale / f"GSHHS_{scale}_L{level}"
    with ZipFile(archive) as zfh:
        for suffix in (".shp", ".dbf", ".shx", ".prj"):
            member_name = str(prefix.with_suffix(suffix))
            with zfh.open(member_name) as source:
                (target_dir / f"GSHHS_{scale}_L{level}{suffix}").write_bytes(source.read())
    return target


def _add_cartopy_coastlines(
    ax: Any,
    *,
    extent: tuple[float, float, float, float],
    source: str,
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
    west, east, south, north = extent
    ax.set_extent((west, east, south, north), crs=ccrs.PlateCarree())

    def natural_earth_path(category: str, name: str) -> str | None:
        filename = f"ne_{resolution}_{name}.shp"
        for config_key in ("pre_existing_data_dir", "data_dir"):
            root = cartopy.config.get(config_key)
            if not root:
                continue
            path = Path(root) / "shapefiles" / "natural_earth" / category / filename
            if path.exists():
                return str(path)
        if not allow_download:
            return None
        return str(shpreader.natural_earth(resolution=resolution, category=category, name=name))

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
            path = natural_earth_path(category, name)
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
        if path is None:
            LOGGER.warning(
                "Cartopy Natural Earth %s/%s at %s is not installed locally; "
                "pass --allow-cartopy-download to fetch it",
                category,
                name,
                resolution,
            )
            return
        feature = cfeature.ShapelyFeature(
            shpreader.Reader(path).geometries(),
            ccrs.PlateCarree(),
            edgecolor=edgecolor,
            facecolor=facecolor,
            linewidth=linewidth,
        )
        ax.add_feature(feature, zorder=zorder)

    def add_gshhs() -> bool:
        scale = {"10m": "full", "50m": "intermediate", "110m": "low"}[resolution]
        scale_key = scale[0]
        filename = f"GSHHS_{scale_key}_L1.shp"
        installed = False
        for config_key in ("pre_existing_data_dir", "data_dir"):
            root = cartopy.config.get(config_key)
            if not root:
                continue
            path = Path(root) / "shapefiles" / "gshhs" / scale_key / filename
            if path.exists():
                installed = True
                break
        if not installed and not allow_download:
            LOGGER.warning(
                "Cartopy GSHHS %s coastlines are not installed locally; "
                "pass --allow-cartopy-download to fetch them",
                scale,
            )
            return False
        try:
            try:
                path = shpreader.gshhs(scale=scale_key, level=1)
            except Exception:
                if not allow_download:
                    raise
                path = _download_soest_gshhs(cartopy.config, scale_key, level=1)
            reader = shpreader.Reader(path)
            feature = cfeature.ShapelyFeature(
                reader.geometries(),
                ccrs.PlateCarree(),
                edgecolor="0.08",
                facecolor="none",
                linewidth=0.75,
            )
        except Exception as exc:
            LOGGER.warning(
                "Cartopy GSHHS %s coastlines are unavailable (%s); "
                "install local GSHHS data or pass --allow-cartopy-download",
                scale,
                exc,
            )
            return False
        ax.add_feature(feature, zorder=5)
        return True

    if source == "gshhs":
        if add_gshhs():
            return
        LOGGER.warning("falling back to Natural Earth coastlines")

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
    coastline_source: str = "naturalearth",
    color_limits: tuple[float, float] | None = None,
    warn_missing_geographic: bool = True,
    emission_points: Sequence[EmissionPoint] = (),
    coordinate_format: str = "ddm",
) -> Path:
    try:
        import matplotlib

        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt
        import matplotlib.ticker as mticker
        from matplotlib.colors import BoundaryNorm, ListedColormap, LogNorm, Normalize
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
        if color_limits is None:
            positive = field.values[np.isfinite(field.values) & (field.values > 0)]
            if positive.size == 0:
                raise ValueError("--log-scale requires at least one positive value")
            color_limits = (float(np.nanmin(positive)), float(np.nanmax(positive)))
        norm = LogNorm(vmin=color_limits[0], vmax=color_limits[1])
    transparent_zero = _is_concentration_field(field)
    plot_values = _transparent_zero_values(field)
    plot_cmap: Any = cmap
    if field.color_levels is not None and field.color_palette is not None:
        rgba = np.asarray(field.color_palette, dtype=float) / 255.0
        plot_cmap = ListedColormap(rgba)
        if not log_scale:
            norm = BoundaryNorm(field.color_levels, ncolors=plot_cmap.N, clip=False)
    elif color_limits is not None and not log_scale:
        norm = Normalize(vmin=color_limits[0], vmax=color_limits[1])
    plot_cmap = _transparent_zero_cmap(plt, plot_cmap, transparent=transparent_zero)

    if min(field.values.shape) == 1:
        scatter_kwargs: dict[str, Any] = {
            "c": plot_values.ravel(),
            "cmap": plot_cmap,
            "norm": norm,
            "s": 34.0,
            "edgecolors": "black",
            "linewidths": 0.25,
        }
        if transform is not None:
            scatter_kwargs["transform"] = transform
        artist = ax.scatter(field.x.ravel(), field.y.ravel(), **scatter_kwargs)
    else:
        mesh_kwargs: dict[str, Any] = {"cmap": plot_cmap, "shading": "auto", "norm": norm}
        if transform is not None:
            mesh_kwargs["transform"] = transform
        artist = ax.pcolormesh(field.x, field.y, plot_values, **mesh_kwargs)
    colorbar_kwargs: dict[str, Any] = {"shrink": 0.88, "pad": 0.025}
    if field.color_levels is not None:
        colorbar_kwargs["ticks"] = field.color_levels
    cbar = fig.colorbar(artist, ax=ax, **colorbar_kwargs)
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
        vector_u, vector_v = _unit_vector_components(field.vectors.u, field.vectors.v)
        ax.quiver(
            field.x[::stride, ::stride],
            field.y[::stride, ::stride],
            vector_u[::stride, ::stride],
            vector_v[::stride, ::stride],
            **vector_kwargs,
        )

    for point in emission_points:
        px = point.longitude if field.geographic and point.longitude is not None else point.x
        py = point.latitude if field.geographic and point.latitude is not None else point.y
        marker_kwargs: dict[str, Any] = {
            "marker": "^",
            "s": 70.0,
            "facecolors": "#d7191c",
            "edgecolors": "white",
            "linewidths": 0.7,
            "zorder": 8,
        }
        label_kwargs: dict[str, Any] = {
            "fontsize": 7,
            "color": "0.05",
            "ha": "left",
            "va": "bottom",
            "zorder": 9,
            "bbox": {"boxstyle": "round,pad=0.18", "facecolor": "white", "edgecolor": "0.35", "alpha": 0.82},
        }
        if transform is not None:
            marker_kwargs["transform"] = transform
            label_kwargs["transform"] = transform
        ax.scatter([px], [py], **marker_kwargs)
        ax.text(px, py, point.label, **label_kwargs)

    summary = _emission_summary_text(emission_points)
    if summary:
        fig.text(
            0.012,
            0.012,
            summary,
            fontsize=8,
            ha="left",
            va="bottom",
            bbox={"boxstyle": "round,pad=0.25", "facecolor": "white", "edgecolor": "0.35", "alpha": 0.86},
        )

    west, east, south, north = _extent(field.x, field.y, 0.04)
    if field.geographic:
        _add_cartopy_coastlines(
            ax,
            extent=(west, east, south, north),
            source=coastline_source,
            resolution=coastline_resolution,
            allow_download=allow_cartopy_download,
        )
        ax.set_xlabel("Longitude [deg]")
        ax.set_ylabel("Latitude [deg]")
        _add_local_secondary_axes(ax, field)
        try:
            gl = ax.gridlines(draw_labels=True, linewidth=0.25, color="0.35", alpha=0.45)
            gl.top_labels = False
            gl.right_labels = False
            gl.xformatter = mticker.FuncFormatter(lambda value, _pos: _format_longitude(value, coordinate_format))
            gl.yformatter = mticker.FuncFormatter(lambda value, _pos: _format_latitude(value, coordinate_format))
        except Exception:
            ax.grid(True, linewidth=0.25, alpha=0.45)
            ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda value, _pos: _format_longitude(value, coordinate_format)))
            ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda value, _pos: _format_latitude(value, coordinate_format)))
    else:
        ax.set_xlim(west, east)
        ax.set_ylim(south, north)
        ax.set_aspect("equal", adjustable="box")
        ax.set_xlabel("x [m]")
        ax.set_ylabel("y [m]")
        ax.grid(True, linewidth=0.25, alpha=0.45)
        if warn_missing_geographic:
            LOGGER.warning("geographic coordinates unavailable; coastlines require latitude/longitude")

    title_text = title or field.title
    detail_labels = [label for label in (field.time_label, field.level_label) if label]
    if detail_labels:
        title_text = f"{title_text}\n{' | '.join(detail_labels)}"
    ax.set_title(title_text, fontsize=11)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return out


def _animation_time_indexes(input_path: str | Path, variable_name: str | None) -> list[int]:
    Dataset = _load_netcdf4()
    with Dataset(input_path) as ds:
        variable = _find_variable(ds, (variable_name,)) if variable_name else None
        if variable is None:
            candidates = _candidate_variables(ds)
            if not candidates:
                return [0]
            variable = ds.variables[candidates[0]]
        dims = tuple(str(dim).lower() for dim in getattr(variable, "dimensions", ()))
        shape = tuple(int(size) for size in getattr(variable, "shape", ()))
        for axis, dim in enumerate(dims):
            if any(token in dim for token in TIME_DIMENSION_TOKENS):
                return list(range(max(1, shape[axis])))
        return [0]


def _expanded_color_limits(low: float, high: float, *, log_scale: bool) -> tuple[float, float]:
    if high > low:
        return low, high
    if log_scale:
        lower = low / 10.0 if low > 0.0 else 1.0e-12
        upper = high * 10.0 if high > 0.0 else 1.0e-11
        if upper <= lower:
            upper = lower * 10.0
        return lower, upper
    pad = max(abs(low) * 0.01, 1.0)
    return low - pad, high + pad


def _animation_color_limits(fields: Sequence[MapField], *, log_scale: bool) -> tuple[float, float] | None:
    samples: list[np.ndarray] = []
    for field in fields:
        values = np.asarray(field.values, dtype=float)
        if log_scale:
            sample = values[np.isfinite(values) & (values > 0.0)]
        else:
            sample = values[np.isfinite(values)]
        if sample.size:
            samples.append(sample)
    if not samples:
        return None
    combined = np.concatenate(samples)
    low = float(np.nanmin(combined))
    high = float(np.nanmax(combined))
    if not log_scale and low >= 0.0:
        low = 0.0
    return _expanded_color_limits(low, high, log_scale=log_scale)


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
    first, rest = frames[0], frames[1:]
    first.save(
        out,
        save_all=True,
        append_images=rest,
        duration=max(1, int(duration_ms)),
        loop=max(0, int(loop)),
        optimize=False,
    )
    for frame in frames:
        frame.close()
    return out


def plot_animation(
    input_path: str | Path,
    output_path: str | Path,
    *,
    variable_name: str | None,
    level_index: int,
    center_lat: float | None,
    center_lon: float | None,
    title: str | None,
    dpi: int,
    cmap: str,
    coastline_source: str,
    coastline_resolution: str,
    allow_cartopy_download: bool,
    figure_size: tuple[float, float],
    log_scale: bool,
    vector_overlay: bool,
    vector_stride: int,
    vector_density: int | None,
    vector_scale: float | None,
    duration_ms: int,
    loop: int,
    config_path: str | Path | None = None,
    coordinate_format: str = "ddm",
) -> Path:
    time_indexes = _animation_time_indexes(input_path, variable_name)
    fields = [
        read_map_field(
            input_path,
            variable_name=variable_name,
            time_index=time_index,
            level_index=level_index,
            center_lat=center_lat,
            center_lon=center_lon,
        )
        for time_index in time_indexes
    ]
    color_limits = _animation_color_limits(fields, log_scale=log_scale)
    if color_limits is not None:
        LOGGER.info(
            "animation color scale fixed across %d frames: vmin=%g vmax=%g",
            len(fields),
            color_limits[0],
            color_limits[1],
        )
    if fields and not fields[0].geographic:
        LOGGER.warning("geographic coordinates unavailable; coastlines require latitude/longitude")
    with tempfile.TemporaryDirectory(prefix="sprtz_plotter_frames_") as tmp:
        frame_paths: list[Path] = []
        for time_index, field in zip(time_indexes, fields):
            frame_path = Path(tmp) / f"frame_{time_index:05d}.png"
            plot_map(
                field,
                frame_path,
                title=title,
                dpi=dpi,
                cmap=cmap,
                coastline_source=coastline_source,
                coastline_resolution=coastline_resolution,
                allow_cartopy_download=allow_cartopy_download,
                figure_size=figure_size,
                log_scale=log_scale,
                vector_overlay=vector_overlay,
                vector_stride=vector_stride,
                vector_density=vector_density,
                vector_scale=vector_scale,
                color_limits=color_limits,
                warn_missing_geographic=False,
                emission_points=read_emission_points(config_path, field, input_path=input_path),
                coordinate_format=coordinate_format,
            )
            frame_paths.append(frame_path)
            LOGGER.info("animation frame %d/%d time_index=%d", len(frame_paths), len(time_indexes), time_index)
        return _write_gif(frame_paths, output_path, duration_ms=duration_ms, loop=loop)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Plot publication-ready Sprtz NetCDF-CF products. The default mode is "
            "map; use 'profile' for vertical profiles or 'render3d' for 3-D views."
        )
    )
    parser.add_argument("input", help="input NetCDF file produced by a Sprtz module")
    parser.add_argument("-o", "--output", required=True, help="output figure path, e.g. map.png, map.pdf, or map.gif")
    parser.add_argument("-v", "--variable", default=None, help="NetCDF variable to plot; auto-detected by default")
    parser.add_argument("--time-index", type=int, default=0, help="time index for multidimensional variables")
    parser.add_argument("--level-index", type=int, default=0, help="vertical/level index for 3-D or 4-D fields")
    parser.add_argument("--center-lat", type=float, default=None, help="grid origin latitude for local x/y products")
    parser.add_argument("--center-lon", type=float, default=None, help="grid origin longitude for local x/y products")
    parser.add_argument("--config", default=None, help="optional Sprtz JSON config; overlays emission points with z ASL and z AGL heights")
    parser.add_argument(
        "--coordinate-format",
        choices=("ddm", "decimal", "dms"),
        default="ddm",
        help="latitude/longitude label format: ddm is DD°MM' (default), decimal is decimal degrees, dms is DD°MM'SS\"",
    )
    parser.add_argument("--title", default=None, help="figure title")
    parser.add_argument("--dpi", type=int, default=600, help="output raster DPI")
    parser.add_argument("--cmap", default="viridis", help="matplotlib colormap")
    parser.add_argument("--log-scale", action="store_true", help="use logarithmic color normalization")
    parser.add_argument("--no-vectors", action="store_true", help="disable automatic wind-vector overlay")
    parser.add_argument("--vector-stride", type=int, default=8, help="plot every Nth wind vector")
    parser.add_argument("--vector-density", type=int, default=None, help="target number of wind vectors along the longest grid axis")
    parser.add_argument("--vector-scale", type=float, default=None, help="matplotlib quiver scale for wind vectors")
    parser.add_argument("--animate", action="store_true", help="write an animated GIF using every time frame of the selected variable")
    parser.add_argument("--frame-duration-ms", type=int, default=300, help="animated GIF frame duration in milliseconds")
    parser.add_argument("--gif-loop", type=int, default=0, help="animated GIF loop count; 0 loops forever")
    parser.add_argument(
        "--coastline-resolution",
        choices=("10m", "50m", "110m"),
        default="10m",
        help="coastline resolution used by Cartopy",
    )
    parser.add_argument(
        "--coastline-source",
        choices=("naturalearth", "gshhs"),
        default="naturalearth",
        help="Cartopy coastline source; use gshhs for finer harbor-scale coastlines",
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


def _delegate_main(module_name: str, argv: Sequence[str]) -> int:
    try:
        module = __import__(f"tools.{module_name}", fromlist=["main"])
    except ModuleNotFoundError:
        module = __import__(module_name, fromlist=["main"])
    return int(module.main(argv))


def _tool_module(module_name: str) -> Any:
    try:
        return __import__(f"tools.{module_name}", fromlist=["*"])
    except ModuleNotFoundError:
        return __import__(module_name, fromlist=["*"])


def read_profile_data(*args: Any, **kwargs: Any) -> Any:
    return _tool_module("profiler").read_profile_data(*args, **kwargs)


def plot_profile(*args: Any, **kwargs: Any) -> Any:
    return _tool_module("profiler").plot_profile(*args, **kwargs)


def plot_profile_animation(*args: Any, **kwargs: Any) -> Any:
    return _tool_module("profiler").plot_profile_animation(*args, **kwargs)


def read_volume_field(*args: Any, **kwargs: Any) -> Any:
    return _tool_module("render3d").read_volume_field(*args, **kwargs)


def read_terrain_field(*args: Any, **kwargs: Any) -> Any:
    return _tool_module("render3d").read_terrain_field(*args, **kwargs)


def read_wind_vector_components(*args: Any, **kwargs: Any) -> Any:
    return _tool_module("render3d").read_wind_vector_components(*args, **kwargs)


def plot_volume(*args: Any, **kwargs: Any) -> Any:
    return _tool_module("render3d").plot_volume(*args, **kwargs)


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in {"profile", "profiler"}:
        return _delegate_main("profiler", argv[1:])
    if argv and argv[0] in {"render3d", "3d"}:
        return _delegate_main("render3d", argv[1:])
    if argv and argv[0] == "map":
        argv = argv[1:]
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format=LOG_FORMAT_VERBOSE,
        datefmt=LOG_DATE_FORMAT,
    )
    try:
        common = {
            "variable_name": args.variable,
            "level_index": args.level_index,
            "center_lat": args.center_lat,
            "center_lon": args.center_lon,
            "title": args.title,
            "dpi": args.dpi,
            "cmap": args.cmap,
            "coastline_source": args.coastline_source,
            "coastline_resolution": args.coastline_resolution,
            "allow_cartopy_download": args.allow_cartopy_download,
            "figure_size": (args.width, args.height),
            "log_scale": args.log_scale,
            "vector_overlay": not args.no_vectors,
            "vector_stride": args.vector_stride,
            "vector_density": args.vector_density,
            "vector_scale": args.vector_scale,
        }
        if args.animate:
            out = plot_animation(
                args.input,
                args.output,
                **common,
                config_path=args.config,
                coordinate_format=args.coordinate_format,
                duration_ms=args.frame_duration_ms,
                loop=args.gif_loop,
            )
        else:
            field = read_map_field(
                args.input,
                variable_name=common["variable_name"],
                time_index=args.time_index,
                level_index=common["level_index"],
                center_lat=common["center_lat"],
                center_lon=common["center_lon"],
            )
            out = plot_map(
                field,
                args.output,
                title=common["title"],
                dpi=common["dpi"],
                cmap=common["cmap"],
                coastline_source=common["coastline_source"],
                coastline_resolution=common["coastline_resolution"],
                allow_cartopy_download=common["allow_cartopy_download"],
                figure_size=common["figure_size"],
                log_scale=common["log_scale"],
                vector_overlay=common["vector_overlay"],
                vector_stride=common["vector_stride"],
                vector_density=common["vector_density"],
                vector_scale=common["vector_scale"],
                emission_points=read_emission_points(args.config, field, input_path=args.input),
                coordinate_format=args.coordinate_format,
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

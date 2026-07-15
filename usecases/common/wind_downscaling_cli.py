#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import logging
import math
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
from pyproj import CRS, Transformer

USECASES_ROOT = Path(__file__).resolve().parents[2]
COMMON_DIR = USECASES_ROOT / "common"
for path in (COMMON_DIR, USECASES_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from datetime_args import parse_script_datetime, script_datetime_to_date_and_hour
from sprtz.config import config_defaults
from sprtz.logging import configure_logging
from sprtz.models import spritzmet, spritzwrf
from sprtz.parallel import get_mpi_context, get_parallel_context


LOGGER = logging.getLogger(__name__)
DEFAULT_USE_CASE_BOUNDS = {
    "south": 40.78,
    "north": 40.85,
    "west": 14.18,
    "east": 14.33,
}
RASTERIO_SUFFIXES = {".tif", ".tiff", ".cog"}
NETCDF_SUFFIXES = {".nc", ".nc4", ".cdf", ".netcdf"}


class UseCaseDependencyError(RuntimeError):
    """Raised when the selected use-case inputs need optional dependencies."""


def _teach(message: str, *args: object) -> None:
    LOGGER.info("teaching note: " + message, *args)


def _check_local_raster_dependencies(*paths: str | Path | None) -> None:
    """Fail before expensive WRF work when optional raster readers are missing."""
    missing: dict[str, list[str]] = {}
    for raw_path in paths:
        if raw_path is None:
            continue
        path = Path(raw_path)
        suffix = path.suffix.lower()
        if suffix in RASTERIO_SUFFIXES and importlib.util.find_spec("rasterio") is None:
            missing.setdefault("rasterio", []).append(str(path))
        if suffix in NETCDF_SUFFIXES and importlib.util.find_spec("netCDF4") is None:
            missing.setdefault("netCDF4", []).append(str(path))
    if not missing:
        return

    details = "; ".join(
        f"{module} is required for {', '.join(values)}" for module, values in missing.items()
    )
    install = "python -m pip install -e '.[geo,netcdf]'"
    raise UseCaseDependencyError(
        f"{details}. Install optional geospatial dependencies with: {install}"
    )


class WindDownscalingResult:
    def __init__(
        self,
        output_path: Path,
        nx: int,
        ny: int,
        dx_m: float,
        dy_m: float,
        center_lat: float,
        center_lon: float,
        source: str,
        fmt: str,
        component: str = "usecase.01_high_resolution_wind_field",
        plot_path: Path | None = None,
        requested_bounds: dict[str, float] | None = None,
        actual_bounds: dict[str, float] | None = None,
    ) -> None:
        self.output_path = output_path
        self.nx = nx
        self.ny = ny
        self.dx_m = dx_m
        self.dy_m = dy_m
        self.center_lat = center_lat
        self.center_lon = center_lon
        self.source = source
        self.format = fmt
        self.component = component
        self.plot_path = plot_path
        self.pipeline = "SpritzWRF -> SpritzMet"
        self.requested_bounds = requested_bounds
        self.actual_bounds = actual_bounds

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "component": self.component,
            "output_path": str(self.output_path),
            "nx": self.nx,
            "ny": self.ny,
            "dx_m": self.dx_m,
            "dy_m": self.dy_m,
            "center_lat": self.center_lat,
            "center_lon": self.center_lon,
            "source": self.source,
            "format": self.format,
            "pipeline": self.pipeline,
        }
        if self.plot_path is not None:
            result["plot_path"] = str(self.plot_path)
        if self.requested_bounds is not None:
            result["requested_bounds"] = self.requested_bounds
        if self.actual_bounds is not None:
            result["actual_bounds"] = self.actual_bounds
        return result


def _optional_float(value: float | None, name: str) -> float:
    if value is None:
        raise ValueError(f"{name} is required when using bounding-box mode")
    return value


def _bounds_from_args(args: argparse.Namespace) -> dict[str, float] | None:
    values = {
        "south": args.south,
        "north": args.north,
        "west": args.west,
        "east": args.east,
    }
    if all(value is None for value in values.values()):
        if args.center_lat is None and args.center_lon is None:
            return dict(DEFAULT_USE_CASE_BOUNDS)
        return None
    if any(value is None for value in values.values()):
        missing = ", ".join(f"--{name}" for name, value in values.items() if value is None)
        raise ValueError(f"{missing} must be provided with bounding-box mode")

    bounds = {name: _optional_float(value, name) for name, value in values.items()}
    if bounds["south"] >= bounds["north"]:
        raise ValueError("--south must be less than --north")
    if bounds["west"] >= bounds["east"]:
        raise ValueError("--west must be less than --east")
    return bounds


def _resolve_grid(args: argparse.Namespace) -> tuple[float, float, int, int, dict[str, float] | None]:
    if args.dx <= 0 or args.dy <= 0:
        raise ValueError("--dx and --dy must be positive")
    bounds = _bounds_from_args(args)
    if bounds is None:
        if args.center_lat is None or args.center_lon is None:
            raise ValueError("--center-lat and --center-lon are required when --south/--north/--west/--east are omitted")
        if args.nx < 2 or args.ny < 2:
            raise ValueError("--nx and --ny must be at least 2")
        _teach(
            "center-grid mode keeps the requested node count fixed: center=(%.6f, %.6f), nx=%s, ny=%s, dx=%.3f m, dy=%.3f m",
            args.center_lat,
            args.center_lon,
            args.nx,
            args.ny,
            args.dx,
            args.dy,
        )
        return args.center_lat, args.center_lon, args.nx, args.ny, None

    center_lat = (bounds["south"] + bounds["north"]) / 2.0
    center_lon = (bounds["west"] + bounds["east"]) / 2.0
    _teach(
        "bbox mode starts from the geographic midpoint because SpritzMet builds a symmetric local projection grid",
    )
    transformer = Transformer.from_crs(CRS.from_epsg(4326), spritzmet.local_crs(center_lat, center_lon), always_xy=True)
    corner_lon = np.asarray([bounds["west"], bounds["west"], bounds["east"], bounds["east"]], dtype=float)
    corner_lat = np.asarray([bounds["south"], bounds["north"], bounds["south"], bounds["north"]], dtype=float)
    corner_x, corner_y = transformer.transform(corner_lon, corner_lat)
    _teach(
        "projected bbox half-widths before snapping are %.3f m east-west and %.3f m north-south",
        float(np.max(np.abs(corner_x))),
        float(np.max(np.abs(corner_y))),
    )

    # SpritzMet grids are center-based. Expand symmetrically to the next exact
    # dx/dy multiple so the requested geographic box is covered conservatively.
    half_x = math.ceil(float(np.max(np.abs(corner_x))) / args.dx) * args.dx
    half_y = math.ceil(float(np.max(np.abs(corner_y))) / args.dy) * args.dy
    nx = int(round((2.0 * half_x) / args.dx)) + 1
    ny = int(round((2.0 * half_y) / args.dy)) + 1
    _teach(
        "snapping outward preserves dx/dy exactly; adjusted half-widths are %.3f m and %.3f m",
        half_x,
        half_y,
    )
    LOGGER.info(
        "bbox mode: requested south=%s north=%s west=%s east=%s; adjusted grid center=(%s, %s), nx=%s, ny=%s",
        bounds["south"],
        bounds["north"],
        bounds["west"],
        bounds["east"],
        center_lat,
        center_lon,
        nx,
        ny,
    )
    return center_lat, center_lon, nx, ny, bounds


def _actual_bounds(met: spritzmet.LocalMeteorology) -> dict[str, float]:
    return {
        "south": float(np.min(met.latitude)),
        "north": float(np.max(met.latitude)),
        "west": float(np.min(met.longitude)),
        "east": float(np.max(met.longitude)),
    }


def _parse_vertical_levels_m(value: str | list[float] | list[int] | tuple[float, ...] | None) -> list[float] | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        levels = [float(part) for part in value]
        return _validate_vertical_levels_m(levels)
    normalized = value.strip().lower()
    if normalized in {"usecase01", "usecase01-exponential", "default", "exp"}:
        raise ValueError(
            "the usecase01-exponential preset was replaced by "
            "usecases/01_high_resolution_wind_field/demo/config.json; pass --config with that file"
        )
    parts = [part.strip() for part in value.replace(";", ",").split(",") if part.strip()]
    if not parts:
        raise ValueError("vertical levels must be a comma-separated list of positive heights above sea level")
    try:
        levels = [float(part) for part in parts]
    except ValueError as exc:
        raise ValueError("vertical levels must contain numeric heights in metres") from exc
    return _validate_vertical_levels_m(levels)


def _validate_vertical_levels_m(levels: list[float]) -> list[float]:
    if not levels:
        raise ValueError("vertical levels must contain at least one height")
    if any(level <= 0.0 for level in levels):
        raise ValueError("vertical levels must be positive metres above sea level")
    if any(next_level <= level for level, next_level in zip(levels, levels[1:])):
        raise ValueError("vertical levels must be strictly increasing")
    return levels


def _with_vertical_level_metadata(
    wrf: spritzwrf.WRFWindField,
    vertical_levels_m: list[float] | None,
) -> spritzwrf.WRFWindField:
    metadata = dict(wrf.metadata or {})
    if vertical_levels_m is None:
        # Streaming selects one time at a time. Preserve the remaining leading
        # axis as vertical levels explicitly so SpritzMet does not interpret a
        # level,y,x slice as time,y,x.
        if metadata.get("level_index") == "all" and metadata.get("time_index") != "all":
            u = np.asarray(wrf.u, dtype=float)
            v = np.asarray(wrf.v, dtype=float)
            if u.ndim == 3 and v.ndim == 3:
                return spritzwrf.WRFWindField(
                    wrf.latitude, wrf.longitude, u[np.newaxis, ...], v[np.newaxis, ...],
                    wrf.source_path, time_index=wrf.time_index, metadata=metadata,
                    precipitation_rate=wrf.precipitation_rate, u10m=wrf.u10m, v10m=wrf.v10m,
                    temperature_2m_c=wrf.temperature_2m_c,
                    relative_humidity_2m=wrf.relative_humidity_2m,
                )
        return wrf
    u = _expand_or_remap_wind(wrf.u, vertical_levels_m, "u", metadata)
    v = _expand_or_remap_wind(wrf.v, vertical_levels_m, "v", metadata)
    metadata["level_meters"] = [float(level) for level in vertical_levels_m]
    metadata["level_meters_source"] = "usecase01_command_line"
    metadata["level_meters_kind"] = "height_above_sea_level"
    if np.asarray(wrf.u).shape != np.asarray(u).shape:
        metadata.setdefault("vertical_level_expansion", "single_near_surface_level_repeated")
    return spritzwrf.WRFWindField(
        wrf.latitude,
        wrf.longitude,
        u,
        v,
        wrf.source_path,
        time_index=wrf.time_index,
        metadata=metadata,
        precipitation_rate=wrf.precipitation_rate,
        u10m=wrf.u10m,
        v10m=wrf.v10m,
        temperature_2m_c=wrf.temperature_2m_c,
        relative_humidity_2m=wrf.relative_humidity_2m,
    )


def _metadata_float_list(metadata: dict[str, Any], key: str) -> list[float]:
    value = metadata.get(key)
    if isinstance(value, (list, tuple)):
        return [float(item) for item in value]
    return []


def _linear_vertical_remap(
    values: np.ndarray,
    source_levels_m: list[float],
    target_levels_m: list[float],
    *,
    field_name: str,
) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    source = np.asarray(source_levels_m, dtype=float)
    target = np.asarray(target_levels_m, dtype=float)
    if arr.ndim not in {3, 4}:
        raise ValueError(f"{field_name} must be shaped as level,y,x or time,level,y,x for vertical remapping")
    if source.size != arr.shape[-3]:
        raise ValueError(
            f"level_meters contains {source.size} source heights, but {field_name} has {arr.shape[-3]} vertical levels"
        )
    order = np.argsort(source)
    source = source[order]
    sorted_arr = np.take(arr, order, axis=-3)
    if np.any(np.diff(source) <= 0.0):
        raise ValueError("WRF level_meters must be distinct for vertical remapping")
    if source.size == 1:
        return np.broadcast_to(sorted_arr, (*sorted_arr.shape[:-3], target.size, *sorted_arr.shape[-2:])).copy()

    # Each requested didactic height is evaluated independently.  Values below
    # the first WRF mass level or above the top level use the nearest two WRF
    # levels as a transparent linear extrapolation instead of silently repeating
    # a diagnostic surface field.
    out = np.empty((*sorted_arr.shape[:-3], target.size, *sorted_arr.shape[-2:]), dtype=float)
    for target_i, target_level in enumerate(target):
        upper = int(np.searchsorted(source, target_level, side="right"))
        if upper <= 0:
            lower, upper = 0, 1
        elif upper >= source.size:
            lower, upper = source.size - 2, source.size - 1
        else:
            lower = upper - 1
        fraction = (float(target_level) - float(source[lower])) / (float(source[upper]) - float(source[lower]))
        out[..., target_i, :, :] = sorted_arr[..., lower, :, :] + fraction * (
            sorted_arr[..., upper, :, :] - sorted_arr[..., lower, :, :]
        )
    return out


def _expand_or_remap_wind(
    values: np.ndarray,
    vertical_levels_m: list[float],
    field_name: str,
    metadata: dict[str, Any],
) -> np.ndarray:
    """Fit WRF wind levels to the didactic height grid."""
    arr = np.asarray(values, dtype=float)
    nz = len(vertical_levels_m)
    if arr.ndim == 2:
        return np.broadcast_to(arr[np.newaxis, np.newaxis, :, :], (1, nz, *arr.shape)).copy()
    if arr.ndim == 3:
        if metadata.get("level_index") == "all" and metadata.get("time_index") != "all":
            if arr.shape[0] == nz:
                return arr[np.newaxis, :, :, :]
            if arr.shape[0] == 1:
                return np.broadcast_to(arr[np.newaxis, :, :, :], (1, nz, *arr.shape[-2:])).copy()
            raise ValueError(
                f"--field-z-levels contains {nz} heights, but {field_name} has {arr.shape[0]} WRF levels"
            )
        return np.broadcast_to(arr[:, np.newaxis, :, :], (arr.shape[0], nz, *arr.shape[-2:])).copy()
    if arr.ndim == 4:
        if arr.shape[1] == 1:
            return np.broadcast_to(arr, (arr.shape[0], nz, *arr.shape[-2:])).copy()
        if arr.shape[1] == nz:
            return arr
        source_levels = _metadata_float_list(metadata, "level_meters")
        if source_levels and len(source_levels) == arr.shape[1]:
            metadata["vertical_level_remapping"] = "linear_interpolation_from_wrf_levels"
            source_min = min(source_levels)
            source_max = max(source_levels)
            if vertical_levels_m[0] < source_min or vertical_levels_m[-1] > source_max:
                metadata["vertical_level_extrapolation"] = "linear_boundary_extrapolation"
            return _linear_vertical_remap(arr, source_levels, vertical_levels_m, field_name=field_name)
    raise ValueError(
        f"--field-z-levels contains {nz} heights, but {field_name} has shape {arr.shape}; "
        "use matching WRF levels, WRF level_meters metadata, or load a single near-surface level"
    )


def _synthetic_wrf(center_lat: float, center_lon: float, nx: int = 7, ny: int = 7) -> spritzwrf.WRFWindField:
    """Create a deterministic WRF-like field for tests and classroom demos."""
    lat_axis = center_lat + (np.arange(ny) - (ny - 1) / 2.0) * 0.009
    lon_axis = center_lon + (np.arange(nx) - (nx - 1) / 2.0) * 0.012
    lon, lat = np.meshgrid(lon_axis, lat_axis)
    u = 3.5 + 0.4 * np.sin(np.deg2rad((lat - center_lat) * 100.0))
    v = 1.2 + 0.3 * np.cos(np.deg2rad((lon - center_lon) * 100.0))
    temperature_2m_c = 18.0 - 0.03 * (lat - center_lat) * 100.0 + 0.02 * (lon - center_lon) * 100.0
    relative_humidity_2m = np.clip(0.62 + 0.04 * np.sin(np.deg2rad((lon - center_lon) * 120.0)), 0.0, 1.0)
    return spritzwrf.WRFWindField(
        lat,
        lon,
        u,
        v,
        Path("synthetic-wrf5-d03"),
        metadata={"synthetic": True, "time_index": "0", "level_index": "0"},
        temperature_2m_c=temperature_2m_c,
        relative_humidity_2m=relative_humidity_2m,
    )


def _require_cf_valid_time_for_netcdf(wrf: spritzwrf.WRFWindField, *, prefer_netcdf: bool) -> None:
    if not prefer_netcdf:
        return
    if wrf.metadata and wrf.metadata.get("time_datetime"):
        return
    raise ValueError(
        "NetCDF output requires WRF valid-time metadata from SpritzWRF. "
        "Provide a WRF file with Times, CF time units, or explicit global time attributes; "
        "Sprtz does not infer scientific datetimes from filenames."
    )


def _wrf_filename(timestamp) -> str:
    return f"wrf5_d03_{timestamp.strftime('%Y%m%dZ%H%M')}.nc"


def _local_hourly_wrf_path(download_dir: str | Path, timestamp) -> Path | None:
    root = Path(download_dir)
    candidates = [
        root / _wrf_filename(timestamp),
        root / "d03" / _wrf_filename(timestamp),
    ]
    for candidate in candidates:
        if candidate.exists() and spritzwrf.readable_netcdf(candidate):
            return candidate
        if candidate.exists():
            LOGGER.warning("step 1/4 input: ignoring unreadable WRF file %s", candidate)
    return None


def _resolve_hourly_wrf_inputs(args: argparse.Namespace) -> list[Path] | None:
    if args.date is None:
        return None
    if args.hours < 1:
        raise ValueError("--hours must be at least 1")
    start = parse_script_datetime(args.date)
    paths: list[Path] = []
    for offset in range(args.hours):
        timestamp = start + timedelta(hours=offset)
        local = _local_hourly_wrf_path(args.download_dir, timestamp)
        if local is not None:
            LOGGER.info("step 1/4 input: reusing hourly WRF file %s", local)
            paths.append(local)
            continue
        LOGGER.info("step 1/4 input: downloading hourly WRF file for %s", timestamp.strftime("%Y%m%dZ%H%M"))
        paths.append(
            spritzwrf.download_meteo_uniparthenope_wrf(
                args.download_dir,
                run_date=timestamp.date().isoformat(),
                cycle_hour=timestamp.hour,
                timeout_s=args.download_timeout_s,
                force=args.force_download,
            )
        )
    return paths


def _resolve_wrf_input(args: argparse.Namespace, download_date: str | None, download_cycle_hour: int) -> Path | None:
    """Step 1: choose the local WRF source or invoke SpritzWRF's downloader."""
    if args.wrf is not None:
        if args.date is not None:
            raise ValueError("--wrf and --date are mutually exclusive")
        wrf_path = Path(args.wrf)
        LOGGER.info("step 1/4 input: using local WRF file %s", wrf_path)
        _teach("a local WRF file makes this workflow reproducible without network access")
        return wrf_path
    if download_date is None:
        LOGGER.info("step 1/4 input: no WRF file requested")
        _teach("without WRF input, only --allow-synthetic can continue; that path is for demos and tests")
        return None

    LOGGER.info("step 1/4 input: spritzwrf.download_meteo_uniparthenope_wrf")
    _teach(
        "SpritzWRF owns WRF acquisition details; the use case only selects the UTC cycle %sZ%02d00",
        download_date,
        download_cycle_hour,
    )
    return spritzwrf.download_meteo_uniparthenope_wrf(
        args.download_dir,
        run_date=download_date,
        cycle_hour=download_cycle_hour,
        timeout_s=args.download_timeout_s,
        force=args.force_download,
    )


def _load_wrf_sequence(
    wrf_paths: list[Path],
    *,
    time_index: int | None,
    level_index: int | None,
    vertical_levels_m: list[float] | None = None,
) -> list[spritzwrf.WRFWindField]:
    fields: list[spritzwrf.WRFWindField] = []
    for wrf_path in wrf_paths:
        LOGGER.info("step 2/4 SpritzWRF: loading hourly WRF file %s", wrf_path)
        wrf = spritzwrf.load_near_surface_wind(wrf_path, time_index=time_index, level_index=level_index)
        fields.append(_with_vertical_level_metadata(wrf, vertical_levels_m))
    return fields


def _combine_local_meteorology(items: list[spritzmet.LocalMeteorology]) -> spritzmet.LocalMeteorology:
    if not items:
        raise ValueError("at least one local meteorology field is required")
    first = items[0]
    u = np.concatenate([item.wind_4d[0] for item in items], axis=0)
    v = np.concatenate([item.wind_4d[1] for item in items], axis=0)
    precipitation = np.concatenate([item.precipitation_3d for item in items], axis=0)
    wind_10m_items = [item.wind_10m_3d for item in items]
    u10m = None
    v10m = None
    if all(wind_10m is not None for wind_10m in wind_10m_items):
        u10m = np.concatenate([wind_10m[0] for wind_10m in wind_10m_items if wind_10m is not None], axis=0)
        v10m = np.concatenate([wind_10m[1] for wind_10m in wind_10m_items if wind_10m is not None], axis=0)
    temperature_items = [item.temperature_2m_3d for item in items]
    temperature_2m_c = None
    if all(values is not None for values in temperature_items):
        temperature_2m_c = np.concatenate([values for values in temperature_items if values is not None], axis=0)
    humidity_items = [item.relative_humidity_2m_3d for item in items]
    relative_humidity_2m = None
    if all(values is not None for values in humidity_items):
        relative_humidity_2m = np.concatenate([values for values in humidity_items if values is not None], axis=0)
    datetimes: list[str] = []
    for item in items:
        if item.valid_datetimes_utc:
            datetimes.extend(item.valid_datetimes_utc)
        elif item.valid_datetime_utc:
            datetimes.append(item.valid_datetime_utc)
    return spritzmet.LocalMeteorology(
        first.x,
        first.y,
        first.latitude,
        first.longitude,
        u,
        v,
        precipitation,
        first.center_lat,
        first.center_lon,
        first.dx_m,
        first.dy_m,
        ";".join(item.source for item in items),
        valid_datetime_utc=datetimes[0] if datetimes else first.valid_datetime_utc,
        valid_datetimes_utc=datetimes or None,
        downscaling_metadata=first.downscaling_metadata,
        u10m=u10m,
        v10m=v10m,
        temperature_2m_c=temperature_2m_c,
        relative_humidity_2m=relative_humidity_2m,
    )


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _interpolate_frames(
    earlier: spritzmet.LocalMeteorology,
    later: spritzmet.LocalMeteorology,
    interval_s: float,
) -> list[spritzmet.LocalMeteorology]:
    """Return temporal frames after ``earlier`` through and including ``later``."""
    if interval_s <= 0.0:
        raise ValueError("--temporal-resolution-s must be positive")
    if not earlier.valid_datetime_utc or not later.valid_datetime_utc:
        raise ValueError("temporal downscaling requires absolute UTC valid times on every input frame")
    start = _parse_utc(earlier.valid_datetime_utc)
    stop = _parse_utc(later.valid_datetime_utc)
    span_s = (stop - start).total_seconds()
    if span_s <= 0.0:
        raise ValueError("WRF valid times must be strictly increasing for temporal downscaling")
    offsets = list(np.arange(interval_s, span_s, interval_s, dtype=float)) + [span_s]

    def blend(a: np.ndarray | None, b: np.ndarray | None, fraction: float) -> np.ndarray | None:
        if a is None or b is None:
            return None
        return np.asarray(a, dtype=float) + fraction * (np.asarray(b, dtype=float) - np.asarray(a, dtype=float))

    result: list[spritzmet.LocalMeteorology] = []
    for offset_s in offsets:
        fraction = offset_s / span_s
        valid = (start + timedelta(seconds=float(offset_s))).isoformat().replace("+00:00", "Z")
        metadata = dict(later.downscaling_metadata or {})
        metadata.update({
            "temporal_downscaling": "linear",
            "temporal_resolution_seconds": float(interval_s),
            "temporal_source_interval_seconds": float(span_s),
        })
        result.append(spritzmet.LocalMeteorology(
            later.x, later.y, later.latitude, later.longitude,
            blend(earlier.wind_4d[0], later.wind_4d[0], fraction),
            blend(earlier.wind_4d[1], later.wind_4d[1], fraction),
            blend(earlier.precipitation_3d, later.precipitation_3d, fraction),
            later.center_lat, later.center_lon, later.dx_m, later.dy_m, later.source,
            valid_datetime_utc=valid, valid_datetimes_utc=[valid],
            downscaling_metadata=metadata,
            u10m=blend(earlier.u10m, later.u10m, fraction),
            v10m=blend(earlier.v10m, later.v10m, fraction),
            temperature_2m_c=blend(earlier.temperature_2m_c, later.temperature_2m_c, fraction),
            relative_humidity_2m=blend(earlier.relative_humidity_2m, later.relative_humidity_2m, fraction),
        ))
    return result


def _load_wrf_field(
    wrf_path: Path | None,
    *,
    time_index: int | None,
    level_index: int | None,
    vertical_levels_m: list[float] | None,
    allow_synthetic: bool,
    center_lat: float,
    center_lon: float,
) -> spritzwrf.WRFWindField:
    """Step 2: invoke SpritzWRF extraction or create the documented demo field."""
    if wrf_path is not None and wrf_path.exists():
        LOGGER.info("step 2/4 SpritzWRF: spritzwrf.load_near_surface_wind")
        _teach("SpritzWRF converts WRF/WRF-like variables into a clean WRFWindField object")
        wrf = _with_vertical_level_metadata(
            spritzwrf.load_near_surface_wind(wrf_path, time_index=time_index, level_index=level_index),
            vertical_levels_m,
        )
        _teach(
            "loaded WRF field shape=%s, time_index=%s, level_index=%s, precipitation=%s",
            wrf.u.shape,
            wrf.metadata.get("time_index") if wrf.metadata else time_index,
            wrf.metadata.get("level_index") if wrf.metadata else level_index,
            "available" if wrf.precipitation_rate is not None else "not available",
        )
        return wrf
    if allow_synthetic:
        LOGGER.info("step 2/4 SpritzWRF: using deterministic synthetic WRF-like demo field")
        _teach("the synthetic field exercises the same SpritzMet path, but it is not meteorological evidence")
        wrf = _with_vertical_level_metadata(_synthetic_wrf(center_lat, center_lon), vertical_levels_m)
        _teach("synthetic WRF-like field shape=%s centered near (%.6f, %.6f)", wrf.u.shape, center_lat, center_lon)
        return wrf
    raise FileNotFoundError(
        "WRF input file is required. Pass --wrf, use --date YYYYMMDDZhhmm --hours N, "
        "or use --download-time YYYYMMDDZhhmm, "
        "or enable --allow-synthetic for tests."
    )




def run_workflow(
    args: argparse.Namespace,
    download_date: str | None,
    download_cycle_hour: int,
    *,
    component: str = "usecase.01_high_resolution_wind_field",
) -> WindDownscalingResult:
    """Run the use-case orchestration, keeping production module calls explicit."""
    configure_logging(False)
    if args.advanced_physics:
        if not math.isfinite(args.bulk_richardson_number):
            raise ValueError("--bulk-richardson-number must be finite")
        if args.mass_consistency_iterations < 0:
            raise ValueError("--mass-consistency-iterations must be non-negative")
        if not 0.0 < args.mass_consistency_relaxation <= 1.0:
            raise ValueError("--mass-consistency-relaxation must be in (0, 1]")
    _teach("this script is scenario orchestration; numerical work stays in sprtz.models.spritzwrf and sprtz.models.spritzmet")
    center_lat, center_lon, nx, ny, requested_bounds = _resolve_grid(args)
    vertical_levels_m = _parse_vertical_levels_m(args.field_z_levels)
    if vertical_levels_m is not None:
        _teach(
            "vertical levels are set on the command line as metres above sea level; first=%.3f m, count=%s",
            vertical_levels_m[0],
            len(vertical_levels_m),
        )
    _check_local_raster_dependencies(args.dem, args.land_cover)

    mpi_ctx = get_mpi_context(args.parallel)
    # Rank 0 alone resolves/downloads and inspects shared inputs.  The compact
    # path/index schedule is broadcast; field arrays are loaded one frame at a
    # time later in the processing loop.
    wrf_paths = _resolve_hourly_wrf_inputs(args) if mpi_ctx.is_root else None
    if mpi_ctx.is_root and wrf_paths is None:
        wrf_path = _resolve_wrf_input(args, download_date, download_cycle_hour)
        wrf_paths = [wrf_path] if wrf_path is not None else []
    wrf_paths = mpi_ctx.bcast(wrf_paths)
    if wrf_paths:
        if args.time_index is None:
            frame_specs = [
                (path, index)
                for path in wrf_paths
                for index in range(spritzwrf.wrf_time_count(path))
            ] if mpi_ctx.is_root else None
        else:
            frame_specs = [(path, args.time_index) for path in wrf_paths] if mpi_ctx.is_root else None
        frame_specs = mpi_ctx.bcast(frame_specs)
    else:
        frame_specs = [(None, 0)]

    terrain_inputs = spritzmet.terrain_downscaling_inputs_from_rasters(
        center_lat=center_lat, center_lon=center_lon, nx=nx, ny=ny,
        dx_m=args.dx, dy_m=args.dy, dem_path=args.dem,
        land_cover_path=args.land_cover, allow_outside_raster=args.allow_synthetic,
    ) if mpi_ctx.is_root else None
    dem_elevation_m, land_cover, terrain_metadata = mpi_ctx.bcast(terrain_inputs)
    if dem_elevation_m is not None or land_cover is not None:
        _teach(
            "terrain-aware SpritzMet downscaling is enabled: DEM=%s, land-cover=%s",
            args.dem or "not supplied",
            args.land_cover or "not supplied",
        )
    station_measurements = None
    if args.station_measurements is not None and mpi_ctx.is_root:
        station_measurements = spritzmet.read_station_measurements_csv(
            args.station_measurements,
            center_lat=center_lat,
            center_lon=center_lon,
        )
        _teach(
            "station-measurement improvement is enabled from %s with %s observations",
            args.station_measurements,
            len(station_measurements),
        )
    station_measurements = mpi_ctx.bcast(station_measurements)

    LOGGER.info("step 3/4 SpritzMet: spritzmet.downscale_wrf_to_local_grid")
    _teach(
        "SpritzMet will build an azimuthal-equidistant local grid: center=(%.6f, %.6f), nx=%s, ny=%s, dx=%.3f m, dy=%.3f m",
        center_lat,
        center_lon,
        nx,
        ny,
        args.dx,
        args.dy,
    )
    physics_options = None
    if args.advanced_physics:
        physics_options = {
            "wind": {
                "stability": {
                    "bulk_richardson_number": args.bulk_richardson_number,
                },
                "mass_consistency": {
                    "iterations": args.mass_consistency_iterations,
                    "relaxation": args.mass_consistency_relaxation,
                },
            }
        }
        _teach(
            "optional advanced wind physics is enabled: bounded bulk-Richardson scaling Ri=%.3f "
            "followed by %s divergence-minimization iterations at relaxation %.3f",
            args.bulk_richardson_number,
            args.mass_consistency_iterations,
            args.mass_consistency_relaxation,
        )
    met_items: list[spritzmet.LocalMeteorology] = []
    fmt = "NetCDF-CF" if not args.json else "json"
    previous_frame: spritzmet.LocalMeteorology | None = None
    for frame_index, (wrf_path, source_time_index) in enumerate(frame_specs):
        wrf = None
        if mpi_ctx.is_root:
            wrf = _load_wrf_field(
                wrf_path, time_index=source_time_index, level_index=args.level_index,
                vertical_levels_m=vertical_levels_m, allow_synthetic=args.allow_synthetic,
                center_lat=center_lat, center_lon=center_lon,
            )
            _require_cf_valid_time_for_netcdf(wrf, prefer_netcdf=not args.json)
        wrf = mpi_ctx.bcast(wrf)
        frame = spritzmet.downscale_wrf_to_local_grid(
            wrf,
            center_lat=center_lat,
            center_lon=center_lon,
            nx=nx,
            ny=ny,
            dx_m=args.dx,
            dy_m=args.dy,
            dem_elevation_m=dem_elevation_m,
            land_cover=land_cover,
            terrain_input_metadata=terrain_metadata,
            downscaling_mode=args.downscaling_mode,
            station_measurements=station_measurements,
            parallel=args.parallel,
            physics_options=physics_options,
        )
        if mpi_ctx.is_root:
            new_frames = (
                _interpolate_frames(previous_frame, frame, args.temporal_resolution_s)
                if previous_frame is not None and args.temporal_resolution_s is not None
                else [frame]
            )
            met_items.extend(new_frames)
            previous_frame = frame
        # Persist every completed time frame. Rewriting the accumulated product
        # keeps the on-disk file CF-valid and readable if a later frame fails.
        # In MPI runs every rank computes and gathers, but only rank 0 writes
        # the shared output.
        if mpi_ctx.is_root:
            partial_met = _combine_local_meteorology(met_items) if len(met_items) > 1 else frame
            fmt = spritzmet.write_local_meteorology(
                args.output,
                partial_met,
                prefer_netcdf=not args.json,
            )
            LOGGER.info(
                "step 4/4 output: persisted completed time frame %s/%s to %s",
                frame_index + 1,
                len(frame_specs),
                args.output,
            )
    if not mpi_ctx.is_root:
        return WindDownscalingResult(Path(args.output), nx, ny, args.dx, args.dy, center_lat, center_lon, "mpi-rank-local", fmt, component=component)
    met = _combine_local_meteorology(met_items) if len(met_items) > 1 else met_items[0]
    finite_wind_speed = np.asarray(met.wind_speed)[np.isfinite(met.wind_speed)]
    if finite_wind_speed.size:
        _teach(
            "downscaled output wind has shape=%s after NetCDF expansion; finite derived wind speed min/max are %.3f/%.3f m s-1",
            met.wind_4d[0].shape,
            float(np.min(finite_wind_speed)),
            float(np.max(finite_wind_speed)),
        )
    else:
        LOGGER.warning(
            "downscaled output wind has shape=%s but contains no finite wind-speed values",
            met.wind_4d[0].shape,
        )
    actual_bounds = _actual_bounds(met) if requested_bounds is not None else None
    if requested_bounds is not None and actual_bounds is not None:
        _teach(
            "actual grid bounds conservatively cover the request: south=%.6f north=%.6f west=%.6f east=%.6f",
            actual_bounds["south"],
            actual_bounds["north"],
            actual_bounds["west"],
            actual_bounds["east"],
        )

    _teach("strict NetCDF-CF is preferred for interchange; --json selects the lightweight JSON fallback")
    if mpi_ctx.is_root:
        _teach("wrote %s output to %s", fmt, args.output)
    if args.calmet_dat is not None:
        calmet_fmt = spritzmet.write_calmet_dat(args.calmet_dat, met)
        _teach("wrote %s binary evaluation output to %s", calmet_fmt, args.calmet_dat)
    return WindDownscalingResult(
        Path(args.output),
        nx,
        ny,
        args.dx,
        args.dy,
        center_lat,
        center_lon,
        met.source,
        fmt,
        component=component,
        requested_bounds=requested_bounds,
        actual_bounds=actual_bounds,
    )


def build_parser(description: str | None = None) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=description
        or "Use case 01: SpritzWRF -> SpritzMet downscaling from WRF 1 km winds to a 100 m local grid"
    )
    parser.add_argument("--config", default=None, help="optional shared JSON configuration; CLI options override matching values")
    parser.add_argument("--wrf", default=None, help="Local WRF NetCDF input; omit when using --date, --download-time, or --allow-synthetic")
    parser.add_argument("--date", default=None, help="Start UTC timestamp as YYYYMMDDZhhmm for hourly WRF sequence mode")
    parser.add_argument("--hours", type=int, default=1, help="Number of hourly WRF files to downscale when --date is used")
    parser.add_argument("--download-time", default=None, help="Download meteo@uniparthenope WRF5 d03 file for UTC YYYYMMDDZhhmm")
    parser.add_argument("--download-dir", default="data/wrf", help="Directory for downloaded WRF files")
    parser.add_argument("--download-timeout-s", type=float, default=120.0)
    parser.add_argument("--force-download", action="store_true")
    parser.add_argument("--print-download-url", action="store_true", help="Print the meteo@uniparthenope URL and exit")
    parser.add_argument("--output", default=None)
    parser.add_argument("--center-lat", type=float, default=None)
    parser.add_argument("--center-lon", type=float, default=None)
    parser.add_argument("--south", type=float, default=None, help="Southern latitude for conservative bounding-box mode")
    parser.add_argument("--north", type=float, default=None, help="Northern latitude for conservative bounding-box mode")
    parser.add_argument("--west", type=float, default=None, help="Western longitude for conservative bounding-box mode")
    parser.add_argument("--east", type=float, default=None, help="Eastern longitude for conservative bounding-box mode")
    parser.add_argument("--nx", type=int, default=101)
    parser.add_argument("--ny", type=int, default=101)
    parser.add_argument("--dx", type=float, default=100.0)
    parser.add_argument("--dy", type=float, default=100.0)
    parser.add_argument("--time-index", type=int, default=None, help="time index for WRF variables; omit to downscale all times")
    parser.add_argument(
        "--temporal-resolution-s", type=float, default=None,
        help="Optional output cadence in seconds (for example 900 for 15-minute linear temporal downscaling)",
    )
    parser.add_argument("--level-index", type=int, default=None, help="vertical level index for 4D WRF wind variables; omit to downscale all levels")
    parser.add_argument(
        "--field-z-levels",
        default=None,
        help=(
            "Comma-separated vertical heights above sea level in metres. "
            "Use --config usecases/01_high_resolution_wind_field/demo/config.json for the documented ASL levels. "
            "A single loaded WRF wind level is repeated onto this didactic z grid; "
            "multi-level WRF input must already match the requested height count."
        ),
    )
    parser.add_argument("--dem", default=None, help="Optional DEM raster for terrain-aware SpritzMet downscaling, e.g. data/dem/cop30_naples.tif")
    parser.add_argument("--land-cover", "--landuse", dest="land_cover", default=None, help="Optional categorical land-cover raster, e.g. data/landcover/lc100_naples.tif")
    parser.add_argument("--downscaling-mode", choices=["deterministic", "ai", "diffusion"], default="deterministic")
    parser.add_argument(
        "--advanced-physics",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Enable optional bounded stability scaling and horizontal divergence minimization",
    )
    parser.add_argument(
        "--bulk-richardson-number",
        type=float,
        default=0.0,
        help="Representative bulk Richardson number used by --advanced-physics",
    )
    parser.add_argument(
        "--mass-consistency-iterations",
        type=int,
        default=80,
        help="Jacobi projection iterations used by --advanced-physics",
    )
    parser.add_argument(
        "--mass-consistency-relaxation",
        type=float,
        default=0.8,
        help="Projection relaxation in (0,1] used by --advanced-physics",
    )
    parser.add_argument("--parallel", choices=["serial", "auto", "mpi"], default="serial", help="parallel execution mode for SpritzMet WRF downscaling")
    parser.add_argument("--thread-backend", choices=["serial", "threads", "processes", "auto"], default="serial", help="rank-local shared-memory backend")
    parser.add_argument("--threads-per-rank", type=int, default=None, help="rank-local worker count")
    parser.add_argument("--gpu-backend", choices=["numpy", "auto", "cupy", "cuda", "mlx", "metal"], default="numpy", help="optional array accelerator backend")
    parser.add_argument(
        "--decomposition",
        choices=["auto", "rows", "tiles", "receptors", "sources", "particles", "realizations"],
        default="auto",
        help="preferred work decomposition strategy",
    )
    parser.add_argument(
        "--station-measurements",
        default=None,
        help="Optional CSV weather-station residual observations with x,y or latitude,longitude plus wind_speed/wind_dir and/or precipitation_rate",
    )
    parser.add_argument("--json", action="store_true", help="write JSON even when netCDF4 is available")
    parser.add_argument("--calmet-dat", default=None, help="Optional CALMET.DAT-compatible binary output for model-evaluation workflows")
    parser.add_argument("--allow-synthetic", action="store_true")
    return parser


def main(
    argv: list[str] | None = None,
    *,
    description: str | None = None,
    component: str = "usecase.01_high_resolution_wind_field",
) -> int:
    parser = build_parser(description)
    config_parser = argparse.ArgumentParser(add_help=False)
    config_parser.add_argument("--config", default=None)
    config_args, _ = config_parser.parse_known_args(argv)
    if config_args.config:
        parser.set_defaults(**config_defaults(config_args.config, sections=("run", "domain", "terrain", "spritzmet")))
    args = parser.parse_args(argv)
    if args.output is None:
        parser.error("--output is required unless provided by --config")
    parallel_ctx = get_parallel_context(args.parallel, args.thread_backend, args.threads_per_rank, args.gpu_backend)
    LOGGER.debug(
        "parallel context: mpi_size=%s thread_backend=%s threads_per_rank=%s gpu_backend=%s decomposition=%s",
        parallel_ctx.mpi.size,
        parallel_ctx.threads.mode,
        parallel_ctx.threads.workers,
        parallel_ctx.gpu.backend,
        args.decomposition,
    )

    download_date = None
    download_cycle_hour = 0
    if args.download_time is not None:
        download_date, download_cycle_hour = script_datetime_to_date_and_hour(args.download_time)

    if args.print_download_url:
        if download_date is None:
            parser.error("--print-download-url requires --download-time")
        configure_logging(False)
        LOGGER.info("%s", spritzwrf.meteo_uniparthenope_wrf_url(download_date, download_cycle_hour))
        return 0

    try:
        result = run_workflow(args, download_date, download_cycle_hour, component=component)
    except UseCaseDependencyError as exc:
        parser.error(str(exc))
    LOGGER.info("%s", result.as_dict())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

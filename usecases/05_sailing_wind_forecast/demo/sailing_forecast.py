from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
from pyproj import Geod

from sprtz.io.jsonio import write_json
from sprtz.io.netcdf_cf import write_cf_time_coordinate
from sprtz.logging import configure_logging

COMMON_DIR = Path(__file__).resolve().parents[2] / "common"
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))

from datetime_args import parse_script_datetime
from plotting import add_plot_argument, plot_netcdf_if_available

LOGGER = logging.getLogger(__name__)
BAY_OF_NAPLES_RACE_BOX = (14.18, 40.78, 14.33, 40.85)
DEFAULT_OUTLOOK_H = 24.0
DEFAULT_HORIZONTAL_RESOLUTION_M = 100.0
DEFAULT_VERTICAL_RESOLUTION_M = 10.0
DEFAULT_TIME_RESOLUTION_S = 600.0
DEFAULT_MAX_POINTS = 60_000_000


@dataclass(frozen=True)
class SailingForecastRequest:
    initialization_date: date
    outlook_h: float
    bbox: tuple[float, float, float, float]
    horizontal_resolution_m: float
    vertical_resolution_m: float
    time_resolution_s: float
    top_altitude_m: float = 300.0
    application: str = "precision top class professional sporting sailing"

    @property
    def initialization_utc(self) -> datetime:
        return datetime.combine(self.initialization_date, time(0, 0), tzinfo=timezone.utc)


def parse_bbox(value: str) -> tuple[float, float, float, float]:
    parts = [float(part.strip()) for part in value.split(",")]
    if len(parts) != 4:
        raise ValueError("bbox must be west,south,east,north")
    west, south, east, north = parts
    if east <= west or north <= south:
        raise ValueError("bbox must satisfy east > west and north > south")
    return west, south, east, north


def _grid_axes(request: SailingForecastRequest) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    west, south, east, north = request.bbox
    geod = Geod(ellps="WGS84")
    mid_lat = 0.5 * (south + north)
    mid_lon = 0.5 * (west + east)
    width_m = geod.inv(west, mid_lat, east, mid_lat)[2]
    height_m = geod.inv(mid_lon, south, mid_lon, north)[2]
    nx = max(2, int(np.floor(width_m / request.horizontal_resolution_m)) + 1)
    ny = max(2, int(np.floor(height_m / request.horizontal_resolution_m)) + 1)
    nz = max(1, int(np.floor(request.top_altitude_m / request.vertical_resolution_m)) + 1)
    nt = max(1, int(np.floor(request.outlook_h * 3600.0 / request.time_resolution_s)) + 1)
    lon_axis = np.linspace(west, east, nx, dtype=float)
    lat_axis = np.linspace(south, north, ny, dtype=float)
    z_axis = np.arange(nz, dtype=float) * request.vertical_resolution_m
    time_axis = np.arange(nt, dtype=float) * request.time_resolution_s
    return lon_axis, lat_axis, z_axis, time_axis


def _validate_request(request: SailingForecastRequest, *, max_points: int) -> None:
    if request.outlook_h <= 0:
        raise ValueError("outlook_h must be positive")
    if request.horizontal_resolution_m <= 0 or request.vertical_resolution_m <= 0:
        raise ValueError("horizontal and vertical resolutions must be positive")
    if request.time_resolution_s <= 0:
        raise ValueError("time_resolution_s must be positive")
    lon, lat, z, t = _grid_axes(request)
    points = lon.size * lat.size * z.size * t.size
    if points > max_points:
        raise ValueError(
            f"forecast grid would contain {points} points; increase --max-points or use a "
            "smaller bbox/outlook/resolution for this lightweight JSON use case"
        )


def build_sailing_forecast(
    request: SailingForecastRequest,
    output_path: str | Path,
    *,
    max_points: int = DEFAULT_MAX_POINTS,
    make_plot: bool = False,
) -> dict[str, Any]:
    """Build a deterministic high-resolution wind forecast product for sailing.

    This use case is forecast-ready orchestration, not a substitute for ingesting
    an authoritative operational forecast. The synthetic wind field encodes
    stable spatial gradients, sea-breeze-like diurnal turning, and vertical shear
    so race-strategy tooling can exercise the complete grid/time/height schema
    offline before project-specific forecast data are plugged in.
    """
    _validate_request(request, max_points=max_points)
    lon_axis, lat_axis, z_axis, time_axis = _grid_axes(request)
    lon2, lat2 = np.meshgrid(lon_axis, lat_axis)
    center_lon = 0.5 * (request.bbox[0] + request.bbox[2])
    center_lat = 0.5 * (request.bbox[1] + request.bbox[3])
    u = np.empty((time_axis.size, z_axis.size, lat_axis.size, lon_axis.size), dtype=float)
    v = np.empty_like(u)
    gust = np.empty_like(u)
    for ti, seconds in enumerate(time_axis):
        phase = 2.0 * np.pi * seconds / 86400.0
        sea_breeze = 1.2 * np.sin(phase - 0.5)
        for zi, height in enumerate(z_axis):
            shear = 1.0 + 0.08 * np.log1p(height / 10.0)
            spatial = 0.35 * np.sin((lon2 - center_lon) * 40.0) + 0.25 * np.cos((lat2 - center_lat) * 55.0)
            u[ti, zi] = shear * (3.8 + sea_breeze + spatial)
            v[ti, zi] = shear * (1.1 + 0.5 * np.cos(phase) - 0.15 * (lat2 - center_lat) * 100.0)
            gust[ti, zi] = np.hypot(u[ti, zi], v[ti, zi]) * (1.18 + 0.03 * zi)
    speed = np.hypot(u, v)
    wind_from = (270.0 - np.rad2deg(np.arctan2(v, u))) % 360.0
    payload = {
        "component": "usecase.sailing_wind_forecast",
        "application": request.application,
        "initialization_utc": request.initialization_utc.isoformat().replace("+00:00", "Z"),
        "outlook_h": request.outlook_h,
        "bbox": {
            "west": request.bbox[0],
            "south": request.bbox[1],
            "east": request.bbox[2],
            "north": request.bbox[3],
        },
        "horizontal_resolution_m": request.horizontal_resolution_m,
        "vertical_resolution_m": request.vertical_resolution_m,
        "time_resolution_s": request.time_resolution_s,
        "longitude": lon_axis.tolist(),
        "latitude": lat_axis.tolist(),
        "height_m": z_axis.tolist(),
        "valid_time_s": time_axis.tolist(),
        "eastward_wind": np.round(u, 4).tolist(),
        "northward_wind": np.round(v, 4).tolist(),
        "wind_speed": np.round(speed, 4).tolist(),
        "wind_from_direction": np.round(wind_from, 3).tolist(),
        "gust_speed": np.round(gust, 4).tolist(),
        "metadata": {
            "workflow": "high-resolution sailing wind forecast",
            "target": "Bay of Naples professional sailing race planning",
            "synthetic": True,
            "network_access": False,
            "notes": (
                "Replace the synthetic field with an authoritative forecast provider "
                "before operational race decisions."
            ),
        },
    }
    write_json(output_path, payload)
    sidecar = write_sailing_netcdf_if_available(payload, Path(output_path).with_suffix(".nc"))
    if sidecar is not None:
        payload["netcdf_path"] = str(sidecar)
        if make_plot:
            plot_path = plot_netcdf_if_available(
                sidecar,
                Path(output_path).with_name(Path(output_path).stem + "_wind_speed_map.png"),
                variable="wind_speed",
                title="Sailing Forecast Surface Wind Speed",
            )
            if plot_path is not None:
                payload["plot_path"] = str(plot_path)
        write_json(output_path, payload)
    return payload


def write_sailing_netcdf_if_available(payload: dict[str, Any], output_path: str | Path) -> Path | None:
    try:
        from netCDF4 import Dataset  # type: ignore
    except Exception:
        LOGGER.warning("netCDF4 is unavailable; skipping sailing forecast NetCDF sidecar")
        return None
    lon = np.asarray(payload["longitude"], dtype=float)
    lat = np.asarray(payload["latitude"], dtype=float)
    height = np.asarray(payload["height_m"], dtype=float)
    valid_time = np.asarray(payload["valid_time_s"], dtype=float)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with Dataset(out, "w") as ds:
        ds.createDimension("time", valid_time.size)
        ds.createDimension("z", height.size)
        ds.createDimension("y", lat.size)
        ds.createDimension("x", lon.size)
        ds.Conventions = "CF-1.8"
        ds.title = "Sprtz sailing wind forecast"
        init_dt = datetime.fromisoformat(str(payload["initialization_utc"]).replace("Z", "+00:00"))
        write_cf_time_coordinate(
            ds,
            [
                (init_dt + timedelta(seconds=float(seconds))).isoformat().replace("+00:00", "Z")
                for seconds in valid_time
            ],
        )
        for name, values, dims, units in [
            ("z", height, ("z",), "m"),
            ("latitude", lat, ("y",), "degrees_north"),
            ("longitude", lon, ("x",), "degrees_east"),
        ]:
            var = ds.createVariable(name, "f8", dims)
            var.units = units
            if name == "z":
                var.standard_name = "height"
                var.long_name = "height above sea level"
                var.positive = "up"
            var[:] = values
        for name, units in [
            ("eastward_wind", "m s-1"),
            ("northward_wind", "m s-1"),
            ("wind_speed", "m s-1"),
            ("wind_from_direction", "degree"),
            ("gust_speed", "m s-1"),
        ]:
            var = ds.createVariable(name, "f8", ("time", "z", "y", "x"), zlib=True)
            var.units = units
            var[:, :, :, :] = np.asarray(payload[name], dtype=float)
    return out


def default_initialization_date() -> date:
    return datetime.now(timezone.utc).date()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a high-resolution sailing wind forecast product")
    parser.add_argument("--initialization-time", default=None, help="UTC initialization datetime as YYYYMMDDZhhmm; defaults to current UTC day at Z00")
    parser.add_argument("--outlook-hours", type=float, default=DEFAULT_OUTLOOK_H)
    parser.add_argument("--bbox", default=",".join(str(v) for v in BAY_OF_NAPLES_RACE_BOX), help="west,south,east,north")
    parser.add_argument("--horizontal-resolution-m", type=float, default=DEFAULT_HORIZONTAL_RESOLUTION_M)
    parser.add_argument("--vertical-resolution-m", type=float, default=DEFAULT_VERTICAL_RESOLUTION_M)
    parser.add_argument("--time-resolution-s", type=float, default=DEFAULT_TIME_RESOLUTION_S)
    parser.add_argument("--top-altitude-m", type=float, default=300.0)
    parser.add_argument("--max-points", type=int, default=DEFAULT_MAX_POINTS)
    parser.add_argument("--output", required=True)
    add_plot_argument(parser)
    args = parser.parse_args(argv)
    init_date = (
        default_initialization_date()
        if args.initialization_time is None
        else parse_script_datetime(args.initialization_time).date()
    )
    request = SailingForecastRequest(
        initialization_date=init_date,
        outlook_h=args.outlook_hours,
        bbox=parse_bbox(args.bbox),
        horizontal_resolution_m=args.horizontal_resolution_m,
        vertical_resolution_m=args.vertical_resolution_m,
        time_resolution_s=args.time_resolution_s,
        top_altitude_m=args.top_altitude_m,
    )
    payload = build_sailing_forecast(request, args.output, max_points=args.max_points, make_plot=args.plot)
    configure_logging(False)
    LOGGER.info(
        "%s",
        {
            "output": args.output,
            "initialization_utc": payload["initialization_utc"],
            "shape": [
                len(payload["valid_time_s"]),
                len(payload["height_m"]),
                len(payload["latitude"]),
                len(payload["longitude"]),
            ],
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

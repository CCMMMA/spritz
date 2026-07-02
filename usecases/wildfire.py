from __future__ import annotations

import logging

import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
from pyproj import CRS, Transformer

from sprtz.config import from_mapping, parse_field_z_levels
from sprtz.io.jsonio import read_json, write_json
from high_resolution_wind import downscale_wrf_to_100m
from sprtz.workflow import run_workflow
from sprtz.logging import configure_logging
from datetime_args import script_datetime_to_iso
from plotting import plot_netcdf_if_available, plot_workflow_netcdfs


LOGGER = logging.getLogger(__name__)


def _center_value(values: Any, *, level_index: int = 0) -> float:
    arr = np.asarray(values, dtype=float)
    if arr.ndim == 4:
        arr = arr[0, min(max(level_index, 0), arr.shape[1] - 1), :, :]
    elif arr.ndim == 3:
        arr = arr[0, :, :]
    if arr.ndim != 2:
        raise ValueError(f"expected a 2D, 3D, or 4D field, got shape {arr.shape}")
    cy = arr.shape[0] // 2
    cx = arr.shape[1] // 2
    return float(arr[cy, cx])

BURNING_MATERIALS: dict[str, dict[str, float]] = {
    "generic": {
        "temperature_k": 1000.0,
        "emission_factor_g_m2": 25.0,
        "heat_flux_offset_w_m2": 100.0,
    },
    "paper": {
        "temperature_k": 873.15,
        "emission_factor_g_m2": 18.0,
        "heat_flux_offset_w_m2": 80.0,
    },
    "plastic": {
        "temperature_k": 1123.15,
        "emission_factor_g_m2": 60.0,
        "heat_flux_offset_w_m2": 150.0,
    },
}

@dataclass(frozen=True)
class WildfireRunResult:
    config_path: Path
    output_dir: Path
    workflow: dict[str, Any]
    heat_release_w: float
    emission_rate_g_s: float
    plots: dict[str, str]
    calmet_dat_path: Path | None = None

    def as_dict(self) -> dict[str, Any]:
        result = {
            "component": "usecase.wildfire_arson",
            "config_path": str(self.config_path),
            "output_dir": str(self.output_dir),
            "workflow": self.workflow,
            "heat_release_w": self.heat_release_w,
            "emission_rate_g_s": self.emission_rate_g_s,
            "plots": self.plots,
        }
        if self.calmet_dat_path is not None:
            result["calmet_dat_path"] = str(self.calmet_dat_path)
        return result


def material_properties(material: str) -> dict[str, float]:
    try:
        return BURNING_MATERIALS[material.lower()]
    except KeyError as exc:
        raise ValueError("material must be one of generic, paper, plastic") from exc


def _parse_iso(value: str | None) -> datetime | None:
    if value is None:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


def _end_from_start(start: str | None, duration_s: float) -> str | None:
    parsed = _parse_iso(start)
    if parsed is None:
        return None
    return (parsed + timedelta(seconds=float(duration_s))).isoformat()


def _local_transformer(center_lat: float, center_lon: float) -> Transformer:
    local = CRS.from_proj4(
        f"+proj=aeqd +lat_0={center_lat:.12f} +lon_0={center_lon:.12f} "
        "+datum=WGS84 +units=m +no_defs"
    )
    return Transformer.from_crs(CRS.from_epsg(4326), local, always_xy=True)


def _local_to_wgs84(center_lat: float, center_lon: float, x: float, y: float) -> tuple[float, float]:
    local = CRS.from_proj4(
        f"+proj=aeqd +lat_0={center_lat:.12f} +lon_0={center_lon:.12f} "
        "+datum=WGS84 +units=m +no_defs"
    )
    transformer = Transformer.from_crs(local, CRS.from_epsg(4326), always_xy=True)
    lon, lat = transformer.transform(x, y)
    return float(lat), float(lon)


def ensure_wildfire_receptor_coordinates(config_path: str | Path) -> bool:
    """Add receptor latitude/longitude to older wildfire configs when possible."""
    path = Path(config_path)
    config = read_json(path)
    receptors = config.get("receptors")
    metadata = config.get("metadata", {})
    if not isinstance(receptors, list) or not receptors:
        return False
    if all("latitude" in receptor and "longitude" in receptor for receptor in receptors):
        return False
    if "center_lat" not in metadata or "center_lon" not in metadata:
        return False
    center_lat = float(metadata["center_lat"])
    center_lon = float(metadata["center_lon"])
    changed = False
    for receptor in receptors:
        if not isinstance(receptor, dict):
            continue
        if "latitude" in receptor and "longitude" in receptor:
            continue
        if "x" not in receptor or "y" not in receptor:
            continue
        lat, lon = _local_to_wgs84(center_lat, center_lon, float(receptor["x"]), float(receptor["y"]))
        receptor["latitude"] = lat
        receptor["longitude"] = lon
        changed = True
    if changed:
        from_mapping(config).validate()
        write_json(path, config)
    return changed


def _load_fire_events(value: str | None) -> list[dict[str, Any]] | None:
    if not value:
        return None
    text = value.strip()
    if text.startswith("["):
        payload = json.loads(text)
    else:
        payload = json.loads(Path(text).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("--fire-events-json must contain a JSON list")
    normalized: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("--fire-events-json entries must be JSON objects")
        event = dict(item)
        for key in ("start_datetime", "end_datetime"):
            if key in event and event[key] is not None:
                event[key] = script_datetime_to_iso(str(event[key]))
        normalized.append(event)
    return normalized


def estimate_heat_release_w(
    burning_temperature_k: float,
    burning_area_m2: float,
    duration_s: float,
    *,
    material: str = "generic",
) -> float:
    """Screening heat-release estimate for scenario definition.

    This is not a fuel-specific combustion model. It creates a consistent
    buoyancy proxy from user-provided burning temperature, area, and duration so
    the Spritz source can be parameterized before a detailed fuel inventory is
    available.
    """
    ambient_k = 293.15
    delta_t = max(0.0, burning_temperature_k - ambient_k)
    area = max(1.0, burning_area_m2)
    duration = max(60.0, duration_s)
    properties = material_properties(material)
    # Effective convective heat-flux scale W/m2. Kept conservative for screening.
    heat_flux = 5.0 * delta_t + properties["heat_flux_offset_w_m2"]
    return heat_flux * area * min(1.0, duration / 3600.0)


def estimate_pm_emission_rate_g_s(burning_area_m2: float, duration_s: float, emission_factor_g_m2: float = 25.0) -> float:
    """Estimate particulate emission rate from burned area and duration."""
    duration = max(60.0, duration_s)
    return max(0.0, burning_area_m2) * max(0.0, emission_factor_g_m2) / duration


def build_wildfire_config(
    output_path: str | Path,
    *,
    center_lat: float,
    center_lon: float,
    burning_lat: float | None = None,
    burning_lon: float | None = None,
    burning_temperature_k: float | None = None,
    burning_material: str = "generic",
    burning_start: str | None = None,
    burning_end: str | None = None,
    burning_duration_s: float = 3600.0,
    burning_area_m2: float = 2500.0,
    emission_factor_g_m2: float | None = None,
    source_height_agl_m: float = 0.0,
    fire_events: list[dict[str, Any]] | None = None,
    weather_start: str | None = None,
    weather_end: str | None = None,
    firefighters_start: str | None = None,
    firefighters_end: str | None = None,
    firefighters_emission_factor: float = 1.0,
    precipitation_washout: bool = False,
    precipitation_rate_mm_h: float = 0.0,
    receptor_radius_m: float = 2500.0,
    receptor_spacing_m: float = 500.0,
    wind_speed_m_s: float = 4.0,
    wind_from_direction_deg: float = 270.0,
    grid_cells: int = 101,
    grid_spacing_m: float = 100.0,
    field_z_levels: Any = None,
) -> dict[str, Any]:
    """Create a Spritz config for one or more arson/wildfire release events."""
    burn_lat = center_lat if burning_lat is None else burning_lat
    burn_lon = center_lon if burning_lon is None else burning_lon
    material = burning_material.lower()
    properties = material_properties(material)
    temperature_k = (
        properties["temperature_k"] if burning_temperature_k is None else burning_temperature_k
    )
    factor = (
        properties["emission_factor_g_m2"]
        if emission_factor_g_m2 is None
        else emission_factor_g_m2
    )
    event_end = burning_end or _end_from_start(burning_start, burning_duration_s)
    if fire_events is None:
        fire_events = [
            {
                "id": "FIRE001",
                "latitude": burn_lat,
                "longitude": burn_lon,
                "height_agl_m": source_height_agl_m,
                "start_datetime": burning_start,
                "end_datetime": event_end,
                "duration_s": burning_duration_s,
                "area_m2": burning_area_m2,
                "material": material,
                "temperature_k": temperature_k,
                "emission_factor_g_m2": factor,
            }
        ]
    x0 = -((grid_cells - 1) / 2.0) * grid_spacing_m
    y0 = x0
    concentration_field_z_levels = list(
        parse_field_z_levels([1.5] if field_z_levels is None else field_z_levels)
    )
    theta = math.radians(270.0 - wind_from_direction_deg)
    station_speed = max(0.1, wind_speed_m_s)
    transformer = _local_transformer(center_lat, center_lon)
    sources: list[dict[str, Any]] = []
    event_metadata: list[dict[str, Any]] = []
    for index, event in enumerate(fire_events, start=1):
        event_material = str(event.get("material", material)).lower()
        event_properties = material_properties(event_material)
        event_temperature = float(event.get("temperature_k", event_properties["temperature_k"]))
        event_duration = float(event.get("duration_s", burning_duration_s))
        event_area = float(event.get("area_m2", burning_area_m2))
        event_factor = float(event.get("emission_factor_g_m2", event_properties["emission_factor_g_m2"]))
        event_lat = float(event.get("latitude", burn_lat))
        event_lon = float(event.get("longitude", burn_lon))
        event_height = float(event.get("height_agl_m", event.get("chimney_height_m", source_height_agl_m)))
        event_start = event.get("start_datetime", burning_start)
        event_finish = event.get("end_datetime", event_end or _end_from_start(event_start, event_duration))
        x, y = transformer.transform(event_lon, event_lat)
        heat_release = estimate_heat_release_w(
            event_temperature,
            event_area,
            event_duration,
            material=event_material,
        )
        emission_rate = estimate_pm_emission_rate_g_s(event_area, event_duration, event_factor)
        source_id = str(event.get("id", f"FIRE{index:03d}"))
        sources.append(
            {
                "id": source_id,
                "x": float(x),
                "y": float(y),
                "z": 0.0,
                "latitude": event_lat,
                "longitude": event_lon,
                "source_type": "area",
                "material": event_material,
                "width": math.sqrt(max(1.0, event_area)),
                "length": math.sqrt(max(1.0, event_area)),
                "height": 3.0,
                "height_agl_m": event_height,
                "stack_height": event_height,
                "start_datetime": event_start,
                "end_datetime": event_finish,
                "exit_temperature": event_temperature,
                "heat_release": heat_release,
                "emission_rate": emission_rate,
                "deposition_velocity": 0.005,
                "wet_scavenging": 0.0,
                "decay_rate": 0.0,
                "settling_velocity": 0.01,
            }
        )
        event_metadata.append(
            {
                "id": source_id,
                "latitude": event_lat,
                "longitude": event_lon,
                "height_agl_m": event_height,
                "start_datetime": event_start,
                "end_datetime": event_finish,
                "material": event_material,
                "temperature_k": event_temperature,
                "area_m2": event_area,
                "emission_rate_g_s": emission_rate,
                "heat_release_w": heat_release,
            }
        )
    receptors: list[dict[str, Any]] = []
    n = int((2.0 * receptor_radius_m) // receptor_spacing_m) + 1
    start = -receptor_radius_m
    for iy in range(n):
        for ix in range(n):
            x = start + ix * receptor_spacing_m
            y = start + iy * receptor_spacing_m
            if math.hypot(x, y) <= receptor_radius_m:
                lat, lon = _local_to_wgs84(center_lat, center_lon, x, y)
                receptors.append(
                    {
                        "id": f"R{len(receptors):04d}",
                        "x": x,
                        "y": y,
                        "z": 1.5,
                        "latitude": lat,
                        "longitude": lon,
                    }
                )
    config = {
        "metadata": {
            "title": "Spritz arson/wildfire screening scenario",
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "center_lat": center_lat,
            "center_lon": center_lon,
            "burning_lat": burn_lat,
            "burning_lon": burn_lon,
            "burning_start": burning_start,
            "burning_end": event_end,
            "burning_duration_s": burning_duration_s,
            "burning_material": material,
            "fire_events": event_metadata,
            "note": "Screening use case; calibrate with fuel inventory and observations before operational decisions.",
        },
        "grid": {
            "nx": grid_cells,
            "ny": grid_cells,
            "dx": grid_spacing_m,
            "dy": grid_spacing_m,
            "x0": x0,
            "y0": y0,
            "projection": f"AEQD centered at {center_lat},{center_lon}",
        },
        "stations": [
            {
                "id": "WRF_LOCAL",
                "x": 0.0,
                "y": 0.0,
                "wind_speed": station_speed,
                "wind_dir": wind_from_direction_deg,
                "temperature": 293.15,
                "mixing_height": 1200.0,
                "precipitation_rate": max(0.0, precipitation_rate_mm_h),
            }
        ],
        "sources": sources,
        "receptors": receptors,
        "run": {
            "stability": "D",
            "numerical_mode": "puff",
            "averaging_time_s": burning_duration_s,
            "output_interval_s": 3600.0,
            "concentration_output": "both",
            "field_z_levels": concentration_field_z_levels,
            "weather_start_datetime": weather_start or burning_start,
            "weather_end_datetime": weather_end or event_end,
            "event_start_datetime": burning_start,
            "event_end_datetime": event_end,
            "firefighters_start_datetime": firefighters_start,
            "firefighters_end_datetime": firefighters_end,
            "firefighters_emission_factor": firefighters_emission_factor,
            "precipitation_washout": precipitation_washout,
            "default_precipitation_rate": max(0.0, precipitation_rate_mm_h),
            "threshold": 0.0,
            "event_type": "wildfire_or_arson",
            "wind_u_m_s": station_speed * math.cos(theta),
            "wind_v_m_s": station_speed * math.sin(theta),
        },
    }
    from_mapping(config).validate()
    write_json(output_path, config)
    return config


def run_wildfire_event(
    output_dir: str | Path,
    *,
    wrf_path: str | Path | None = None,
    center_lat: float,
    center_lon: float,
    burning_temperature_k: float | None,
    burning_material: str = "generic",
    burning_start: str | None = None,
    burning_end: str | None = None,
    burning_duration_s: float = 3600.0,
    burning_area_m2: float = 2500.0,
    source_height_agl_m: float = 0.0,
    fire_events: list[dict[str, Any]] | None = None,
    weather_start: str | None = None,
    weather_end: str | None = None,
    firefighters_start: str | None = None,
    firefighters_end: str | None = None,
    firefighters_emission_factor: float = 1.0,
    precipitation_washout: bool = False,
    backend: str = "particles",
    interchange: str = "netcdf",
    allow_synthetic_wrf: bool = False,
    download_time: str | None = None,
    download_date: str | None = None,
    download_cycle_hour: int = 0,
    download_dir: str | Path = "data/wrf",
    force_download: bool = False,
    dem_path: str | Path | None = None,
    land_cover_path: str | Path | None = None,
    calmet_dat_path: str | Path | None = "CALMET.DAT",
) -> WildfireRunResult:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    wind_out = out / ("wrf_100m_wind.nc" if interchange == "netcdf" else "wrf_100m_wind.json")
    calmet_out = None
    if calmet_dat_path is not None:
        raw_calmet = Path(calmet_dat_path)
        calmet_out = raw_calmet if raw_calmet.is_absolute() else out / raw_calmet
    wind_result = downscale_wrf_to_100m(
        wrf_path,
        wind_out,
        center_lat=center_lat,
        center_lon=center_lon,
        allow_synthetic=allow_synthetic_wrf,
        prefer_netcdf=interchange == "netcdf",
        download_time=download_time,
        download_date=download_date,
        download_cycle_hour=download_cycle_hour,
        download_dir=download_dir,
        force_download=force_download,
        dem_path=dem_path,
        land_cover_path=land_cover_path,
        calmet_dat_path=calmet_out,
    )
    plots: dict[str, str] = {}
    wind_plot = plot_netcdf_if_available(
        wind_out,
        out / "wrf_100m_wind_map.png",
        variable="wind_speed",
        title="Intermediate SpritzMet Wind Speed",
        center_lat=center_lat,
        center_lon=center_lon,
    )
    if wind_plot is not None:
        plots["wind"] = str(wind_plot)
    # Use center-cell wind as representative source wind for the screening config.
    if wind_result.format == "json":
        data = json.loads(wind_out.read_text(encoding="utf-8"))
        wind_speed = _center_value(data["wind_speed"])
        wind_dir = _center_value(data["wind_from_direction"])
        precipitation_rate = _center_value(data.get("precipitation_rate", [[0.0]]))
    else:
        try:
            from netCDF4 import Dataset  # type: ignore

            with Dataset(wind_out) as ds:
                wind_speed = _center_value(ds.variables["wind_speed"][:])
                wind_dir = _center_value(ds.variables["wind_from_direction"][:])
                if "precipitation_rate" in ds.variables:
                    precipitation_rate = _center_value(ds.variables["precipitation_rate"][:])
                else:
                    precipitation_rate = 0.0
        except Exception:
            wind_speed = 4.0
            wind_dir = 270.0
            precipitation_rate = 0.0
    config_path = out / "wildfire_event.json"
    config = build_wildfire_config(
        config_path,
        center_lat=center_lat,
        center_lon=center_lon,
        burning_temperature_k=burning_temperature_k,
        burning_material=burning_material,
        burning_start=burning_start,
        burning_end=burning_end,
        burning_duration_s=burning_duration_s,
        burning_area_m2=burning_area_m2,
        source_height_agl_m=source_height_agl_m,
        fire_events=fire_events,
        weather_start=weather_start,
        weather_end=weather_end,
        firefighters_start=firefighters_start,
        firefighters_end=firefighters_end,
        firefighters_emission_factor=firefighters_emission_factor,
        precipitation_washout=precipitation_washout,
        precipitation_rate_mm_h=precipitation_rate,
        wind_speed_m_s=wind_speed,
        wind_from_direction_deg=wind_dir,
    )
    workflow = run_workflow(config_path, out / "model", backend=backend, interchange=interchange, parallel="serial")
    plots.update(
        plot_workflow_netcdfs(
            workflow,
            out,
            center_lat=center_lat,
            center_lon=center_lon,
            prefix="model_",
        )
    )
    heat_release = sum(float(source["heat_release"]) for source in config["sources"])
    emission_rate = sum(float(source["emission_rate"]) for source in config["sources"])
    return WildfireRunResult(
        config_path,
        out,
        workflow,
        heat_release,
        emission_rate,
        plots,
        wind_result.calmet_dat_path,
    )


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run a Spritz arson/wildfire screening use case")
    parser.add_argument("--wrf", default=None, help="Local WRF NetCDF input; omit when using --download-time")
    parser.add_argument("--download-time", default=None, help="Download WRF5 d03 data from meteo@uniparthenope for UTC YYYYMMDDZhhmm")
    parser.add_argument("--download-dir", default="data/wrf")
    parser.add_argument("--force-download", action="store_true")
    parser.add_argument("--dem", default=None, help="Optional DEM raster for terrain-aware SpritzMet wind/precipitation downscaling")
    parser.add_argument("--land-cover", "--landuse", dest="land_cover", default=None, help="Optional categorical land-cover raster for terrain-aware SpritzMet downscaling")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--center-lat", type=float, required=True)
    parser.add_argument("--center-lon", type=float, required=True)
    parser.add_argument("--temperature-k", type=float, default=None)
    parser.add_argument("--material", choices=sorted(BURNING_MATERIALS), default="generic")
    parser.add_argument("--start", default=None, help="UTC fire/arson start datetime as YYYYMMDDZhhmm")
    parser.add_argument("--end", default=None, help="UTC fire/arson end datetime as YYYYMMDDZhhmm")
    parser.add_argument("--duration-s", type=float, default=3600.0)
    parser.add_argument("--area-m2", type=float, default=2500.0)
    parser.add_argument("--height-agl-m", type=float, default=0.0)
    parser.add_argument("--fire-events-json", default=None, help="JSON list of multi-fire event objects")
    parser.add_argument("--weather-start", default=None, help="UTC weather start datetime as YYYYMMDDZhhmm")
    parser.add_argument("--weather-end", default=None, help="UTC weather end datetime as YYYYMMDDZhhmm")
    parser.add_argument("--firefighters-start", default=None, help="UTC firefighter-action start datetime as YYYYMMDDZhhmm")
    parser.add_argument("--firefighters-end", default=None, help="UTC firefighter-action end datetime as YYYYMMDDZhhmm")
    parser.add_argument("--firefighters-emission-factor", type=float, default=1.0)
    parser.add_argument("--precipitation-washout", action="store_true")
    parser.add_argument("--backend", choices=["gaussian", "particles"], default="particles")
    parser.add_argument("--interchange", choices=["json", "netcdf"], default="netcdf")
    parser.add_argument("--calmet-dat", default="CALMET.DAT", help="CALMET.DAT-compatible binary output path, relative to --output-dir unless absolute")
    parser.add_argument("--no-calmet-dat", action="store_true", help="Do not write CALMET.DAT-compatible meteorology for model evaluation")
    parser.add_argument("--allow-synthetic-wrf", action="store_true")
    args = parser.parse_args(argv)
    fire_events = _load_fire_events(args.fire_events_json)
    result = run_wildfire_event(
        args.output_dir,
        wrf_path=args.wrf,
        center_lat=args.center_lat,
        center_lon=args.center_lon,
        burning_temperature_k=args.temperature_k,
        burning_material=args.material,
        burning_start=script_datetime_to_iso(args.start),
        burning_end=script_datetime_to_iso(args.end),
        burning_duration_s=args.duration_s,
        burning_area_m2=args.area_m2,
        source_height_agl_m=args.height_agl_m,
        fire_events=fire_events,
        weather_start=script_datetime_to_iso(args.weather_start),
        weather_end=script_datetime_to_iso(args.weather_end),
        firefighters_start=script_datetime_to_iso(args.firefighters_start),
        firefighters_end=script_datetime_to_iso(args.firefighters_end),
        firefighters_emission_factor=args.firefighters_emission_factor,
        precipitation_washout=args.precipitation_washout,
        backend=args.backend,
        interchange=args.interchange,
        allow_synthetic_wrf=args.allow_synthetic_wrf,
        download_time=args.download_time,
        download_dir=args.download_dir,
        force_download=args.force_download,
        dem_path=args.dem,
        land_cover_path=args.land_cover,
        calmet_dat_path=None if args.no_calmet_dat else args.calmet_dat,
    )
    configure_logging(False)
    LOGGER.info("%s", result.as_dict())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

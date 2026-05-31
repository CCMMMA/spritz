from __future__ import annotations

import logging

import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sprtz.config import from_mapping
from sprtz.io.jsonio import write_json
from high_resolution_wind import interpolate_wrf_to_100m
from sprtz.workflow import run_workflow
from sprtz.logging import configure_logging


LOGGER = logging.getLogger(__name__)

@dataclass(frozen=True)
class WildfireRunResult:
    config_path: Path
    output_dir: Path
    workflow: dict[str, Any]
    heat_release_w: float
    emission_rate_g_s: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "component": "usecase.wildfire_arson",
            "config_path": str(self.config_path),
            "output_dir": str(self.output_dir),
            "workflow": self.workflow,
            "heat_release_w": self.heat_release_w,
            "emission_rate_g_s": self.emission_rate_g_s,
        }


def estimate_heat_release_w(burning_temperature_k: float, burning_area_m2: float, duration_s: float) -> float:
    """Screening heat-release estimate for scenario definition.

    This is not a fuel-specific combustion model. It creates a consistent
    buoyancy proxy from user-provided burning temperature, area, and duration so
    the Sprtz source can be parameterized before a detailed fuel inventory is
    available.
    """
    ambient_k = 293.15
    delta_t = max(0.0, burning_temperature_k - ambient_k)
    area = max(1.0, burning_area_m2)
    duration = max(60.0, duration_s)
    # Effective convective heat-flux scale W/m2. Kept conservative for screening.
    heat_flux = 5.0 * delta_t + 100.0
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
    burning_temperature_k: float = 1100.0,
    burning_start: str | None = None,
    burning_duration_s: float = 3600.0,
    burning_area_m2: float = 2500.0,
    emission_factor_g_m2: float = 25.0,
    receptor_radius_m: float = 2500.0,
    receptor_spacing_m: float = 500.0,
    wind_speed_m_s: float = 4.0,
    wind_from_direction_deg: float = 270.0,
    grid_cells: int = 101,
    grid_spacing_m: float = 100.0,
) -> dict[str, Any]:
    """Create a Sprtz config for an arson/wildfire release scenario."""
    burn_lat = center_lat if burning_lat is None else burning_lat
    burn_lon = center_lon if burning_lon is None else burning_lon
    # Use the burn point as local origin. For small wildfire/arson domains this
    # avoids depending on an external projection in the scenario config.
    x0 = -((grid_cells - 1) / 2.0) * grid_spacing_m
    y0 = x0
    heat_release = estimate_heat_release_w(burning_temperature_k, burning_area_m2, burning_duration_s)
    emission_rate = estimate_pm_emission_rate_g_s(burning_area_m2, burning_duration_s, emission_factor_g_m2)
    theta = math.radians(270.0 - wind_from_direction_deg)
    station_speed = max(0.1, wind_speed_m_s)
    receptors: list[dict[str, Any]] = []
    n = int((2.0 * receptor_radius_m) // receptor_spacing_m) + 1
    start = -receptor_radius_m
    for iy in range(n):
        for ix in range(n):
            x = start + ix * receptor_spacing_m
            y = start + iy * receptor_spacing_m
            if math.hypot(x, y) <= receptor_radius_m:
                receptors.append({"id": f"R{len(receptors):04d}", "x": x, "y": y, "z": 1.5})
    config = {
        "metadata": {
            "title": "Sprtz arson/wildfire screening scenario",
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "center_lat": center_lat,
            "center_lon": center_lon,
            "burning_lat": burn_lat,
            "burning_lon": burn_lon,
            "burning_start": burning_start,
            "burning_duration_s": burning_duration_s,
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
            }
        ],
        "sources": [
            {
                "id": "FIRE001",
                "x": 0.0,
                "y": 0.0,
                "z": 0.0,
                "source_type": "area",
                "width": math.sqrt(max(1.0, burning_area_m2)),
                "length": math.sqrt(max(1.0, burning_area_m2)),
                "height": 3.0,
                "stack_height": 0.0,
                "exit_temperature": burning_temperature_k,
                "heat_release": heat_release,
                "emission_rate": emission_rate,
                "deposition_velocity": 0.005,
                "wet_scavenging": 0.0,
                "decay_rate": 0.0,
                "settling_velocity": 0.01,
            }
        ],
        "receptors": receptors,
        "run": {
            "stability": "D",
            "numerical_mode": "puff",
            "averaging_time_s": burning_duration_s,
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
    burning_temperature_k: float,
    burning_start: str | None = None,
    burning_duration_s: float = 3600.0,
    burning_area_m2: float = 2500.0,
    backend: str = "particles",
    interchange: str = "netcdf",
    allow_synthetic_wrf: bool = False,
    download_date: str | None = None,
    download_cycle_hour: int = 0,
    download_dir: str | Path = "data/wrf",
    force_download: bool = False,
) -> WildfireRunResult:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    wind_out = out / ("wrf_100m_wind.nc" if interchange == "netcdf" else "wrf_100m_wind.json")
    wind_result = interpolate_wrf_to_100m(
        wrf_path,
        wind_out,
        center_lat=center_lat,
        center_lon=center_lon,
        allow_synthetic=allow_synthetic_wrf,
        prefer_netcdf=interchange == "netcdf",
        download_date=download_date,
        download_cycle_hour=download_cycle_hour,
        download_dir=download_dir,
        force_download=force_download,
    )
    # Use center-cell wind as representative source wind for the screening config.
    if wind_result.format == "json":
        data = json.loads(wind_out.read_text(encoding="utf-8"))
        cy = len(data["wind_speed"]) // 2
        cx = len(data["wind_speed"][0]) // 2
        wind_speed = float(data["wind_speed"][cy][cx])
        wind_dir = float(data["wind_from_direction"][cy][cx])
    else:
        try:
            from netCDF4 import Dataset  # type: ignore

            with Dataset(wind_out) as ds:
                speed = ds.variables["wind_speed"][0]
                direction = ds.variables["wind_from_direction"][0]
                cy = speed.shape[0] // 2
                cx = speed.shape[1] // 2
                wind_speed = float(speed[cy, cx])
                wind_dir = float(direction[cy, cx])
        except Exception:
            wind_speed = 4.0
            wind_dir = 270.0
    config_path = out / "wildfire_event.json"
    config = build_wildfire_config(
        config_path,
        center_lat=center_lat,
        center_lon=center_lon,
        burning_temperature_k=burning_temperature_k,
        burning_start=burning_start,
        burning_duration_s=burning_duration_s,
        burning_area_m2=burning_area_m2,
        wind_speed_m_s=wind_speed,
        wind_from_direction_deg=wind_dir,
    )
    workflow = run_workflow(config_path, out / "model", backend=backend, interchange=interchange, parallel="serial")
    source = config["sources"][0]
    return WildfireRunResult(
        config_path,
        out,
        workflow,
        float(source["heat_release"]),
        float(source["emission_rate"]),
    )


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run a Sprtz arson/wildfire screening use case")
    parser.add_argument("--wrf", default=None, help="Local WRF NetCDF input; omit when using --download-date")
    parser.add_argument("--download-date", default=None, help="Download WRF5 d03 data from meteo@uniparthenope for YYYY-MM-DD")
    parser.add_argument("--download-cycle-hour", type=int, default=0)
    parser.add_argument("--download-dir", default="data/wrf")
    parser.add_argument("--force-download", action="store_true")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--center-lat", type=float, required=True)
    parser.add_argument("--center-lon", type=float, required=True)
    parser.add_argument("--temperature-k", type=float, required=True)
    parser.add_argument("--start", default=None)
    parser.add_argument("--duration-s", type=float, default=3600.0)
    parser.add_argument("--area-m2", type=float, default=2500.0)
    parser.add_argument("--backend", choices=["gaussian", "particles"], default="particles")
    parser.add_argument("--interchange", choices=["json", "netcdf"], default="netcdf")
    parser.add_argument("--allow-synthetic-wrf", action="store_true")
    args = parser.parse_args(argv)
    result = run_wildfire_event(
        args.output_dir,
        wrf_path=args.wrf,
        center_lat=args.center_lat,
        center_lon=args.center_lon,
        burning_temperature_k=args.temperature_k,
        burning_start=args.start,
        burning_duration_s=args.duration_s,
        burning_area_m2=args.area_m2,
        backend=args.backend,
        interchange=args.interchange,
        allow_synthetic_wrf=args.allow_synthetic_wrf,
        download_date=args.download_date,
        download_cycle_hour=args.download_cycle_hour,
        download_dir=args.download_dir,
        force_download=args.force_download,
    )
    configure_logging(False)
    LOGGER.info("%s", result.as_dict())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

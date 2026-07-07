from __future__ import annotations

import argparse
import logging
import math
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from pyproj import CRS, Transformer

from sprtz.config import from_mapping
from sprtz.io.jsonio import write_json
from sprtz.logging import configure_logging
from sprtz.workflow import run_workflow

COMMON_DIR = Path(__file__).resolve().parents[2] / "common"
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))

from datetime_args import script_datetime_to_iso
from plotting import plot_workflow_netcdfs

LOGGER = logging.getLogger(__name__)

ACERRA_STACK_LAT = 40.978473
ACERRA_STACK_LON = 14.384058
ACERRA_STACK_HEIGHT_M = 110.0
DEFAULT_START = "2026-06-01T00:00:00+00:00"
DEFAULT_DURATION_H = 12.0


@dataclass(frozen=True)
class AcerraRunResult:
    config_path: Path
    output_dir: Path
    workflow: dict[str, Any] | None
    plots: dict[str, str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "component": "usecase.acerra_waste_to_energy",
            "config_path": str(self.config_path),
            "output_dir": str(self.output_dir),
            "workflow": self.workflow,
            "plots": self.plots,
        }


def _local_to_wgs84(center_lat: float, center_lon: float, x: float, y: float) -> tuple[float, float]:
    local = CRS.from_proj4(
        f"+proj=aeqd +lat_0={center_lat:.12f} +lon_0={center_lon:.12f} "
        "+datum=WGS84 +units=m +no_defs"
    )
    transformer = Transformer.from_crs(local, CRS.from_epsg(4326), always_xy=True)
    lon, lat = transformer.transform(x, y)
    return float(lat), float(lon)


def _receptors(radius_m: float, spacing_m: float) -> list[dict[str, Any]]:
    receptors: list[dict[str, Any]] = []
    steps = int((2.0 * radius_m) // spacing_m) + 1
    start = -radius_m
    for iy in range(steps):
        for ix in range(steps):
            x = start + ix * spacing_m
            y = start + iy * spacing_m
            if math.hypot(x, y) > radius_m:
                continue
            lat, lon = _local_to_wgs84(ACERRA_STACK_LAT, ACERRA_STACK_LON, x, y)
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
    return receptors


def build_acerra_config(
    output_path: str | Path,
    *,
    start_datetime: str = DEFAULT_START,
    duration_h: float = DEFAULT_DURATION_H,
    emission_rate_g_s: float = 10.0,
    stack_height_m: float = ACERRA_STACK_HEIGHT_M,
    output_interval_s: float = 3600.0,
    precipitation_washout: bool = True,
    receptor_radius_m: float = 5000.0,
    receptor_spacing_m: float = 500.0,
) -> dict[str, Any]:
    start = datetime.fromisoformat(start_datetime.replace("Z", "+00:00"))
    end = start + timedelta(hours=float(duration_h))
    grid_cells = 121
    grid_spacing = 100.0
    half_width = ((grid_cells - 1) / 2.0) * grid_spacing
    config = {
        "metadata": {
            "title": "Spritz Acerra waste-to-energy 12-hour chimney screening scenario",
            "facility": "Waste-to-energy plant, Acerra",
            "latitude": ACERRA_STACK_LAT,
            "longitude": ACERRA_STACK_LON,
            "scientific_scope": "didactic screening scenario requiring plant-specific validation",
        },
        "grid": {
            "nx": grid_cells,
            "ny": grid_cells,
            "dx": grid_spacing,
            "dy": grid_spacing,
            "x0": -half_width,
            "y0": -half_width,
            "projection": f"AEQD centered at {ACERRA_STACK_LAT},{ACERRA_STACK_LON}",
        },
        "stations": [
            {
                "id": "ACERRA_SCREENING_WIND",
                "x": 0.0,
                "y": 0.0,
                "wind_speed": 4.0,
                "wind_dir": 270.0,
                "temperature": 293.15,
                "mixing_height": 1200.0,
                "precipitation_rate": 0.0,
            }
        ],
        "sources": [
            {
                "id": "ACERRA_WTE_STACK",
                "x": 0.0,
                "y": 0.0,
                "z": 0.0,
                "latitude": ACERRA_STACK_LAT,
                "longitude": ACERRA_STACK_LON,
                "source_type": "point",
                "material": "generic",
                "height_agl_m": stack_height_m,
                "stack_height": stack_height_m,
                "stack_diameter": 2.0,
                "exit_velocity": 15.0,
                "exit_temperature": 420.0,
                "emission_rate": emission_rate_g_s,
                "deposition_velocity": 0.001,
                "wet_scavenging": 0.0,
                "decay_rate": 0.0,
                "settling_velocity": 0.002,
                "start_datetime": start.isoformat(),
                "end_datetime": end.isoformat(),
            }
        ],
        "receptors": _receptors(receptor_radius_m, receptor_spacing_m),
        "run": {
            "backend": "gaussian",
            "stability": "D",
            "numerical_mode": "puff",
            "averaging_time_s": duration_h * 3600.0,
            "output_interval_s": output_interval_s,
            "weather_start_datetime": start.isoformat(),
            "weather_end_datetime": end.isoformat(),
            "event_start_datetime": start.isoformat(),
            "event_end_datetime": end.isoformat(),
            "precipitation_washout": precipitation_washout,
            "precipitation_washout_coefficient_s_per_mm_h": 1.0e-5,
            "default_precipitation_rate": 0.0,
            "threshold": 0.0,
        },
    }
    from_mapping(config).validate()
    write_json(output_path, config)
    return config


def run_acerra_case(
    output_dir: str | Path,
    *,
    interchange: str = "netcdf",
    run_model: bool = True,
    start_datetime: str = DEFAULT_START,
    duration_h: float = DEFAULT_DURATION_H,
    make_plot: bool = False,
) -> AcerraRunResult:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    config_path = out / "acerra_waste_to_energy.json"
    build_acerra_config(config_path, start_datetime=start_datetime, duration_h=duration_h)
    workflow = None
    plots: dict[str, str] = {}
    if run_model:
        workflow = run_workflow(config_path, out / "model", interchange=interchange)
        if make_plot:
            plots = plot_workflow_netcdfs(
                workflow,
                out,
                center_lat=ACERRA_STACK_LAT,
                center_lon=ACERRA_STACK_LON,
            )
    return AcerraRunResult(config_path, out, workflow, plots)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Acerra waste-to-energy chimney use case")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--interchange", choices=["json", "netcdf"], default="netcdf")
    parser.add_argument("--config-only", action="store_true")
    parser.add_argument("--plot", action="store_true", help="also generate maps and profiles after computation")
    parser.add_argument("--start", default=None, help="UTC scenario start datetime as YYYYMMDDZhhmm")
    parser.add_argument("--duration-h", type=float, default=DEFAULT_DURATION_H)
    args = parser.parse_args(argv)
    configure_logging(False)
    result = run_acerra_case(
        args.output_dir,
        interchange=args.interchange,
        run_model=not args.config_only,
        start_datetime=script_datetime_to_iso(args.start) or DEFAULT_START,
        duration_h=args.duration_h,
        make_plot=args.plot,
    )
    LOGGER.info("%s", result.as_dict())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

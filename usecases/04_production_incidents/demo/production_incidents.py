from __future__ import annotations

import argparse
import csv
import logging
import math
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from pyproj import CRS, Transformer

from sprtz.config import from_mapping
from sprtz.io.jsonio import write_json
from sprtz.logging import configure_logging
from sprtz.models import visualization
from sprtz.workflow import run_workflow

COMMON_DIR = Path(__file__).resolve().parents[2] / "common"
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))

from plotting import plot_workflow_netcdfs

LOGGER = logging.getLogger(__name__)
DEFAULT_CATALOG = Path(__file__).resolve().parent / "events.csv"


@dataclass(frozen=True)
class IncidentEvent:
    year: str
    code: str
    place: str
    latitude: float
    longitude: float
    date: str
    start_hour: int
    duration_h: float
    note: str = ""

    @property
    def start_local_iso(self) -> str:
        day = datetime.strptime(self.date, "%d/%m/%Y").date()
        return datetime(day.year, day.month, day.day, self.start_hour).isoformat()

    def as_metadata(self) -> dict[str, Any]:
        return {
            "year": self.year,
            "cod_gisa": self.code,
            "place": self.place,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "date": self.date,
            "start_local": self.start_local_iso,
            "duration_h": self.duration_h,
            "note": self.note,
        }


@dataclass(frozen=True)
class IncidentRunResult:
    event: IncidentEvent
    config_path: Path
    output_dir: Path
    workflow: dict[str, Any] | None
    map_path: Path | None
    plots: dict[str, str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "event": self.event.as_metadata(),
            "config_path": str(self.config_path),
            "output_dir": str(self.output_dir),
            "workflow": self.workflow,
            "map_path": None if self.map_path is None else str(self.map_path),
            "plots": self.plots,
        }


def _decimal(value: str) -> float:
    return float(value.strip().replace(",", "."))


def _duration_hours(value: str) -> float:
    text = value.strip().lower().replace(",", ".")
    number = text.split()[0]
    return float(number)


def load_incident_catalog(path: str | Path = DEFAULT_CATALOG) -> list[IncidentEvent]:
    with Path(path).open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        events = [
            IncidentEvent(
                year=str(row["Anno"]).strip(),
                code=str(row["CodGisa"]).strip(),
                place=str(row["Luogo"]).strip(),
                latitude=_decimal(str(row["lat"])),
                longitude=_decimal(str(row["long"])),
                date=str(row["Data"]).strip(),
                start_hour=int(str(row["Ora inizio"]).strip()),
                duration_h=_duration_hours(str(row["Durata"])),
                note=str(row.get("Note", "")).strip(),
            )
            for row in reader
            if row.get("CodGisa")
        ]
    if not events:
        raise ValueError(f"incident catalog is empty: {path}")
    return events


def select_event(events: list[IncidentEvent], code: str) -> IncidentEvent:
    for event in events:
        if event.code == code:
            return event
    raise ValueError(f"incident code not found in catalog: {code}")


def _local_to_wgs84(
    center_lat: float,
    center_lon: float,
    x: float,
    y: float,
) -> tuple[float, float]:
    local = CRS.from_proj4(
        f"+proj=aeqd +lat_0={center_lat:.12f} +lon_0={center_lon:.12f} "
        "+datum=WGS84 +units=m +no_defs"
    )
    transformer = Transformer.from_crs(local, CRS.from_epsg(4326), always_xy=True)
    lon, lat = transformer.transform(x, y)
    return float(lat), float(lon)


def _receptors(
    event: IncidentEvent,
    *,
    radius_m: float,
    spacing_m: float,
) -> list[dict[str, Any]]:
    receptors: list[dict[str, Any]] = []
    steps = int((2.0 * radius_m) // spacing_m) + 1
    start = -radius_m
    for iy in range(steps):
        for ix in range(steps):
            x = start + ix * spacing_m
            y = start + iy * spacing_m
            if math.hypot(x, y) > radius_m:
                continue
            lat, lon = _local_to_wgs84(event.latitude, event.longitude, x, y)
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


def build_incident_config(
    event: IncidentEvent,
    output_path: str | Path,
    *,
    emission_rate_g_s: float = 20.0,
    wind_speed_m_s: float = 3.0,
    wind_from_direction_deg: float = 270.0,
    receptor_radius_m: float = 3500.0,
    receptor_spacing_m: float = 500.0,
    grid_cells: int = 81,
    grid_spacing_m: float = 100.0,
) -> dict[str, Any]:
    grid_half_width = ((grid_cells - 1) / 2.0) * grid_spacing_m
    config = {
        "metadata": {
            "title": f"Spritz production incident {event.code} - {event.place}",
            "event": event.as_metadata(),
            "coordinate_reference": "Local AEQD centered on incident latitude/longitude",
            "scientific_scope": "screening scenario requiring project-specific validation",
        },
        "grid": {
            "nx": grid_cells,
            "ny": grid_cells,
            "dx": grid_spacing_m,
            "dy": grid_spacing_m,
            "x0": -grid_half_width,
            "y0": -grid_half_width,
            "projection": f"AEQD centered at {event.latitude},{event.longitude}",
        },
        "stations": [
            {
                "id": "EVENT_WIND",
                "x": 0.0,
                "y": 0.0,
                "wind_speed": wind_speed_m_s,
                "wind_dir": wind_from_direction_deg,
                "temperature": 293.15,
                "mixing_height": 900.0,
            }
        ],
        "sources": [
            {
                "id": event.code,
                "x": 0.0,
                "y": 0.0,
                "z": 0.0,
                "source_type": "area",
                "width": 100.0,
                "length": 100.0,
                "height": 3.0,
                "stack_height": 0.0,
                "emission_rate": emission_rate_g_s,
                "deposition_velocity": 0.003,
                "settling_velocity": 0.005,
            }
        ],
        "receptors": _receptors(
            event,
            radius_m=receptor_radius_m,
            spacing_m=receptor_spacing_m,
        ),
        "run": {
            "stability": "D",
            "numerical_mode": "puff",
            "averaging_time_s": event.duration_h * 3600.0,
            "threshold": 0.0,
            "event_start_local": event.start_local_iso,
            "event_duration_h": event.duration_h,
        },
    }
    from_mapping(config).validate()
    write_json(output_path, config)
    return config


def run_incident_case(
    output_dir: str | Path,
    *,
    catalog_path: str | Path = DEFAULT_CATALOG,
    code: str = "2021_44",
    interchange: str = "netcdf",
    run_model: bool = True,
    make_map: bool = False,
    basemap: str | Path | None = None,
    basemap_extent: tuple[float, float, float, float] | None = None,
    emission_rate_g_s: float = 20.0,
    wind_speed_m_s: float = 3.0,
    wind_from_direction_deg: float = 270.0,
) -> IncidentRunResult:
    event = select_event(load_incident_catalog(catalog_path), code)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    config_path = out / f"{event.code}_config.json"
    build_incident_config(
        event,
        config_path,
        emission_rate_g_s=emission_rate_g_s,
        wind_speed_m_s=wind_speed_m_s,
        wind_from_direction_deg=wind_from_direction_deg,
    )
    workflow = None
    map_path = None
    plots: dict[str, str] = {}
    if run_model:
        workflow = run_workflow(
            config_path,
            out / "model",
            interchange=interchange,
            backend="gaussian",
        )
        if make_map:
            plots = plot_workflow_netcdfs(
                workflow,
                out,
                center_lat=event.latitude,
                center_lon=event.longitude,
                prefix=f"{event.code}_",
            )
            concentration_plot = plots.get("concentration")
            if concentration_plot is not None:
                map_path = Path(concentration_plot)
    return IncidentRunResult(event, config_path, out, workflow, map_path, plots)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run catalog-driven Spritz production incident cases"
    )
    parser.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    parser.add_argument("--code", default="2021_44")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--interchange", choices=["json", "netcdf"], default="netcdf")
    parser.add_argument("--config-only", action="store_true")
    parser.add_argument("--plot", action="store_true", help="also generate maps after computation")
    parser.add_argument("--basemap", default=None, help="optional local raster basemap image")
    parser.add_argument("--basemap-extent", default=None, help="west,south,east,north extent")
    parser.add_argument("--emission-rate-g-s", type=float, default=20.0)
    parser.add_argument("--wind-speed-m-s", type=float, default=3.0)
    parser.add_argument("--wind-from-direction-deg", type=float, default=270.0)
    args = parser.parse_args(argv)
    configure_logging(False)
    result = run_incident_case(
        args.output_dir,
        catalog_path=args.catalog,
        code=args.code,
        interchange=args.interchange,
        run_model=not args.config_only,
        make_map=args.plot,
        basemap=args.basemap,
        basemap_extent=visualization.parse_extent(args.basemap_extent),
        emission_rate_g_s=args.emission_rate_g_s,
        wind_speed_m_s=args.wind_speed_m_s,
        wind_from_direction_deg=args.wind_from_direction_deg,
    )
    LOGGER.info("%s", result.as_dict())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

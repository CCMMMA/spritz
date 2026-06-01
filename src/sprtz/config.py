from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .exceptions import ConfigurationError
from .io.jsonio import read_json
from .io.legacy import parse_legacy_file


@dataclass(frozen=True)
class GridConfig:
    nx: int
    ny: int
    dx: float
    dy: float
    x0: float = 0.0
    y0: float = 0.0
    projection: str = "LOCAL"

    def validate(self) -> None:
        if self.nx <= 0 or self.ny <= 0:
            raise ConfigurationError("grid nx and ny must be positive integers")
        if self.dx <= 0 or self.dy <= 0:
            raise ConfigurationError("grid dx and dy must be positive")


@dataclass(frozen=True)
class Station:
    id: str
    x: float
    y: float
    wind_speed: float
    wind_dir: float
    temperature: float = 293.15
    mixing_height: float = 1000.0

    def validate(self) -> None:
        if not self.id:
            raise ConfigurationError("station id must not be empty")
        if self.wind_speed < 0:
            raise ConfigurationError(f"station {self.id}: wind_speed must be non-negative")
        if not 0 <= self.wind_dir <= 360:
            raise ConfigurationError(f"station {self.id}: wind_dir must be in [0, 360]")
        if self.mixing_height <= 0:
            raise ConfigurationError(f"station {self.id}: mixing_height must be positive")


@dataclass(frozen=True)
class Source:
    id: str
    x: float
    y: float
    z: float = 0.0
    emission_rate: float = 1.0
    stack_height: float = 10.0
    exit_velocity: float = 0.0
    exit_temperature: float = 293.15
    stack_diameter: float = 1.0
    source_type: str = "point"
    width: float = 0.0
    length: float = 0.0
    height: float = 0.0
    heat_release: float = 0.0
    deposition_velocity: float = 0.0
    wet_scavenging: float = 0.0
    decay_rate: float = 0.0
    settling_velocity: float = 0.0

    def validate(self) -> None:
        if not self.id:
            raise ConfigurationError("source id must not be empty")
        if self.source_type.lower() not in {"point", "area", "volume", "line", "road", "roadway", "flare", "spray"}:
            raise ConfigurationError(f"source {self.id}: unsupported source_type")
        if self.emission_rate < 0:
            raise ConfigurationError(f"source {self.id}: emission_rate must be non-negative")
        if self.stack_height < 0:
            raise ConfigurationError(f"source {self.id}: stack_height must be non-negative")
        for name in ("stack_diameter", "width", "length", "height", "heat_release", "deposition_velocity", "wet_scavenging", "decay_rate", "settling_velocity"):
            if float(getattr(self, name)) < 0:
                raise ConfigurationError(f"source {self.id}: {name} must be non-negative")


@dataclass(frozen=True)
class Receptor:
    id: str
    x: float
    y: float
    z: float = 0.0
    latitude: float | None = None
    longitude: float | None = None

    def validate(self) -> None:
        if not self.id:
            raise ConfigurationError("receptor id must not be empty")
        if self.latitude is not None and not -90.0 <= float(self.latitude) <= 90.0:
            raise ConfigurationError(f"receptor {self.id}: latitude must be in [-90, 90]")
        if self.longitude is not None and not -180.0 <= float(self.longitude) <= 180.0:
            raise ConfigurationError(f"receptor {self.id}: longitude must be in [-180, 180]")


@dataclass(frozen=True)
class SuiteConfig:
    grid: GridConfig
    stations: tuple[Station, ...] = ()
    sources: tuple[Source, ...] = ()
    receptors: tuple[Receptor, ...] = ()
    landuse: dict[str, Any] = field(default_factory=dict)
    run: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        self.grid.validate()
        for group in (self.stations, self.sources, self.receptors):
            seen: set[str] = set()
            for item in group:
                item.validate()
                if item.id in seen:
                    raise ConfigurationError(f"duplicate id: {item.id}")
                seen.add(item.id)
        stability = str(self.run.get("stability", self.run.get("STABILITY", "D"))).upper()
        if stability not in {"A", "B", "C", "D", "E", "F"}:
            raise ConfigurationError("run.stability must be one of A, B, C, D, E, F")
        threshold = self.run.get("threshold", self.run.get("THRESHOLD"))
        if threshold is not None and float(threshold) < 0:
            raise ConfigurationError("run.threshold must be non-negative")
        numerical_mode = str(self.run.get("numerical_mode", self.run.get("NUMERICAL_MODE", "puff"))).lower()
        if numerical_mode not in {"puff", "plume"}:
            raise ConfigurationError("run.numerical_mode must be puff or plume")
        averaging_time = self.run.get("averaging_time_s", self.run.get("AVERAGING_TIME_S", 3600.0))
        if float(averaging_time) <= 0:
            raise ConfigurationError("run.averaging_time_s must be positive")
        output_interval = self.run.get("output_interval_s", self.run.get("OUTPUT_INTERVAL_S"))
        if output_interval is not None and float(output_interval) <= 0:
            raise ConfigurationError("run.output_interval_s must be positive")
        output_duration = self.run.get("output_duration_s", self.run.get("OUTPUT_DURATION_S"))
        if output_duration is not None and float(output_duration) <= 0:
            raise ConfigurationError("run.output_duration_s must be positive")
        output_start = self.run.get("output_start_s", self.run.get("OUTPUT_START_S"))
        if output_start is not None and float(output_start) < 0:
            raise ConfigurationError("run.output_start_s must be non-negative")


def _grid_from_mapping(data: dict[str, Any]) -> GridConfig:
    grid = data.get("grid", data)
    return GridConfig(
        nx=int(grid.get("nx", grid.get("NX", 10))),
        ny=int(grid.get("ny", grid.get("NY", 10))),
        dx=float(grid.get("dx", grid.get("DX", 1000.0))),
        dy=float(grid.get("dy", grid.get("DY", grid.get("dx", grid.get("DX", 1000.0))))),
        x0=float(grid.get("x0", grid.get("X0", 0.0))),
        y0=float(grid.get("y0", grid.get("Y0", 0.0))),
        projection=str(grid.get("projection", grid.get("PROJECTION", "LOCAL"))),
    )


def _stations(data: dict[str, Any]) -> tuple[Station, ...]:
    return tuple(Station(**item) for item in data.get("stations", []))


def _sources(data: dict[str, Any]) -> tuple[Source, ...]:
    return tuple(Source(**item) for item in data.get("sources", []))


def _receptors(data: dict[str, Any]) -> tuple[Receptor, ...]:
    return tuple(Receptor(**item) for item in data.get("receptors", []))


def from_mapping(data: dict[str, Any], *, validate: bool = True) -> SuiteConfig:
    cfg = SuiteConfig(
        grid=_grid_from_mapping(data),
        stations=_stations(data),
        sources=_sources(data),
        receptors=_receptors(data),
        landuse=dict(data.get("landuse", {})),
        run={**dict(data.get("run", {})), **{str(k).lower(): v for k, v in dict(data.get("run", {})).items()}},
        raw=dict(data),
    )
    if validate:
        cfg.validate()
    return cfg


def _legacy_to_mapping(path: Path) -> dict[str, Any]:
    legacy = parse_legacy_file(path)
    data: dict[str, Any] = {
        "grid": {
            "nx": legacy.get_int("NX", 10),
            "ny": legacy.get_int("NY", 10),
            "dx": legacy.get_float("DX", 1000.0),
            "dy": legacy.get_float("DY", legacy.get_float("DX", 1000.0)),
            "x0": legacy.get_float("X0", 0.0),
            "y0": legacy.get_float("Y0", 0.0),
            "projection": legacy.get("PROJECTION", "LOCAL"),
        },
        "stations": [],
        "sources": [],
        "receptors": [],
        "run": legacy.values,
    }
    if "STATION" in legacy.values:
        data["stations"].append(_csv_record(legacy.values["STATION"], Station))
    if "SOURCE" in legacy.values:
        data["sources"].append(_csv_record(legacy.values["SOURCE"], Source))
    if "RECEPTOR" in legacy.values:
        data["receptors"].append(_csv_record(legacy.values["RECEPTOR"], Receptor))
    return data


def _csv_record(value: str, cls: type[Any]) -> dict[str, Any]:
    names = [f.name for f in cls.__dataclass_fields__.values()]
    parts = [p.strip() for p in value.split(",")]
    if len(parts) > len(names):
        raise ConfigurationError(f"too many CSV fields for {cls.__name__}: {value}")
    out: dict[str, Any] = {}
    for name, part in zip(names, parts):
        out[name] = part if name == "id" else float(part)
    return out


def load_config(path: str | Path) -> SuiteConfig:
    p = Path(path)
    if not p.exists():
        raise ConfigurationError(f"configuration file not found: {p}")
    if p.suffix.lower() == ".json":
        return from_mapping(read_json(p))
    return from_mapping(_legacy_to_mapping(p))

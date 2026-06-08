from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .exceptions import ConfigurationError
from .io.jsonio import read_json
from .io.legacy import parse_legacy_file


_BACKEND_ALIASES = {
    "gauss": "gaussian",
    "gaussian": "gaussian",
    "spritz": "gaussian",
    "particle": "particles",
    "particles": "particles",
    "lagrangian": "particles",
    "firefront": "firefront",
    "fire": "firefront",
    "fire+puff": "fire+puff",
    "firms": "firms",
    "firms+fire": "firms+fire",
    "firms+fire+puff": "firms+fire+puff",
}

_BURNING_MATERIALS = {"generic", "paper", "plastic"}


def normalize_backend(value: Any) -> str:
    """Return the canonical clean-room dispersion backend name."""
    key = str(value).strip().lower()
    try:
        return _BACKEND_ALIASES[key]
    except KeyError as exc:
        raise ConfigurationError(
            "run.backend must be gaussian/gauss, particles, firefront, fire+puff, firms, firms+fire, or firms+fire+puff"
        ) from exc


def configured_backend(run: dict[str, Any], override: str | None = None) -> str:
    """Resolve backend selection from an optional CLI override and run config."""
    if override is not None:
        return normalize_backend(override)
    return normalize_backend(
        run.get(
            "backend",
            run.get(
                "BACKEND",
                run.get("dispersion_backend", run.get("DISPERSION_BACKEND", "gaussian")),
            ),
        )
    )


def parse_field_z_levels(value: Any) -> tuple[float, ...]:
    """Parse vertical field levels from JSON scalars, arrays, or legacy strings."""
    if value is None:
        return (0.0,)
    if isinstance(value, str):
        parts = [part.strip() for part in value.split(",") if part.strip()]
        if not parts:
            raise ConfigurationError("run.field_z_levels must not be empty")
        levels = tuple(float(part) for part in parts)
    elif isinstance(value, (int, float)):
        levels = (float(value),)
    else:
        try:
            levels = tuple(float(part) for part in value)
        except (TypeError, ValueError) as exc:
            raise ConfigurationError("run.field_z_levels must be a number or list of numbers") from exc
    if not levels:
        raise ConfigurationError("run.field_z_levels must not be empty")
    if any(level < 0 for level in levels):
        raise ConfigurationError("run.field_z_levels must be non-negative")
    return levels


def parse_datetime_value(value: Any, *, field_name: str = "datetime") -> datetime | None:
    """Parse an ISO-8601 datetime value used by time-aware screening runs."""
    if value is None or value == "":
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError as exc:
        raise ConfigurationError(f"{field_name} must be an ISO-8601 datetime") from exc


def run_datetime(run: dict[str, Any], *names: str) -> datetime | None:
    for name in names:
        value = run.get(name, run.get(name.upper()))
        if value is not None:
            return parse_datetime_value(value, field_name=f"run.{name}")
    return None


def _validate_datetime_pair(
    start: datetime | None,
    end: datetime | None,
    *,
    label: str,
) -> None:
    if start is not None and end is not None:
        try:
            invalid_order = end < start
        except TypeError as exc:
            raise ConfigurationError(
                f"{label} start and end datetimes must use compatible timezone information"
            ) from exc
        if invalid_order:
            raise ConfigurationError(f"{label} end datetime must not be before start datetime")


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
    precipitation_rate: float = 0.0

    def validate(self) -> None:
        if not self.id:
            raise ConfigurationError("station id must not be empty")
        if self.wind_speed < 0:
            raise ConfigurationError(f"station {self.id}: wind_speed must be non-negative")
        if not 0 <= self.wind_dir <= 360:
            raise ConfigurationError(f"station {self.id}: wind_dir must be in [0, 360]")
        if self.mixing_height <= 0:
            raise ConfigurationError(f"station {self.id}: mixing_height must be positive")
        if self.precipitation_rate < 0:
            raise ConfigurationError(f"station {self.id}: precipitation_rate must be non-negative")


@dataclass(frozen=True)
class Source:
    id: str
    x: float
    y: float
    z: float = 0.0
    latitude: float | None = None
    longitude: float | None = None
    emission_rate: float = 1.0
    stack_height: float = 10.0
    height_agl_m: float | None = None
    exit_velocity: float = 0.0
    exit_temperature: float = 293.15
    stack_diameter: float = 1.0
    source_type: str = "point"
    material: str = "generic"
    start_datetime: str | None = None
    end_datetime: str | None = None
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
        if self.height_agl_m is not None and float(self.height_agl_m) < 0:
            raise ConfigurationError(f"source {self.id}: height_agl_m must be non-negative")
        if self.latitude is not None and not -90.0 <= float(self.latitude) <= 90.0:
            raise ConfigurationError(f"source {self.id}: latitude must be in [-90, 90]")
        if self.longitude is not None and not -180.0 <= float(self.longitude) <= 180.0:
            raise ConfigurationError(f"source {self.id}: longitude must be in [-180, 180]")
        if self.material.lower() not in _BURNING_MATERIALS:
            raise ConfigurationError(f"source {self.id}: material must be generic, paper, or plastic")
        _validate_datetime_pair(
            parse_datetime_value(self.start_datetime, field_name=f"source {self.id} start_datetime"),
            parse_datetime_value(self.end_datetime, field_name=f"source {self.id} end_datetime"),
            label=f"source {self.id}",
        )
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
class FireIgnitionPoint:
    lat: float | None = None
    lon: float | None = None
    time: str = ""
    row: int | None = None
    col: int | None = None


@dataclass(frozen=True)
class FireFightingAction:
    type: str
    polygon_wkt: str
    t_start: str
    t_end: str


@dataclass(frozen=True)
class SpottingConfig:
    model: str = "randomfront"
    firebrand_radius_m: float = 0.010
    abl_height_m: float = 1000.0
    n_firebrands_per_cell: int = 5
    intensity_threshold_kw_m: float = 100.0
    sigma_spotting: float = 0.70
    sigma_angular_rad: float = 0.785
    p_percentile: float = 0.995


@dataclass(frozen=True)
class FIRMSConfig:
    enabled: bool = False
    source: str = "VIIRS_NOAA20_NRT"
    day_range: int = 1
    date: str = ""
    confidence_filter: tuple[str, ...] = ("n", "h")
    min_frp_mw: float = 1.0
    map_key_env: str = "FIRMS_MAP_KEY"
    cache_dir: str = ""
    bbox_pad_deg: float = 0.1
    cluster_distance_m: float = 500.0


@dataclass(frozen=True)
class BuoyancyConfig:
    enabled: bool = False
    nc_wind_dominated: float = 2.0
    nc_plume_dominated: float = 10.0
    alpha_inflow_max: float = 0.35
    beta_updraft_max: float = 0.50
    inflow_radius_cells: int = 3
    prob_threshold: float = 0.5


@dataclass(frozen=True)
class GPUConfig:
    backend: str = "numpy"
    device_id: int = 0
    cupy_stream: bool = True
    chunk_realizations: int = 0


@dataclass(frozen=True)
class SpritzMetMPIConfig:
    enabled: bool = False
    parallel: str = "auto"
    halo_cells: int = 1
    collective_io: bool = True
    fallback_scatter: bool = True


@dataclass(frozen=True)
class SpritzMetConfig:
    mpi: SpritzMetMPIConfig = field(default_factory=SpritzMetMPIConfig)


@dataclass(frozen=True)
class FireConfig:
    ignitions: tuple[FireIgnitionPoint, ...] = ()
    realizations: int = 100
    ros_model: str = "wang"
    moisture_default: float = 0.08
    spotting: bool = False
    spotting_model: str = "randomfront"
    spotting_config: SpottingConfig = field(default_factory=SpottingConfig)
    firefighting: tuple[FireFightingAction, ...] = ()
    fuel_map: str = "corine"
    t_max_seconds: float = 21600.0
    output_interval_seconds: float = 600.0
    seed: int = 42
    numba: bool = False
    parallel: str = "auto"
    firms: FIRMSConfig = field(default_factory=FIRMSConfig)
    buoyancy: BuoyancyConfig = field(default_factory=BuoyancyConfig)
    gpu: GPUConfig = field(default_factory=GPUConfig)

    def validate(self) -> None:
        if self.realizations <= 0:
            raise ConfigurationError("fire.realizations must be positive")
        if self.ros_model not in {"wang", "classic"}:
            raise ConfigurationError("fire.ros_model must be wang or classic")
        if not 0.0 <= self.moisture_default <= 1.0:
            raise ConfigurationError("fire.moisture_default must be in [0, 1]")
        if self.t_max_seconds <= 0 or self.output_interval_seconds <= 0:
            raise ConfigurationError("fire durations must be positive")
        if self.parallel not in {"auto", "mpi", "serial"}:
            raise ConfigurationError("fire.parallel must be auto, mpi, or serial")


@dataclass(frozen=True)
class SuiteConfig:
    grid: GridConfig
    stations: tuple[Station, ...] = ()
    sources: tuple[Source, ...] = ()
    receptors: tuple[Receptor, ...] = ()
    landuse: dict[str, Any] = field(default_factory=dict)
    run: dict[str, Any] = field(default_factory=dict)
    fire: FireConfig | None = None
    spritzmet: SpritzMetConfig = field(default_factory=SpritzMetConfig)
    raw: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        self.grid.validate()
        if self.fire is not None:
            self.fire.validate()
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
        configured_backend(self.run)
        output_mode = self.run.get("concentration_output", self.run.get("CONCENTRATION_OUTPUT"))
        if output_mode is not None:
            mode = str(output_mode).strip().lower()
            if mode not in {"receptor", "receptors", "grid", "field", "grid_field", "both"}:
                raise ConfigurationError("run.concentration_output must be receptors, grid, or both")
        field_levels = self.run.get(
            "field_z_levels",
            self.run.get("FIELD_Z_LEVELS", self.run.get("z_levels", self.run.get("Z_LEVELS"))),
        )
        parse_field_z_levels(field_levels)
        _validate_datetime_pair(
            run_datetime(self.run, "weather_start_datetime", "simulation_start_datetime"),
            run_datetime(self.run, "weather_end_datetime", "simulation_end_datetime"),
            label="weather simulation",
        )
        _validate_datetime_pair(
            run_datetime(self.run, "event_start_datetime", "fire_start_datetime"),
            run_datetime(self.run, "event_end_datetime", "fire_end_datetime"),
            label="fire/arson event",
        )
        _validate_datetime_pair(
            run_datetime(self.run, "firefighters_start_datetime"),
            run_datetime(self.run, "firefighters_end_datetime"),
            label="firefighters actions",
        )
        washout_coeff = self.run.get(
            "precipitation_washout_coefficient_s_per_mm_h",
            self.run.get("PRECIPITATION_WASHOUT_COEFFICIENT_S_PER_MM_H"),
        )
        if washout_coeff is not None and float(washout_coeff) < 0:
            raise ConfigurationError("run.precipitation_washout_coefficient_s_per_mm_h must be non-negative")
        firefighter_factor = self.run.get(
            "firefighters_emission_factor",
            self.run.get("FIREFIGHTERS_EMISSION_FACTOR"),
        )
        if firefighter_factor is not None and not 0.0 <= float(firefighter_factor) <= 1.0:
            raise ConfigurationError("run.firefighters_emission_factor must be in [0, 1]")


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


def _source_mapping(item: dict[str, Any]) -> dict[str, Any]:
    source = dict(item)
    height_aliases = (
        "height_agl_m",
        "height_on_ground_m",
        "release_height_m",
        "chimney_height_m",
        "stack_height_m",
    )
    for alias in height_aliases:
        if alias in source and "stack_height" not in source:
            source["stack_height"] = source[alias]
    if "height_agl_m" not in source and "stack_height" in source:
        source["height_agl_m"] = source["stack_height"]
    z_aliases = ("source_ground_height_m", "source_z_m", "ground_elevation_m")
    for alias in z_aliases:
        if alias in source and "z" not in source:
            source["z"] = source[alias]
    allowed = set(Source.__dataclass_fields__)
    return {key: value for key, value in source.items() if key in allowed}


def _sources(data: dict[str, Any]) -> tuple[Source, ...]:
    return tuple(Source(**_source_mapping(item)) for item in data.get("sources", []))


def _receptors(data: dict[str, Any]) -> tuple[Receptor, ...]:
    return tuple(Receptor(**item) for item in data.get("receptors", []))


def _fire(data: dict[str, Any]) -> FireConfig | None:
    block = data.get("fire")
    if block is None:
        return None
    item = dict(block)
    item["ignitions"] = tuple(FireIgnitionPoint(**dict(v)) for v in item.get("ignitions", []))
    item["firefighting"] = tuple(FireFightingAction(**dict(v)) for v in item.get("firefighting", []))
    if "spotting_config" in item:
        item["spotting_config"] = SpottingConfig(**dict(item["spotting_config"]))
    if "firms" in item:
        firms = dict(item["firms"])
        if isinstance(firms.get("confidence_filter"), list):
            firms["confidence_filter"] = tuple(str(v) for v in firms["confidence_filter"])
        item["firms"] = FIRMSConfig(**firms)
    if "buoyancy" in item:
        item["buoyancy"] = BuoyancyConfig(**dict(item["buoyancy"]))
    if "gpu" in item:
        item["gpu"] = GPUConfig(**dict(item["gpu"]))
    return FireConfig(**item)


def from_mapping(data: dict[str, Any], *, validate: bool = True) -> SuiteConfig:
    cfg = SuiteConfig(
        grid=_grid_from_mapping(data),
        stations=_stations(data),
        sources=_sources(data),
        receptors=_receptors(data),
        landuse=dict(data.get("landuse", {})),
        run={**dict(data.get("run", {})), **{str(k).lower(): v for k, v in dict(data.get("run", {})).items()}},
        fire=_fire(data),
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
    if cls is Source:
        names = [
            "id",
            "x",
            "y",
            "z",
            "emission_rate",
            "stack_height",
            "exit_velocity",
            "exit_temperature",
            "stack_diameter",
        ]
    else:
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

from __future__ import annotations

"""SpritzWRF: clean-room WRF extraction utilities for Spritz.

SpritzWRF provides a typed, documented Python API that inspects WRF files and
extracts wind and precipitation fields into the common Spritz interoperability schema used by
SpritzMet and downstream dispersion models.
"""

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.request import urlopen
import shutil

import numpy as np

from sprtz.io.jsonio import write_json
from sprtz.io.netcdf_cf import available as netcdf_available, iso_utc

METEO_UNIPARTHENOPE_HISTORY_BASE = "https://data.meteo.uniparthenope.it/files/wrf5/d03/history"


@dataclass(frozen=True)
class WRFWindField:
    """Near-surface meteorology extracted from WRF or WRF-like NetCDF."""

    latitude: np.ndarray
    longitude: np.ndarray
    u: np.ndarray
    v: np.ndarray
    source_path: Path
    time_index: int = 0
    metadata: dict[str, Any] | None = None
    precipitation_rate: np.ndarray | None = None
    u10m: np.ndarray | None = None
    v10m: np.ndarray | None = None
    temperature_2m_c: np.ndarray | None = None
    relative_humidity_2m: np.ndarray | None = None

    @property
    def wind_speed(self) -> np.ndarray:
        return np.hypot(self.u, self.v)

    @property
    def wind_from_direction(self) -> np.ndarray:
        # Meteorological direction from which the wind blows.
        return (270.0 - np.rad2deg(np.arctan2(self.v, self.u))) % 360.0


def meteo_uniparthenope_wrf_url(run_date: str | date | datetime, cycle_hour: int | str) -> str:
    """Return the canonical meteo@uniparthenope WRF5 d03 history URL.

    The public history-file path used by the operational use cases is::

        https://data.meteo.uniparthenope.it/files/wrf5/d03/history/YYYY/MM/DD/wrf5_d03_YYYYMMDDZhh00.nc

    Parameters
    ----------
    run_date:
        Date as ``YYYY-MM-DD``, ``datetime.date``, or ``datetime``.
    cycle_hour:
        Model cycle hour.  Values such as ``0`` and ``"00"`` become ``00``.
    """
    if isinstance(run_date, datetime):
        d = run_date.date()
    elif isinstance(run_date, date):
        d = run_date
    else:
        d = date.fromisoformat(str(run_date))
    hour = int(cycle_hour)
    if hour < 0 or hour > 23:
        raise ValueError("cycle_hour must be between 0 and 23")
    hh = f"{hour:02d}"
    ymd = d.strftime("%Y%m%d")
    return f"{METEO_UNIPARTHENOPE_HISTORY_BASE}/{d:%Y/%m/%d}/wrf5_d03_{ymd}Z{hh}00.nc"


def download_meteo_uniparthenope_wrf(
    destination_dir: str | Path,
    *,
    run_date: str | date | datetime,
    cycle_hour: int | str = 0,
    timeout_s: float = 120.0,
    force: bool = False,
) -> Path:
    """Download a WRF5 d03 history NetCDF file from meteo@uniparthenope.

    Existing files are reused unless ``force=True``.  The function uses only the
    Python standard library so the downloader works in minimal deployments.
    """
    url = meteo_uniparthenope_wrf_url(run_date, cycle_hour)
    name = url.rsplit("/", 1)[-1]
    out_dir = Path(destination_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / name
    if target.exists() and target.stat().st_size > 0 and not force:
        return target
    tmp = target.with_suffix(target.suffix + ".part")
    try:
        with urlopen(url, timeout=timeout_s) as response, tmp.open("wb") as handle:  # noqa: S310 - user-requested public HTTPS data download
            shutil.copyfileobj(response, handle)
        tmp.replace(target)
    except Exception:
        if tmp.exists():
            tmp.unlink()
        raise
    return target


TIME_DIMENSIONS = {"time", "times", "time_counter"}
VERTICAL_DIMENSIONS = {
    "bottom_top",
    "bottom_top_stag",
    "level",
    "levels",
    "lev",
    "z",
    "height",
    "height_m",
}
Y_DIMENSIONS = {"south_north", "south_north_stag", "y", "lat", "latitude"}
X_DIMENSIONS = {"west_east", "west_east_stag", "x", "lon", "longitude"}


def _bounded_index(requested: int, size: int) -> int:
    if size <= 0:
        raise ValueError("cannot select from an empty WRF dimension")
    return min(max(requested, 0), size - 1)


def _dimension_kind(dim: str) -> str | None:
    lower = dim.lower()
    if lower in TIME_DIMENSIONS or lower.startswith("time"):
        return "time"
    if lower in VERTICAL_DIMENSIONS:
        return "level"
    if lower in Y_DIMENSIONS:
        return "y"
    if lower in X_DIMENSIONS:
        return "x"
    return None


def _select_2d(arr: np.ndarray, time_index: int) -> np.ndarray:
    arr = np.asarray(arr, dtype=float)
    while arr.ndim > 2:
        arr = arr[time_index if arr.shape[0] > time_index else 0]
    return arr


def _select_wrf_spatial_2d_from_array(
    arr: np.ndarray,
    dims: tuple[str, ...],
    name: str,
    *,
    time_index: int | None,
    level_index: int | None,
    path: Path,
) -> np.ndarray:
    """Select one horizontal slice using WRF/CF dimension names.

    WRF winds may be stored as ``(Time, bottom_top, south_north, west_east)``;
    near-surface fields are commonly ``(Time, south_north, west_east)``.  Keep
    the time and vertical choices independent so a later time step does not
    accidentally select the same-numbered vertical level.
    """
    if dims and len(dims) != arr.ndim:
        raise ValueError(f"variable {name} in {path} has inconsistent dimensions")
    if not dims:
        if time_index is None and level_index is None and arr.ndim in {2, 3, 4}:
            return arr
        if arr.ndim == 4 and time_index is not None and level_index is None:
            return arr[_bounded_index(time_index, arr.shape[0]), :, :, :]
        if arr.ndim == 4 and time_index is None and level_index is not None:
            return arr[:, _bounded_index(level_index, arr.shape[1]), :, :]
        if arr.ndim == 4:
            return arr[_bounded_index(time_index or 0, arr.shape[0]), _bounded_index(level_index or 0, arr.shape[1]), :, :]
        if arr.ndim == 3 and time_index is None:
            return arr
        return _select_2d(arr, time_index)

    selected = arr
    remaining_dims = list(dims)
    for axis in range(len(dims) - 1, -1, -1):
        kind = _dimension_kind(dims[axis])
        if kind == "time" and time_index is not None:
            selected = np.take(selected, _bounded_index(time_index, selected.shape[axis]), axis=axis)
            remaining_dims.pop(axis)
        elif kind == "level" and level_index is not None:
            selected = np.take(selected, _bounded_index(level_index, selected.shape[axis]), axis=axis)
            remaining_dims.pop(axis)

    kinds = [_dimension_kind(dim) for dim in remaining_dims]
    if "y" not in kinds or "x" not in kinds:
        raise ValueError(
            f"variable {name} in {path} must include y/x dimensions after selection; "
            f"got dimensions {remaining_dims} with shape {selected.shape}"
        )
    ordered_axes: list[int] = []
    for wanted in ("time", "level", "y", "x"):
        for axis, kind in enumerate(kinds):
            if kind == wanted:
                ordered_axes.append(axis)
                break
    extra_axes = [axis for axis in range(selected.ndim) if axis not in ordered_axes]
    for axis in extra_axes:
        if selected.shape[axis] != 1:
            raise ValueError(
                f"variable {name} in {path} has unsupported dimension {remaining_dims[axis]!r} "
                f"with size {selected.shape[axis]}"
            )
    ordered = np.transpose(selected, ordered_axes + extra_axes)
    if extra_axes:
        ordered = np.squeeze(ordered, axis=tuple(range(len(ordered_axes), ordered.ndim)))
    return np.asarray(ordered, dtype=float)


def _select_wrf_spatial_2d(variable: Any, *, time_index: int | None, level_index: int | None, path: Path) -> np.ndarray:
    arr = np.asarray(variable[:], dtype=float)
    dims = tuple(str(dim) for dim in getattr(variable, "dimensions", ()))
    name = str(getattr(variable, "name", "unknown"))
    return _select_wrf_spatial_2d_from_array(arr, dims, name, time_index=time_index, level_index=level_index, path=path)


def _has_level_dimension(variable: Any) -> bool:
    return any(_dimension_kind(str(dim)) == "level" for dim in getattr(variable, "dimensions", ()))


def _destagger_wrf_component(values: np.ndarray, variable: Any) -> np.ndarray:
    """Average WRF staggered U/V grids onto the mass grid after time/level selection."""
    arr = np.asarray(values, dtype=float)
    dims = tuple(str(dim) for dim in getattr(variable, "dimensions", ()))
    if any(dim.lower() == "west_east_stag" for dim in dims):
        arr = 0.5 * (arr[..., :-1] + arr[..., 1:])
    if any(dim.lower() == "south_north_stag" for dim in dims):
        if arr.ndim < 2:
            raise ValueError(f"variable {getattr(variable, 'name', 'unknown')} has staggered y dimension but no y axis")
        arr = 0.5 * (arr[..., :-1, :] + arr[..., 1:, :])
    return np.asarray(arr, dtype=float)


def _select_precipitation_rate(ds: Any, time_index: int | None, level_index: int | None, path: Path) -> np.ndarray | None:
    """Return a WRF precipitation-rate proxy in mm h-1 when variables exist."""

    def read_raw(name: str) -> tuple[np.ndarray, tuple[str, ...]] | None:
        if name not in ds.variables:
            return None
        variable = ds.variables[name]
        return np.asarray(variable[:], dtype=float), tuple(str(dim) for dim in getattr(variable, "dimensions", ()))

    for name in ("RAINRATE", "PRECIP_RATE", "precipitation_rate", "precip_rate"):
        raw = read_raw(name)
        if raw is not None:
            arr, dims = raw
            return _select_wrf_spatial_2d_from_array(
                arr,
                dims,
                name,
                time_index=time_index,
                level_index=level_index,
                path=path,
            )

    accum = None
    accum_dims: tuple[str, ...] = ()
    for name in ("RAINC", "RAINNC", "RAINSH"):
        raw = read_raw(name)
        if raw is not None:
            values, dims = raw
            if accum is not None and dims != accum_dims:
                raise ValueError("WRF accumulated precipitation variables must use matching dimensions")
            accum = values if accum is None else accum + values
            accum_dims = dims
    if accum is None:
        return None
    arr = np.asarray(accum, dtype=float)
    time_axis = next(
        (axis for axis, dim in enumerate(accum_dims) if dim.lower() in TIME_DIMENSIONS or dim.lower().startswith("time")),
        None,
    )
    if time_axis is None:
        return np.maximum(
            _select_wrf_spatial_2d_from_array(
                arr,
                accum_dims,
                "accumulated_precipitation",
                time_index=time_index,
                level_index=level_index,
                path=path,
            ),
            0.0,
        )
    current_dims = tuple(dim for axis, dim in enumerate(accum_dims) if axis != time_axis)
    if time_index is None:
        values = []
        for index in range(arr.shape[time_axis]):
            current_arr = np.take(arr, index, axis=time_axis)
            current = _select_wrf_spatial_2d_from_array(
                current_arr,
                current_dims,
                "accumulated_precipitation",
                time_index=0,
                level_index=level_index,
                path=path,
            )
            if index == 0:
                values.append(np.maximum(current, 0.0))
            else:
                previous_arr = np.take(arr, index - 1, axis=time_axis)
                previous = _select_wrf_spatial_2d_from_array(
                    previous_arr,
                    current_dims,
                    "accumulated_precipitation",
                    time_index=0,
                    level_index=level_index,
                    path=path,
                )
                values.append(np.maximum(current - previous, 0.0))
        return np.asarray(values, dtype=float)
    index = _bounded_index(time_index, arr.shape[time_axis])
    current_arr = np.take(arr, index, axis=time_axis)
    current = _select_wrf_spatial_2d_from_array(
        current_arr,
        current_dims,
        "accumulated_precipitation",
        time_index=0,
        level_index=level_index,
        path=path,
    )
    if index == 0:
        return np.maximum(current, 0.0)
    previous_arr = np.take(arr, index - 1, axis=time_axis)
    previous = _select_wrf_spatial_2d_from_array(
        previous_arr,
        current_dims,
        "accumulated_precipitation",
        time_index=0,
        level_index=level_index,
        path=path,
    )
    return np.maximum(current - previous, 0.0)


def _select_optional_2d(
    ds: Any,
    names: tuple[str, ...],
    *,
    time_index: int | None,
    level_index: int | None,
    path: Path,
) -> np.ndarray | None:
    for name in names:
        if name in ds.variables:
            return _select_wrf_spatial_2d(
                ds.variables[name],
                time_index=time_index,
                level_index=level_index,
                path=path,
            )
    return None


def _select_temperature_2m_c(ds: Any, time_index: int | None, path: Path) -> np.ndarray | None:
    temperature = _select_optional_2d(
        ds,
        ("T2", "TEMP2", "temperature_2m", "air_temperature_2m", "air_temperature"),
        time_index=time_index,
        level_index=0,
        path=path,
    )
    if temperature is None:
        return None
    units = ""
    for name in ("T2", "TEMP2", "temperature_2m", "air_temperature_2m", "air_temperature"):
        if name in ds.variables:
            units = str(getattr(ds.variables[name], "units", "")).strip().lower()
            break
    arr = np.asarray(temperature, dtype=float)
    if units in {"c", "degc", "degree_celsius", "degrees_celsius", "celsius"}:
        return arr
    if units in {"k", "kelvin"} or float(np.nanmean(arr)) > 150.0:
        return arr - 273.15
    return arr


def _relative_humidity_from_q2(q2: np.ndarray, psfc_pa: np.ndarray, temperature_2m_c: np.ndarray) -> np.ndarray:
    q = np.maximum(np.asarray(q2, dtype=float), 0.0)
    pressure = np.maximum(np.asarray(psfc_pa, dtype=float), 1.0)
    tc = np.asarray(temperature_2m_c, dtype=float)
    vapor_pressure = q * pressure / np.maximum(0.622 + 0.378 * q, 1.0e-12)
    saturation = 611.2 * np.exp((17.67 * tc) / np.maximum(tc + 243.5, 1.0e-6))
    return np.clip(vapor_pressure / np.maximum(saturation, 1.0e-12), 0.0, 1.0)


def _select_relative_humidity_2m(
    ds: Any,
    time_index: int | None,
    path: Path,
    temperature_2m_c: np.ndarray | None,
) -> np.ndarray | None:
    rh = _select_optional_2d(
        ds,
        ("RH2", "relative_humidity_2m", "relative_humidity"),
        time_index=time_index,
        level_index=0,
        path=path,
    )
    if rh is not None:
        arr = np.asarray(rh, dtype=float)
        return np.clip(arr / 100.0 if float(np.nanmax(arr)) > 1.5 else arr, 0.0, 1.0)
    if temperature_2m_c is None:
        return None
    q2 = _select_optional_2d(ds, ("Q2", "specific_humidity_2m", "specific_humidity"), time_index=time_index, level_index=0, path=path)
    psfc = _select_optional_2d(ds, ("PSFC", "surface_pressure", "pressure"), time_index=time_index, level_index=0, path=path)
    if q2 is None or psfc is None:
        return None
    return _relative_humidity_from_q2(q2, psfc, temperature_2m_c)


def _decode_wrf_time(value: Any) -> str:
    arr = np.asarray(value)
    if arr.dtype.kind in {"S", "U"}:
        return b"".join(np.asarray(arr, dtype="S1").ravel()).decode("utf-8", errors="replace").strip()
    if arr.size == 1:
        item = arr.item()
        return item.decode("utf-8", errors="replace").strip() if isinstance(item, bytes) else str(item).strip()
    return str(value).strip()


def _selected_wrf_datetime(ds: Any, time_index: int) -> str | None:
    if "Times" in ds.variables:
        values = np.asarray(ds.variables["Times"][:])
        if values.size:
            index = min(max(time_index, 0), values.shape[0] - 1)
            parsed = iso_utc(_decode_wrf_time(values[index]))
            if parsed:
                return parsed
    if "time" in ds.variables:
        time_var = ds.variables["time"]
        units = str(getattr(time_var, "units", "")).strip()
        if "since" in units.lower():
            try:
                from netCDF4 import num2date  # type: ignore

                values = np.asarray(time_var[:], dtype=float)
                if values.size:
                    index = min(max(time_index, 0), values.shape[0] - 1)
                    dt = num2date(
                        float(values[index]),
                        units=units,
                        calendar=str(getattr(time_var, "calendar", "standard")),
                        only_use_cftime_datetimes=False,
                    )
                    parsed = iso_utc(dt.isoformat())
                    if parsed:
                        return parsed
            except Exception:
                pass
    for attr in ("SIMULATION_START_DATE", "START_DATE", "valid_time", "time_datetime"):
        if attr in ds.ncattrs():
            parsed = iso_utc(getattr(ds, attr))
            if parsed:
                return parsed
    return None


def _selected_wrf_datetimes(ds: Any) -> list[str] | None:
    if "Times" in ds.variables:
        values = np.asarray(ds.variables["Times"][:])
        parsed = [iso_utc(_decode_wrf_time(value)) for value in values]
        result = [value for value in parsed if value]
        return result or None
    if "time" in ds.variables:
        time_var = ds.variables["time"]
        units = str(getattr(time_var, "units", "")).strip()
        if "since" in units.lower():
            try:
                from netCDF4 import num2date  # type: ignore

                values = np.asarray(time_var[:], dtype=float)
                parsed = [
                    iso_utc(
                        num2date(
                            float(value),
                            units=units,
                            calendar=str(getattr(time_var, "calendar", "standard")),
                            only_use_cftime_datetimes=False,
                        ).isoformat()
                    )
                    for value in values
                ]
                result = [value for value in parsed if value]
                return result or None
            except Exception:
                pass
    return None


def _wrf_geopotential_level_meters(ds: Any, level_index: int | None, time_index: int | None) -> list[float] | None:
    if not all(name in ds.variables for name in ("PH", "PHB")):
        return None
    try:
        ph = np.asarray(ds.variables["PH"][:], dtype=float)
        phb = np.asarray(ds.variables["PHB"][:], dtype=float)
    except Exception:
        return None
    if ph.shape != phb.shape or ph.ndim != 4:
        return None
    time_size = ph.shape[0]
    selected_time = 0 if time_index is None else _bounded_index(time_index, time_size)
    z_stag = (ph[selected_time] + phb[selected_time]) / 9.80665
    if z_stag.shape[0] < 2:
        return None
    z_mass_asl = 0.5 * (z_stag[:-1] + z_stag[1:])
    levels = [float(np.nanmean(z_mass_asl[index])) for index in range(z_mass_asl.shape[0])]
    if level_index is None:
        return levels
    index = _bounded_index(level_index, len(levels))
    return [levels[index]]


def _wrf_level_meters(ds: Any, level_index: int | None, time_index: int | None = 0) -> list[float] | None:
    for name in ("height_m", "height", "z", "level", "bottom_top"):
        if name not in ds.variables:
            continue
        variable = ds.variables[name]
        dims = tuple(str(dim) for dim in getattr(variable, "dimensions", ()))
        if len(dims) != 1 or _dimension_kind(dims[0]) != "level":
            continue
        try:
            values = np.asarray(variable[:], dtype=float).ravel()
        except Exception:
            continue
        if not values.size:
            continue
        if level_index is None:
            return [float(value) for value in values]
        index = _bounded_index(level_index, values.size)
        return [float(values[index])]
    return _wrf_geopotential_level_meters(ds, level_index, time_index)


def load_near_surface_wind(
    path: str | Path,
    *,
    time_index: int | None = 0,
    level_index: int | None = 0,
) -> WRFWindField:
    """Extract near-surface wind from WRF/WRF-like NetCDF into a SpritzWRF object.

    Accepted variable combinations include:

    - ``XLAT``/``XLONG`` with ``U10``/``V10``
    - ``XLAT``/``XLONG`` with ``WSPD10``/``WDIR10``
    - CF-like ``latitude``/``longitude`` with ``eastward_wind``/``northward_wind``

    Four-dimensional wind variables are interpreted as time, vertical level,
    y, and x dimensions when WRF/CF dimension names are present.  ``None`` for
    ``time_index`` or ``level_index`` preserves the full corresponding axis.
    """
    if not netcdf_available():
        raise RuntimeError("netCDF4 is required to read WRF NetCDF files; install sprtz[netcdf]")
    from netCDF4 import Dataset  # type: ignore

    p = Path(path)
    with Dataset(p) as ds:
        def read2d(names: tuple[str, ...]) -> np.ndarray:
            for name in names:
                if name in ds.variables:
                    return _select_wrf_spatial_2d(
                        ds.variables[name],
                        time_index=time_index,
                        level_index=level_index,
                        path=p,
                    )
            raise KeyError(f"none of variables {names} found in WRF file {p}")

        def read_wind_component(names: tuple[str, ...]) -> np.ndarray:
            for name in names:
                if name in ds.variables:
                    variable = ds.variables[name]
                    selected = _select_wrf_spatial_2d(
                        variable,
                        time_index=time_index,
                        level_index=level_index,
                        path=p,
                    )
                    return _destagger_wrf_component(selected, variable)
            raise KeyError(f"none of variables {names} found in WRF file {p}")

        def read_coordinate(names: tuple[str, ...]) -> np.ndarray:
            for name in names:
                if name in ds.variables:
                    return _select_wrf_spatial_2d(
                        ds.variables[name],
                        time_index=0 if time_index is None else time_index,
                        level_index=0,
                        path=p,
                    )
            raise KeyError(f"none of variables {names} found in WRF file {p}")

        lat = read_coordinate(("XLAT", "XLAT_M", "lat", "latitude"))
        lon = read_coordinate(("XLONG", "XLONG_M", "lon", "longitude"))
        diagnostic_height_m: float | None = None
        u10m: np.ndarray | None = None
        v10m: np.ndarray | None = None
        if "U10" in ds.variables and "V10" in ds.variables:
            u10m = read2d(("U10",))
            v10m = read2d(("V10",))
        elif "WSPD10" in ds.variables and "WDIR10" in ds.variables:
            wspd10 = read2d(("WSPD10",))
            wdir10 = read2d(("WDIR10",))
            theta10 = np.deg2rad(270.0 - wdir10)
            u10m = wspd10 * np.cos(theta10)
            v10m = wspd10 * np.sin(theta10)
        has_model_level_wind = (
            any(
                name in ds.variables and _has_level_dimension(ds.variables[name])
                for name in ("eastward_wind", "u", "U")
            )
            and any(
                name in ds.variables and _has_level_dimension(ds.variables[name])
                for name in ("northward_wind", "v", "V")
            )
        )
        if level_index is None and has_model_level_wind:
            u = read_wind_component(("eastward_wind", "u", "U"))
            v = read_wind_component(("northward_wind", "v", "V"))
        elif u10m is not None and v10m is not None:
            u = u10m
            v = v10m
            diagnostic_height_m = 10.0
        else:
            u = read_wind_component(("eastward_wind", "u", "U"))
            v = read_wind_component(("northward_wind", "v", "V"))
        precipitation_rate = _select_precipitation_rate(ds, time_index, level_index, p)
        temperature_2m_c = _select_temperature_2m_c(ds, time_index, p)
        relative_humidity_2m = _select_relative_humidity_2m(ds, time_index, p, temperature_2m_c)
        attrs = {name: str(getattr(ds, name)) for name in ds.ncattrs()}
        if time_index is None:
            selected_datetimes = _selected_wrf_datetimes(ds)
            if selected_datetimes:
                attrs["time_datetime"] = selected_datetimes[0]
                attrs["time_datetimes"] = selected_datetimes
        else:
            selected_datetime = _selected_wrf_datetime(ds, time_index)
            if selected_datetime:
                attrs["time_datetime"] = selected_datetime
        attrs["time_index"] = "all" if time_index is None else str(time_index)
        attrs["level_index"] = "all" if level_index is None else str(level_index)
        level_meters = [diagnostic_height_m] if diagnostic_height_m is not None else _wrf_level_meters(ds, level_index, time_index)
        if level_meters:
            attrs["level_meters"] = level_meters
            attrs["level_meters_kind"] = "height_above_ground" if diagnostic_height_m is not None else "height_above_sea_level"
            attrs["level_meters_source"] = "diagnostic_10m_wind" if diagnostic_height_m is not None else "wrf_vertical_coordinate"
    return WRFWindField(
        lat,
        lon,
        u,
        v,
        p,
        time_index=0 if time_index is None else time_index,
        metadata=attrs,
        precipitation_rate=precipitation_rate,
        u10m=u10m,
        v10m=v10m,
        temperature_2m_c=temperature_2m_c,
        relative_humidity_2m=relative_humidity_2m,
    )


def describe_wrf_input(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    result: dict[str, Any] = {"component": "spritzwrf", "path": str(p), "exists": p.exists()}
    if not p.exists():
        return result
    result["size_bytes"] = p.stat().st_size
    try:
        from netCDF4 import Dataset  # type: ignore
    except Exception:
        result["netcdf"] = "netCDF4 not installed; metadata only"
        return result
    with Dataset(p) as ds:
        result["dimensions"] = {name: len(dim) for name, dim in ds.dimensions.items()}
        result["variables"] = sorted(ds.variables.keys())[:100]
        result["attrs"] = {name: str(getattr(ds, name)) for name in ds.ncattrs()}
    return result


def run(input_path: str | Path, output: str | Path) -> dict[str, Any]:
    result = describe_wrf_input(input_path)
    write_json(output, result)
    return result

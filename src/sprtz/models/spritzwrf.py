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

METEO_UNIPARTHENOPE_BASE = "https://data.meteo.uniparthenope.it/files/wrf5/d03/history"


@dataclass(frozen=True)
class WRFWindField:
    """Near-surface wind and precipitation field extracted from WRF or WRF-like NetCDF."""

    latitude: np.ndarray
    longitude: np.ndarray
    u: np.ndarray
    v: np.ndarray
    source_path: Path
    time_index: int = 0
    metadata: dict[str, Any] | None = None
    precipitation_rate: np.ndarray | None = None

    @property
    def wind_speed(self) -> np.ndarray:
        return np.hypot(self.u, self.v)

    @property
    def wind_from_direction(self) -> np.ndarray:
        # Meteorological direction from which the wind blows.
        return (270.0 - np.rad2deg(np.arctan2(self.v, self.u))) % 360.0


def meteo_uniparthenope_wrf_url(run_date: str | date | datetime, cycle_hour: int | str) -> str:
    """Return the canonical meteo@uniparthenope WRF5 d03 history URL.

    The public archive path used by the operational use cases is::

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
    return f"{METEO_UNIPARTHENOPE_BASE}/{d:%Y/%m/%d}/wrf5_d03_{ymd}Z{hh}00.nc"


def download_meteo_uniparthenope_wrf(
    destination_dir: str | Path,
    *,
    run_date: str | date | datetime,
    cycle_hour: int | str = 0,
    timeout_s: float = 120.0,
    force: bool = False,
) -> Path:
    """Download a WRF5 d03 NetCDF file from the meteo@uniparthenope archive.

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
    time_index: int,
    level_index: int,
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
        return _select_2d(arr, time_index)

    selected = arr
    remaining_dims = list(dims)
    for axis in range(len(dims) - 1, -1, -1):
        dim = dims[axis]
        lower = dim.lower()
        if lower in TIME_DIMENSIONS or lower.startswith("time"):
            selected = np.take(selected, _bounded_index(time_index, selected.shape[axis]), axis=axis)
            remaining_dims.pop(axis)
        elif lower in VERTICAL_DIMENSIONS:
            selected = np.take(selected, _bounded_index(level_index, selected.shape[axis]), axis=axis)
            remaining_dims.pop(axis)

    squeeze_axes = [
        axis
        for axis, dim in enumerate(remaining_dims)
        if selected.shape[axis] == 1 and dim.lower() not in Y_DIMENSIONS and dim.lower() not in X_DIMENSIONS
    ]
    for axis in reversed(squeeze_axes):
        selected = np.squeeze(selected, axis=axis)
        remaining_dims.pop(axis)

    if selected.ndim != 2:
        raise ValueError(
            f"variable {name} in {path} must resolve to a 2D y/x slice; "
            f"got dimensions {remaining_dims} with shape {selected.shape}"
        )
    return np.asarray(selected, dtype=float)


def _select_wrf_spatial_2d(variable: Any, *, time_index: int, level_index: int, path: Path) -> np.ndarray:
    arr = np.asarray(variable[:], dtype=float)
    dims = tuple(str(dim) for dim in getattr(variable, "dimensions", ()))
    name = str(getattr(variable, "name", "unknown"))
    return _select_wrf_spatial_2d_from_array(arr, dims, name, time_index=time_index, level_index=level_index, path=path)


def _select_precipitation_rate(ds: Any, time_index: int, level_index: int, path: Path) -> np.ndarray | None:
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
    index = _bounded_index(time_index, arr.shape[time_axis])
    current_arr = np.take(arr, index, axis=time_axis)
    current_dims = tuple(dim for axis, dim in enumerate(accum_dims) if axis != time_axis)
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


def load_near_surface_wind(path: str | Path, *, time_index: int = 0, level_index: int = 0) -> WRFWindField:
    """Extract near-surface wind from WRF/WRF-like NetCDF into a SpritzWRF object.

    Accepted variable combinations include:

    - ``XLAT``/``XLONG`` with ``U10``/``V10``
    - ``XLAT``/``XLONG`` with ``WSPD10``/``WDIR10``
    - CF-like ``latitude``/``longitude`` with ``eastward_wind``/``northward_wind``

    Four-dimensional wind variables are interpreted as time, vertical level,
    y, and x dimensions when WRF/CF dimension names are present.  ``level_index``
    selects the vertical level independently from ``time_index``.
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

        lat = read2d(("XLAT", "XLAT_M", "lat", "latitude"))
        lon = read2d(("XLONG", "XLONG_M", "lon", "longitude"))
        if "U10" in ds.variables and "V10" in ds.variables:
            u = read2d(("U10",))
            v = read2d(("V10",))
        elif "WSPD10" in ds.variables and "WDIR10" in ds.variables:
            wspd = read2d(("WSPD10",))
            wdir = read2d(("WDIR10",))
            theta = np.deg2rad(270.0 - wdir)
            u = wspd * np.cos(theta)
            v = wspd * np.sin(theta)
        else:
            u = read2d(("eastward_wind", "u", "U"))
            v = read2d(("northward_wind", "v", "V"))
        precipitation_rate = _select_precipitation_rate(ds, time_index, level_index, p)
        attrs = {name: str(getattr(ds, name)) for name in ds.ncattrs()}
        selected_datetime = _selected_wrf_datetime(ds, time_index)
        if selected_datetime:
            attrs["time_datetime"] = selected_datetime
        attrs["time_index"] = str(time_index)
        attrs["level_index"] = str(level_index)
    return WRFWindField(
        lat,
        lon,
        u,
        v,
        p,
        time_index=time_index,
        metadata=attrs,
        precipitation_rate=precipitation_rate,
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

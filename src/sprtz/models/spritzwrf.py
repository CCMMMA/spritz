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
from sprtz.io.netcdf_cf import available as netcdf_available

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


def _select_2d(arr: np.ndarray, time_index: int) -> np.ndarray:
    arr = np.asarray(arr, dtype=float)
    while arr.ndim > 2:
        arr = arr[time_index if arr.shape[0] > time_index else 0]
    return arr


def _select_precipitation_rate(ds: Any, time_index: int) -> np.ndarray | None:
    """Return a WRF precipitation-rate proxy in mm h-1 when variables exist."""

    def read_raw(name: str) -> np.ndarray | None:
        if name not in ds.variables:
            return None
        return np.asarray(ds.variables[name][:], dtype=float)

    for name in ("RAINRATE", "PRECIP_RATE", "precipitation_rate", "precip_rate"):
        raw = read_raw(name)
        if raw is not None:
            return _select_2d(raw, time_index)

    accum = None
    for name in ("RAINC", "RAINNC", "RAINSH"):
        raw = read_raw(name)
        if raw is not None:
            accum = raw if accum is None else accum + raw
    if accum is None:
        return None
    arr = np.asarray(accum, dtype=float)
    if arr.ndim < 3:
        return np.maximum(_select_2d(arr, time_index), 0.0)
    index = min(max(time_index, 0), arr.shape[0] - 1)
    current = _select_2d(arr, index)
    if index == 0:
        return np.maximum(current, 0.0)
    previous = _select_2d(arr, index - 1)
    return np.maximum(current - previous, 0.0)


def load_near_surface_wind(path: str | Path, *, time_index: int = 0) -> WRFWindField:
    """Extract near-surface wind from WRF/WRF-like NetCDF into a SpritzWRF object.

    Accepted variable combinations include:

    - ``XLAT``/``XLONG`` with ``U10``/``V10``
    - ``XLAT``/``XLONG`` with ``WSPD10``/``WDIR10``
    - CF-like ``latitude``/``longitude`` with ``eastward_wind``/``northward_wind``
    """
    if not netcdf_available():
        raise RuntimeError("netCDF4 is required to read WRF NetCDF files; install sprtz[netcdf]")
    from netCDF4 import Dataset  # type: ignore

    p = Path(path)
    with Dataset(p) as ds:
        def read2d(names: tuple[str, ...]) -> np.ndarray:
            for name in names:
                if name in ds.variables:
                    return _select_2d(np.asarray(ds.variables[name][:], dtype=float), time_index)
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
        precipitation_rate = _select_precipitation_rate(ds, time_index)
        attrs = {name: str(getattr(ds, name)) for name in ds.ncattrs()}
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

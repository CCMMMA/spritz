from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from sprtz.exceptions import DataFormatError
from sprtz.io.jsonio import read_json, write_json


def available() -> bool:
    try:
        import netCDF4  # noqa: F401
    except Exception:
        return False
    return True


def _as_array(data: Any) -> np.ndarray:
    arr = np.asarray(data, dtype=float)
    if arr.size == 0:
        raise DataFormatError("NetCDF variable data must not be empty")
    return arr


def write_cf_meteorology(path: str | Path, meteo: dict[str, Any]) -> None:
    """Write SpritzMet-like meteorology using a compact CF-inspired NetCDF schema.

    When netCDF4 is not installed, a JSON file with the same logical schema is
    written so tests and lightweight deployments remain deterministic.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if not available():
        write_json(p, {"format": "cf-json-fallback", **meteo})
        return
    from netCDF4 import Dataset  # type: ignore

    u = _as_array(meteo.get("u", [[0.0]]))
    v = _as_array(meteo.get("v", [[0.0]]))
    if u.shape != v.shape or u.ndim != 2:
        raise DataFormatError("meteorology u/v must be two-dimensional arrays with matching shapes")
    temp = _as_array(meteo.get("temperature", np.full(u.shape, 293.15)))
    mh = _as_array(meteo.get("mixing_height", np.full(u.shape, 1000.0)))
    if temp.shape != u.shape or mh.shape != u.shape:
        raise DataFormatError("temperature and mixing_height must match u/v shape")

    with Dataset(p, "w") as ds:
        ny, nx = u.shape
        ds.createDimension("time", 1)
        ds.createDimension("y", ny)
        ds.createDimension("x", nx)
        ds.Conventions = "CF-1.8"
        ds.title = "Sprtz SpritzMet meteorology"
        ds.featureType = "grid"
        x = ds.createVariable("x", "f8", ("x",))
        y = ds.createVariable("y", "f8", ("y",))
        x.standard_name = "projection_x_coordinate"
        y.standard_name = "projection_y_coordinate"
        x.units = y.units = "m"
        x[:] = np.arange(nx, dtype=float)
        y[:] = np.arange(ny, dtype=float)
        for name, values, standard_name, units in [
            ("eastward_wind", u, "eastward_wind", "m s-1"),
            ("northward_wind", v, "northward_wind", "m s-1"),
            ("air_temperature", temp, "air_temperature", "K"),
            ("atmosphere_boundary_layer_thickness", mh, "atmosphere_boundary_layer_thickness", "m"),
        ]:
            var = ds.createVariable(name, "f8", ("time", "y", "x"), zlib=True)
            var.standard_name = standard_name
            var.units = units
            var[0, :, :] = values


def read_cf_meteorology(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if p.suffix.lower() in {".json", ".jsn"} or not available():
        data = read_json(p)
        if data.get("format") == "cf-json-fallback":
            data = {k: v for k, v in data.items() if k != "format"}
        return data
    from netCDF4 import Dataset  # type: ignore

    with Dataset(p) as ds:
        def read_var(*names: str, default: float) -> list[list[float]]:
            for name in names:
                if name in ds.variables:
                    values = np.asarray(ds.variables[name][:], dtype=float)
                    if values.ndim == 3:
                        values = values[0]
                    return values.tolist()
            shape = (len(ds.dimensions.get("y", [])), len(ds.dimensions.get("x", [])))
            return np.full(shape, default, dtype=float).tolist()

        return {
            "component": "spritzmet",
            "format": "NetCDF-CF",
            "u": read_var("eastward_wind", "u", default=0.0),
            "v": read_var("northward_wind", "v", default=0.0),
            "temperature": read_var("air_temperature", "temperature", default=293.15),
            "mixing_height": read_var("atmosphere_boundary_layer_thickness", "mixing_height", default=1000.0),
        }


def write_cf_concentration(path: str | Path, rows: list[dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if not available():
        write_json(p, {"format": "cf-json-fallback", "component": "concentration", "rows": rows})
        return
    from netCDF4 import Dataset  # type: ignore

    times = sorted({float(row.get("time", 0.0)) for row in rows}) or [0.0]
    receptors = list(dict.fromkeys(str(row.get("receptor", f"R{i}")) for i, row in enumerate(rows)))
    time_index = {value: i for i, value in enumerate(times)}
    receptor_index = {value: i for i, value in enumerate(receptors)}
    by_receptor: dict[str, dict[str, Any]] = {}
    for row in rows:
        by_receptor.setdefault(str(row.get("receptor", "")), row)

    with Dataset(p, "w") as ds:
        ds.createDimension("time", len(times))
        ds.createDimension("receptor", len(receptors))
        ds.Conventions = "CF-1.8"
        ds.title = "Sprtz receptor concentration"
        time = ds.createVariable("time", "f8", ("time",))
        time.units = "seconds since simulation start"
        time.long_name = "model output time"
        time[:] = np.asarray(times, dtype=float)
        rec = ds.createVariable("receptor", "i4", ("receptor",))
        rec.long_name = "receptor index"
        rec[:] = np.arange(len(receptors), dtype=np.int32)
        rec_id = ds.createVariable("receptor_id", str, ("receptor",))
        rec_id.long_name = "receptor identifier"
        rec_id[:] = np.asarray(receptors, dtype=object)
        x = ds.createVariable("x", "f8", ("receptor",), zlib=True)
        y = ds.createVariable("y", "f8", ("receptor",), zlib=True)
        x.units = y.units = "m"
        x.long_name = "projection_x_coordinate"
        y.long_name = "projection_y_coordinate"
        x[:] = [float(by_receptor.get(receptor, {}).get("x", 0.0)) for receptor in receptors]
        y[:] = [float(by_receptor.get(receptor, {}).get("y", 0.0)) for receptor in receptors]
        for name, units, standard_name in [
            ("concentration", "g m-3", "mass_concentration_of_air_pollutant_in_air"),
            ("dry_flux", "g m-2 s-1", "dry_deposition_flux"),
            ("wet_flux", "g m-2 s-1", "wet_deposition_flux"),
        ]:
            var = ds.createVariable(name, "f8", ("time", "receptor"), zlib=True)
            var.units = units
            var.long_name = standard_name
            values = np.full((len(times), len(receptors)), np.nan, dtype=float)
            for row in rows:
                ti = time_index[float(row.get("time", 0.0))]
                ri = receptor_index[str(row.get("receptor", ""))]
                values[ti, ri] = float(row.get(name, 0.0))
            var[:, :] = values
        if any("latitude" in row and "longitude" in row for row in rows):
            for name, units, long_name in [
                ("latitude", "degrees_north", "receptor latitude"),
                ("longitude", "degrees_east", "receptor longitude"),
            ]:
                var = ds.createVariable(name, "f8", ("receptor",), zlib=True)
                var.units = units
                var.long_name = long_name
                var[:] = [float(by_receptor.get(receptor, {}).get(name, np.nan)) for receptor in receptors]


def read_cf_concentration(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    if p.suffix.lower() in {".json", ".jsn"} or not available():
        data = read_json(p)
        if "rows" in data:
            return list(data["rows"])
        raise DataFormatError(f"not a concentration NetCDF/JSON file: {p}")
    from netCDF4 import Dataset  # type: ignore

    with Dataset(p) as ds:
        c_all = np.asarray(ds.variables["concentration"][:], dtype=float)
        if c_all.ndim == 1:
            c_all = c_all[np.newaxis, :]
        dry_all = np.asarray(ds.variables["dry_flux"][:], dtype=float) if "dry_flux" in ds.variables else np.zeros_like(c_all)
        wet_all = np.asarray(ds.variables["wet_flux"][:], dtype=float) if "wet_flux" in ds.variables else np.zeros_like(c_all)
        if dry_all.ndim == 1:
            dry_all = dry_all[np.newaxis, :]
        if wet_all.ndim == 1:
            wet_all = wet_all[np.newaxis, :]
        times = np.asarray(ds.variables["time"][:], dtype=float) if "time" in ds.variables else np.asarray([0.0])
        x = np.asarray(ds.variables.get("x", np.zeros(c_all.shape[1], dtype=float))[:], dtype=float)
        y = np.asarray(ds.variables.get("y", np.zeros(c_all.shape[1], dtype=float))[:], dtype=float)
        if x.ndim == 2:
            x = x[0]
        if y.ndim == 2:
            y = y[0]
        lat = np.asarray(ds.variables["latitude"][:], dtype=float) if "latitude" in ds.variables else None
        lon = np.asarray(ds.variables["longitude"][:], dtype=float) if "longitude" in ds.variables else None
        if "receptor_id" in ds.variables:
            receptor_ids = [str(value) for value in ds.variables["receptor_id"][:]]
        else:
            receptor_ids = [f"R{i}" for i in range(c_all.shape[1])]
        rows: list[dict[str, Any]] = []
        for ti, time_value in enumerate(times):
            for i in range(c_all.shape[1]):
                rows.append(
                    {
                        "time": float(time_value),
                        "receptor": receptor_ids[i],
                        "x": float(x[i]),
                        "y": float(y[i]),
                        "concentration": float(c_all[ti, i]),
                        "dry_flux": float(dry_all[ti, i]),
                        "wet_flux": float(wet_all[ti, i]),
                        **(
                            {}
                            if lat is None or lon is None or np.isnan(lat[i]) or np.isnan(lon[i])
                            else {"latitude": float(lat[i]), "longitude": float(lon[i])}
                        ),
                    }
                )
        return rows

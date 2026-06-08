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
    precip = _as_array(meteo.get("precipitation_rate", np.zeros(u.shape, dtype=float)))
    fmc = _as_array(meteo.get("fmc", np.full(u.shape, 0.08, dtype=float)))
    if temp.shape != u.shape or mh.shape != u.shape or precip.shape != u.shape or fmc.shape != u.shape:
        raise DataFormatError("temperature, mixing_height, and precipitation_rate must match u/v shape")

    with Dataset(p, "w") as ds:
        ny, nx = u.shape
        ds.createDimension("time", 1)
        ds.createDimension("y", ny)
        ds.createDimension("x", nx)
        ds.Conventions = "CF-1.8"
        ds.title = "Spritz SpritzMet meteorology"
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
            ("precipitation_rate", precip, "precipitation_rate", "mm h-1"),
            ("fmc", fmc, "", "1"),
        ]:
            var = ds.createVariable(name, "f8", ("time", "y", "x"), zlib=True)
            if standard_name:
                var.standard_name = standard_name
            var.units = units
            if name == "fmc":
                var.long_name = "dead fine fuel moisture content"
                var.valid_range = np.asarray([0.01, 0.40], dtype=np.float32)
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
            "precipitation_rate": read_var("precipitation_rate", "rainfall_rate", default=0.0),
            "fmc": read_var("fmc", default=0.08),
        }


def _field_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    marked = [row for row in rows if str(row.get("output_kind", "")).lower() == "field"]
    return marked or rows


def _concentration_field(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    selected = _field_rows(rows)
    if not selected:
        return None
    times = sorted({float(row.get("time", 0.0)) for row in selected})
    xs = sorted({float(row.get("x", 0.0)) for row in selected})
    ys = sorted({float(row.get("y", 0.0)) for row in selected})
    zs = sorted({float(row.get("z", 0.0)) for row in selected})
    expected = len(times) * len(zs) * len(ys) * len(xs)
    coordinate_keys = {
        (
            float(row.get("time", 0.0)),
            float(row.get("z", 0.0)),
            float(row.get("y", 0.0)),
            float(row.get("x", 0.0)),
        )
        for row in selected
    }
    if len(coordinate_keys) != expected:
        return None
    indexes = {
        "time": {value: i for i, value in enumerate(times)},
        "z": {value: i for i, value in enumerate(zs)},
        "y": {value: i for i, value in enumerate(ys)},
        "x": {value: i for i, value in enumerate(xs)},
    }
    payload: dict[str, Any] = {"time": times, "x": xs, "y": ys, "z": zs}
    for name in ("concentration", "dry_flux", "wet_flux"):
        values = np.full((len(times), len(zs), len(ys), len(xs)), np.nan, dtype=float)
        for row in selected:
            ti = indexes["time"][float(row.get("time", 0.0))]
            zi = indexes["z"][float(row.get("z", 0.0))]
            yi = indexes["y"][float(row.get("y", 0.0))]
            xi = indexes["x"][float(row.get("x", 0.0))]
            values[ti, zi, yi, xi] = float(row.get(name, 0.0))
        if np.isnan(values).any():
            return None
        payload[name] = values
    return payload


def write_cf_concentration(path: str | Path, rows: list[dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    field = _concentration_field(rows)
    if not available():
        payload: dict[str, Any] = {
            "format": "cf-json-fallback",
            "component": "concentration",
            "rows": rows,
        }
        if field is not None:
            payload["field"] = {
                key: value.tolist() if isinstance(value, np.ndarray) else value
                for key, value in field.items()
            }
        write_json(p, payload)
        return
    from netCDF4 import Dataset  # type: ignore

    times = sorted({float(row.get("time", 0.0)) for row in rows}) or [0.0]
    receptors = list(dict.fromkeys(str(row.get("receptor", f"R{i}")) for i, row in enumerate(rows)))
    time_index = {value: i for i, value in enumerate(times)}
    receptor_index = {value: i for i, value in enumerate(receptors)}
    by_receptor: dict[str, dict[str, Any]] = {}
    datetime_by_time: dict[float, str] = {}
    for row in rows:
        by_receptor.setdefault(str(row.get("receptor", "")), row)
        if row.get("datetime"):
            datetime_by_time.setdefault(float(row.get("time", 0.0)), str(row["datetime"]))

    with Dataset(p, "w") as ds:
        ds.createDimension("time", len(times))
        ds.createDimension("receptor", len(receptors))
        ds.Conventions = "CF-1.8"
        ds.title = "Spritz receptor concentration"
        time = ds.createVariable("time", "f8", ("time",))
        time.units = "seconds since simulation start"
        time.long_name = "model output time"
        time[:] = np.asarray(times, dtype=float)
        if datetime_by_time:
            time_dt = ds.createVariable("time_datetime", str, ("time",))
            time_dt.long_name = "ISO-8601 model output datetime"
            time_dt[:] = np.asarray([datetime_by_time.get(value, "") for value in times], dtype=object)
        rec = ds.createVariable("receptor", "i4", ("receptor",))
        rec.long_name = "receptor index"
        rec[:] = np.arange(len(receptors), dtype=np.int32)
        rec_id = ds.createVariable("receptor_id", str, ("receptor",))
        rec_id.long_name = "receptor identifier"
        rec_id[:] = np.asarray(receptors, dtype=object)
        x = ds.createVariable("x", "f8", ("receptor",), zlib=True)
        y = ds.createVariable("y", "f8", ("receptor",), zlib=True)
        z = ds.createVariable("z", "f8", ("receptor",), zlib=True)
        x.units = y.units = "m"
        z.units = "m"
        x.long_name = "projection_x_coordinate"
        y.long_name = "projection_y_coordinate"
        z.long_name = "receptor height above local ground"
        x[:] = [float(by_receptor.get(receptor, {}).get("x", 0.0)) for receptor in receptors]
        y[:] = [float(by_receptor.get(receptor, {}).get("y", 0.0)) for receptor in receptors]
        z[:] = [float(by_receptor.get(receptor, {}).get("z", 0.0)) for receptor in receptors]
        kind = ds.createVariable("output_kind", str, ("receptor",))
        kind.long_name = "concentration output receptor kind"
        kind[:] = np.asarray(
            [str(by_receptor.get(receptor, {}).get("output_kind", "receptor")) for receptor in receptors],
            dtype=object,
        )
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
                var[:] = [
                    float(by_receptor.get(receptor, {}).get(name, np.nan))
                    for receptor in receptors
                ]
        if field is not None:
            ds.createDimension("field_z", len(field["z"]))
            ds.createDimension("field_y", len(field["y"]))
            ds.createDimension("field_x", len(field["x"]))
            for name, values, units, long_name in [
                ("field_x", field["x"], "m", "model grid x coordinate"),
                ("field_y", field["y"], "m", "model grid y coordinate"),
                ("field_z", field["z"], "m", "model grid height above local ground"),
            ]:
                var = ds.createVariable(name, "f8", (name,), zlib=True)
                var.units = units
                var.long_name = long_name
                var[:] = np.asarray(values, dtype=float)
            for name, units, long_name in [
                ("concentration_field", "g m-3", "gridded mass concentration"),
                ("dry_flux_field", "g m-2 s-1", "gridded dry deposition flux"),
                ("wet_flux_field", "g m-2 s-1", "gridded wet deposition flux"),
            ]:
                source_name = name.removesuffix("_field")
                var = ds.createVariable(
                    name,
                    "f8",
                    ("time", "field_z", "field_y", "field_x"),
                    zlib=True,
                )
                var.units = units
                var.long_name = long_name
                var.coordinates = "time field_z field_y field_x"
                var[:, :, :, :] = np.asarray(field[source_name], dtype=float)


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
        if "time_datetime" in ds.variables:
            datetimes = [str(value) for value in ds.variables["time_datetime"][:]]
        else:
            datetimes = [""] * len(times)
        x = np.asarray(ds.variables.get("x", np.zeros(c_all.shape[1], dtype=float))[:], dtype=float)
        y = np.asarray(ds.variables.get("y", np.zeros(c_all.shape[1], dtype=float))[:], dtype=float)
        z = np.asarray(ds.variables.get("z", np.zeros(c_all.shape[1], dtype=float))[:], dtype=float)
        if x.ndim == 2:
            x = x[0]
        if y.ndim == 2:
            y = y[0]
        if z.ndim == 2:
            z = z[0]
        lat = np.asarray(ds.variables["latitude"][:], dtype=float) if "latitude" in ds.variables else None
        lon = np.asarray(ds.variables["longitude"][:], dtype=float) if "longitude" in ds.variables else None
        if "receptor_id" in ds.variables:
            receptor_ids = [str(value) for value in ds.variables["receptor_id"][:]]
        else:
            receptor_ids = [f"R{i}" for i in range(c_all.shape[1])]
        if "output_kind" in ds.variables:
            output_kinds = [str(value) for value in ds.variables["output_kind"][:]]
        else:
            output_kinds = ["receptor"] * c_all.shape[1]
        rows: list[dict[str, Any]] = []
        for ti, time_value in enumerate(times):
            for i in range(c_all.shape[1]):
                rows.append(
                    {
                        "time": float(time_value),
                        **({} if not datetimes[ti] else {"datetime": datetimes[ti]}),
                        "receptor": receptor_ids[i],
                        "output_kind": output_kinds[i],
                        "x": float(x[i]),
                        "y": float(y[i]),
                        "z": float(z[i]),
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

from __future__ import annotations

from datetime import datetime, timezone
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


def annotate_local_x(var: Any) -> None:
    var.standard_name = "projection_x_coordinate"
    var.long_name = getattr(var, "long_name", "local projection x coordinate")
    var.units = "m"
    var.axis = "X"


def annotate_local_y(var: Any) -> None:
    var.standard_name = "projection_y_coordinate"
    var.long_name = getattr(var, "long_name", "local projection y coordinate")
    var.units = "m"
    var.axis = "Y"


def annotate_latitude(var: Any) -> None:
    var.standard_name = "latitude"
    var.long_name = "latitude"
    var.units = "degrees_north"


def annotate_longitude(var: Any) -> None:
    var.standard_name = "longitude"
    var.long_name = "longitude"
    var.units = "degrees_east"


def annotate_height(var: Any, *, long_name: str = "height above local ground") -> None:
    var.standard_name = "height"
    var.long_name = long_name
    var.units = "m"
    var.axis = "Z"
    var.positive = "up"


def annotate_surface_altitude(var: Any) -> None:
    var.standard_name = "surface_altitude"
    var.long_name = "surface altitude above mean sea level"
    var.units = "m"
    var.positive = "up"
    var.coordinates = "latitude longitude"


def _write_relative_time_coordinate(ds: Any, times: list[float] | tuple[float, ...]) -> Any:
    time = ds.createVariable("time", "f8", ("time",))
    time.standard_name = "time"
    time.long_name = "model output time"
    time.axis = "T"
    time.calendar = "proleptic_gregorian"
    time.units = "seconds since 1970-01-01 00:00:00 UTC"
    time.comment = "No absolute UTC datetime was available; value is seconds since simulation start."
    time[:] = np.asarray(times, dtype=float)
    return time


def set_spatiotemporal_coordinates(var: Any, dims: tuple[str, ...] | list[str]) -> None:
    names = list(dims)
    coords: list[str] = []
    if "time" in names:
        coords.append("time")
    if "z" in names:
        coords.append("z")
    if "field_z" in names:
        coords.append("field_z")
    if "latitude" not in names and ("y" in names or "field_y" in names):
        coords.append("latitude" if "y" in names else "field_latitude")
    if "longitude" not in names and ("x" in names or "field_x" in names):
        coords.append("longitude" if "x" in names else "field_longitude")
    if coords:
        var.coordinates = " ".join(coords)


def _as_array(data: Any) -> np.ndarray:
    arr = np.asarray(data, dtype=float)
    if arr.size == 0:
        raise DataFormatError("NetCDF variable data must not be empty")
    return arr


def _as_wind_4d(data: Any, *, name: str) -> np.ndarray:
    arr = _as_array(data)
    if arr.ndim == 2:
        return arr[np.newaxis, np.newaxis, :, :]
    if arr.ndim == 3:
        return arr[:, np.newaxis, :, :]
    if arr.ndim == 4:
        return arr
    raise DataFormatError(f"meteorology {name} must be shaped as y,x; time,y,x; or time,z,y,x")


def _as_surface_3d(data: Any, *, name: str, shape: tuple[int, int, int]) -> np.ndarray:
    arr = _as_array(data)
    ntime, ny, nx = shape
    if arr.ndim == 2:
        arr = arr[np.newaxis, :, :]
    elif arr.ndim != 3:
        raise DataFormatError(f"meteorology {name} must be shaped as y,x or time,y,x")
    if arr.shape == (1, ny, nx) and ntime > 1:
        arr = np.repeat(arr, ntime, axis=0)
    if arr.shape != shape:
        raise DataFormatError(f"meteorology {name} shape {arr.shape} must match time/y/x shape {shape}")
    return arr


def _surface_2d(values: np.ndarray, *, name: str) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    if arr.ndim == 4:
        return arr[0, 0, :, :]
    if arr.ndim == 3:
        return arr[0, :, :]
    if arr.ndim == 2:
        return arr
    raise DataFormatError(f"meteorology {name} cannot be reduced to a 2D surface slice")


def parse_utc_datetime(value: Any) -> datetime | None:
    """Parse a UTC datetime from common Sprtz/CF metadata strings."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    text = text.replace("_", "T")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def iso_utc(value: Any) -> str | None:
    dt = parse_utc_datetime(value)
    if dt is None:
        return None
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def cf_time_units(value: Any) -> str | None:
    dt = parse_utc_datetime(value)
    if dt is None:
        return None
    return f"seconds since {dt:%Y-%m-%d %H:%M:%S} UTC"


def write_cf_time_coordinate(ds: Any, datetimes: list[Any] | tuple[Any, ...] | np.ndarray | None = None) -> Any:
    """Create a CF-compliant time coordinate when absolute UTC times are known."""
    ntime = len(ds.dimensions["time"])
    time = ds.createVariable("time", "f8", ("time",))
    time.standard_name = "time"
    time.long_name = "time"
    time.axis = "T"
    time.calendar = "proleptic_gregorian"
    raw_datetimes = [] if datetimes is None else list(datetimes)
    parsed = [parse_utc_datetime(value) for value in raw_datetimes]
    parsed = [value for value in parsed if value is not None]
    if parsed:
        base = parsed[0]
        time.units = f"seconds since {base:%Y-%m-%d %H:%M:%S} UTC"
        padded = parsed[:ntime]
        if len(padded) < ntime:
            padded.extend([padded[-1]] * (ntime - len(padded)))
        values = [(value - base).total_seconds() for value in padded]
        time[:] = np.asarray(values, dtype=float)
        time_dt = ds.createVariable("time_datetime", str, ("time",))
        time_dt.long_name = "ISO-8601 UTC time"
        time_dt[:] = np.asarray(
            [value.isoformat(timespec="seconds").replace("+00:00", "Z") for value in padded],
            dtype=object,
        )
    else:
        time.units = "seconds since 1970-01-01 00:00:00 UTC"
        time.comment = "No absolute UTC datetime was available; value is an ordinal timestep."
        time[:] = np.arange(ntime, dtype=float)
    return time


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

    u = _as_wind_4d(meteo.get("u", meteo.get("eastward_wind", [[0.0]])), name="u")
    v = _as_wind_4d(meteo.get("v", meteo.get("northward_wind", [[0.0]])), name="v")
    if u.shape != v.shape:
        raise DataFormatError("meteorology u/v arrays must have matching shapes")
    wind_speed = np.hypot(u, v)
    wind_from_direction = (270.0 - np.rad2deg(np.arctan2(v, u))) % 360.0
    ntime, nz, ny, nx = u.shape
    surface_shape = (ntime, ny, nx)
    grid = meteo.get("grid", {}) if isinstance(meteo.get("grid", {}), dict) else {}
    temp = _as_surface_3d(meteo.get("temperature", np.full((ny, nx), 293.15)), name="temperature", shape=surface_shape)
    mh = _as_surface_3d(meteo.get("mixing_height", np.full((ny, nx), 1000.0)), name="mixing_height", shape=surface_shape)
    precip = _as_surface_3d(
        meteo.get("precipitation_rate", np.zeros((ny, nx), dtype=float)),
        name="precipitation_rate",
        shape=surface_shape,
    )
    fmc = _as_surface_3d(meteo.get("fmc", np.full((ny, nx), 0.08, dtype=float)), name="fmc", shape=surface_shape)

    with Dataset(p, "w") as ds:
        ds.createDimension("time", ntime)
        ds.createDimension("z", nz)
        ds.createDimension("y", ny)
        ds.createDimension("x", nx)
        ds.Conventions = "CF-1.8"
        ds.title = "Spritz SpritzMet meteorology"
        ds.featureType = "grid"
        metadata = meteo.get("metadata", {}) if isinstance(meteo.get("metadata", {}), dict) else {}
        time_candidates = (
            meteo.get("time_datetime")
            or meteo.get("valid_datetime_utc")
            or metadata.get("valid_datetime_utc")
            or metadata.get("simulation_start_datetime")
            or metadata.get("weather_start_datetime")
        )
        if isinstance(time_candidates, str) or time_candidates is None:
            time_values = [time_candidates] if time_candidates else None
        else:
            time_values = list(time_candidates)
        write_cf_time_coordinate(ds, time_values)
        x = ds.createVariable("x", "f8", ("x",))
        y = ds.createVariable("y", "f8", ("y",))
        annotate_local_x(x)
        annotate_local_y(y)
        x_values = float(grid.get("x0", 0.0)) + np.arange(nx, dtype=float) * float(grid.get("dx", 1.0))
        y_values = float(grid.get("y0", 0.0)) + np.arange(ny, dtype=float) * float(grid.get("dy", 1.0))
        x[:] = x_values
        y[:] = y_values
        z = ds.createVariable("z", "f8", ("z",))
        annotate_height(z, long_name="height above ground")
        z[:] = np.asarray(meteo.get("z", meteo.get("height_m", [10.0] * nz)), dtype=float)
        center_lat = metadata.get("center_lat")
        center_lon = metadata.get("center_lon")
        if center_lat is not None and center_lon is not None:
            try:
                from pyproj import CRS, Transformer

                local = CRS.from_proj4(
                    f"+proj=aeqd +lat_0={float(center_lat):.12f} +lon_0={float(center_lon):.12f} "
                    "+datum=WGS84 +units=m +no_defs"
                )
                transformer = Transformer.from_crs(local, CRS.from_epsg(4326), always_xy=True)
                xx, yy = np.meshgrid(x_values, y_values)
                lon_values, lat_values = transformer.transform(xx, yy)
                lat = ds.createVariable("latitude", "f8", ("y", "x"), zlib=True)
                lon = ds.createVariable("longitude", "f8", ("y", "x"), zlib=True)
                annotate_latitude(lat)
                annotate_longitude(lon)
                lat[:, :] = np.asarray(lat_values, dtype=float)
                lon[:, :] = np.asarray(lon_values, dtype=float)
                ds.center_latitude = float(center_lat)
                ds.center_longitude = float(center_lon)
            except Exception:
                pass
        for name, values, standard_name, units in [
            ("eastward_wind", u, "eastward_wind", "m s-1"),
            ("northward_wind", v, "northward_wind", "m s-1"),
            ("wind_speed", wind_speed, "wind_speed", "m s-1"),
            ("wind_from_direction", wind_from_direction, "wind_from_direction", "degree"),
            ("air_temperature", temp, "air_temperature", "K"),
            ("atmosphere_boundary_layer_thickness", mh, "atmosphere_boundary_layer_thickness", "m"),
            ("precipitation_rate", precip, "precipitation_rate", "mm h-1"),
            ("fmc", fmc, "", "1"),
        ]:
            dims = (
                ("time", "z", "y", "x")
                if name in {"eastward_wind", "northward_wind", "wind_speed", "wind_from_direction"}
                else ("time", "y", "x")
            )
            var = ds.createVariable(name, "f8", dims, zlib=True)
            if standard_name:
                var.standard_name = standard_name
            var.units = units
            set_spatiotemporal_coordinates(var, dims)
            if name == "fmc":
                var.long_name = "dead fine fuel moisture content"
                var.valid_range = np.asarray([0.01, 0.40], dtype=np.float32)
            var[:] = values


def read_cf_meteorology(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if p.suffix.lower() in {".json", ".jsn"} or not available():
        data = read_json(p)
        if data.get("format") == "cf-json-fallback":
            data = {k: v for k, v in data.items() if k != "format"}
        return data
    from netCDF4 import Dataset  # type: ignore

    with Dataset(p) as ds:
        def read_var(*names: str, default: float) -> list[Any]:
            for name in names:
                if name in ds.variables:
                    values = np.asarray(ds.variables[name][:], dtype=float)
                    return values.tolist()
            shape = (len(ds.dimensions.get("y", [])), len(ds.dimensions.get("x", [])))
            return np.full(shape, default, dtype=float).tolist()
        result = {
            "component": "spritzmet",
            "format": "NetCDF-CF",
            "u": read_var("eastward_wind", "u", default=0.0),
            "v": read_var("northward_wind", "v", default=0.0),
            "temperature": read_var("air_temperature", "temperature", default=293.15),
            "mixing_height": read_var("atmosphere_boundary_layer_thickness", "mixing_height", default=1000.0),
            "precipitation_rate": read_var("precipitation_rate", "rainfall_rate", default=0.0),
            "fmc": read_var("fmc", default=0.08),
        }
        if "U10M" in ds.variables:
            result["u10m"] = np.asarray(ds.variables["U10M"][:], dtype=float).tolist()
        if "V10M" in ds.variables:
            result["v10m"] = np.asarray(ds.variables["V10M"][:], dtype=float).tolist()
        if "wind_speed_10m" in ds.variables:
            result["wind_speed_10m"] = np.asarray(ds.variables["wind_speed_10m"][:], dtype=float).tolist()
        if "wind_from_direction_10m" in ds.variables:
            result["wind_from_direction_10m"] = np.asarray(ds.variables["wind_from_direction_10m"][:], dtype=float).tolist()
        if "time" in ds.variables:
            result["time"] = np.asarray(ds.variables["time"][:], dtype=float).tolist()
            result["time_units"] = str(getattr(ds.variables["time"], "units", ""))
        if "time_datetime" in ds.variables:
            result["time_datetime"] = [str(value) for value in ds.variables["time_datetime"][:]]
        for name in ("x", "y", "z"):
            if name in ds.variables:
                result[name] = np.asarray(ds.variables[name][:], dtype=float).tolist()
                result[f"{name}_units"] = str(getattr(ds.variables[name], "units", ""))
                result[f"{name}_long_name"] = str(getattr(ds.variables[name], "long_name", ""))
        result["z_reference"] = str(getattr(ds, "spritzmet_level_meters_kind", "height_above_ground"))
        return result


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
    z_reference = str(selected[0].get("z_reference", "height_above_sea_level"))
    payload: dict[str, Any] = {"time": times, "x": xs, "y": ys, "z": zs, "z_reference": z_reference}
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
    if selected and "latitude" in selected[0] and "longitude" in selected[0]:
        latitude = np.full((len(ys), len(xs)), np.nan, dtype=float)
        longitude = np.full((len(ys), len(xs)), np.nan, dtype=float)
        seen: set[tuple[int, int]] = set()
        for row in selected:
            yi = indexes["y"][float(row.get("y", 0.0))]
            xi = indexes["x"][float(row.get("x", 0.0))]
            key = (yi, xi)
            lat_value = float(row["latitude"])
            lon_value = float(row["longitude"])
            if key in seen:
                continue
            latitude[yi, xi] = lat_value
            longitude[yi, xi] = lon_value
            seen.add(key)
        if len(seen) == len(ys) * len(xs) and np.isfinite(latitude).all() and np.isfinite(longitude).all():
            payload["latitude"] = latitude
            payload["longitude"] = longitude
    for row_name, payload_name in (("terrain_m", "surface_altitude"), ("land_cover", "land_cover")):
        if selected and row_name in selected[0]:
            values = np.full((len(ys), len(xs)), np.nan, dtype=float)
            seen: set[tuple[int, int]] = set()
            for row in selected:
                yi = indexes["y"][float(row.get("y", 0.0))]
                xi = indexes["x"][float(row.get("x", 0.0))]
                key = (yi, xi)
                value = float(row[row_name])
                if key in seen:
                    continue
                values[yi, xi] = value
                seen.add(key)
            else:
                if len(seen) == len(ys) * len(xs) and np.isfinite(values).all():
                    payload[payload_name] = values
    return payload


class DenseConcentrationWriter:
    """Append gridded concentration arrays directly to a NetCDF-CF product."""

    def __init__(
        self,
        path: str | Path,
        *,
        times: tuple[float, ...],
        x: Any,
        y: Any,
        z: Any,
        point_receptors: list[dict[str, Any]] | tuple[dict[str, Any], ...] = (),
        z_reference: str = "height_above_sea_level",
        latitude: Any | None = None,
        longitude: Any | None = None,
        surface_altitude: Any | None = None,
        land_cover: Any | None = None,
        datetimes: dict[float, str] | None = None,
    ) -> None:
        if not available():
            raise DataFormatError("direct dense NetCDF concentration writing requires netCDF4")
        from netCDF4 import Dataset  # type: ignore

        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.times = tuple(float(value) for value in times)
        self._time_index = {value: index for index, value in enumerate(self.times)}
        self.point_receptors = list(point_receptors)
        self.ds = Dataset(self.path, "w")
        ds = self.ds
        field_x = np.asarray(x, dtype=float)
        field_y = np.asarray(y, dtype=float)
        field_z = np.asarray(z, dtype=float)
        ds.createDimension("time", len(self.times))
        if self.point_receptors:
            ds.createDimension("receptor", len(self.point_receptors))
        ds.createDimension("field_z", len(field_z))
        ds.createDimension("field_y", len(field_y))
        ds.createDimension("field_x", len(field_x))
        ds.Conventions = "CF-1.8"
        ds.title = "Spritz receptor concentration"

        if datetimes:
            time = write_cf_time_coordinate(ds, [datetimes.get(value, "") for value in self.times])
            time.long_name = "model output time"
        else:
            _write_relative_time_coordinate(ds, self.times)

        if self.point_receptors:
            rec = ds.createVariable("receptor", "i4", ("receptor",))
            rec.long_name = "receptor index"
            rec[:] = np.arange(len(self.point_receptors), dtype=np.int32)
            rec_id = ds.createVariable("receptor_id", str, ("receptor",))
            rec_id.long_name = "receptor identifier"
            rec_id[:] = np.asarray([str(row.get("receptor", f"R{i}")) for i, row in enumerate(self.point_receptors)], dtype=object)
            for name, annotator in (("x", annotate_local_x), ("y", annotate_local_y)):
                var = ds.createVariable(name, "f8", ("receptor",), zlib=True)
                annotator(var)
                var[:] = [float(row.get(name, np.nan)) for row in self.point_receptors]
            receptor_z = ds.createVariable("z", "f8", ("receptor",), zlib=True)
            annotate_height(receptor_z, long_name="receptor height above local ground")
            receptor_z[:] = [float(row.get("z", np.nan)) for row in self.point_receptors]
            kind = ds.createVariable("output_kind", str, ("receptor",))
            kind.long_name = "concentration output receptor kind"
            kind[:] = np.asarray(["receptor"] * len(self.point_receptors), dtype=object)
            if any("latitude" in row and "longitude" in row for row in self.point_receptors):
                for name, annotator in (("latitude", annotate_latitude), ("longitude", annotate_longitude)):
                    var = ds.createVariable(name, "f8", ("receptor",), zlib=True)
                    annotator(var)
                    var.long_name = f"receptor {name}"
                    var[:] = [float(row.get(name, np.nan)) for row in self.point_receptors]
            for name, units, long_name in [
                ("concentration", "g m-3", "mass_concentration_of_air_pollutant_in_air"),
                ("dry_flux", "g m-2 s-1", "dry_deposition_flux"),
                ("wet_flux", "g m-2 s-1", "wet_deposition_flux"),
            ]:
                var = ds.createVariable(name, "f8", ("time", "receptor"), zlib=True)
                var.units = units
                var.long_name = long_name
                var[:, :] = np.nan

        ds.spritz_concentration_field_z_reference = z_reference
        z_long_name = (
            "model grid altitude above mean sea level"
            if z_reference == "height_above_sea_level"
            else "model grid height above local ground"
        )
        for name, values, units, long_name in [
            ("field_x", field_x, "m", "model grid x coordinate"),
            ("field_y", field_y, "m", "model grid y coordinate"),
            ("field_z", field_z, "m", z_long_name),
        ]:
            var = ds.createVariable(name, "f8", (name,), zlib=True)
            var.long_name = long_name
            if name == "field_x":
                annotate_local_x(var)
                var.long_name = long_name
            elif name == "field_y":
                annotate_local_y(var)
                var.long_name = long_name
            elif z_reference == "height_above_sea_level":
                var.standard_name = "altitude"
                var.units = units
                var.positive = "up"
                var.axis = "Z"
                var.long_name = long_name
            else:
                annotate_height(var, long_name=long_name)
            var[:] = values
        if latitude is not None and longitude is not None:
            for name, values, annotator, long_name in [
                ("field_latitude", latitude, annotate_latitude, "model grid latitude"),
                ("field_longitude", longitude, annotate_longitude, "model grid longitude"),
            ]:
                var = ds.createVariable(name, "f8", ("field_y", "field_x"), zlib=True)
                annotator(var)
                var.long_name = long_name
                var[:, :] = np.asarray(values, dtype=float)
        if surface_altitude is not None:
            surface = np.asarray(surface_altitude, dtype=float)
            var = ds.createVariable("surface_altitude", "f8", ("field_y", "field_x"), zlib=True)
            annotate_surface_altitude(var)
            var.coordinates = "field_latitude field_longitude" if latitude is not None and longitude is not None else "field_y field_x"
            var[:, :] = surface
            altitude = ds.createVariable("field_altitude", "f8", ("field_z", "field_y", "field_x"), zlib=True)
            altitude.standard_name = "altitude"
            altitude.long_name = "model grid altitude above mean sea level"
            altitude.units = "m"
            altitude.positive = "up"
            altitude.coordinates = (
                "field_z field_latitude field_longitude"
                if latitude is not None and longitude is not None
                else "field_z field_y field_x"
            )
            if z_reference == "height_above_sea_level":
                altitude[:, :, :] = np.broadcast_to(field_z[:, np.newaxis, np.newaxis], (len(field_z), len(field_y), len(field_x)))
            else:
                altitude[:, :, :] = field_z[:, np.newaxis, np.newaxis] + surface[np.newaxis, :, :]
        if land_cover is not None:
            var = ds.createVariable("land_cover", "i4", ("field_y", "field_x"), zlib=True)
            var.long_name = "categorical land-cover class"
            var.coordinates = "field_latitude field_longitude" if latitude is not None and longitude is not None else "field_y field_x"
            var[:, :] = np.asarray(np.rint(land_cover), dtype=np.int32)
        for name, units, long_name in [
            ("concentration_field", "g m-3", "gridded mass concentration"),
            ("dry_flux_field", "g m-2 s-1", "gridded dry deposition flux"),
            ("wet_flux_field", "g m-2 s-1", "gridded wet deposition flux"),
        ]:
            var = ds.createVariable(name, "f8", ("time", "field_z", "field_y", "field_x"), zlib=True)
            var.units = units
            var.long_name = long_name
            coordinates = "time field_z field_y field_x"
            if surface_altitude is not None:
                coordinates += " field_altitude"
            if latitude is not None and longitude is not None:
                coordinates += " field_latitude field_longitude"
            var.coordinates = coordinates

    def write_time(
        self,
        time_value: float,
        *,
        concentration: Any,
        dry_flux: Any,
        wet_flux: Any,
        receptor_rows: list[dict[str, Any]] | tuple[dict[str, Any], ...] = (),
    ) -> None:
        ti = self._time_index[float(time_value)]
        self.ds.variables["concentration_field"][ti, :, :, :] = np.asarray(concentration, dtype=float)
        self.ds.variables["dry_flux_field"][ti, :, :, :] = np.asarray(dry_flux, dtype=float)
        self.ds.variables["wet_flux_field"][ti, :, :, :] = np.asarray(wet_flux, dtype=float)
        if receptor_rows:
            for ri, row in enumerate(receptor_rows):
                self.ds.variables["concentration"][ti, ri] = float(row.get("concentration", 0.0))
                self.ds.variables["dry_flux"][ti, ri] = float(row.get("dry_flux", 0.0))
                self.ds.variables["wet_flux"][ti, ri] = float(row.get("wet_flux", 0.0))

    def close(self) -> None:
        self.ds.close()

    def __enter__(self) -> "DenseConcentrationWriter":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()


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
        if datetime_by_time:
            time = write_cf_time_coordinate(ds, [datetime_by_time.get(value, "") for value in times])
            time.long_name = "model output time"
        else:
            time = ds.createVariable("time", "f8", ("time",))
            time.standard_name = "time"
            time.long_name = "model output time"
            time.axis = "T"
            time.calendar = "proleptic_gregorian"
            time.units = "seconds since 1970-01-01 00:00:00 UTC"
            time.comment = "No absolute UTC datetime was available; value is seconds since simulation start."
            time[:] = np.asarray(times, dtype=float)
        rec = ds.createVariable("receptor", "i4", ("receptor",))
        rec.long_name = "receptor index"
        rec[:] = np.arange(len(receptors), dtype=np.int32)
        rec_id = ds.createVariable("receptor_id", str, ("receptor",))
        rec_id.long_name = "receptor identifier"
        rec_id[:] = np.asarray(receptors, dtype=object)
        x = ds.createVariable("x", "f8", ("receptor",), zlib=True)
        y = ds.createVariable("y", "f8", ("receptor",), zlib=True)
        z = ds.createVariable("z", "f8", ("receptor",), zlib=True)
        annotate_local_x(x)
        annotate_local_y(y)
        annotate_height(z, long_name="receptor height above local ground")
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
                if name == "latitude":
                    annotate_latitude(var)
                else:
                    annotate_longitude(var)
                var.long_name = long_name
                var[:] = [
                    float(by_receptor.get(receptor, {}).get(name, np.nan))
                    for receptor in receptors
                ]
        if field is not None:
            ds.createDimension("field_z", len(field["z"]))
            ds.createDimension("field_y", len(field["y"]))
            ds.createDimension("field_x", len(field["x"]))
            z_reference = str(field.get("z_reference", "height_above_sea_level"))
            ds.spritz_concentration_field_z_reference = z_reference
            z_long_name = (
                "model grid altitude above mean sea level"
                if z_reference == "height_above_sea_level"
                else "model grid height above local ground"
            )
            for name, values, units, long_name in [
                ("field_x", field["x"], "m", "model grid x coordinate"),
                ("field_y", field["y"], "m", "model grid y coordinate"),
                ("field_z", field["z"], "m", z_long_name),
            ]:
                var = ds.createVariable(name, "f8", (name,), zlib=True)
                var.long_name = long_name
                if name == "field_x":
                    annotate_local_x(var)
                    var.long_name = long_name
                elif name == "field_y":
                    annotate_local_y(var)
                    var.long_name = long_name
                else:
                    if z_reference == "height_above_sea_level":
                        var.standard_name = "altitude"
                        var.units = units
                        var.positive = "up"
                        var.axis = "Z"
                        var.long_name = long_name
                    else:
                        annotate_height(var, long_name=long_name)
                var[:] = np.asarray(values, dtype=float)
            if "latitude" in field and "longitude" in field:
                for name, source_name, units, long_name, standard_name in [
                    ("field_latitude", "latitude", "degrees_north", "model grid latitude", "latitude"),
                    ("field_longitude", "longitude", "degrees_east", "model grid longitude", "longitude"),
                ]:
                    var = ds.createVariable(name, "f8", ("field_y", "field_x"), zlib=True)
                    var.long_name = long_name
                    if standard_name == "latitude":
                        annotate_latitude(var)
                    else:
                        annotate_longitude(var)
                    var.long_name = long_name
                    var[:, :] = np.asarray(field[source_name], dtype=float)
            if "surface_altitude" in field:
                var = ds.createVariable("surface_altitude", "f8", ("field_y", "field_x"), zlib=True)
                annotate_surface_altitude(var)
                var.coordinates = (
                    "field_latitude field_longitude"
                    if "latitude" in field and "longitude" in field
                    else "field_y field_x"
                )
                var[:, :] = np.asarray(field["surface_altitude"], dtype=float)
                altitude = ds.createVariable("field_altitude", "f8", ("field_z", "field_y", "field_x"), zlib=True)
                altitude.standard_name = "altitude"
                altitude.long_name = "model grid altitude above mean sea level"
                altitude.units = "m"
                altitude.positive = "up"
                altitude.coordinates = (
                    "field_z field_latitude field_longitude"
                    if "latitude" in field and "longitude" in field
                    else "field_z field_y field_x"
                )
                if z_reference == "height_above_sea_level":
                    altitude[:, :, :] = np.broadcast_to(
                        np.asarray(field["z"], dtype=float)[:, np.newaxis, np.newaxis],
                        (len(field["z"]), len(field["y"]), len(field["x"])),
                    )
                else:
                    altitude[:, :, :] = (
                        np.asarray(field["z"], dtype=float)[:, np.newaxis, np.newaxis]
                        + np.asarray(field["surface_altitude"], dtype=float)[np.newaxis, :, :]
                    )
            if "land_cover" in field:
                var = ds.createVariable("land_cover", "i4", ("field_y", "field_x"), zlib=True)
                var.long_name = "categorical land-cover class"
                var.coordinates = "field_latitude field_longitude" if "latitude" in field and "longitude" in field else "field_y field_x"
                var[:, :] = np.asarray(np.rint(field["land_cover"]), dtype=np.int32)
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
                coordinates = "time field_z field_y field_x"
                if "surface_altitude" in field:
                    coordinates += " field_altitude"
                if "latitude" in field and "longitude" in field:
                    coordinates += " field_latitude field_longitude"
                var.coordinates = coordinates
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
        if "concentration" not in ds.variables:
            return []
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

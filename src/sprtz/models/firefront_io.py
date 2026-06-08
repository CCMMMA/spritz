from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from sprtz.io.jsonio import write_json


def _snap_arrays(result: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    snaps = result.get("snapshots") or [{"t": 0.0, "fire_probability": result["fire_probability"], "intensity": result["intensity"]}]
    prob = np.stack([np.asarray(s["fire_probability"], dtype=np.float32) for s in snaps])
    intensity = np.stack([np.asarray(s["intensity"], dtype=np.float32) for s in snaps])
    times = np.asarray([float(s["t"]) for s in snaps], dtype=np.float64)
    return times, prob, intensity


def write_netcdf(path: str | Path, result: dict[str, Any], grid_info: dict[str, Any], config: Any, t_start: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        from netCDF4 import Dataset
    except Exception:
        payload = {k: (v.tolist() if isinstance(v, np.ndarray) else v) for k, v in result.items() if k != "snapshots"}
        payload["format"] = "cf-json-fallback"
        write_json(p, payload)
        return
    times, prob, intensity = _snap_arrays(result)
    ny, nx = prob.shape[-2:]
    with Dataset(p, "w") as ds:
        ds.createDimension("time", len(times))
        ds.createDimension("y", ny)
        ds.createDimension("x", nx)
        ds.Conventions = "CF-1.8"
        ds.title = "SpritzFire stochastic wildfire spread"
        ds.institution = "CCMMMA"
        ds.source = "Sprtz firefront module"
        ds.references = "Trucchia et al. (2020) doi:10.3390/fire3030026"
        ds.realizations = int(config.realizations)
        ds.ros_model = str(config.ros_model)
        ds.seed = int(config.seed)
        ds.history = f"{datetime.now(timezone.utc).isoformat()}: sprtzfire run"
        tvar = ds.createVariable("time", "f8", ("time",))
        tvar.standard_name = "time"
        tvar.units = f"seconds since {t_start}"
        tvar[:] = times
        x = ds.createVariable("x", "f4", ("x",))
        y = ds.createVariable("y", "f4", ("y",))
        x.standard_name = "projection_x_coordinate"
        y.standard_name = "projection_y_coordinate"
        x.units = y.units = "m"
        dx = float(grid_info.get("dx", 1.0))
        dy = float(grid_info.get("dy", dx))
        x[:] = np.arange(nx, dtype=np.float32) * dx
        y[:] = np.arange(ny, dtype=np.float32) * dy
        lat_data = np.asarray(grid_info.get("lat", np.full((ny, nx), np.nan)), dtype=np.float32)
        lon_data = np.asarray(grid_info.get("lon", np.full((ny, nx), np.nan)), dtype=np.float32)
        for name, data, units, standard_name in [("lat", lat_data, "degrees_north", "latitude"), ("lon", lon_data, "degrees_east", "longitude")]:
            var = ds.createVariable(name, "f4", ("y", "x"), zlib=True)
            var.units = units
            var.standard_name = standard_name
            var[:, :] = data
        fp = ds.createVariable("fire_probability", "f4", ("time", "y", "x"), zlib=True)
        fp.units = "1"
        fp.long_name = "probability of fire arrival (ensemble fraction)"
        fp[:, :, :] = prob
        arr = ds.createVariable("arrival_time", "f4", ("y", "x"), zlib=True)
        arr.units = "s"
        arr.long_name = "ensemble mean fire arrival time"
        arr[:, :] = np.asarray(result["arrival_time"], dtype=np.float32)
        iv = ds.createVariable("intensity", "f4", ("time", "y", "x"), zlib=True)
        iv.units = "kW m-1"
        iv.long_name = "Byram fireline intensity"
        iv[:, :, :] = intensity


def write_csv(path: str | Path, result: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    prob = np.asarray(result["fire_probability"], dtype=float)
    arr = np.asarray(result["arrival_time"], dtype=float)
    with p.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["row", "col", "fire_probability", "arrival_time"])
        writer.writeheader()
        for r in range(prob.shape[0]):
            for c in range(prob.shape[1]):
                writer.writerow({"row": r, "col": c, "fire_probability": prob[r, c], "arrival_time": arr[r, c]})


def geojson_perimeters(snapshots: list[dict[str, Any]], threshold: float = 0.5) -> dict[str, Any]:
    features: list[dict[str, Any]] = []
    for snap in snapshots:
        prob = np.asarray(snap["fire_probability"], dtype=float)
        rows, cols = np.where(prob >= threshold)
        if rows.size == 0:
            continue
        r0, r1 = int(rows.min()), int(rows.max() + 1)
        c0, c1 = int(cols.min()), int(cols.max() + 1)
        poly = [[[c0, r0], [c1, r0], [c1, r1], [c0, r1], [c0, r0]]]
        features.append({"type": "Feature", "properties": {"t": float(snap["t"]), "threshold": threshold}, "geometry": {"type": "Polygon", "coordinates": poly}})
    return {"type": "FeatureCollection", "features": features}


def write_geojson(path: str | Path, result: dict[str, Any], threshold: float = 0.5) -> None:
    write_json(path, geojson_perimeters(list(result.get("snapshots", [])), threshold=threshold))

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np

from sprtz.config import load_config
from sprtz.models.firefront import demo_firefront_from_config
from sprtz.models.firefront_io import write_csv, write_geojson, write_netcdf


def run_mpi(config_path: str, output_dir: str) -> None:
    try:
        from mpi4py import MPI
    except Exception as exc:
        raise ImportError("SpritzFire MPI requires mpi4py; install with `pip install sprtz[mpi]`.") from exc
    comm = MPI.COMM_WORLD
    rank = comm.Get_rank()
    size = comm.Get_size()
    config = load_config(config_path) if rank == 0 else None
    config = comm.bcast(config, root=0)
    total = int(config.fire.realizations if config.fire else 100)
    chunk = int(np.ceil(total / size))
    start = rank * chunk
    end = min(total, start + chunk)
    local_n = max(0, end - start)
    fire_cfg = replace(config.fire, realizations=max(local_n, 1), seed=int(config.fire.seed) + rank) if config.fire else None
    local_config = replace(config, fire=fire_cfg)
    front = demo_firefront_from_config(local_config)
    ws = np.full((config.grid.ny, config.grid.nx), 4.0, dtype=np.float32)
    wd = np.full_like(ws, np.pi / 2)
    if local_n:
        result = front.run(ws, wd)
        payload = (local_n, front.burning[:local_n].copy(), front.arrived[:local_n].copy(), result)
    else:
        payload = (0, np.zeros((0, config.grid.ny, config.grid.nx), dtype=bool), np.zeros((0, config.grid.ny, config.grid.nx), dtype=np.float32), {})
    gathered = comm.gather(payload, root=0)
    if rank != 0:
        return
    burn = np.concatenate([item[1] for item in gathered if item[0] > 0], axis=0)
    arr = np.concatenate([item[2] for item in gathered if item[0] > 0], axis=0)
    arr = arr.astype(np.float32)
    arr[~np.isfinite(arr)] = np.nan
    result = {
        "component": "firefront",
        "fire_probability": burn.mean(axis=0).astype(np.float32),
        "arrival_time": np.nanmean(arr, axis=0).astype(np.float32),
        "intensity": np.zeros((config.grid.ny, config.grid.nx), dtype=np.float32),
        "snapshots": [],
    }
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    write_netcdf(out / "firefront.nc", result, {"dx": config.grid.dx, "dy": config.grid.dy}, config.fire, "simulation start")
    write_csv(out / "firefront.csv", result)
    write_geojson(out / "fire_perimeter.geojson", result)

from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import configured_backend, from_mapping, load_config
from .models import spritzmet, spritzpost, spritz, particles
from .parallel import get_mpi_context
from .terrain.acquisition import run_acquisition


def run_workflow(
    config_path: str | Path,
    output_dir: str | Path,
    *,
    backend: str | None = None,
    interchange: str = "netcdf",
    parallel: str = "serial",
    auto_terrain: bool = False,
    allow_terrain_network: bool = False,
    output_interval_s: float | None = None,
) -> dict[str, Any]:
    ctx = get_mpi_context(parallel)
    out = Path(output_dir)
    if ctx.is_root:
        out.mkdir(parents=True, exist_ok=True)
    ctx.barrier()
    config = load_config(config_path)
    if output_interval_s is not None:
        run_config = dict(config.raw.get("run", {}))
        run_config["output_interval_s"] = float(output_interval_s)
        config = from_mapping({**config.raw, "run": run_config})
    model_backend = configured_backend(config.run, backend)
    use_netcdf = interchange == "netcdf"
    terrain_result: dict[str, Any] | None = None
    terrain_cfg = dict(config.raw.get("terrain", {}))
    if auto_terrain or bool(terrain_cfg.get("enabled", False)):
        terrain_output = terrain_cfg.get("output")
        if terrain_output:
            terrain_path = Path(terrain_output)
            if not terrain_path.is_absolute():
                terrain_path = out / terrain_path
        else:
            terrain_path = out / ("geo.nc" if use_netcdf else "geo.json")
        acquisition_config = dict(config.raw)
        acquisition_config["terrain"] = {**terrain_cfg, "output": str(terrain_path)}
        if ctx.is_root:
            terrain_result = run_acquisition(
                acquisition_config,
                prefer_netcdf=use_netcdf,
                allow_network=allow_terrain_network,
            )
        ctx.barrier()
    meteo_path = out / ("meteo.nc" if use_netcdf else "meteo.json")
    conc_path = out / ("concentration.nc" if use_netcdf else "concentration.csv")
    post_path = out / "post.json"
    if ctx.is_root:
        meteo = spritzmet.run(config, meteo_path, "netcdf" if use_netcdf else "json")
    else:
        meteo = {"component": "spritzmet"}
    ctx.barrier()
    if model_backend == "particles":
        conc = particles.run(config, meteo_path, conc_path, "netcdf" if use_netcdf else "csv", parallel=parallel)
        model_component = "particles"
    elif model_backend == "gaussian":
        conc = spritz.run(config, meteo_path, conc_path, "netcdf" if use_netcdf else "csv", parallel=parallel)
        model_component = "spritz"
    else:
        raise ValueError("backend must be gaussian or particles")
    if ctx.is_root:
        post = spritzpost.run(conc_path, post_path, threshold=config.run.get("threshold", config.run.get("THRESHOLD")))
    else:
        post = {"component": "spritzpost"}
    result = {
        "meteo": str(meteo_path),
        "concentration": str(conc_path),
        "post": str(post_path),
        "n_receptors": len({str(row.get("receptor", "")) for row in conc}),
        "n_output_rows": len(conc),
        "interchange": interchange,
        "backend": model_backend,
        "parallel": "mpi" if ctx.enabled else "serial",
        "mpi_size": ctx.size,
        "components": [meteo["component"], model_component, post["component"]],
    }
    if terrain_result is not None:
        result["terrain"] = terrain_result["output"]
        result["terrain_cache_key"] = terrain_result["cache_key"]
    if output_interval_s is not None:
        result["output_interval_s"] = float(output_interval_s)
    return ctx.bcast(result, root=0)

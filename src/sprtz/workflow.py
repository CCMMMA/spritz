from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import load_config
from .models import spritzmet, spritzpost, spritz, particles
from .parallel import get_mpi_context


def run_workflow(
    config_path: str | Path,
    output_dir: str | Path,
    *,
    backend: str = "gaussian",
    interchange: str = "netcdf",
    parallel: str = "serial",
) -> dict[str, Any]:
    ctx = get_mpi_context(parallel)
    out = Path(output_dir)
    if ctx.is_root:
        out.mkdir(parents=True, exist_ok=True)
    ctx.barrier()
    config = load_config(config_path)
    use_netcdf = interchange == "netcdf"
    meteo_path = out / ("meteo.nc" if use_netcdf else "meteo.json")
    conc_path = out / ("concentration.nc" if use_netcdf else "concentration.csv")
    post_path = out / "post.json"
    if ctx.is_root:
        meteo = spritzmet.run(config, meteo_path, "netcdf" if use_netcdf else "json")
    else:
        meteo = {"component": "spritzmet"}
    ctx.barrier()
    if backend == "particles":
        conc = particles.run(config, meteo_path, conc_path, "netcdf" if use_netcdf else "csv", parallel=parallel)
        model_component = "particles"
    elif backend == "gaussian":
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
        "n_receptors": len(conc),
        "interchange": interchange,
        "parallel": "mpi" if ctx.enabled else "serial",
        "mpi_size": ctx.size,
        "components": [meteo["component"], model_component, post["component"]],
    }
    return ctx.bcast(result, root=0)

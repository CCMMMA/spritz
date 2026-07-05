from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Callable
from dataclasses import replace

from .config import configured_backend, from_mapping, load_config
from .io.calpuff import write_calpuff_concentration_dat
from .io.jsonio import write_json
from .models import spritzmet, spritzpost, spritz, particles
from .parallel import get_parallel_context
from .terrain.acquisition import run_acquisition


def run_workflow(
    config_path: str | Path,
    output_dir: str | Path,
    *,
    backend: str | None = None,
    interchange: str = "netcdf",
    parallel: str = "serial",
    gpu_backend: str | None = None,
    thread_backend: str = "serial",
    threads_per_rank: int | None = None,
    decomposition: str = "auto",
    auto_terrain: bool = False,
    allow_terrain_network: bool = False,
    output_interval_s: float | None = None,
    meteo_input: str | Path | None = None,
    terrain_input: str | Path | None = None,
    calpuff_binary: bool = False,
    concentration_progress_callback: Callable[[int, float], None] | None = None,
) -> dict[str, Any]:
    parallel_ctx = get_parallel_context(parallel, thread_backend, threads_per_rank, gpu_backend or "numpy")
    ctx = parallel_ctx.mpi
    out = Path(output_dir)
    if ctx.is_root:
        out.mkdir(parents=True, exist_ok=True)
    ctx.barrier()
    config = load_config(config_path)
    if output_interval_s is not None:
        run_config = dict(config.raw.get("run", {}))
        run_config["output_interval_s"] = float(output_interval_s)
        config = from_mapping({**config.raw, "run": run_config})
    if gpu_backend is not None:
        run_config = dict(config.raw.get("run", {}))
        run_config["gpu_backend"] = gpu_backend
        config = from_mapping({**config.raw, "run": run_config})
        if config.fire is not None:
            config = replace(config, fire=replace(config.fire, gpu=replace(config.fire.gpu, backend=gpu_backend)))
    model_backend = configured_backend(config.run, backend)
    use_netcdf = interchange == "netcdf"
    if model_backend in {"firefront", "fire+puff", "firms", "firms+fire", "firms+fire+puff"}:
        if model_backend.startswith("firms"):
            if config.fire is None:
                raise ValueError("FIRMS workflow requires a fire configuration block")
            from .terrain.firms import FIRMSDownloader

            downloader = FIRMSDownloader(config.fire.firms)
            df = downloader.filter(downloader.download(_domain_bbox(config, config.fire.firms.bbox_pad_deg)))
            ignitions = tuple(downloader.to_ignition_points(df))
            if not ignitions:
                raise ValueError("FIRMS returned no hotspots after filtering")
            config = replace(config, fire=replace(config.fire, ignitions=ignitions))
        if ctx.enabled and config.fire and config.fire.parallel != "serial":
            from .models.firefront_mpi import run_mpi

            run_mpi(str(config_path), str(out), config_override=config)
            return ctx.bcast({"backend": model_backend, "firefront": str(out / "firefront.nc"), "parallel": "mpi"}, root=0)
        result = run_firefront_serial(config, out, interchange)
        if model_backend.endswith("+puff"):
            config = from_mapping({**config.raw, "run": {**dict(config.raw.get("run", {})), "backend": "gaussian"}})
            puff_result = run_workflow(
                config_path,
                output_dir,
                backend="gaussian",
                interchange=interchange,
                parallel=parallel,
                gpu_backend=gpu_backend,
                thread_backend=thread_backend,
                threads_per_rank=threads_per_rank,
                decomposition=decomposition,
                terrain_input=terrain_input,
            )
            result["puff"] = puff_result.get("concentration")
        return ctx.bcast(result, root=0)
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
    if meteo_input is None:
        meteo = spritzmet.run(
            config,
            meteo_path,
            "netcdf" if use_netcdf else "json",
            parallel=parallel,
            gpu_backend=gpu_backend,
        )
    else:
        source_meteo_path = Path(meteo_input)
        if not source_meteo_path.exists():
            raise FileNotFoundError(f"meteorology input not found: {source_meteo_path}")
        if ctx.is_root:
            if source_meteo_path.resolve() != meteo_path.resolve():
                shutil.copy2(source_meteo_path, meteo_path)
        meteo = {"component": "spritzmet.external_meteorology", "source": str(source_meteo_path)}
    ctx.barrier()
    if model_backend == "particles":
        conc = particles.run(
            config,
            meteo_path,
            conc_path,
            "netcdf" if use_netcdf else "csv",
            parallel=parallel,
            gpu_backend=gpu_backend,
            terrain_input=terrain_input,
            progress_callback=concentration_progress_callback,
        )
        model_component = "particles"
    elif model_backend == "gaussian":
        conc = spritz.run(
            config,
            meteo_path,
            conc_path,
            "netcdf" if use_netcdf else "csv",
            parallel=parallel,
            gpu_backend=gpu_backend,
            terrain_input=terrain_input,
            progress_callback=concentration_progress_callback,
        )
        model_component = "spritz"
    else:
        raise ValueError("backend must be gaussian or particles")
    if ctx.is_root:
        calpuff_path = out / "concentration_calpuff.dat"
        if calpuff_binary:
            write_calpuff_concentration_dat(calpuff_path, conc)
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
        "gpu_backend": gpu_backend or str(config.run.get("gpu_backend", "numpy")),
        "thread_backend": parallel_ctx.threads.mode,
        "threads_per_rank": parallel_ctx.threads.workers,
        "decomposition": decomposition,
        "mpi_size": ctx.size,
        "components": [meteo["component"], model_component, post["component"]],
    }
    if terrain_result is not None:
        result["terrain"] = terrain_result["output"]
        result["terrain_cache_key"] = terrain_result["cache_key"]
    elif terrain_input is not None:
        result["terrain"] = str(terrain_input)
    if output_interval_s is not None:
        result["output_interval_s"] = float(output_interval_s)
    if meteo_input is not None:
        result["meteo_input"] = str(meteo_input)
    if calpuff_binary:
        result["calpuff_concentration"] = str(out / "concentration_calpuff.dat")
    return ctx.bcast(result, root=0)


def run_firefront_serial(config, output_dir: str | Path, interchange: str = "netcdf") -> dict[str, Any]:
    from .models.firefront import demo_firefront_from_config
    from .models.firefront_io import write_csv, write_geojson, write_netcdf

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    front = demo_firefront_from_config(config)
    ws = [[float(config.run.get("default_fire_wind_speed", 4.0))] * config.grid.nx for _ in range(config.grid.ny)]
    wd = [[float(config.run.get("default_fire_wind_dir_rad", 1.5707963267948966))] * config.grid.nx for _ in range(config.grid.ny)]
    result = front.run(ws, wd)
    fire_path = out / ("firefront.nc" if interchange == "netcdf" else "firefront.json")
    if interchange == "netcdf":
        write_netcdf(fire_path, result, {"dx": config.grid.dx, "dy": config.grid.dy}, front.cfg, "simulation start")
    else:
        write_json(fire_path, _jsonable(result))
    write_csv(out / "firefront.csv", result)
    write_geojson(out / "fire_perimeter.geojson", result)
    return {"firefront": str(fire_path), "fire_perimeter": str(out / "fire_perimeter.geojson"), "backend": "firefront"}


def _jsonable(value: Any) -> Any:
    try:
        import numpy as np

        if isinstance(value, np.ndarray):
            return _jsonable(value.tolist())
        if isinstance(value, np.floating):
            value = float(value)
        if isinstance(value, np.integer):
            return int(value)
    except Exception:
        pass
    if isinstance(value, float) and (value != value or value in {float("inf"), float("-inf")}):
        return None
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    return value


def _domain_bbox(config, pad: float) -> tuple[float, float, float, float]:
    lats = [v for group in (config.sources, config.receptors) for v in [group.latitude] if v is not None]
    lons = [v for group in (config.sources, config.receptors) for v in [group.longitude] if v is not None]
    if not lats or not lons:
        raise ValueError("FIRMS workflows require at least one source or receptor latitude/longitude")
    return (min(lons) - pad, min(lats) - pad, max(lons) + pad, max(lats) + pad)

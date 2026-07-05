from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Sequence

from .config import SuiteConfig, configured_backend, from_mapping, load_config
from .doctor import format_report, run_diagnostics
from .exceptions import SpritzError
from .logging import configure_logging
from .models import backward, ctgproc, makegeo, particles, spritz, spritzmet, spritzpost, spritzwrf
from .models import terrain, visualization
from .parallel import get_mpi_context, get_parallel_context
from .terrain import acquisition as terrain_acquisition
from .workflow import run_workflow

LOGGER = logging.getLogger(__name__)
_BACKEND_CHOICES = ["gaussian", "gauss", "particles", "particle", "firefront", "fire", "fire+puff", "firms", "firms+fire", "firms+fire+puff"]


def _with_output_interval(config_path: str | Path, output_interval: float | None):
    cfg = load_config(config_path)
    if output_interval is None:
        return cfg
    run_config = dict(cfg.raw.get("run", {}))
    run_config["output_interval_s"] = float(output_interval)
    return from_mapping({**cfg.raw, "run": run_config})


def _config_parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--config", required=True, help="JSON, NetCDF-CF companion, or tolerant Fortran-style control file")
    parser.add_argument("--verbose", action="store_true", help="enable debug logging")
    return parser


def _add_gpu_backend(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--gpu-backend",
        choices=["numpy", "auto", "cupy", "cuda"],
        default=None,
        help="optional array accelerator backend; cupy requires CUDA",
    )


def _add_hybrid_parallel_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--thread-backend",
        choices=["serial", "threads", "processes", "auto"],
        default="serial",
        help="rank-local shared-memory backend",
    )
    parser.add_argument("--threads-per-rank", type=int, default=None, help="rank-local worker count")
    parser.add_argument(
        "--decomposition",
        choices=[
            "auto",
            "rows",
            "tiles",
            "receptors",
            "sources",
            "particles",
            "realizations",
            "source-particle-auto",
            "source-receptor-2d",
        ],
        default="auto",
        help="preferred work decomposition strategy",
    )


def _run_dispersion(
    config: SuiteConfig,
    meteo_path: str | Path,
    output_path: str | Path,
    output_format: str,
    *,
    backend: str | None = None,
    seed: int | None = None,
    parallel: str = "serial",
    gpu_backend: str | None = None,
    thread_backend: str = "serial",
    threads_per_rank: int | None = None,
    decomposition: str = "auto",
) -> list[dict[str, float | str]]:
    get_parallel_context(parallel, thread_backend, threads_per_rank, gpu_backend or "numpy")
    LOGGER.debug("dispersion decomposition=%s", decomposition)
    model_backend = configured_backend(config.run, backend)
    if model_backend == "particles":
        return particles.run(
            config,
            meteo_path,
            output_path,
            output_format,
            seed,
            parallel=parallel,
            gpu_backend=gpu_backend,
        )
    return spritz.run(config, meteo_path, output_path, output_format, parallel=parallel, gpu_backend=gpu_backend)


def _guard(fn, argv: Sequence[str] | None = None) -> int:
    try:
        return fn(argv)
    except SpritzError as exc:
        if not logging.getLogger().handlers:
            configure_logging(False)
        LOGGER.error("%s", exc)
        return 1


def spritzmet_main(argv: Sequence[str] | None = None) -> int:
    def run(argv_: Sequence[str] | None) -> int:
        parser = _config_parser("Run the pure Python SpritzMet diagnostic kernel")
        parser.add_argument("--output", required=True)
        parser.add_argument("--format", default="auto", choices=["auto", "json", "netcdf"])
        parser.add_argument("--parallel", default="serial", choices=["serial", "auto", "mpi"])
        _add_gpu_backend(parser)
        _add_hybrid_parallel_options(parser)
        args = parser.parse_args(argv_)
        configure_logging(args.verbose)
        get_parallel_context(args.parallel, args.thread_backend, args.threads_per_rank, args.gpu_backend or "numpy")
        spritzmet.run(load_config(args.config), args.output, args.format, parallel=args.parallel, gpu_backend=args.gpu_backend)
        return 0

    return _guard(run, argv)


def sprtzfire_main(argv: Sequence[str] | None = None) -> int:
    def run(argv_: Sequence[str] | None) -> int:
        parser = _config_parser("Run SpritzFire wildfire spread")
        parser.add_argument("--output-dir", required=True)
        parser.add_argument("--interchange", choices=["json", "netcdf"], default="netcdf")
        parser.add_argument("--parallel", choices=["serial", "auto", "mpi"], default="serial")
        _add_gpu_backend(parser)
        _add_hybrid_parallel_options(parser)
        parser.add_argument("--firms", action="store_true")
        parser.add_argument("--firms-source", default=None)
        parser.add_argument("--firms-date", default=None)
        parser.add_argument("--firms-confidence", nargs="*", default=None)
        parser.add_argument("--firms-min-frp", type=float, default=None)
        args = parser.parse_args(argv_)
        configure_logging(args.verbose)
        backend = "firms+fire" if args.firms else "firefront"
        result = run_workflow(
            args.config,
            args.output_dir,
            backend=backend,
            interchange=args.interchange,
            parallel=args.parallel,
            gpu_backend=args.gpu_backend,
            thread_backend=args.thread_backend,
            threads_per_rank=args.threads_per_rank,
            decomposition=args.decomposition,
        )
        LOGGER.info("%s", result)
        return 0

    return _guard(run, argv)


def spritz_main(argv: Sequence[str] | None = None) -> int:
    def run(argv_: Sequence[str] | None) -> int:
        parser = _config_parser("Run the unified pure Python Spritz concentration kernel")
        parser.add_argument("--meteo", required=True)
        parser.add_argument("--output", required=True)
        parser.add_argument("--format", default="auto", choices=["auto", "csv", "legacy", "netcdf", "calpuff"])
        parser.add_argument("--backend", choices=_BACKEND_CHOICES, default=None, help="override run.backend")
        parser.add_argument("--seed", type=int, default=None, help="particle backend seed override")
        parser.add_argument("--parallel", default="serial", choices=["serial", "auto", "mpi"], help="parallel execution mode")
        parser.add_argument("--output-interval", type=float, default=None, help="optional concentration output interval in seconds")
        _add_gpu_backend(parser)
        _add_hybrid_parallel_options(parser)
        args = parser.parse_args(argv_)
        configure_logging(args.verbose)
        _run_dispersion(
            _with_output_interval(args.config, args.output_interval),
            args.meteo,
            args.output,
            args.format,
            backend=args.backend,
            seed=args.seed,
            parallel=args.parallel,
            gpu_backend=args.gpu_backend,
            thread_backend=args.thread_backend,
            threads_per_rank=args.threads_per_rank,
            decomposition=args.decomposition,
        )
        return 0

    return _guard(run, argv)


def sprtz_particles_main(argv: Sequence[str] | None = None) -> int:
    def run(argv_: Sequence[str] | None) -> int:
        parser = _config_parser("Run the particle-based Spritz alternative")
        parser.add_argument("--meteo", required=True)
        parser.add_argument("--output", required=True)
        parser.add_argument("--format", default="auto", choices=["auto", "csv", "legacy", "netcdf", "calpuff"])
        parser.add_argument("--seed", type=int, default=None)
        parser.add_argument("--parallel", default="serial", choices=["serial", "auto", "mpi"], help="parallel execution mode")
        _add_gpu_backend(parser)
        _add_hybrid_parallel_options(parser)
        args = parser.parse_args(argv_)
        configure_logging(args.verbose)
        _run_dispersion(
            load_config(args.config),
            args.meteo,
            args.output,
            args.format,
            backend="particles",
            seed=args.seed,
            parallel=args.parallel,
            gpu_backend=args.gpu_backend,
            thread_backend=args.thread_backend,
            threads_per_rank=args.threads_per_rank,
            decomposition=args.decomposition,
        )
        return 0

    return _guard(run, argv)


def sprtz_backward_main(argv: Sequence[str] | None = None) -> int:
    def run(argv_: Sequence[str] | None) -> int:
        parser = _config_parser("Run backward source or ignition attribution")
        parser.add_argument("--meteo", default=None, help="SpritzMet JSON/NetCDF product; required for plume models")
        parser.add_argument("--output", required=True)
        parser.add_argument("--model", choices=["gaussian", "particles", "firefront"], default="gaussian")
        parser.add_argument("--format", choices=["json", "csv"], default="json")
        parser.add_argument("--seed", type=int, default=None)
        args = parser.parse_args(argv_)
        configure_logging(args.verbose)
        result = backward.run_backward(
            load_config(args.config),
            args.meteo,
            args.output,
            model=args.model,
            output_format=args.format,
            seed=args.seed,
        )
        LOGGER.info("%s", result.get("component", "spritz.backward"))
        return 0

    return _guard(run, argv)


def spritzpost_main(argv: Sequence[str] | None = None) -> int:
    def run(argv_: Sequence[str] | None) -> int:
        parser = argparse.ArgumentParser(description="Run the pure Python SpritzPost postprocessor")
        parser.add_argument("--input", required=True)
        parser.add_argument("--output", required=True)
        parser.add_argument("--threshold", type=float, default=None)
        parser.add_argument("--rank", type=int, default=1, help="nth-highest rank to report")
        parser.add_argument("--average-window", type=int, default=None, help="optional averaging window in records")
        parser.add_argument("--average-kind", choices=["running", "block"], default="running")
        parser.add_argument("--verbose", action="store_true")
        args = parser.parse_args(argv_)
        configure_logging(args.verbose)
        spritzpost.run(
            args.input,
            args.output,
            args.threshold,
            rank=args.rank,
            average_window=args.average_window,
            average_kind=args.average_kind,
        )
        return 0

    return _guard(run, argv)


def spritzwrf_main(argv: Sequence[str] | None = None) -> int:
    def run(argv_: Sequence[str] | None) -> int:
        parser = argparse.ArgumentParser(description="Inspect/adapt a WRF file for Python SpritzMet workflows")
        parser.add_argument("--input", required=True)
        parser.add_argument("--output", required=True)
        parser.add_argument("--verbose", action="store_true")
        args = parser.parse_args(argv_)
        configure_logging(args.verbose)
        spritzwrf.run(args.input, args.output)
        return 0

    return _guard(run, argv)


def ctgproc_main(argv: Sequence[str] | None = None) -> int:
    def run(argv_: Sequence[str] | None) -> int:
        parser = argparse.ArgumentParser(description="Aggregate land-use categories")
        parser.add_argument("--input", required=True)
        parser.add_argument("--output", required=True)
        parser.add_argument("--verbose", action="store_true")
        args = parser.parse_args(argv_)
        configure_logging(args.verbose)
        ctgproc.run(args.input, args.output)
        return 0

    return _guard(run, argv)



def terrain_main(argv: Sequence[str] | None = None) -> int:
    def run(argv_: Sequence[str] | None) -> int:
        parser = argparse.ArgumentParser(description="Build a Terrain product on a local modeling grid")
        parser.add_argument("--terrain", required=True, help="ASCII terrain raster")
        parser.add_argument("--output", required=True, help="NetCDF-CF or JSON terrain product")
        parser.add_argument("--center-lat", type=float, required=True)
        parser.add_argument("--center-lon", type=float, required=True)
        parser.add_argument("--nx", type=int, default=101)
        parser.add_argument("--ny", type=int, default=101)
        parser.add_argument("--dx", type=float, default=100.0)
        parser.add_argument("--dy", type=float, default=100.0)
        parser.add_argument("--source-dx", type=float, default=100.0)
        parser.add_argument("--source-dy", type=float, default=None)
        parser.add_argument("--json", action="store_true", help="write JSON even when netCDF4 is available")
        parser.add_argument("--verbose", action="store_true")
        args = parser.parse_args(argv_)
        configure_logging(args.verbose)
        result = terrain.run(
            args.terrain,
            args.output,
            center_lat=args.center_lat,
            center_lon=args.center_lon,
            nx=args.nx,
            ny=args.ny,
            dx_m=args.dx,
            dy_m=args.dy,
            source_dx_m=args.source_dx,
            source_dy_m=args.source_dy,
            prefer_netcdf=not args.json,
        )
        LOGGER.info("%s", result)
        return 0

    return _guard(run, argv)


def _provider_spec(value: str, *, kind: str) -> dict[str, object]:
    path = Path(value)
    if path.exists():
        spec: dict[str, object] = {"source": "local", "path": str(path)}
        lowered_path = path.name.lower()
        if kind == "dem" and ("cop30" in lowered_path or "copernicus" in lowered_path):
            spec.update({"dataset": "copernicus-cop30", "resolution": "30m"})
        if kind == "landuse" and ("lc100" in lowered_path or "landcover" in lowered_path):
            spec.update({"dataset": "copernicus-lc100", "resolution": "100m"})
        return spec
    lowered = value.lower()
    if kind == "dem" and lowered in {"copernicus-30", "copernicus-dem", "copernicus-glo-30"}:
        return {"source": "copernicus-dem", "resolution": "30m"}
    if kind == "landuse" and lowered in {"esa-worldcover-2021", "esa-worldcover", "worldcover"}:
        return {"source": "esa-worldcover", "year": 2021}
    raise SpritzError(f"unsupported {kind} provider or missing local path: {value}")


def _landuse_provider_spec(value: str, mapping: str | None = None) -> dict[str, object]:
    spec = _provider_spec(value, kind="landuse")
    if mapping:
        spec["target_categories"] = mapping
    return spec


def sprtz_terrain_main(argv: Sequence[str] | None = None) -> int:
    def run(argv_: Sequence[str] | None) -> int:
        parser = argparse.ArgumentParser(description="Spritz terrain acquisition and GEO generation")
        sub = parser.add_subparsers(dest="command", required=True)
        fetch = sub.add_parser("fetch", help="build a terrain/GEO product from local or online providers")
        fetch.add_argument("--config", default=None, help="JSON configuration with domain and terrain sections")
        fetch.add_argument("--center-lat", type=float)
        fetch.add_argument("--center-lon", type=float)
        fetch.add_argument("--dx", type=float, default=100.0)
        fetch.add_argument("--dy", type=float, default=100.0)
        fetch.add_argument("--nx", type=int, default=100)
        fetch.add_argument("--ny", type=int, default=100)
        fetch.add_argument("--projection", default="auto-utm")
        fetch.add_argument("--buffer-m", type=float, default=0.0)
        fetch.add_argument("--dem", default="copernicus-30")
        fetch.add_argument("--landuse", default="esa-worldcover-2021")
        fetch.add_argument(
            "--landuse-mapping",
            default=None,
            help="source land-cover mapping for local rasters, e.g. copernicus-lc100",
        )
        fetch.add_argument("--output", default=None)
        fetch.add_argument("--cache-dir", default=None)
        fetch.add_argument("--json", action="store_true", help="write JSON even when netCDF4 is available")
        fetch.add_argument("--allow-network", action="store_true", help="allow explicit online provider access")
        fetch.add_argument("--verbose", action="store_true")
        args = parser.parse_args(argv_)
        configure_logging(args.verbose)
        if args.command == "fetch":
            if args.config:
                result = terrain_acquisition.run_acquisition(
                    args.config,
                    output=args.output,
                    prefer_netcdf=not args.json,
                    allow_network=args.allow_network,
                    cache_dir=args.cache_dir,
                )
            else:
                if args.center_lat is None or args.center_lon is None or args.output is None:
                    raise SpritzError("--center-lat, --center-lon, and --output are required without --config")
                config = {
                    "domain": {
                        "center_lat": args.center_lat,
                        "center_lon": args.center_lon,
                        "nx": args.nx,
                        "ny": args.ny,
                        "dx_m": args.dx,
                        "dy_m": args.dy,
                        "projection": args.projection,
                        "buffer_m": args.buffer_m,
                    },
                    "terrain": {
                        "enabled": True,
                        "dem": _provider_spec(args.dem, kind="dem"),
                        "landuse": _landuse_provider_spec(
                            args.landuse,
                            mapping=args.landuse_mapping,
                        ),
                        "output": args.output,
                    },
                }
                result = terrain_acquisition.run_acquisition(
                    config,
                    prefer_netcdf=not args.json,
                    allow_network=args.allow_network,
                    cache_dir=args.cache_dir,
                )
            LOGGER.info("%s", result)
            return 0
        return 2

    return _guard(run, argv)


def makegeo_main(argv: Sequence[str] | None = None) -> int:
    def run(argv_: Sequence[str] | None) -> int:
        parser = argparse.ArgumentParser(description="Build a GEO table from terrain and land-use rasters")
        parser.add_argument("--terrain", required=True)
        parser.add_argument("--landuse", required=True)
        parser.add_argument("--output", required=True)
        parser.add_argument("--verbose", action="store_true")
        args = parser.parse_args(argv_)
        configure_logging(args.verbose)
        makegeo.run(args.terrain, args.landuse, args.output)
        return 0

    return _guard(run, argv)


def plot_main(argv: Sequence[str] | None = None) -> int:
    def run(argv_: Sequence[str] | None) -> int:
        parser = argparse.ArgumentParser(description="Create publishing-quality figures from suite outputs")
        parser.add_argument("--input", required=True)
        parser.add_argument("--output", required=True)
        parser.add_argument("--title", default="Concentration field")
        parser.add_argument("--dpi", type=int, default=300)
        parser.add_argument("--coordinates", choices=["auto", "local", "geographic"], default="auto")
        parser.add_argument("--center-lat", type=float, default=None)
        parser.add_argument("--center-lon", type=float, default=None)
        parser.add_argument("--value-field", default="concentration")
        parser.add_argument("--basemap", default=None, help="local raster image used as plot background")
        parser.add_argument("--basemap-extent", default=None, help="west,south,east,north image extent")
        parser.add_argument("--tile-provider", default=None, help="contextily provider, e.g. OpenStreetMap.Mapnik")
        parser.add_argument("--tile-zoom", type=int, default=14)
        parser.add_argument("--allow-network-basemap", action="store_true")
        parser.add_argument("--marker-size", type=float, default=None)
        parser.add_argument("--cmap", default="viridis")
        parser.add_argument("--log-scale", action="store_true")
        parser.add_argument("--verbose", action="store_true")
        args = parser.parse_args(argv_)
        configure_logging(args.verbose)
        visualization.concentration_scatter(
            args.input,
            args.output,
            title=args.title,
            dpi=args.dpi,
            coordinate_system=args.coordinates,
            center_lat=args.center_lat,
            center_lon=args.center_lon,
            value_field=args.value_field,
            basemap_path=args.basemap,
            basemap_extent=visualization.parse_extent(args.basemap_extent),
            tile_provider=args.tile_provider,
            tile_zoom=args.tile_zoom,
            allow_network_basemap=args.allow_network_basemap,
            marker_size=args.marker_size,
            cmap=args.cmap,
            log_scale=args.log_scale,
        )
        return 0

    return _guard(run, argv)


def main(argv: Sequence[str] | None = None) -> int:
    def run(argv_: Sequence[str] | None) -> int:
        parser = argparse.ArgumentParser(prog="sprtz", description="Pure Python Spritz toolkit")
        parser.add_argument("--verbose", action="store_true", help="enable debug logging")
        sub = parser.add_subparsers(dest="command", required=True)
        workflow = sub.add_parser("run", help="run SpritzMet -> Spritz/particles -> SpritzPost workflow")
        workflow.add_argument("config")
        workflow.add_argument("--output-dir", default="output")
        workflow.add_argument("--backend", choices=_BACKEND_CHOICES, default=None, help="override run.backend")
        workflow.add_argument("--interchange", choices=["json", "netcdf"], default="netcdf")
        workflow.add_argument("--parallel", choices=["serial", "auto", "mpi"], default="serial")
        _add_gpu_backend(workflow)
        _add_hybrid_parallel_options(workflow)
        workflow.add_argument("--auto-terrain", action="store_true", help="run configured terrain acquisition before meteorology")
        workflow.add_argument("--allow-terrain-network", action="store_true", help="allow explicit online terrain providers")
        workflow.add_argument("--terrain-input", default=None, help="prepared GEO/terrain NetCDF used by dispersion models")
        workflow.add_argument("--output-interval", type=float, default=None, help="optional concentration output interval in seconds")
        validate = sub.add_parser("validate", help="load and validate a configuration file")
        validate.add_argument("config")
        backward_cmd = sub.add_parser("backward", help="run backward source or ignition attribution")
        backward_cmd.add_argument("config")
        backward_cmd.add_argument("--meteo", default=None)
        backward_cmd.add_argument("--output", required=True)
        backward_cmd.add_argument("--model", choices=["gaussian", "particles", "firefront"], default="gaussian")
        backward_cmd.add_argument("--format", choices=["json", "csv"], default="json")
        backward_cmd.add_argument("--seed", type=int, default=None)
        doctor = sub.add_parser("doctor", help="run local production-readiness diagnostics")
        doctor.add_argument("--require-netcdf", action="store_true")
        doctor.add_argument("--require-viz", action="store_true")
        doctor.add_argument("--require-mpi", action="store_true")
        doctor.add_argument("--json", action="store_true")
        args = parser.parse_args(argv_)
        configure_logging(args.verbose)
        if args.command == "run":
            result = run_workflow(
                args.config,
                args.output_dir,
                backend=args.backend,
                interchange=args.interchange,
                parallel=args.parallel,
                gpu_backend=args.gpu_backend,
                thread_backend=args.thread_backend,
                threads_per_rank=args.threads_per_rank,
                decomposition=args.decomposition,
                auto_terrain=args.auto_terrain,
                allow_terrain_network=args.allow_terrain_network,
                terrain_input=args.terrain_input,
                output_interval_s=args.output_interval,
            )
            ctx = get_mpi_context(args.parallel)
            if ctx.is_root:
                for key, value in result.items():
                    LOGGER.info("%s: %s", key, value)
            return 0
        if args.command == "validate":
            cfg = load_config(Path(args.config))
            LOGGER.info(
                "valid: grid=%sx%s sources=%s receptors=%s",
                cfg.grid.nx,
                cfg.grid.ny,
                len(cfg.sources),
                len(cfg.receptors),
            )
            return 0
        if args.command == "backward":
            result = backward.run_backward(
                load_config(Path(args.config)),
                args.meteo,
                args.output,
                model=args.model,
                output_format=args.format,
                seed=args.seed,
            )
            LOGGER.info("%s", result.get("component", "spritz.backward"))
            return 0
        if args.command == "doctor":
            report = run_diagnostics(
                require_netcdf=args.require_netcdf,
                require_viz=args.require_viz,
                require_mpi=args.require_mpi,
            )
            if args.json:
                LOGGER.info("%s", json.dumps(report, indent=2, sort_keys=True))
            else:
                LOGGER.info("%s", format_report(report))
            return 0 if report["ok"] else 1
        return 2

    return _guard(run, argv)


if __name__ == "__main__":
    raise SystemExit(main())

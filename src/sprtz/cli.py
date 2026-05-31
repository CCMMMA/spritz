from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Sequence

from .config import load_config
from .doctor import format_report, run_diagnostics
from .exceptions import SprtzError
from .logging import configure_logging
from .models import ctgproc, makegeo, particles, spritz, spritzmet, spritzpost, spritzwrf
from .models import terrain, visualization
from .parallel import get_mpi_context
from .workflow import run_workflow

LOGGER = logging.getLogger(__name__)


def _config_parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--config", required=True, help="JSON, NetCDF-CF companion, or tolerant Fortran-style control file")
    parser.add_argument("--verbose", action="store_true", help="enable debug logging")
    return parser


def _guard(fn, argv: Sequence[str] | None = None) -> int:
    try:
        return fn(argv)
    except SprtzError as exc:
        if not logging.getLogger().handlers:
            configure_logging(False)
        LOGGER.error("%s", exc)
        return 1


def spritzmet_main(argv: Sequence[str] | None = None) -> int:
    def run(argv_: Sequence[str] | None) -> int:
        parser = _config_parser("Run the pure Python SpritzMet diagnostic kernel")
        parser.add_argument("--output", required=True)
        parser.add_argument("--format", default="auto", choices=["auto", "json", "netcdf"])
        args = parser.parse_args(argv_)
        configure_logging(args.verbose)
        spritzmet.run(load_config(args.config), args.output, args.format)
        return 0

    return _guard(run, argv)


def spritz_main(argv: Sequence[str] | None = None) -> int:
    def run(argv_: Sequence[str] | None) -> int:
        parser = _config_parser("Run the pure Python Spritz screening kernel")
        parser.add_argument("--meteo", required=True)
        parser.add_argument("--output", required=True)
        parser.add_argument("--format", default="auto", choices=["auto", "csv", "legacy", "netcdf"])
        parser.add_argument("--parallel", default="serial", choices=["serial", "auto", "mpi"], help="parallel execution mode")
        args = parser.parse_args(argv_)
        configure_logging(args.verbose)
        spritz.run(load_config(args.config), args.meteo, args.output, args.format, parallel=args.parallel)
        return 0

    return _guard(run, argv)


def sprtz_particles_main(argv: Sequence[str] | None = None) -> int:
    def run(argv_: Sequence[str] | None) -> int:
        parser = _config_parser("Run the particle-based Spritz alternative")
        parser.add_argument("--meteo", required=True)
        parser.add_argument("--output", required=True)
        parser.add_argument("--format", default="auto", choices=["auto", "csv", "legacy", "netcdf"])
        parser.add_argument("--seed", type=int, default=None)
        parser.add_argument("--parallel", default="serial", choices=["serial", "auto", "mpi"], help="parallel execution mode")
        args = parser.parse_args(argv_)
        configure_logging(args.verbose)
        particles.run(load_config(args.config), args.meteo, args.output, args.format, args.seed, parallel=args.parallel)
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
        parser.add_argument("--verbose", action="store_true")
        args = parser.parse_args(argv_)
        configure_logging(args.verbose)
        visualization.concentration_scatter(args.input, args.output, title=args.title, dpi=args.dpi)
        return 0

    return _guard(run, argv)


def main(argv: Sequence[str] | None = None) -> int:
    def run(argv_: Sequence[str] | None) -> int:
        parser = argparse.ArgumentParser(prog="sprtz", description="Pure Python Sprtz toolkit")
        parser.add_argument("--verbose", action="store_true", help="enable debug logging")
        sub = parser.add_subparsers(dest="command", required=True)
        workflow = sub.add_parser("run", help="run SpritzMet -> Spritz/particles -> SpritzPost workflow")
        workflow.add_argument("config")
        workflow.add_argument("--output-dir", default="output")
        workflow.add_argument("--backend", choices=["gaussian", "particles"], default="gaussian")
        workflow.add_argument("--interchange", choices=["json", "netcdf"], default="netcdf")
        workflow.add_argument("--parallel", choices=["serial", "auto", "mpi"], default="serial")
        validate = sub.add_parser("validate", help="load and validate a configuration file")
        validate.add_argument("config")
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

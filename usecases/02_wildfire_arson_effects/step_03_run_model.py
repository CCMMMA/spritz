#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sprtz.workflow import run_workflow
from sprtz.io.jsonio import read_json

USECASES_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(USECASES_ROOT))

from plotting import plot_workflow_netcdfs
from wildfire import ensure_wildfire_receptor_coordinates


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Spritz for a prepared wildfire/arson configuration")
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--backend", choices=["gaussian", "particles"], default="particles")
    parser.add_argument("--interchange", choices=["json", "netcdf"], default="netcdf")
    args = parser.parse_args(argv)
    ensure_wildfire_receptor_coordinates(args.config)
    config = read_json(args.config)
    metadata = config.get("metadata", {})
    center_lat = metadata.get("center_lat")
    center_lon = metadata.get("center_lon")
    workflow = run_workflow(args.config, args.output_dir, backend=args.backend, interchange=args.interchange, parallel="serial")
    plot_workflow_netcdfs(
        workflow,
        args.output_dir,
        center_lat=None if center_lat is None else float(center_lat),
        center_lon=None if center_lon is None else float(center_lon),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

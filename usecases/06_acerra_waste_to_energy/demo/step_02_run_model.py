#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sprtz.workflow import run_workflow

USECASES_ROOT = Path(__file__).resolve().parents[2]
COMMON_DIR = USECASES_ROOT / "common"
for path in (COMMON_DIR, USECASES_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from plotting import add_plot_argument, plot_workflow_netcdfs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Spritz for a prepared Acerra waste-to-energy configuration")
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--interchange", choices=["json", "netcdf"], default="netcdf")
    add_plot_argument(parser)
    args = parser.parse_args(argv)
    workflow = run_workflow(args.config, args.output_dir, interchange=args.interchange)
    if args.plot:
        plot_workflow_netcdfs(workflow, args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

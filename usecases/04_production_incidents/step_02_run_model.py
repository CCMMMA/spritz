#!/usr/bin/env python3
from __future__ import annotations

import argparse

from sprtz.workflow import run_workflow


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Spritz for a prepared production-incident configuration")
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--interchange", choices=["json", "netcdf"], default="netcdf")
    args = parser.parse_args(argv)
    run_workflow(args.config, args.output_dir, backend="gaussian", interchange=args.interchange)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

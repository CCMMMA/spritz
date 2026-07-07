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
    parser = argparse.ArgumentParser(description="Run the coupled wildfire fire-spread stage")
    add_plot_argument(parser)
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[2]
    out = root / "output_fire_smoke"
    workflow = run_workflow(root / "examples" / "wildfire_minimal.json", out, backend="firefront", interchange="netcdf")
    if args.plot:
        plot_workflow_netcdfs(workflow, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

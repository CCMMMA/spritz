from __future__ import annotations

import sys
from pathlib import Path

from sprtz.workflow import run_workflow

USECASES_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(USECASES_ROOT))

from plotting import plot_workflow_netcdfs


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    out = root / "output_fire"
    workflow = run_workflow(root / "examples" / "wildfire_minimal.json", out, backend="firefront", interchange="netcdf")
    plot_workflow_netcdfs(workflow, out)


if __name__ == "__main__":
    main()

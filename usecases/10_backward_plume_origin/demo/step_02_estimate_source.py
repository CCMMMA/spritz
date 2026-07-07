from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sprtz.config import load_config
from sprtz.models import backward

USECASES_ROOT = Path(__file__).resolve().parents[2]
COMMON_DIR = USECASES_ROOT / "common"
for path in (COMMON_DIR, USECASES_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from plotting import add_plot_argument, plot_netcdf_if_available, write_grid_result_netcdf_if_available


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Estimate backward plume source likelihood")
    add_plot_argument(parser)
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[2]
    out = root / "output_backward_plume"
    cfg = load_config(root / "examples" / "backward_plume.json")
    result = backward.run_backward(cfg, out / "meteo.nc", out / "source_likelihood.json", model="gaussian")
    sidecar = write_grid_result_netcdf_if_available(
        result,
        out / "source_likelihood.nc",
        variable="source_likelihood",
        long_name="backward plume source likelihood",
    )
    if args.plot:
        plot_netcdf_if_available(sidecar, out / "source_likelihood_map.png", variable="source_likelihood")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

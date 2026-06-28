from __future__ import annotations

import sys
from pathlib import Path

from sprtz.config import load_config
from sprtz.models import backward

USECASES_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(USECASES_ROOT))

from plotting import plot_netcdf_if_available, write_grid_result_netcdf_if_available


def main() -> None:
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
    plot_netcdf_if_available(sidecar, out / "source_likelihood_map.png", variable="source_likelihood")


if __name__ == "__main__":
    main()

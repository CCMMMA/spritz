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
    out = root / "output_backward_fire"
    out.mkdir(parents=True, exist_ok=True)
    cfg = load_config(root / "examples" / "backward_firefront.json")
    result = backward.run_backward(cfg, None, out / "ignition_likelihood.json", model="firefront")
    sidecar = write_grid_result_netcdf_if_available(
        result,
        out / "ignition_likelihood.nc",
        variable="ignition_likelihood",
        long_name="backward fire ignition likelihood",
    )
    plot_netcdf_if_available(sidecar, out / "ignition_likelihood_map.png", variable="ignition_likelihood")


if __name__ == "__main__":
    main()

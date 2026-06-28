from __future__ import annotations

import sys
from pathlib import Path

from sprtz.config import load_config
from sprtz.models import spritzmet

USECASES_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(USECASES_ROOT))

from plotting import plot_netcdf_if_available


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    out = root / "output_backward_plume"
    out.mkdir(parents=True, exist_ok=True)
    cfg = load_config(root / "examples" / "backward_plume.json")
    meteo = out / "meteo.nc"
    spritzmet.run(cfg, meteo, "netcdf")
    plot_netcdf_if_available(meteo, out / "meteo_map.png", variable="wind_speed", title="Backward Plume Meteorology")


if __name__ == "__main__":
    main()

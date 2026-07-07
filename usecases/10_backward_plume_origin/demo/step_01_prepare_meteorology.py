from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sprtz.config import load_config
from sprtz.models import spritzmet

USECASES_ROOT = Path(__file__).resolve().parents[2]
COMMON_DIR = USECASES_ROOT / "common"
for path in (COMMON_DIR, USECASES_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from plotting import add_plot_argument, plot_netcdf_if_available


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare meteorology for the backward plume demo")
    add_plot_argument(parser)
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[2]
    out = root / "output_backward_plume"
    out.mkdir(parents=True, exist_ok=True)
    cfg = load_config(root / "examples" / "backward_plume.json")
    meteo = out / "meteo.nc"
    spritzmet.run(cfg, meteo, "netcdf")
    if args.plot:
        plot_netcdf_if_available(meteo, out / "meteo_map.png", variable="wind_speed", title="Backward Plume Meteorology")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

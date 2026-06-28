from __future__ import annotations

from pathlib import Path

from sprtz.config import load_config
from sprtz.models import spritzmet


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    out = root / "output_backward_plume"
    out.mkdir(parents=True, exist_ok=True)
    cfg = load_config(root / "examples" / "backward_plume.json")
    spritzmet.run(cfg, out / "meteo.json", "json")


if __name__ == "__main__":
    main()

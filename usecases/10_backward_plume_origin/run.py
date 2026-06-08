from __future__ import annotations

from pathlib import Path

from sprtz.config import load_config
from sprtz.models import backward, spritzmet


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    cfg = load_config(root / "examples" / "backward_plume.json")
    out = root / "output_backward_plume"
    out.mkdir(parents=True, exist_ok=True)
    meteo = out / "meteo.json"
    spritzmet.run(cfg, meteo, "json")
    backward.run_backward(cfg, meteo, out / "source_likelihood.json", model="gaussian")


if __name__ == "__main__":
    main()

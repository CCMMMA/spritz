from __future__ import annotations

from pathlib import Path

from sprtz.config import load_config
from sprtz.models import backward


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    out = root / "output_backward_plume"
    cfg = load_config(root / "examples" / "backward_plume.json")
    backward.run_backward(cfg, out / "meteo.json", out / "source_likelihood.json", model="gaussian")


if __name__ == "__main__":
    main()

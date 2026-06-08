from __future__ import annotations

from pathlib import Path

from sprtz.config import load_config
from sprtz.models import backward


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    cfg = load_config(root / "examples" / "backward_firefront.json")
    out = root / "output_backward_fire"
    out.mkdir(parents=True, exist_ok=True)
    backward.run_backward(cfg, None, out / "ignition_likelihood.json", model="firefront")


if __name__ == "__main__":
    main()

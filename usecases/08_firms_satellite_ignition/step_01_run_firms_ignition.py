from __future__ import annotations

from pathlib import Path

from sprtz.workflow import run_workflow


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    run_workflow(root / "examples" / "wildfire_minimal.json", root / "output_firms", backend="firms+fire", interchange="json")


if __name__ == "__main__":
    main()

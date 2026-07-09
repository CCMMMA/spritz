#!/usr/bin/env python3
import argparse
import json
import logging
from pathlib import Path

import numpy as np

from sprtz.logging import configure_logging

LOGGER = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a deterministic satellite-mask demo file")
    parser.add_argument("--output", required=True)
    parser.add_argument("--size", type=int, default=11, help="Default width and height")
    parser.add_argument("--width", type=int, help="Mask columns; overrides --size")
    parser.add_argument("--height", type=int, help="Mask rows; overrides --size")
    args = parser.parse_args(argv)
    width = args.width if args.width is not None else args.size
    height = args.height if args.height is not None else args.size
    if width < 1 or height < 1:
        parser.error("--size, --width, and --height must be at least 1")
    x_axis = np.zeros(1) if width == 1 else np.linspace(-1.0, 1.0, width)
    y_axis = np.zeros(1) if height == 1 else np.linspace(-1.0, 1.0, height)
    x, y = np.meshgrid(x_axis, y_axis)
    mask = np.exp(-((x - 0.15) ** 2 + (y + 0.05) ** 2) / 0.22)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp")
    temporary.write_text(json.dumps({"mask": mask.tolist()}, indent=2) + "\n", encoding="utf-8")
    temporary.replace(output)
    LOGGER.info("Wrote deterministic %dx%d satellite mask to %s", height, width, output)
    return 0


if __name__ == "__main__":
    configure_logging(False)
    raise SystemExit(main())

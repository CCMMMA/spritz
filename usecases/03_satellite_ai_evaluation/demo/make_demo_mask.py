#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

import numpy as np


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a deterministic satellite-mask demo file")
    parser.add_argument("--output", required=True)
    parser.add_argument("--size", type=int, default=11)
    args = parser.parse_args()
    y, x = np.mgrid[-1:1:complex(args.size), -1:1:complex(args.size)]
    mask = np.exp(-((x - 0.15) ** 2 + (y + 0.05) ** 2) / 0.22)
    Path(args.output).write_text(json.dumps({"mask": mask.tolist()}, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Compatibility-neutral entry point for the Sentinel-5P subset downloader."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

if __name__ == "__main__":
    legacy_path = Path(__file__).with_name("copernicus-s5p-no2-download.py")
    spec = importlib.util.spec_from_file_location("copernicus_s5p_downloader", legacy_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load Sentinel-5P downloader from {legacy_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    raise SystemExit(module.main(sys.argv[1:], prog=Path(__file__).name))

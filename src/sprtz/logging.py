from __future__ import annotations

import logging
import sys
from typing import TextIO


LOG_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S%z"
LOG_FORMAT = "%(asctime)s +%(relativeCreated).0fms %(message)s"
LOG_FORMAT_VERBOSE = "%(asctime)s +%(relativeCreated).0fms %(levelname)s %(name)s: %(message)s"


def configure_logging(verbose: bool = False, *, stream: TextIO | None = None) -> None:
    """Configure process-wide logging for CLIs and use-case scripts.

    All log records include an absolute timestamp and elapsed milliseconds so
    runtime logs can be used to evaluate wall-clock performance. Verbose mode
    adds severity and logger name for diagnostics.
    """
    level = logging.DEBUG if verbose else logging.INFO
    fmt = LOG_FORMAT_VERBOSE if verbose else LOG_FORMAT
    logging.basicConfig(
        level=level,
        format=fmt,
        datefmt=LOG_DATE_FORMAT,
        stream=stream or sys.stdout,
        force=True,
    )

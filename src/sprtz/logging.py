from __future__ import annotations

import logging
import sys
from typing import TextIO


def configure_logging(verbose: bool = False, *, stream: TextIO | None = None) -> None:
    """Configure process-wide logging for CLIs and use-case scripts.

    Normal CLI mode emits message text only, which keeps JSON and shell-oriented
    output parseable while still using the logging subsystem.  Verbose mode adds
    severity and logger name for diagnostics.
    """
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(levelname)s %(name)s: %(message)s" if verbose else "%(message)s"
    logging.basicConfig(
        level=level,
        format=fmt,
        stream=stream or sys.stdout,
        force=True,
    )

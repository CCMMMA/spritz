from __future__ import annotations

import io
import logging
import re

from sprtz.logging import configure_logging


def test_configure_logging_includes_timestamp_and_elapsed_time() -> None:
    stream = io.StringIO()
    configure_logging(False, stream=stream)

    logging.getLogger("sprtz.test").info("hello")

    line = stream.getvalue().strip()
    assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{4} \+\d+ms hello", line)

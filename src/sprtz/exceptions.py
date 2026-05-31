from __future__ import annotations


class SprtzError(Exception):
    """Base exception for sprtz."""


class ConfigurationError(SprtzError, ValueError):
    """Raised when a suite configuration is invalid."""


class DataFormatError(SprtzError, ValueError):
    """Raised when an input data file cannot be parsed safely."""


class ParallelExecutionError(SprtzError, RuntimeError):
    """Raised when requested parallel execution cannot be initialized."""

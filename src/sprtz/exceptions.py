from __future__ import annotations


class SpritzError(Exception):
    """Base exception for sprtz."""


class ConfigurationError(SpritzError, ValueError):
    """Raised when a suite configuration is invalid."""


class DataFormatError(SpritzError, ValueError):
    """Raised when an input data file cannot be parsed safely."""


class ParallelExecutionError(SpritzError, RuntimeError):
    """Raised when requested parallel execution cannot be initialized."""

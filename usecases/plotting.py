"""Compatibility imports for shared use-case plotting helpers."""

try:
    from usecases.common.plotting import *  # noqa: F403
except ModuleNotFoundError as exc:
    if exc.name != "usecases":
        raise
    from common.plotting import *  # noqa: F403

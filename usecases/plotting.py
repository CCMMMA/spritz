"""Compatibility alias for the shared use-case plotting helpers."""

try:
    from usecases.common import plotting as _plotting
except ModuleNotFoundError as exc:
    if exc.name != "usecases":
        raise
    from common import plotting as _plotting

# Make ``import plotting`` and ``import usecases.common.plotting`` return the
# same module object. This keeps monkeypatching and private helper lookup
# consistent instead of creating a shallow wildcard-import facade.
import sys

sys.modules[__name__] = _plotting

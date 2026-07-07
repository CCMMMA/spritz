"""Dagonstar workflow sketch for the 05 Sailing Wind Forecast use case."""

from __future__ import annotations

# Install dagonstar separately and adapt the task helper to the API version used
# by your deployment. This sketch preserves the documented Sprtz step order.


def build_workflow(task):
    """Return Dagonstar-compatible tasks for this use case."""
    t1 = task("step_01", "python usecases/05_sailing_wind_forecast/demo/step_01_build_forecast.py")
    return [value for key, value in sorted(locals().items()) if key.startswith("t")]

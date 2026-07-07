"""Dagonstar workflow sketch for the 08 Firms Satellite Ignition use case."""

from __future__ import annotations

# Install dagonstar separately and adapt the task helper to the API version used
# by your deployment. This sketch preserves the documented Sprtz step order.


def build_workflow(task):
    """Return Dagonstar-compatible tasks for this use case."""
    t1 = task("step_01", "python usecases/08_firms_satellite_ignition/demo/step_01_run_firms_ignition.py")
    return [value for key, value in sorted(locals().items()) if key.startswith("t")]

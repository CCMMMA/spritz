"""Dagonstar workflow sketch for the 11 Backward Fire Origin use case."""

from __future__ import annotations

# Install dagonstar separately and adapt the task helper to the API version used
# by your deployment. This sketch preserves the documented Sprtz step order.


def build_workflow(task):
    """Return Dagonstar-compatible tasks for this use case."""
    t1 = task("step_01", "python usecases/11_backward_fire_origin/demo/step_01_estimate_ignition.py")
    return [value for key, value in sorted(locals().items()) if key.startswith("t")]

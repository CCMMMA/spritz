"""Dagonstar workflow sketch for the 10 Backward Plume Origin use case."""

from __future__ import annotations

# Install dagonstar separately and adapt the task helper to the API version used
# by your deployment. This sketch preserves the documented Sprtz step order.


def build_workflow(task):
    """Return Dagonstar-compatible tasks for this use case."""
    t1 = task("step_01", "python usecases/10_backward_plume_origin/demo/step_01_prepare_meteorology.py")
    t2 = task("step_02", "python usecases/10_backward_plume_origin/demo/step_02_estimate_source.py")
    t1 >> t2
    return [value for key, value in sorted(locals().items()) if key.startswith("t")]

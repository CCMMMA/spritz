"""Dagonstar workflow sketch for the 02 Wildfire Arson Effects use case."""

from __future__ import annotations

# Install dagonstar separately and adapt the task helper to the API version used
# by your deployment. This sketch preserves the documented Sprtz step order.


def build_workflow(task):
    """Return Dagonstar-compatible tasks for this use case."""
    t1 = task("step_01", "python usecases/02_wildfire_arson_effects/demo/step_01_downscale_wind.py")
    t2 = task("step_02", "python usecases/02_wildfire_arson_effects/demo/step_02_build_config.py")
    t3 = task("step_03", "python usecases/02_wildfire_arson_effects/demo/step_03_run_model.py")
    t1 >> t2
    t2 >> t3
    return [value for key, value in sorted(locals().items()) if key.startswith("t")]

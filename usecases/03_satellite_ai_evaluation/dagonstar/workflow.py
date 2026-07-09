"""Dagonstar workflow sketch for the 03 Satellite Ai Evaluation use case."""

from __future__ import annotations

# Install dagonstar separately and adapt the task helper to the API version used
# by your deployment. The shell pipeline is the canonical executable sequence.


def build_workflow(task):
    """Return Dagonstar-compatible tasks for this use case."""
    pipeline = task(
        "satellite_ai_evaluation",
        "bash usecases/03_satellite_ai_evaluation/pipeline/pipeline.sh",
    )
    return [pipeline]

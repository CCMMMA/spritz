#!/usr/bin/env python3
"""Score Spritz output against paired controlled-tracer receptor observations."""

from __future__ import annotations

import argparse
import csv
import logging
from pathlib import Path
from typing import Any

import numpy as np

from sprtz.io.jsonio import write_json
from sprtz.io.netcdf_cf import read_cf_concentration
from sprtz.logging import configure_logging

LOGGER = logging.getLogger(__name__)


def _key(row: dict[str, Any]) -> tuple[str, float]:
    receptor = row.get("receptor_id", row.get("id"))
    time = row.get("time_s", row.get("time"))
    if receptor is None or time is None:
        raise ValueError("rows must contain receptor_id (or id) and time_s (or time)")
    return str(receptor), float(time)


def _read_observations(path: str | Path) -> list[dict[str, Any]]:
    with Path(path).open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError("controlled-tracer observation CSV is empty")
    for row in rows:
        _key(row)
        if "concentration" not in row:
            raise ValueError("observation CSV must contain concentration")
        row["concentration"] = float(row["concentration"])
    return rows


def _read_model(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path)
    if source.suffix.lower() in {".nc", ".cdf", ".netcdf", ".json"}:
        rows = read_cf_concentration(source)
    else:
        with source.open(newline="", encoding="utf-8-sig") as stream:
            rows = list(csv.DictReader(stream))
    receptor_rows = [row for row in rows if str(row.get("output_kind", "receptor")).lower() != "field"]
    return receptor_rows or rows


def paired_samples(
    model_rows: list[dict[str, Any]],
    observation_rows: list[dict[str, Any]],
) -> tuple[np.ndarray, np.ndarray, list[dict[str, Any]]]:
    model = {_key(row): float(row.get("concentration", 0.0)) for row in model_rows}
    predicted: list[float] = []
    observed: list[float] = []
    pairs: list[dict[str, Any]] = []
    for row in observation_rows:
        key = _key(row)
        if key not in model:
            continue
        prediction = model[key]
        observation = float(row["concentration"])
        if not np.isfinite(prediction) or not np.isfinite(observation) or prediction < 0.0 or observation < 0.0:
            continue
        predicted.append(prediction)
        observed.append(observation)
        pairs.append({"receptor_id": key[0], "time_s": key[1], "model": prediction, "observed": observation})
    if not pairs:
        raise ValueError("model and observations have no finite paired receptor/time samples")
    return np.asarray(predicted), np.asarray(observed), pairs


def validation_metrics(
    predicted: np.ndarray,
    observed: np.ndarray,
    *,
    detection_limit: float,
) -> dict[str, float | int | None]:
    if detection_limit < 0.0:
        raise ValueError("detection limit must be non-negative")
    mean_model = float(np.mean(predicted))
    mean_observed = float(np.mean(observed))
    mean_sum = mean_model + mean_observed
    difference = predicted - observed
    positive = (predicted > 0.0) & (observed > 0.0)
    ratio = np.divide(predicted, observed, out=np.full_like(predicted, np.nan), where=observed > 0.0)
    predicted_detected = predicted >= detection_limit
    observed_detected = observed >= detection_limit
    return {
        "paired_sample_count": int(predicted.size),
        "fractional_bias": 2.0 * (mean_model - mean_observed) / mean_sum if mean_sum > 0.0 else 0.0,
        "normalized_mean_square_error": (
            float(np.mean(difference**2)) / (mean_model * mean_observed)
            if mean_model > 0.0 and mean_observed > 0.0 else None
        ),
        "fraction_within_factor_2": float(np.mean(positive & (ratio >= 0.5) & (ratio <= 2.0))),
        "fraction_within_factor_5": float(np.mean(positive & (ratio >= 0.2) & (ratio <= 5.0))),
        "pearson_correlation": (
            float(np.corrcoef(predicted, observed)[0, 1])
            if predicted.size > 1 and np.std(predicted) > 0.0 and np.std(observed) > 0.0 else None
        ),
        "root_mean_square_error": float(np.sqrt(np.mean(difference**2))),
        "mean_absolute_error": float(np.mean(np.abs(difference))),
        "true_positive": int(np.count_nonzero(predicted_detected & observed_detected)),
        "false_positive": int(np.count_nonzero(predicted_detected & ~observed_detected)),
        "false_negative": int(np.count_nonzero(~predicted_detected & observed_detected)),
        "true_negative": int(np.count_nonzero(~predicted_detected & ~observed_detected)),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, help="Spritz receptor CSV/JSON/NetCDF")
    parser.add_argument("--observations", required=True, help="Controlled-tracer paired observation CSV")
    parser.add_argument("--output", required=True)
    parser.add_argument("--experiment", required=True, choices=("prairie-grass", "copenhagen", "etex", "captex", "custom"))
    parser.add_argument("--backend", required=True, choices=("gaussian", "particles"))
    parser.add_argument("--unit", required=True, help="Shared model/observation concentration unit")
    parser.add_argument("--detection-limit", type=float, default=0.0)
    args = parser.parse_args(argv)
    configure_logging(False)
    try:
        predicted, observed, pairs = paired_samples(_read_model(args.model), _read_observations(args.observations))
        metrics = validation_metrics(predicted, observed, detection_limit=args.detection_limit)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    write_json(args.output, {
        "component": "usecase03.controlled_tracer_validation",
        "experiment": args.experiment,
        "backend": args.backend,
        "unit": args.unit,
        "detection_limit": args.detection_limit,
        "model_path": str(Path(args.model)),
        "observation_path": str(Path(args.observations)),
        "metrics": metrics,
        "pairs": pairs,
        "interpretation": "Paired receptor/time validation against an independent controlled release.",
    })
    LOGGER.info("Wrote %s controlled-tracer validation to %s", args.backend, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

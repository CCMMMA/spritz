from __future__ import annotations

import logging

import csv
import sys
from pathlib import Path
from typing import Any

import numpy as np

from sprtz.exceptions import DataFormatError
from sprtz.io.jsonio import read_json, write_json
from sprtz.io.netcdf_cf import read_cf_concentration
from sprtz.logging import configure_logging

COMMON_DIR = Path(__file__).resolve().parents[2] / "common"
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))

from plotting import add_plot_argument, plot_netcdf_if_available


def _read_concentration(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    if p.suffix.lower() in {".nc", ".cdf", ".netcdf", ".json", ".jsn"}:
        try:
            return read_cf_concentration(p)
        except Exception:
            data = read_json(p)
            if isinstance(data, dict) and "rows" in data:
                return list(data["rows"])
            raise
    with p.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _read_satellite_mask(path: str | Path) -> np.ndarray:
    p = Path(path)
    if p.suffix.lower() in {".json", ".jsn"}:
        data = read_json(p)
        if isinstance(data, dict):
            if "mask" in data:
                return np.asarray(data["mask"], dtype=float)
            if "probability" in data:
                return np.asarray(data["probability"], dtype=float)
        return np.asarray(data, dtype=float)
    if p.suffix.lower() == ".npy":
        return np.asarray(np.load(p), dtype=float)
    if p.suffix.lower() in {".csv", ".txt", ".asc"}:
        return np.asarray(np.loadtxt(p, delimiter="," if p.suffix.lower() == ".csv" else None), dtype=float)
    raise DataFormatError(f"unsupported satellite mask format: {p}")


def concentration_to_probability(rows: list[dict[str, Any]], shape: tuple[int, int] | None = None, percentile_scale: float = 95.0) -> np.ndarray:
    values = np.asarray([float(row.get("concentration", 0.0)) for row in rows], dtype=float)
    if values.size == 0:
        raise DataFormatError("empty concentration input")
    scale = np.percentile(values, percentile_scale)
    if scale <= 0:
        scale = max(float(values.max()), 1.0)
    probabilities = np.clip(values / scale, 0.0, 1.0)
    if shape is None:
        n = int(np.ceil(np.sqrt(values.size)))
        padded = np.zeros(n * n, dtype=float)
        padded[: probabilities.size] = probabilities
        return padded.reshape(n, n)
    expected = int(shape[0] * shape[1])
    if expected != probabilities.size:
        # Resample along index space for pragmatic comparison when satellite
        # pixels and model receptors have different counts.
        src = np.linspace(0.0, 1.0, probabilities.size)
        dst = np.linspace(0.0, 1.0, expected)
        probabilities = np.interp(dst, src, probabilities)
    return probabilities.reshape(shape)


def _confusion(predicted: np.ndarray, observed: np.ndarray, threshold: float) -> dict[str, int]:
    pred = predicted >= threshold
    obs = observed >= threshold
    return {
        "true_positive": int(np.logical_and(pred, obs).sum()),
        "false_positive": int(np.logical_and(pred, ~obs).sum()),
        "true_negative": int(np.logical_and(~pred, ~obs).sum()),
        "false_negative": int(np.logical_and(~pred, obs).sum()),
    }


def _metrics(confusion: dict[str, int]) -> dict[str, float]:
    tp = confusion["true_positive"]
    fp = confusion["false_positive"]
    tn = confusion["true_negative"]
    fn = confusion["false_negative"]
    total = max(1, tp + fp + tn + fn)
    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)
    return {
        "accuracy": (tp + tn) / total,
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / max(1.0e-12, precision + recall),
        "critical_success_index": tp / max(1, tp + fp + fn),
        "false_alarm_ratio": fp / max(1, tp + fp),
        "probability_of_detection": recall,
    }


def _ai_calibrate(predicted: np.ndarray, observed: np.ndarray) -> dict[str, Any]:
    """Tiny deterministic AI-style calibration layer using logistic gradient descent.

    This avoids mandatory heavy ML dependencies while providing a documented
    extension point for scikit-learn, PyTorch, or remote sensing foundation
    models in operational deployments.
    """
    x = predicted.ravel().astype(float)
    y = (observed.ravel() >= 0.5).astype(float)
    w = 1.0
    b = 0.0
    lr = 0.2
    for _ in range(200):
        z = np.clip(w * x + b, -40.0, 40.0)
        p = 1.0 / (1.0 + np.exp(-z))
        grad_w = float(np.mean((p - y) * x))
        grad_b = float(np.mean(p - y))
        w -= lr * grad_w
        b -= lr * grad_b
    calibrated = 1.0 / (1.0 + np.exp(-np.clip(w * x + b, -40.0, 40.0)))
    rmse = float(np.sqrt(np.mean((calibrated - y) ** 2)))
    return {"method": "logistic_gradient_descent", "weight": float(w), "bias": float(b), "rmse": rmse}


def evaluate_wildfire_event(
    concentration_path: str | Path,
    satellite_mask_path: str | Path,
    output_path: str | Path,
    *,
    threshold: float = 0.5,
    use_ai_calibration: bool = True,
    make_plot: bool = False,
) -> dict[str, Any]:
    """Evaluate a wildfire/arson simulation against satellite-derived evidence.

    The satellite input is expected to be a probability mask from burned-area,
    active-fire, or smoke-plume retrieval. Accepted lightweight formats are JSON,
    NPY, CSV, TXT, or ASCII grid-like numeric matrices.
    """
    rows = _read_concentration(concentration_path)
    observed = _read_satellite_mask(satellite_mask_path)
    if observed.ndim != 2:
        raise DataFormatError("satellite mask must be a two-dimensional array")
    observed = np.clip(observed.astype(float), 0.0, 1.0)
    predicted = concentration_to_probability(rows, observed.shape)
    confusion = _confusion(predicted, observed, threshold)
    metrics = _metrics(confusion)
    result: dict[str, Any] = {
        "component": "usecase.satellite_ai_evaluation",
        "concentration_path": str(concentration_path),
        "satellite_mask_path": str(satellite_mask_path),
        "threshold": threshold,
        "confusion": confusion,
        "metrics": metrics,
        "predicted_probability_summary": {
            "min": float(predicted.min()),
            "mean": float(predicted.mean()),
            "max": float(predicted.max()),
        },
        "observed_probability_summary": {
            "min": float(observed.min()),
            "mean": float(observed.mean()),
            "max": float(observed.max()),
        },
    }
    if use_ai_calibration:
        result["ai_calibration"] = _ai_calibrate(predicted, observed)
    write_json(output_path, result)
    if make_plot:
        concentration_map = plot_netcdf_if_available(
            concentration_path,
            Path(output_path).with_name(Path(output_path).stem + "_concentration_map.png"),
            variable="concentration",
            title="Evaluated Concentration",
        )
        if concentration_map is not None:
            result["concentration_map"] = str(concentration_map)
            write_json(output_path, result)
    return result


LOGGER = logging.getLogger(__name__)

def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Evaluate wildfire/arson Spritz output with satellite masks and AI calibration")
    parser.add_argument("--concentration", required=True)
    parser.add_argument("--satellite-mask", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--no-ai", action="store_true")
    add_plot_argument(parser)
    args = parser.parse_args(argv)
    result = evaluate_wildfire_event(
        args.concentration,
        args.satellite_mask,
        args.output,
        threshold=args.threshold,
        use_ai_calibration=not args.no_ai,
        make_plot=args.plot,
    )
    configure_logging(False)
    LOGGER.info("%s", result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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
            rows = read_cf_concentration(p)
            receptor_rows = [
                row for row in rows
                if str(row.get("output_kind", "receptor")).lower() != "field"
            ]
            return receptor_rows or rows
        except Exception:
            data = read_json(p)
            if isinstance(data, dict) and "rows" in data:
                rows = list(data["rows"])
                receptor_rows = [
                    row for row in rows
                    if str(row.get("output_kind", "receptor")).lower() != "field"
                ]
                return receptor_rows or rows
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


def _read_station_observations(path: str | Path) -> list[dict[str, Any]]:
    """Read station observations from the use-case CSV.

    The station CSV is used as an independent spatial-pattern diagnostic. The
    current file provides NO2 observations; these are not physically converted
    to Aerosol Index or Spritz concentration. They are normalized across
    colocated in-domain stations before skill statistics are computed.
    """

    stations: list[dict[str, Any]] = []
    with Path(path).open("r", newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            station_id = row.get("id") or row.get("station_id") or row.get("name")
            lat = row.get("LAT") or row.get("lat") or row.get("latitude")
            lon = row.get("LON") or row.get("lon") or row.get("longitude")
            no2 = row.get("NO2") or row.get("no2") or row.get("no2_ug_m3")
            if station_id is None or lat is None or lon is None or no2 is None:
                raise DataFormatError(
                    "station CSV must contain id, LAT, LON, and NO2 columns"
                )
            stations.append(
                {
                    "id": str(station_id),
                    "latitude": float(lat),
                    "longitude": float(lon),
                    "no2": float(no2),
                }
            )
    if not stations:
        raise DataFormatError("station CSV must contain at least one observation")
    return stations


def _normalise_samples(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    if values.size == 0:
        return values
    low = float(np.nanmin(values))
    high = float(np.nanmax(values))
    if high <= low:
        return np.zeros_like(values, dtype=float)
    return np.clip((values - low) / (high - low), 0.0, 1.0)


def _continuous_stats(predicted: np.ndarray, observed: np.ndarray) -> dict[str, float | None]:
    difference = predicted - observed
    return {
        "bias": float(np.mean(difference)),
        "mean_absolute_error": float(np.mean(np.abs(difference))),
        "root_mean_square_error": float(np.sqrt(np.mean(difference**2))),
        "pearson_correlation": (
            float(np.corrcoef(predicted.ravel(), observed.ravel())[0, 1])
            if predicted.size > 1
            and float(np.std(predicted)) > 0.0
            and float(np.std(observed)) > 0.0
            else None
        ),
    }


def _read_model_field_sample_source(
    concentration_path: str | Path,
    *,
    time_index: int | None,
) -> np.ndarray | None:
    path = Path(concentration_path)
    if path.suffix.lower() not in {".nc", ".cdf", ".netcdf"}:
        return None
    try:
        from netCDF4 import Dataset
    except Exception as exc:  # pragma: no cover - depends on optional extras.
        LOGGER.warning("Skipping station/model field validation: %s", exc)
        return None
    with Dataset(path) as ds:
        if "concentration_field" not in ds.variables:
            return None
        field = np.ma.filled(ds["concentration_field"][:], np.nan).astype(float)
    if field.ndim == 4:
        resolved = 0 if time_index is None else time_index
        if resolved < 0:
            resolved = field.shape[0] + resolved
        if not 0 <= resolved < field.shape[0]:
            raise DataFormatError(
                f"time index {time_index} is outside the {field.shape[0]} field times"
            )
        return np.asarray(field[resolved, 0, :, :], dtype=float)
    if field.ndim == 3:
        resolved = 0 if time_index is None else time_index
        if resolved < 0:
            resolved = field.shape[0] + resolved
        if not 0 <= resolved < field.shape[0]:
            raise DataFormatError(
                f"time index {time_index} is outside the {field.shape[0]} field times"
            )
        return np.asarray(field[resolved, :, :], dtype=float)
    return None


def _station_validation(
    *,
    concentration_path: str | Path,
    satellite_mask_path: str | Path,
    station_observations_path: str | Path,
    time_index: int | None,
    model_absolute_threshold: float = 1.0e-15,
    model_relative_threshold: float = 1.0e-12,
) -> dict[str, Any]:
    satellite_payload = read_json(satellite_mask_path)
    if not isinstance(satellite_payload, dict):
        raise DataFormatError("station validation requires aligned satellite JSON provenance")
    provenance = satellite_payload.get("provenance", {})
    bbox = provenance.get("domain_bbox_wgs84")
    if not isinstance(bbox, list) or len(bbox) != 4:
        raise DataFormatError(
            "station validation requires satellite provenance domain_bbox_wgs84"
        )
    satellite_field = np.asarray(satellite_payload.get("downscaled_field"), dtype=float)
    if satellite_field.ndim != 2:
        raise DataFormatError("station validation requires downscaled_field in satellite JSON")
    model_field = _read_model_field_sample_source(
        concentration_path,
        time_index=time_index,
    )
    if model_field is None:
        raise DataFormatError(
            "station validation requires NetCDF concentration_field model output"
        )
    if model_field.shape != satellite_field.shape:
        raise DataFormatError(
            "model concentration field and satellite downscaled field shapes differ "
            f"({model_field.shape} != {satellite_field.shape})"
        )
    model_peak = float(np.nanmax(np.where(np.isfinite(model_field), model_field, 0.0)))
    model_active_threshold = max(
        float(model_absolute_threshold),
        float(model_relative_threshold) * model_peak,
    )

    west, south, east, north = [float(value) for value in bbox]
    ny, nx = satellite_field.shape
    samples: list[dict[str, Any]] = []
    for station in _read_station_observations(station_observations_path):
        lon = float(station["longitude"])
        lat = float(station["latitude"])
        inside = west <= lon <= east and south <= lat <= north
        if not inside:
            continue
        col = int(round((lon - west) / max(east - west, np.finfo(float).eps) * (nx - 1)))
        row = int(round((north - lat) / max(north - south, np.finfo(float).eps) * (ny - 1)))
        row = min(max(row, 0), ny - 1)
        col = min(max(col, 0), nx - 1)
        model_value = float(model_field[row, col])
        satellite_value = float(satellite_field[row, col])
        if not np.isfinite(model_value) or not np.isfinite(satellite_value):
            continue
        if model_value <= model_active_threshold:
            model_value = 0.0
        samples.append(
            {
                "id": station["id"],
                "latitude": lat,
                "longitude": lon,
                "row": row,
                "col": col,
                "station_no2": float(station["no2"]),
                "model_concentration": model_value,
                "satellite_probability": satellite_value,
            }
        )
    if not samples:
        return {
            "station_observations_path": str(station_observations_path),
            "station_count": 0,
            "in_domain_count": 0,
            "note": "no finite station/model/satellite colocations inside the Spritz domain",
        }

    no2 = np.asarray([sample["station_no2"] for sample in samples], dtype=float)
    model = np.asarray([sample["model_concentration"] for sample in samples], dtype=float)
    satellite = np.asarray([sample["satellite_probability"] for sample in samples], dtype=float)
    no2_norm = _normalise_samples(no2)
    model_norm = _normalise_samples(model)
    satellite_norm = _normalise_samples(satellite)
    for index, sample in enumerate(samples):
        sample["station_no2_normalized"] = float(no2_norm[index])
        sample["model_probability_at_station"] = float(model_norm[index])
        sample["satellite_probability_at_station"] = float(satellite_norm[index])
    return {
        "station_observations_path": str(station_observations_path),
        "observable": "NO2",
        "observable_unit": "ug_m3",
        "method": "colocated_station_spatial_pattern_diagnostic",
        "note": (
            "NO2 stations are an independent normalized spatial-pattern check; "
            "they are not converted to Aerosol Index or Spritz concentration."
        ),
        "station_count": len(_read_station_observations(station_observations_path)),
        "in_domain_count": len(samples),
        "domain_bbox_wgs84": bbox,
        "model_active_threshold": model_active_threshold,
        "model_vs_station": _continuous_stats(model_norm, no2_norm),
        "satellite_vs_station": _continuous_stats(satellite_norm, no2_norm),
        "model_vs_satellite_at_stations": _continuous_stats(model_norm, satellite_norm),
        "samples": samples,
    }


def concentration_to_probability(
    rows: list[dict[str, Any]],
    shape: tuple[int, int] | None = None,
    percentile_scale: float = 95.0,
    *,
    allow_index_resampling: bool = False,
) -> np.ndarray:
    values = np.asarray([float(row.get("concentration", 0.0)) for row in rows], dtype=float)
    if values.size == 0:
        raise DataFormatError("empty concentration input")
    if not np.isfinite(values).all():
        raise DataFormatError("concentration input contains non-finite values")
    if (values < 0.0).any():
        raise DataFormatError("concentration input contains negative values")
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
        if not allow_index_resampling:
            raise DataFormatError(
                "model and satellite sample counts differ "
                f"({probabilities.size} != {expected}); align inputs explicitly "
                "or enable index resampling for a documented diagnostic"
            )
        src = np.linspace(0.0, 1.0, probabilities.size)
        dst = np.linspace(0.0, 1.0, expected)
        probabilities = np.interp(dst, src, probabilities)
    return probabilities.reshape(shape)


def _select_time_rows(
    rows: list[dict[str, Any]],
    time_index: int | None,
) -> tuple[list[dict[str, Any]], float | str | None]:
    if time_index is None:
        return rows, None
    times = list(dict.fromkeys(row.get("time", row.get("datetime")) for row in rows))
    if not times or times == [None]:
        if time_index not in {0, -1}:
            raise DataFormatError("concentration input has no selectable time axis")
        return rows, None
    resolved = time_index if time_index >= 0 else len(times) + time_index
    if not 0 <= resolved < len(times):
        raise DataFormatError(
            f"time index {time_index} is outside the {len(times)} concentration times"
        )
    selected_time = times[resolved]
    return [
        row for row in rows
        if row.get("time", row.get("datetime")) == selected_time
    ], selected_time


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


def _field_boundary_diagnostics(
    concentration_path: str | Path,
    *,
    absolute_threshold: float = 1.0e-15,
    relative_threshold: float = 1.0e-12,
    mass_fraction_threshold: float = 1.0e-6,
) -> dict[str, Any] | None:
    """Summarize gridded plume boundary contact with a numerical-noise floor.

    NetCDF concentration fields can contain tiny positive floating-point tails
    at the domain edge after interpolation or stochastic sampling. Treating
    every value greater than zero as physical plume contact makes the diagnostic
    chase numerical dust. This use-case diagnostic therefore first tests
    boundary cells against ``max(absolute_threshold, relative_threshold *
    timestep_peak)`` and then requires their edge mass fraction to exceed
    ``mass_fraction_threshold`` before reporting meaningful boundary contact.
    """
    path = Path(concentration_path)
    if path.suffix.lower() not in {".nc", ".cdf", ".netcdf"}:
        return None
    if absolute_threshold < 0.0:
        raise ValueError("absolute boundary threshold must be non-negative")
    if relative_threshold < 0.0:
        raise ValueError("relative boundary threshold must be non-negative")
    if mass_fraction_threshold < 0.0:
        raise ValueError("boundary mass-fraction threshold must be non-negative")
    try:
        from netCDF4 import Dataset
    except Exception as exc:  # pragma: no cover - depends on optional extras.
        LOGGER.warning("Skipping NetCDF boundary diagnostics: %s", exc)
        return None

    with Dataset(path) as ds:
        if "concentration_field" not in ds.variables:
            return None
        field = np.ma.filled(ds["concentration_field"][:], np.nan).astype(float)
        if field.ndim == 4:
            # time, field_z, field_y, field_x. Use the lowest configured
            # comparison altitude; use case 03 writes one ASL field_z level.
            field = field[:, 0, :, :]
        elif field.ndim != 3:
            return None
        x = np.asarray(ds["field_x"][:], dtype=float) if "field_x" in ds.variables else np.arange(field.shape[-1])
        y = np.asarray(ds["field_y"][:], dtype=float) if "field_y" in ds.variables else np.arange(field.shape[-2])

    timesteps: list[dict[str, Any]] = []
    any_boundary_contact = False
    for index, values in enumerate(field):
        finite = np.isfinite(values)
        safe_values = np.where(finite, values, 0.0)
        peak = float(np.nanmax(safe_values)) if safe_values.size else 0.0
        threshold = max(float(absolute_threshold), float(relative_threshold) * peak)
        active = safe_values > threshold
        boundary_masks = {
            "south": active[0, :],
            "north": active[-1, :],
            "west": active[:, 0],
            "east": active[:, -1],
        }
        boundary_values = {
            "south": safe_values[0, :],
            "north": safe_values[-1, :],
            "west": safe_values[:, 0],
            "east": safe_values[:, -1],
        }
        field_sum = float(np.sum(safe_values))
        edge_sum = {
            name: float(np.sum(np.where(mask, boundary_values[name], 0.0)))
            for name, mask in boundary_masks.items()
        }
        edge_mass_fraction = {
            name: (value / field_sum if field_sum > 0.0 else 0.0)
            for name, value in edge_sum.items()
        }
        raw_edge_contact = {name: bool(mask.any()) for name, mask in boundary_masks.items()}
        edge_contact = {
            name: bool(raw_edge_contact[name] and edge_mass_fraction[name] >= mass_fraction_threshold)
            for name in boundary_masks
        }
        any_boundary_contact = any_boundary_contact or any(edge_contact.values())
        active_positions = np.argwhere(active)
        margins = None
        if active_positions.size:
            margins = {
                "west_cells": int(active_positions[:, 1].min()),
                "east_cells": int(values.shape[1] - 1 - active_positions[:, 1].max()),
                "south_cells": int(active_positions[:, 0].min()),
                "north_cells": int(values.shape[0] - 1 - active_positions[:, 0].max()),
            }
        peak_y, peak_x = np.unravel_index(np.nanargmax(safe_values), values.shape)
        timesteps.append(
            {
                "index": index,
                "peak": peak,
                "active_threshold": threshold,
                "active_cells": int(active.sum()),
                "peak_x_m": float(x[peak_x]),
                "peak_y_m": float(y[peak_y]),
                "margins": margins,
                "boundary_contact": edge_contact,
                "raw_boundary_contact": raw_edge_contact,
                "boundary_active_cells": {name: int(mask.sum()) for name, mask in boundary_masks.items()},
                "boundary_sum_above_threshold": edge_sum,
                "boundary_mass_fraction": edge_mass_fraction,
            }
        )
    return {
        "method": "threshold_aware_boundary_contact",
        "absolute_threshold": float(absolute_threshold),
        "relative_threshold": float(relative_threshold),
        "mass_fraction_threshold": float(mass_fraction_threshold),
        "any_boundary_contact": bool(any_boundary_contact),
        "timesteps": timesteps,
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
    model_scale: float = 1.0,
    model_offset: float = 0.0,
    background: float = 0.0,
    satellite_scale: float = 1.0,
    satellite_offset: float = 0.0,
    model_unit: str = "ug_m3",
    satellite_unit: str = "ug_m3",
    target_unit: str = "ug_m3",
    allow_index_resampling: bool = False,
    time_index: int | None = None,
    boundary_threshold_absolute: float = 1.0e-15,
    boundary_threshold_relative: float = 1.0e-12,
    boundary_mass_fraction_threshold: float = 1.0e-6,
    station_observations: str | Path | None = None,
) -> dict[str, Any]:
    """Evaluate a wildfire/arson simulation against satellite-derived evidence.

    The satellite input is expected to be a probability mask from burned-area,
    active-fire, or smoke-plume retrieval. Accepted lightweight formats are JSON,
    NPY, CSV, TXT, or ASCII grid-like numeric matrices.
    """
    rows = _read_concentration(concentration_path)
    rows, selected_time = _select_time_rows(rows, time_index)
    selected_datetime = rows[0].get("datetime") if rows else None
    observed = _read_satellite_mask(satellite_mask_path)
    if observed.ndim != 2:
        raise DataFormatError("satellite mask must be a two-dimensional array")
    if observed.size == 0:
        raise DataFormatError("satellite mask must not be empty")
    if not np.isfinite(observed).all():
        raise DataFormatError("satellite mask contains non-finite values")
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("threshold must be between 0 and 1")
    if model_unit != target_unit or satellite_unit != target_unit:
        LOGGER.warning(
            "Input units differ from target unit; supplied scale/offset values "
            "are treated as the explicit conversion contract"
        )
    converted_rows = [
        {
            **row,
            "concentration": (
                float(row.get("concentration", 0.0)) * model_scale
                + model_offset
                + background
            ),
        }
        for row in rows
    ]
    observed = observed.astype(float) * satellite_scale + satellite_offset
    if (observed < 0.0).any():
        raise DataFormatError("converted satellite values must be non-negative")
    observed = np.clip(observed, 0.0, 1.0)
    predicted = concentration_to_probability(
        converted_rows,
        observed.shape,
        allow_index_resampling=allow_index_resampling,
    )
    difference = predicted - observed
    ratio = np.divide(
        predicted,
        observed,
        out=np.full_like(predicted, np.nan),
        where=observed != 0.0,
    )
    confusion = _confusion(predicted, observed, threshold)
    metrics = _metrics(confusion)
    result: dict[str, Any] = {
        "component": "usecase.satellite_ai_evaluation",
        "concentration_path": str(concentration_path),
        "satellite_mask_path": str(satellite_mask_path),
        "threshold": threshold,
        "selected_time_index": time_index,
        "selected_model_time": selected_time,
        "selected_model_datetime": selected_datetime,
        "preparation": {
            "model_unit": model_unit,
            "satellite_unit": satellite_unit,
            "target_unit": target_unit,
            "model_scale": model_scale,
            "model_offset": model_offset,
            "background": background,
            "satellite_scale": satellite_scale,
            "satellite_offset": satellite_offset,
            "alignment": "exact" if len(converted_rows) == observed.size else "index_resampled",
            "model_samples": len(converted_rows),
            "satellite_samples": int(observed.size),
        },
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
        "continuous_statistics": {
            "bias": float(np.mean(difference)),
            "mean_absolute_error": float(np.mean(np.abs(difference))),
            "root_mean_square_error": float(np.sqrt(np.mean(difference**2))),
            "pearson_correlation": (
                float(np.corrcoef(predicted.ravel(), observed.ravel())[0, 1])
                if predicted.size > 1
                and float(np.std(predicted)) > 0.0
                and float(np.std(observed)) > 0.0
                else None
            ),
        },
    }
    boundary_diagnostics = _field_boundary_diagnostics(
        concentration_path,
        absolute_threshold=boundary_threshold_absolute,
        relative_threshold=boundary_threshold_relative,
        mass_fraction_threshold=boundary_mass_fraction_threshold,
    )
    if boundary_diagnostics is not None:
        result["field_boundary_diagnostics"] = boundary_diagnostics
    if station_observations is not None:
        result["station_validation"] = _station_validation(
            concentration_path=concentration_path,
            satellite_mask_path=satellite_mask_path,
            station_observations_path=station_observations,
            time_index=time_index,
            model_absolute_threshold=boundary_threshold_absolute,
            model_relative_threshold=boundary_threshold_relative,
        )
    if use_ai_calibration:
        result["ai_calibration"] = _ai_calibrate(predicted, observed)
    write_json(output_path, result)
    output = Path(output_path)
    write_json(
        output.with_name(output.stem + "_difference.json"),
        {"difference": difference.tolist(), "unit": "probability"},
    )
    write_json(
        output.with_name(output.stem + "_ratio.json"),
        {
            "ratio": [
                [None if not np.isfinite(value) else float(value) for value in row]
                for row in ratio
            ],
            "unit": "1",
        },
    )
    with output.with_name(output.stem + "_stats.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.writer(handle)
        writer.writerow(["metric", "value"])
        for name, value in {**metrics, **result["continuous_statistics"]}.items():
            writer.writerow([name, "" if value is None else value])
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
    parser.add_argument("--model-scale", type=float, default=1.0)
    parser.add_argument("--model-offset", type=float, default=0.0)
    parser.add_argument("--background", type=float, default=0.0)
    parser.add_argument("--satellite-scale", type=float, default=1.0)
    parser.add_argument("--satellite-offset", type=float, default=0.0)
    parser.add_argument("--model-unit", default="ug_m3")
    parser.add_argument("--satellite-unit", default="ug_m3")
    parser.add_argument("--target-unit", default="ug_m3")
    parser.add_argument("--allow-index-resampling", action="store_true")
    parser.add_argument(
        "--time-index",
        type=int,
        default=None,
        help="Select one model output time; negative indexes count from the end",
    )
    parser.add_argument(
        "--boundary-threshold-absolute",
        type=float,
        default=1.0e-15,
        help="Absolute concentration floor for gridded boundary-contact diagnostics",
    )
    parser.add_argument(
        "--boundary-threshold-relative",
        type=float,
        default=1.0e-12,
        help="Relative-to-peak concentration floor for gridded boundary-contact diagnostics",
    )
    parser.add_argument(
        "--boundary-mass-fraction-threshold",
        type=float,
        default=1.0e-6,
        help="Minimum edge mass fraction required for meaningful boundary contact",
    )
    parser.add_argument(
        "--station-observations",
        help=(
            "Optional station CSV with id,LAT,LON,NO2 columns for colocated "
            "station/model/satellite spatial-pattern diagnostics"
        ),
    )
    add_plot_argument(parser)
    args = parser.parse_args(argv)
    configure_logging(False)
    result = evaluate_wildfire_event(
        args.concentration,
        args.satellite_mask,
        args.output,
        threshold=args.threshold,
        use_ai_calibration=not args.no_ai,
        make_plot=args.plot,
        model_scale=args.model_scale,
        model_offset=args.model_offset,
        background=args.background,
        satellite_scale=args.satellite_scale,
        satellite_offset=args.satellite_offset,
        model_unit=args.model_unit,
        satellite_unit=args.satellite_unit,
        target_unit=args.target_unit,
        allow_index_resampling=args.allow_index_resampling,
        time_index=args.time_index,
        boundary_threshold_absolute=args.boundary_threshold_absolute,
        boundary_threshold_relative=args.boundary_threshold_relative,
        boundary_mass_fraction_threshold=args.boundary_mass_fraction_threshold,
        station_observations=args.station_observations,
    )
    LOGGER.info("%s", result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

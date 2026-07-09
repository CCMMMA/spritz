import numpy as np

from sprtz.models.spritzmet_physics import (
    correct_temperature,
    field_metrics,
    hypsometric_pressure,
    minimize_divergence,
    relative_humidity_from_vapor_pressure,
    vapor_pressure_from_relative_humidity,
    wind_metrics,
)


def test_temperature_cools_and_pressure_decreases_with_elevation() -> None:
    temperature = np.full((2, 2), 20.0)
    delta = np.full((2, 2), 1000.0)
    corrected = correct_temperature(temperature, delta)
    pressure = hypsometric_pressure(np.full((2, 2), 101325.0), temperature, delta, target_temperature_c=corrected)
    np.testing.assert_allclose(corrected, 13.5)
    assert np.all(pressure < 101325.0)
    assert np.all(pressure > 85000.0)


def test_humidity_reconstruction_preserves_vapor_pressure_and_bounds_rh() -> None:
    source_temperature = np.asarray([20.0, 10.0])
    corrected_temperature = np.asarray([10.0, 20.0])
    vapor_pressure = vapor_pressure_from_relative_humidity(np.asarray([0.5, 0.9]), source_temperature)
    corrected_rh = relative_humidity_from_vapor_pressure(vapor_pressure, corrected_temperature)
    np.testing.assert_allclose(
        vapor_pressure_from_relative_humidity(corrected_rh, corrected_temperature),
        np.minimum(vapor_pressure, vapor_pressure_from_relative_humidity(np.ones(2), corrected_temperature)),
    )
    assert np.all((0.0 <= corrected_rh) & (corrected_rh <= 1.0))


def test_stability_temperature_method_has_bounded_response() -> None:
    corrected = correct_temperature(
        np.full((2, 2), 20.0),
        np.full((2, 2), 1000.0),
        method="stability",
        bulk_richardson_number=np.asarray([[-2.0, -0.5], [0.5, 2.0]]),
    )
    assert np.all(corrected <= 15.0)
    assert np.all(corrected >= 10.2)


def test_mass_consistency_reduces_divergence_for_smooth_flow() -> None:
    axis = np.linspace(0.0, 2.0 * np.pi, 33)
    xx, yy = np.meshgrid(axis, axis)
    _, _, diagnostics = minimize_divergence(
        np.sin(xx),
        np.sin(yy),
        axis[1] - axis[0],
        axis[1] - axis[0],
        iterations=300,
    )
    assert diagnostics["divergence_rms_after_s-1"] < diagnostics["divergence_rms_before_s-1"]


def test_validation_metrics_report_known_errors() -> None:
    scalar = field_metrics(np.asarray([2.0, 4.0]), np.asarray([1.0, 2.0]))
    assert scalar == {"rmse": np.sqrt(2.5), "mae": 1.5, "bias": 1.5}
    wind = wind_metrics(
        np.asarray([1.0]),
        np.asarray([0.0]),
        np.asarray([0.0]),
        np.asarray([1.0]),
    )
    np.testing.assert_allclose(wind["vector_rmse"], np.sqrt(2.0))
    np.testing.assert_allclose(wind["wind_direction_mae_degrees"], 90.0)

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np

Stability = Literal["A", "B", "C", "D", "E", "F"]


def wind_components(speed: float, direction_degrees_from: float) -> tuple[float, float]:
    theta = math.radians(270.0 - direction_degrees_from)
    return speed * math.cos(theta), speed * math.sin(theta)


def met_wind_from_uv(u: np.ndarray | float, v: np.ndarray | float) -> np.ndarray | float:
    """Meteorological wind direction in degrees, from which wind blows."""
    return (270.0 - np.degrees(np.arctan2(v, u))) % 360.0


def wind_speed(u: np.ndarray | float, v: np.ndarray | float) -> np.ndarray | float:
    """Horizontal wind speed from eastward and northward components."""
    return np.hypot(u, v)


def random_walk_std_from_k(k: np.ndarray | float, dt: np.ndarray | float) -> np.ndarray | float:
    """Standard deviation for a 1-D Fickian random walk: sqrt(2 K dt)."""
    return np.sqrt(np.maximum(0.0, 2.0 * np.asarray(k, dtype=float) * np.asarray(dt, dtype=float)))


def exponential_loss_factor(lambda_total: np.ndarray | float, dt: np.ndarray | float) -> np.ndarray | float:
    """Mass survival factor for first-order loss over dt seconds."""
    return np.exp(-np.maximum(0.0, lambda_total) * np.asarray(dt, dtype=float))


@dataclass(frozen=True)
class DispersionParameters:
    sigma_x: float
    sigma_y: float
    sigma_z: float


@dataclass(frozen=True)
class SourceGeometry:
    source_type: str = "point"
    width: float = 0.0
    length: float = 0.0
    height: float = 0.0
    heat_release: float = 0.0
    diameter: float = 1.0


def _positive(value: float, floor: float = 1.0e-12) -> float:
    return max(float(value), floor)


def pasquill_sigmas(distance_m: float, stability: str = "D") -> tuple[float, float]:
    """Legacy-compatible Pasquill-Gifford plume spreads.

    This compact relation is retained as a migration/screening option.  Newer
    Spritz kernels use :func:`dispersion_parameters`, which adds source
    dimensions and a longitudinal puff spread.
    """
    x = max(float(distance_m), 1.0)
    table = {
        "A": (0.22, 0.20),
        "B": (0.16, 0.12),
        "C": (0.11, 0.08),
        "D": (0.08, 0.06),
        "E": (0.06, 0.03),
        "F": (0.04, 0.016),
    }
    ay, az = table.get(stability.upper(), table["D"])
    return ay * x * (1 + 0.0001 * x) ** -0.5, az * x


def dispersion_parameters(
    travel_distance_m: float,
    stability: str = "D",
    *,
    elapsed_s: float | None = None,
    initial_sigma_y: float = 0.0,
    initial_sigma_z: float = 0.0,
    source_width: float = 0.0,
    source_length: float = 0.0,
    source_height: float = 0.0,
) -> DispersionParameters:
    """Return numerical puff spreads with finite source-size treatment.

    The formulation is intentionally transparent: Pasquill-Gifford lateral and
    vertical spreads are combined in quadrature with finite source dimensions.
    A longitudinal spread is estimated from elapsed travel time when available,
    otherwise from the lateral spread.  This supports non-steady puff and
    roadway/area/volume screening without importing original proprietary code.
    """
    x = max(float(travel_distance_m), 1.0)
    sy, sz = pasquill_sigmas(x, stability)
    finite_y = max(source_width, source_length) / math.sqrt(12.0) if max(source_width, source_length) > 0 else 0.0
    finite_x = source_length / math.sqrt(12.0) if source_length > 0 else finite_y
    finite_z = source_height / math.sqrt(12.0) if source_height > 0 else 0.0
    turbulent_x = sy if elapsed_s is None else max(sy, 0.10 * x, 0.1 * math.sqrt(max(elapsed_s, 1.0)))
    return DispersionParameters(
        sigma_x=_positive(math.hypot(turbulent_x, finite_x)),
        sigma_y=_positive(math.hypot(sy, initial_sigma_y, finite_y)),
        sigma_z=_positive(math.hypot(sz, initial_sigma_z, finite_z)),
    )


def plume_rise_briggs(
    *,
    wind_speed: float,
    stack_diameter: float = 1.0,
    exit_velocity: float = 0.0,
    exit_temperature: float = 293.15,
    ambient_temperature: float = 293.15,
    heat_release: float = 0.0,
    downwind_distance: float = 1000.0,
) -> float:
    """Screening Briggs-style effective plume rise.

    The relation captures buoyancy and momentum effects smoothly and
    conservatively for software validation and sensitivity testing; it is not a
    byte-for-byte reproduction of any original implementation.
    """
    u = max(float(wind_speed), 0.1)
    diameter = max(float(stack_diameter), 0.1)
    delta_t = max(float(exit_temperature) - float(ambient_temperature), 0.0)
    buoyancy = 9.80665 * exit_velocity * diameter**2 * delta_t / (4.0 * max(ambient_temperature, 1.0))
    if heat_release > 0:
        buoyancy += 8.8e-6 * heat_release
    momentum = max(float(exit_velocity), 0.0) * diameter / u
    x = max(float(downwind_distance), 1.0)
    buoyant_rise = 1.6 * (max(buoyancy, 0.0) ** (1.0 / 3.0)) * (x ** (2.0 / 3.0)) / u if buoyancy > 0 else 0.0
    return max(buoyant_rise, 3.0 * momentum)


def stack_tip_downwash(stack_height: float, stack_diameter: float, exit_velocity: float, wind_speed: float) -> float:
    if exit_velocity <= 1.5 * max(wind_speed, 0.1):
        return min(stack_height, 2.0 * max(stack_diameter, 0.0))
    return 0.0


def effective_release_height(
    *,
    stack_height: float,
    source_z: float = 0.0,
    receptor_z: float = 0.0,
    wind_speed: float,
    downwind_distance: float,
    stack_diameter: float = 1.0,
    exit_velocity: float = 0.0,
    exit_temperature: float = 293.15,
    ambient_temperature: float = 293.15,
    heat_release: float = 0.0,
    downwash: bool = True,
) -> float:
    rise = plume_rise_briggs(
        wind_speed=wind_speed,
        stack_diameter=stack_diameter,
        exit_velocity=exit_velocity,
        exit_temperature=exit_temperature,
        ambient_temperature=ambient_temperature,
        heat_release=heat_release,
        downwind_distance=downwind_distance,
    )
    penalty = stack_tip_downwash(stack_height, stack_diameter, exit_velocity, wind_speed) if downwash else 0.0
    return max(source_z + stack_height + rise - penalty - receptor_z, 0.0)


def depletion_factor(
    *,
    travel_time_s: float,
    decay_rate_s: float = 0.0,
    deposition_velocity_m_s: float = 0.0,
    mixing_height_m: float = 1000.0,
    wet_scavenging_s: float = 0.0,
    settling_velocity_m_s: float = 0.0,
) -> float:
    hmix = max(float(mixing_height_m), 1.0)
    rate = max(decay_rate_s, 0.0) + max(wet_scavenging_s, 0.0)
    rate += max(deposition_velocity_m_s, 0.0) / hmix
    rate += max(settling_velocity_m_s, 0.0) / hmix
    return math.exp(-rate * max(float(travel_time_s), 0.0))


def gaussian_plume(
    q: float,
    wind_speed: float,
    x_downwind: float,
    y_crosswind: float,
    z: float,
    h: float,
    stability: str = "D",
) -> float:
    if x_downwind <= 0 or wind_speed <= 0:
        return 0.0
    sy, sz = pasquill_sigmas(x_downwind, stability)
    lateral = math.exp(-0.5 * (y_crosswind / sy) ** 2)
    vertical = math.exp(-0.5 * ((z - h) / sz) ** 2) + math.exp(-0.5 * ((z + h) / sz) ** 2)
    return q / (2 * math.pi * wind_speed * sy * sz) * lateral * vertical


def gaussian_puff(
    *,
    mass: float,
    x_receptor: float,
    y_receptor: float,
    z_receptor: float,
    x_center: float,
    y_center: float,
    z_center: float,
    sigmas: DispersionParameters,
    reflection: bool = True,
) -> float:
    sx = _positive(sigmas.sigma_x)
    sy = _positive(sigmas.sigma_y)
    sz = _positive(sigmas.sigma_z)
    norm = float(mass) / (((2.0 * math.pi) ** 1.5) * sx * sy * sz)
    gx = math.exp(-0.5 * ((x_receptor - x_center) / sx) ** 2)
    gy = math.exp(-0.5 * ((y_receptor - y_center) / sy) ** 2)
    gz = math.exp(-0.5 * ((z_receptor - z_center) / sz) ** 2)
    if reflection:
        gz += math.exp(-0.5 * ((z_receptor + z_center) / sz) ** 2)
    return norm * gx * gy * gz


def source_geometry_factor(source_type: str) -> tuple[float, float, float]:
    kind = source_type.lower().strip()
    if kind in {"area", "road", "roadway", "line"}:
        return (1.0, 1.0, 0.0)
    if kind in {"volume", "spray"}:
        return (1.0, 1.0, 1.0)
    if kind == "flare":
        return (0.0, 0.0, 0.0)
    return (0.0, 0.0, 0.0)

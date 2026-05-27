from __future__ import annotations

from pypuff.config import from_mapping, load_config
from pypuff.core.physics import depletion_factor, dispersion_parameters, effective_release_height, gaussian_puff
from pypuff.models import calmet, calpuff


def test_puff_dispersion_is_positive_and_finite_source_increases_spread():
    point = dispersion_parameters(1000.0, "D")
    area = dispersion_parameters(1000.0, "D", source_width=200.0, source_length=300.0, source_height=40.0)
    assert area.sigma_y > point.sigma_y
    assert area.sigma_z > point.sigma_z
    assert gaussian_puff(
        mass=1.0,
        x_receptor=1000.0,
        y_receptor=0.0,
        z_receptor=0.0,
        x_center=1000.0,
        y_center=0.0,
        z_center=40.0,
        sigmas=point,
    ) > 0.0


def test_deposition_and_decay_reduce_mass():
    no_loss = depletion_factor(travel_time_s=1000.0)
    lossy = depletion_factor(travel_time_s=1000.0, decay_rate_s=0.001, deposition_velocity_m_s=0.01, mixing_height_m=500.0)
    assert 0.0 < lossy < no_loss <= 1.0


def test_plume_rise_raises_effective_height():
    base = effective_release_height(stack_height=40.0, wind_speed=5.0, downwind_distance=1000.0)
    hot = effective_release_height(
        stack_height=40.0,
        wind_speed=5.0,
        downwind_distance=1000.0,
        exit_velocity=15.0,
        exit_temperature=420.0,
        ambient_temperature=293.0,
        stack_diameter=2.0,
    )
    assert hot > base


def test_numerical_options_change_results(tmp_path):
    cfg = load_config("examples/minimal.json")
    plume_cfg = from_mapping({**cfg.raw, "run": {**cfg.raw["run"], "numerical_mode": "plume"}})
    meteo_path = tmp_path / "meteo.json"
    calmet.run(cfg, meteo_path, "json")
    puff = calpuff.run(cfg, meteo_path, tmp_path / "puff.csv", "csv")
    plume = calpuff.run(plume_cfg, meteo_path, tmp_path / "plume.csv", "csv")
    assert puff != plume
    assert "dry_flux" in puff[0]

from pypuff.core.stats import block_average, ranked, running_average


def test_calpost_style_averages_and_rank():
    assert running_average([1, 3, 5], 2) == [2.0, 4.0]
    assert block_average([1, 3, 5, 7], 2) == [2.0, 6.0]
    assert ranked([1, 9, 3], 2) == 3.0

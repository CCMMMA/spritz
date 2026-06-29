import math

import pytest

from sprtz.config import config_defaults, configured_backend, from_mapping, load_config, parse_field_z_levels
from sprtz.exceptions import ConfigurationError


def test_load_json_minimal():
    cfg = load_config("examples/minimal.json")
    assert cfg.grid.nx == 5
    assert len(cfg.sources) == 1
    assert len(cfg.receptors) == 2


def test_load_legacy_minimal():
    cfg = load_config("examples/minimal.inp")
    assert cfg.grid.ny == 4
    assert cfg.stations[0].id == "S1"


def test_run_backend_can_be_selected_from_json():
    base = load_config("examples/minimal.json")
    cfg = from_mapping({**base.raw, "run": {**base.raw["run"], "backend": "gauss"}})
    assert configured_backend(cfg.run) == "gaussian"
    cfg = from_mapping({**base.raw, "run": {**base.raw["run"], "backend": "particles"}})
    assert configured_backend(cfg.run) == "particles"


def test_invalid_backend_is_rejected():
    base = load_config("examples/minimal.json")
    with pytest.raises(ConfigurationError):
        from_mapping({**base.raw, "run": {**base.raw["run"], "backend": "unknown"}})


def test_source_height_alias_and_datetime_validation():
    base = load_config("examples/minimal.json")
    raw = {
        **base.raw,
        "sources": [
            {
                **base.raw["sources"][0],
                "height_agl_m": 110.0,
                "start_datetime": "2026-06-01T00:00:00+00:00",
                "end_datetime": "2026-06-01T12:00:00+00:00",
                "material": "paper",
            }
        ],
    }
    cfg = from_mapping(raw)
    assert cfg.sources[0].stack_height == 40.0
    assert cfg.sources[0].height_agl_m == 110.0
    raw["sources"][0]["end_datetime"] = "2026-05-31T23:00:00+00:00"
    with pytest.raises(ConfigurationError):
        from_mapping(raw)


def test_generated_exponential_field_z_levels():
    levels = parse_field_z_levels({"preset": "exponential", "count": 3, "base_m": 10.0})
    assert levels == pytest.approx((10.0, 10.0 * math.e, 10.0 * math.e**2))


def test_shared_json_config_defaults_flatten_sections(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        (
            '{"domain": {"center_lat": 40.8, "dx_m": 100.0}, '
            '"terrain": {"dem_path": "dem.tif"}, "run": {"level_index": 2}}'
        ),
        encoding="utf-8",
    )
    defaults = config_defaults(path)
    assert defaults["center_lat"] == 40.8
    assert defaults["dx"] == 100.0
    assert defaults["dem"] == "dem.tif"
    assert defaults["level_index"] == 2

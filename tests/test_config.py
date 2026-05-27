from pypuff.config import load_config


def test_load_json_minimal():
    cfg = load_config("examples/minimal.json")
    assert cfg.grid.nx == 5
    assert len(cfg.sources) == 1
    assert len(cfg.receptors) == 2


def test_load_legacy_minimal():
    cfg = load_config("examples/minimal.inp")
    assert cfg.grid.ny == 4
    assert cfg.stations[0].id == "S1"

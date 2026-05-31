from sprtz.config import load_config
from sprtz.io.netcdf_cf import read_cf_concentration, read_cf_meteorology
from sprtz.models import spritzmet, particles


def test_netcdf_cf_fallback_and_particle_backend(tmp_path):
    cfg = load_config("examples/minimal.json")
    meteo_path = tmp_path / "meteo.nc"
    conc_path = tmp_path / "particles.nc"
    spritzmet.run(cfg, meteo_path, "netcdf")
    meteo = read_cf_meteorology(meteo_path)
    assert "u" in meteo and "v" in meteo
    rows = particles.run(cfg, meteo_path, conc_path, "netcdf", seed=7)
    assert len(rows) == 2
    reread = read_cf_concentration(conc_path)
    assert len(reread) == 2


def test_particle_backend_is_deterministic(tmp_path):
    cfg = load_config("examples/minimal.json")
    meteo_path = tmp_path / "meteo.json"
    spritzmet.run(cfg, meteo_path, "json")
    a = particles.run(cfg, meteo_path, tmp_path / "a.csv", "csv", seed=3)
    b = particles.run(cfg, meteo_path, tmp_path / "b.csv", "csv", seed=3)
    assert a == b

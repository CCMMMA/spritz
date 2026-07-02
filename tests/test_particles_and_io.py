from sprtz.config import from_mapping, load_config
from sprtz.io.netcdf_cf import read_cf_concentration, read_cf_meteorology
from sprtz.models import spritzmet, particles


def test_netcdf_cf_fallback_and_particle_backend(tmp_path):
    base = load_config("examples/minimal.json")
    raw = dict(base.raw)
    raw["metadata"] = {**dict(base.raw.get("metadata", {})), "center_lat": 40.0, "center_lon": 14.0}
    raw["receptors"] = [
        {**receptor, "latitude": 40.0 + index * 0.1, "longitude": 14.0 + index * 0.1}
        for index, receptor in enumerate(base.raw["receptors"])
    ]
    cfg = from_mapping(raw)
    meteo_path = tmp_path / "meteo.nc"
    conc_path = tmp_path / "particles.nc"
    spritzmet.run(cfg, meteo_path, "netcdf")
    meteo = read_cf_meteorology(meteo_path)
    assert "u" in meteo and "v" in meteo
    try:
        from netCDF4 import Dataset  # type: ignore
    except Exception:
        Dataset = None
    if Dataset is not None:
        with Dataset(meteo_path) as ds:
            assert ds.variables["wind_speed"].dimensions == ("time", "z", "y", "x")
            assert ds.variables["wind_from_direction"].dimensions == ("time", "z", "y", "x")
            assert ds.variables["latitude"].dimensions == ("y", "x")
            assert ds.variables["longitude"].dimensions == ("y", "x")
    rows = particles.run(cfg, meteo_path, conc_path, "netcdf", seed=7)
    assert len(rows) == 2
    assert all("latitude" in row and "longitude" in row for row in rows)
    reread = read_cf_concentration(conc_path)
    assert len(reread) == 2
    assert all("latitude" in row and "longitude" in row for row in reread)


def test_particle_backend_is_deterministic(tmp_path):
    cfg = load_config("examples/minimal.json")
    meteo_path = tmp_path / "meteo.json"
    spritzmet.run(cfg, meteo_path, "json")
    a = particles.run(cfg, meteo_path, tmp_path / "a.csv", "csv", seed=3)
    b = particles.run(cfg, meteo_path, tmp_path / "b.csv", "csv", seed=3)
    assert a == b

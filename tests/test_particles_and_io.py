from sprtz.config import from_mapping, load_config
from sprtz.io.netcdf_cf import read_cf_concentration, read_cf_meteorology, write_cf_concentration
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
            assert ds.variables["x"].axis == "X"
            assert ds.variables["y"].axis == "Y"
            assert ds.variables["z"].axis == "Z"
            assert ds.variables["latitude"].dimensions == ("y", "x")
            assert ds.variables["longitude"].dimensions == ("y", "x")
            assert ds.variables["latitude"].standard_name == "latitude"
            assert ds.variables["longitude"].standard_name == "longitude"
            assert "latitude longitude" in ds.variables["wind_speed"].coordinates
    rows = particles.run(cfg, meteo_path, conc_path, "netcdf", seed=7)
    assert len(rows) == 2
    assert all("latitude" in row and "longitude" in row for row in rows)
    reread = read_cf_concentration(conc_path)
    assert len(reread) == 2
    assert all("latitude" in row and "longitude" in row for row in reread)


def test_concentration_netcdf_writes_field_lat_lon_coordinates(tmp_path):
    try:
        from netCDF4 import Dataset  # type: ignore
    except Exception:
        return
    rows = []
    for y, lat in [(-50.0, 39.9995), (50.0, 40.0005)]:
        for x, lon in [(-50.0, 13.9995), (50.0, 14.0005)]:
            rows.append(
                {
                    "time": 0.0,
                    "receptor": f"G0_{int(y)}_{int(x)}",
                    "output_kind": "field",
                    "x": x,
                    "y": y,
                    "z": 2.5,
                    "latitude": lat,
                    "longitude": lon,
                    "terrain_m": 100.0,
                    "land_cover": 50,
                    "concentration": 1.0,
                    "dry_flux": 0.0,
                    "wet_flux": 0.0,
                }
            )
    path = tmp_path / "concentration.nc"
    write_cf_concentration(path, rows)

    with Dataset(path) as ds:
        assert ds.variables["latitude"].dimensions == ("receptor",)
        assert ds.variables["latitude"].standard_name == "latitude"
        assert ds.variables["longitude"].standard_name == "longitude"
        assert ds.variables["field_latitude"].dimensions == ("field_y", "field_x")
        assert ds.variables["field_longitude"].dimensions == ("field_y", "field_x")
        assert ds.variables["field_z"].axis == "Z"
        assert ds.variables["surface_altitude"].standard_name == "surface_altitude"
        assert ds.variables["field_altitude"].standard_name == "altitude"
        assert ds.variables["field_altitude"].dimensions == ("field_z", "field_y", "field_x")
        assert "field_altitude" in ds.variables["concentration_field"].coordinates
        assert ds.variables["concentration_field"].coordinates.endswith("field_latitude field_longitude")


def test_particle_backend_is_deterministic(tmp_path):
    cfg = load_config("examples/minimal.json")
    meteo_path = tmp_path / "meteo.json"
    spritzmet.run(cfg, meteo_path, "json")
    a = particles.run(cfg, meteo_path, tmp_path / "a.csv", "csv", seed=3)
    b = particles.run(cfg, meteo_path, tmp_path / "b.csv", "csv", seed=3)
    assert a == b


def test_concentration_vertical_profile_plot(tmp_path):
    try:
        import matplotlib  # noqa: F401
        from netCDF4 import Dataset  # noqa: F401
    except Exception:
        return
    from usecases.plotting import plot_concentration_vertical_profiles_if_available

    base = load_config("examples/minimal.json")
    cfg = from_mapping(
        {
            **base.raw,
            "receptors": [],
            "run": {
                **base.raw["run"],
                "output_interval_s": 60.0,
                "output_duration_s": 120.0,
                "concentration_output": "grid",
                "field_z_levels": [1.5, 10.0],
                "particles": 50,
                "particle_duration_s": 60.0,
            },
        }
    )
    meteo_path = tmp_path / "meteo.nc"
    conc_path = tmp_path / "particles.nc"
    figure_path = tmp_path / "particles_concentration_vertical_profiles.png"
    spritzmet.run(cfg, meteo_path, "netcdf")
    particles.run(cfg, meteo_path, conc_path, "netcdf", seed=9)

    assert plot_concentration_vertical_profiles_if_available(conc_path, figure_path) == figure_path
    assert figure_path.exists()

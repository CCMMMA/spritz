import numpy as np

from sprtz.config import from_mapping, load_config
from sprtz.io.netcdf_cf import DenseConcentrationWriter, read_cf_concentration, read_cf_meteorology, write_cf_concentration
from sprtz.models import spritzmet, particles


def test_dense_concentration_writer_syncs_each_time_frame():
    class Variable:
        def __init__(self):
            self.values = {}

        def __setitem__(self, key, value):
            self.values[key] = value

    class Dataset:
        def __init__(self):
            self.variables = {
                name: Variable()
                for name in (
                    "concentration_field",
                    "dry_flux_field",
                    "wet_flux_field",
                    "concentration",
                    "dry_flux",
                    "wet_flux",
                )
            }
            self.sync_calls = 0

        def sync(self):
            self.sync_calls += 1

    writer = DenseConcentrationWriter.__new__(DenseConcentrationWriter)
    writer._time_index = {3600.0: 0}
    writer.ds = Dataset()

    writer.write_time(
        3600.0,
        concentration=np.ones((1, 1, 1)),
        dry_flux=np.zeros((1, 1, 1)),
        wet_flux=np.zeros((1, 1, 1)),
        receptor_rows=[{"concentration": 1.0, "dry_flux": 2.0, "wet_flux": 3.0}],
    )

    assert writer.ds.sync_calls == 1
    assert writer.ds.variables["concentration"].values[(0, 0)] == 1.0


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
        assert ds.variables["field_z"].standard_name == "altitude"
        assert ds.variables["field_z"].long_name == "model grid altitude above mean sea level"
        assert ds.spritz_concentration_field_z_reference == "height_above_sea_level"
        assert ds.variables["surface_altitude"].standard_name == "surface_altitude"
        assert ds.variables["field_altitude"].standard_name == "altitude"
        assert ds.variables["field_altitude"].dimensions == ("field_z", "field_y", "field_x")
        np.testing.assert_allclose(ds.variables["field_altitude"][:, 0, 0], ds.variables["field_z"][:])
        assert "field_altitude" in ds.variables["concentration_field"].coordinates
        assert ds.variables["concentration_field"].coordinates.endswith("field_latitude field_longitude")


def test_particle_backend_is_deterministic(tmp_path):
    cfg = load_config("examples/minimal.json")
    meteo_path = tmp_path / "meteo.json"
    spritzmet.run(cfg, meteo_path, "json")
    a = particles.run(cfg, meteo_path, tmp_path / "a.csv", "csv", seed=3)
    b = particles.run(cfg, meteo_path, tmp_path / "b.csv", "csv", seed=3)
    assert a == b


def test_particle_worker_rank_never_opens_dense_netcdf(tmp_path, monkeypatch):
    class WorkerContext:
        rank = 1
        size = 2
        is_root = False

        @staticmethod
        def partition(size):
            return range(0, size, 2)

        @staticmethod
        def allgather(value):
            return [value]

    cfg = load_config("examples/minimal.json")
    meteo_path = tmp_path / "meteo.json"
    spritzmet.run(cfg, meteo_path, "json")
    monkeypatch.setattr(particles, "get_mpi_context", lambda parallel: WorkerContext())

    def reject_writer(*args, **kwargs):
        raise AssertionError("a worker rank attempted to open the NetCDF writer")

    monkeypatch.setattr(particles, "DenseConcentrationWriter", reject_writer)
    particles.simulate_particles(
        cfg,
        particles.read_meteorology(meteo_path),
        parallel="mpi",
        dense_output=tmp_path / "worker-must-not-write.nc",
    )

    assert not (tmp_path / "worker-must-not-write.nc").exists()


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

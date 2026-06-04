import csv

from sprtz.config import from_mapping, load_config
from sprtz.models import spritzmet, spritzpost, spritz, ctgproc
from sprtz.io.jsonio import read_json
from sprtz.io.netcdf_cf import available as netcdf_available, read_cf_concentration


def test_spritzmet_shape():
    cfg = load_config("examples/minimal.json")
    met = spritzmet.build_meteorology(cfg)
    assert len(met["u"]) == cfg.grid.ny
    assert len(met["u"][0]) == cfg.grid.nx


def test_station_precipitation_reaches_spritzmet_field():
    base = load_config("examples/minimal.json")
    cfg = from_mapping(
        {
            **base.raw,
            "stations": [{**base.raw["stations"][0], "precipitation_rate": 3.5}],
        }
    )
    met = spritzmet.build_meteorology(cfg)
    assert met["precipitation_rate"][0][0] == 3.5


def test_spritz_and_post(tmp_path):
    cfg = load_config("examples/minimal.json")
    meteo_path = tmp_path / "meteo.json"
    conc_path = tmp_path / "conc.csv"
    post_path = tmp_path / "post.json"
    spritzmet.run(cfg, meteo_path)
    rows = spritz.run(cfg, meteo_path, conc_path)
    assert len(rows) == 2
    with conc_path.open() as handle:
        assert len(list(csv.DictReader(handle))) == 2
    result = spritzpost.run(conc_path, post_path)
    assert "R1" in result["receptors"]


def test_spritz_output_interval_csv_and_netcdf(tmp_path):
    base = load_config("examples/minimal.json")
    cfg = from_mapping(
        {
            **base.raw,
            "run": {
                **base.raw["run"],
                "output_interval_s": 600.0,
                "output_duration_s": 1800.0,
            },
        }
    )
    meteo_path = tmp_path / "meteo.json"
    csv_path = tmp_path / "conc.csv"
    nc_path = tmp_path / "conc.nc"
    spritzmet.run(cfg, meteo_path)
    rows = spritz.run(cfg, meteo_path, csv_path, "csv")
    assert sorted({row["time"] for row in rows}) == [600.0, 1200.0, 1800.0]
    assert len(rows) == 6
    with csv_path.open() as handle:
        assert len(list(csv.DictReader(handle))) == 6
    spritz.run(cfg, meteo_path, nc_path, "netcdf")
    reread = read_cf_concentration(nc_path)
    assert len(reread) == 6
    assert sorted({row["time"] for row in reread}) == [600.0, 1200.0, 1800.0]


def test_spritz_can_write_3d_concentration_field(tmp_path):
    base = load_config("examples/minimal.json")
    cfg = from_mapping(
        {
            **base.raw,
            "receptors": [],
            "run": {
                **base.raw["run"],
                "concentration_output": "grid",
                "field_z_levels": [0.0, 25.0],
            },
        }
    )
    meteo_path = tmp_path / "meteo.json"
    conc_path = tmp_path / "field.nc"
    spritzmet.run(cfg, meteo_path, "json")
    rows = spritz.run(cfg, meteo_path, conc_path, "netcdf")
    assert len(rows) == cfg.grid.nx * cfg.grid.ny * 2
    if netcdf_available():
        from netCDF4 import Dataset  # type: ignore

        with Dataset(conc_path) as ds:
            assert ds.variables["concentration_field"].shape == (
                1,
                2,
                cfg.grid.ny,
                cfg.grid.nx,
            )
    else:
        data = read_json(conc_path)
        assert data["field"]["z"] == [0.0, 25.0]
        assert len(data["field"]["concentration"][0][0]) == cfg.grid.ny
        assert len(data["field"]["concentration"][0][0][0]) == cfg.grid.nx


def test_precipitation_washout_reduces_concentration():
    base = load_config("examples/minimal.json")
    meteo = {
        "u": [[2.0]],
        "v": [[0.0]],
        "temperature": [[293.15]],
        "mixing_height": [[1000.0]],
        "precipitation_rate": [[8.0]],
    }
    dry_cfg = from_mapping({**base.raw, "run": {**base.raw["run"], "precipitation_washout": False}})
    wet_cfg = from_mapping({**base.raw, "run": {**base.raw["run"], "precipitation_washout": True}})
    dry_rows = spritz.compute_concentrations(dry_cfg, meteo)
    wet_rows = spritz.compute_concentrations(wet_cfg, meteo)
    assert wet_rows[0]["concentration"] < dry_rows[0]["concentration"]
    assert wet_rows[0]["wet_flux"] > dry_rows[0]["wet_flux"]


def test_ctgproc():
    raster = ctgproc.read_ascii_grid("examples/landuse.asc")
    result = ctgproc.aggregate_categories(raster)
    assert result["categories"]["2"]["count"] == 4

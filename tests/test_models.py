import csv

from sprtz.config import from_mapping, load_config
from sprtz.models import spritzmet, spritzpost, spritz, ctgproc
from sprtz.io.netcdf_cf import read_cf_concentration


def test_spritzmet_shape():
    cfg = load_config("examples/minimal.json")
    met = spritzmet.build_meteorology(cfg)
    assert len(met["u"]) == cfg.grid.ny
    assert len(met["u"][0]) == cfg.grid.nx


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


def test_ctgproc():
    raster = ctgproc.read_ascii_grid("examples/landuse.asc")
    result = ctgproc.aggregate_categories(raster)
    assert result["categories"]["2"]["count"] == 4

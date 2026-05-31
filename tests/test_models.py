import csv

from sprtz.config import load_config
from sprtz.models import spritzmet, spritzpost, spritz, ctgproc


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


def test_ctgproc():
    raster = ctgproc.read_ascii_grid("examples/landuse.asc")
    result = ctgproc.aggregate_categories(raster)
    assert result["categories"]["2"]["count"] == 4

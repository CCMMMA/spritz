from __future__ import annotations

from pathlib import Path

from sprtz.config import from_mapping, load_config
from sprtz.io.jsonio import write_json
from sprtz.io.netcdf_cf import read_cf_concentration
from sprtz.models import spritz, spritzmet, visualization


def test_prepare_plot_data_uses_lat_lon_fields() -> None:
    rows = [
        {"x": 0, "y": 0, "latitude": "40,926506", "longitude": "14,380875", "concentration": 1.2}
    ]
    data = visualization.prepare_plot_data(rows, coordinate_system="auto")
    assert data.coordinate_system == "geographic"
    assert data.x[0] == 14.380875
    assert data.y[0] == 40.926506


def test_prepare_plot_data_transforms_local_coordinates() -> None:
    rows = [{"x": 0.0, "y": 0.0, "concentration": 1.0}]
    data = visualization.prepare_plot_data(
        rows,
        coordinate_system="geographic",
        center_lat=40.926506,
        center_lon=14.380875,
    )
    assert abs(data.x[0] - 14.380875) < 1.0e-9
    assert abs(data.y[0] - 40.926506) < 1.0e-9


def test_concentration_outputs_preserve_receptor_lat_lon(tmp_path: Path) -> None:
    base = load_config("examples/minimal.json")
    cfg = from_mapping(
        {
            **base.raw,
            "receptors": [
                {
                    "id": "GEO1",
                    "x": 1000.0,
                    "y": 1000.0,
                    "z": 1.5,
                    "latitude": 40.926506,
                    "longitude": 14.380875,
                }
            ],
        }
    )
    meteo = tmp_path / "meteo.json"
    concentration = tmp_path / "concentration.nc"
    spritzmet.run(cfg, meteo, "json")
    spritz.run(cfg, meteo, concentration, "netcdf")
    rows = read_cf_concentration(concentration)
    assert rows[0]["latitude"] == 40.926506
    assert rows[0]["longitude"] == 14.380875


def test_parse_extent() -> None:
    assert visualization.parse_extent("14.3,40.8,14.5,41.0") == (14.3, 40.8, 14.5, 41.0)


def test_visualization_reads_json_fallback_rows(tmp_path: Path) -> None:
    path = tmp_path / "concentration.json"
    write_json(
        path,
        {
            "format": "cf-json-fallback",
            "rows": [{"x": 10.0, "y": 20.0, "concentration": 2.5}],
        },
    )
    data = visualization.prepare_plot_data(visualization._read_rows(path))
    assert data.values[0] == 2.5

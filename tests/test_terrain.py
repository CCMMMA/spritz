from __future__ import annotations

import numpy as np

from sprtz.io.jsonio import read_json
from sprtz.models import terrain


def test_terrain_resamples_terrain_to_local_grid() -> None:
    terrain_values = np.arange(25, dtype=float).reshape(5, 5)
    product = terrain.terrain_to_local_grid(
        terrain_values,
        center_lat=40.85,
        center_lon=14.27,
        nx=3,
        ny=3,
        dx_m=100.0,
        dy_m=100.0,
        source_dx_m=100.0,
    )
    assert product.elevation_m.shape == (3, 3)
    assert np.isfinite(product.elevation_m).all()
    assert product.elevation_m[1, 1] == 12.0


def test_terrain_writes_json_product(tmp_path) -> None:
    out = tmp_path / "terrain.json"
    result = terrain.run(
        "examples/terrain.asc",
        out,
        center_lat=40.85,
        center_lon=14.27,
        nx=5,
        ny=5,
        dx_m=100.0,
        dy_m=100.0,
        prefer_netcdf=False,
    )
    data = read_json(out)
    assert result["component"] == "terrain"
    assert data["component"] == "terrain.terrain"
    assert "elevation_m" in data


def test_assign_receptor_terrain() -> None:
    terrain_values = np.arange(9, dtype=float).reshape(3, 3)
    product = terrain.terrain_to_local_grid(
        terrain_values,
        center_lat=40.85,
        center_lon=14.27,
        nx=3,
        ny=3,
        dx_m=100.0,
        dy_m=100.0,
        source_dx_m=100.0,
    )
    assigned = terrain.assign_receptor_terrain(product, [{"id": "R0", "x": 0.0, "y": 0.0}])
    assert assigned[0]["terrain_m"] == 4.0

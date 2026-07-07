import csv
from pathlib import Path
import struct

import numpy as np
import pytest

from sprtz.config import from_mapping, load_config
from sprtz.core.grid import Grid
from sprtz.models import spritzmet, spritzpost, spritz, particles, ctgproc, spritzwrf
from sprtz.io.calpuff import write_calpuff_concentration_dat
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


def test_spritz_reports_progress_after_each_output_time(tmp_path):
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
    conc_path = tmp_path / "conc.csv"
    spritzmet.run(cfg, meteo_path)
    progress: list[tuple[int, float]] = []

    spritz.run(cfg, meteo_path, conc_path, "csv", progress_callback=lambda index, time_s: progress.append((index, time_s)))

    assert progress == [(1, 600.0), (2, 1200.0), (3, 1800.0)]


def test_gaussian_puff_integrates_continuous_output_window():
    base = load_config("examples/minimal.json")
    cfg = from_mapping(
        {
            **base.raw,
            "grid": {
                **base.raw["grid"],
                "nx": 5,
                "ny": 5,
                "dx": 100.0,
                "dy": 100.0,
                "x0": -200.0,
                "y0": -200.0,
            },
            "sources": [
                {
                    **base.raw["sources"][0],
                    "x": 0.0,
                    "y": 0.0,
                    "z": 0.0,
                    "stack_height": 0.0,
                    "height": 1.0,
                    "heat_release": 0.0,
                    "exit_temperature": 293.15,
                    "exit_velocity": 0.0,
                    "emission_rate": 1.0,
                }
            ],
            "receptors": [],
            "run": {
                **base.raw["run"],
                "output_interval_s": 600.0,
                "output_duration_s": 600.0,
                "concentration_output": "grid",
                "field_z_levels": [0.0],
                "gaussian_puff_samples": 12,
            },
        }
    )
    meteo = {
        "u": [[1.0]],
        "v": [[0.0]],
        "temperature": [[293.15]],
        "mixing_height": [[1000.0]],
        "precipitation_rate": [[0.0]],
    }

    rows = spritz.compute_concentrations(cfg, meteo)
    centerline = {row["x"]: row["concentration"] for row in rows if row["y"] == 0.0 and row["z"] == 0.0}

    assert centerline[200.0] > 0.0
    assert centerline[-100.0] == 0.0


def test_gaussian_puff_time_integral_keeps_concentration_units():
    base = load_config("examples/minimal.json")
    cfg = from_mapping(
        {
            **base.raw,
            "grid": {
                **base.raw["grid"],
                "nx": 1,
                "ny": 1,
                "dx": 100.0,
                "dy": 100.0,
                "x0": 300.0,
                "y0": 0.0,
            },
            "sources": [
                {
                    **base.raw["sources"][0],
                    "x": 0.0,
                    "y": 0.0,
                    "z": 0.0,
                    "stack_height": 0.0,
                    "height": 1.0,
                    "heat_release": 0.0,
                    "exit_temperature": 293.15,
                    "exit_velocity": 0.0,
                    "emission_rate": 1.0,
                    "deposition_velocity": 0.0,
                    "wet_scavenging": 0.0,
                    "settling_velocity": 0.0,
                }
            ],
            "receptors": [],
            "run": {
                **base.raw["run"],
                "output_interval_s": 600.0,
                "output_duration_s": 600.0,
                "concentration_output": "grid",
                "field_z_levels": [0.0],
                "gaussian_puff_samples": 3,
                "stability": "D",
            },
        }
    )
    meteo = {
        "u": [[1.0]],
        "v": [[0.0]],
        "temperature": [[293.15]],
        "mixing_height": [[1000.0]],
        "precipitation_rate": [[0.0]],
    }

    rows = spritz.compute_concentrations(cfg, meteo)

    assert len(rows) == 1
    assert rows[0]["concentration"] > 1.0e-7


def test_gaussian_puff_uses_absolute_release_height_for_elevated_field_levels():
    base = load_config("examples/minimal.json")
    cfg = from_mapping(
        {
            **base.raw,
            "grid": {
                **base.raw["grid"],
                "nx": 1,
                "ny": 1,
                "dx": 100.0,
                "dy": 100.0,
                "x0": 300.0,
                "y0": 0.0,
            },
            "sources": [
                {
                    **base.raw["sources"][0],
                    "x": 0.0,
                    "y": 0.0,
                    "z": 0.0,
                    "stack_height": 0.0,
                    "height": 1.0,
                    "heat_release": 0.0,
                    "exit_temperature": 293.15,
                    "exit_velocity": 0.0,
                    "emission_rate": 1.0,
                    "deposition_velocity": 0.0,
                    "wet_scavenging": 0.0,
                    "settling_velocity": 0.0,
                }
            ],
            "receptors": [],
            "run": {
                **base.raw["run"],
                "output_interval_s": 600.0,
                "output_duration_s": 600.0,
                "concentration_output": "grid",
                "field_z_levels": [0.0, 1000.0],
                "gaussian_puff_samples": 1,
                "stability": "D",
            },
        }
    )
    meteo = {
        "u": [[1.0]],
        "v": [[0.0]],
        "temperature": [[293.15]],
        "mixing_height": [[1000.0]],
        "precipitation_rate": [[0.0]],
    }

    rows = spritz.compute_concentrations(cfg, meteo)
    by_z = {row["z"]: row["concentration"] for row in rows}

    assert by_z[0.0] > 1.0e-7
    assert by_z[1000.0] < by_z[0.0] * 1.0e-20


def test_gaussian_puff_initial_sigma_z_broadens_vertical_field():
    base = load_config("examples/minimal.json")
    raw = {
        **base.raw,
        "grid": {
            **base.raw["grid"],
            "nx": 1,
            "ny": 1,
            "dx": 100.0,
            "dy": 100.0,
            "x0": 300.0,
            "y0": 0.0,
        },
        "sources": [
            {
                **base.raw["sources"][0],
                "x": 0.0,
                "y": 0.0,
                "z": 0.0,
                "stack_height": 0.0,
                "height": 1.0,
                "heat_release": 0.0,
                "exit_temperature": 293.15,
                "exit_velocity": 0.0,
                "emission_rate": 1.0,
                "deposition_velocity": 0.0,
                "wet_scavenging": 0.0,
                "settling_velocity": 0.0,
            }
        ],
        "receptors": [],
        "run": {
            **base.raw["run"],
            "output_interval_s": 600.0,
            "output_duration_s": 600.0,
            "concentration_output": "grid",
            "field_z_levels": [500.0],
            "gaussian_puff_samples": 1,
            "stability": "D",
        },
    }
    meteo = {
        "u": [[1.0]],
        "v": [[0.0]],
        "temperature": [[293.15]],
        "mixing_height": [[1000.0]],
        "precipitation_rate": [[0.0]],
    }

    narrow = spritz.compute_concentrations(from_mapping(raw), meteo)[0]["concentration"]
    broad = spritz.compute_concentrations(
        from_mapping({**raw, "run": {**raw["run"], "gaussian_initial_sigma_z": 250.0}}),
        meteo,
    )[0]["concentration"]

    assert broad > narrow


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
    terrain_path = tmp_path / "geo.nc"
    spritzmet.run(cfg, meteo_path, "json")
    if netcdf_available():
        from netCDF4 import Dataset  # type: ignore

        grid = Grid(**cfg.grid.__dict__)
        with Dataset(terrain_path, "w") as ds:
            ds.createDimension("y", cfg.grid.ny)
            ds.createDimension("x", cfg.grid.nx)
            ds.createVariable("y", "f8", ("y",))[:] = np.asarray(grid.y, dtype=float)
            ds.createVariable("x", "f8", ("x",))[:] = np.asarray(grid.x, dtype=float)
            ds.createVariable("surface_altitude", "f8", ("y", "x"))[:, :] = np.arange(
                cfg.grid.ny * cfg.grid.nx,
                dtype=float,
            ).reshape(cfg.grid.ny, cfg.grid.nx)
            ds.createVariable("land_cover", "i4", ("y", "x"))[:, :] = np.full((cfg.grid.ny, cfg.grid.nx), 50)
    rows = spritz.run(
        cfg,
        meteo_path,
        conc_path,
        "netcdf",
        terrain_input=terrain_path if netcdf_available() else None,
    )
    assert rows == []
    if netcdf_available():
        from netCDF4 import Dataset  # type: ignore

        with Dataset(conc_path) as ds:
            assert ds.variables["concentration_field"].shape == (
                1,
                2,
                cfg.grid.ny,
                cfg.grid.nx,
            )
            assert "surface_altitude" in ds.variables
            assert "land_cover" in ds.variables
            np.testing.assert_allclose(ds.variables["surface_altitude"][:], np.arange(cfg.grid.ny * cfg.grid.nx).reshape(cfg.grid.ny, cfg.grid.nx))
    else:
        data = read_json(conc_path)
        assert data["field"]["z"] == [0.0, 25.0]
        assert len(data["field"]["concentration"][0][0]) == cfg.grid.ny
        assert len(data["field"]["concentration"][0][0][0]) == cfg.grid.nx


def test_gaussian_grid_uses_terrain_lifted_asl_source_and_masks_subsurface_levels():
    base = load_config("examples/minimal.json")
    cfg = from_mapping(
        {
            **base.raw,
            "grid": {"nx": 3, "ny": 1, "dx": 100.0, "dy": 100.0, "x0": 0.0, "y0": 0.0},
            "sources": [
                {
                    **base.raw["sources"][0],
                    "x": 0.0,
                    "y": 0.0,
                    "z": 0.0,
                    "stack_height": 10.0,
                    "height_agl_m": 10.0,
                    "exit_velocity": 0.0,
                    "heat_release": 0.0,
                }
            ],
            "receptors": [],
            "run": {
                **base.raw["run"],
                "concentration_output": "grid",
                "field_z_levels": [5.0, 115.0],
                "output_interval_s": 600.0,
                "output_duration_s": 600.0,
                "numerical_mode": "puff",
                "gaussian_puff_samples": 2,
                "gaussian_initial_sigma_z": 25.0,
                "gaussian_initial_sigma_h": 25.0,
            },
        }
    )
    meteo = {"u": [[2.0, 2.0, 2.0]], "v": [[0.0, 0.0, 0.0]], "mixing_height": [[1000.0, 1000.0, 1000.0]]}
    terrain_fields = {"terrain_m": np.full((1, 3), 100.0)}

    rows = spritz.compute_concentrations(cfg, meteo, terrain_fields=terrain_fields)

    below = [row for row in rows if row["z"] == 5.0]
    above = [row for row in rows if row["z"] == 115.0]
    assert all(row["concentration"] == 0.0 for row in below)
    assert max(row["concentration"] for row in above) > 0.0


def test_source_release_defaults_to_ground_and_honors_explicit_height():
    ground_source = from_mapping(
        {
            "grid": {"nx": 1, "ny": 1, "dx": 100.0, "dy": 100.0},
            "sources": [{"id": "S1", "x": 0.0, "y": 0.0}],
        }
    ).sources[0]
    chimney_source = from_mapping(
        {
            "grid": {"nx": 1, "ny": 1, "dx": 100.0, "dy": 100.0},
            "sources": [{"id": "S1", "x": 0.0, "y": 0.0, "height_agl_m": 15.0}],
        }
    ).sources[0]
    legacy_stack_source = from_mapping(
        {
            "grid": {"nx": 1, "ny": 1, "dx": 100.0, "dy": 100.0},
            "sources": [{"id": "S1", "x": 0.0, "y": 0.0, "stack_height": 12.0}],
        }
    ).sources[0]

    assert spritz._source_release_height_agl_m(ground_source) == 0.0
    assert spritz._source_release_height_agl_m(chimney_source) == 15.0
    assert spritz._source_release_height_agl_m(legacy_stack_source) == 12.0


def test_calpuff_style_concentration_binary_records(tmp_path: Path) -> None:
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
    rows = spritz.compute_concentrations(
        cfg,
        {
            "u": [[2.0]],
            "v": [[0.0]],
            "temperature": [[293.15]],
            "mixing_height": [[1000.0]],
            "precipitation_rate": [[0.0]],
        },
    )
    out = tmp_path / "concentration.calpuff"

    assert write_calpuff_concentration_dat(out, rows) == "CALPUFF.CONC"

    records = _fortran_records(out)
    assert records[0][:80].rstrip() == b"CALPUFF.CONC"
    assert struct.unpack(">6i", records[1]) == (1, cfg.grid.nx, cfg.grid.ny, 2, 1, 3)
    assert "CONCENTRATION_G_M3" in records[7].decode("ascii")


def test_particles_emit_time_dependent_grid_field():
    base = load_config("examples/minimal.json")
    cfg = from_mapping(
        {
            **base.raw,
            "grid": {
                **base.raw["grid"],
                "nx": 5,
                "ny": 5,
                "dx": 500.0,
                "dy": 500.0,
                "x0": -1000.0,
                "y0": -1000.0,
            },
            "receptors": [],
            "run": {
                **base.raw["run"],
                "output_interval_s": 600.0,
                "output_duration_s": 1200.0,
                "concentration_output": "grid",
                "field_z_levels": [50.0],
                "particles": 300,
                "particle_duration_s": 1200.0,
            },
        }
    )
    meteo = {
        "u": [[2.0]],
        "v": [[0.0]],
        "temperature": [[293.15]],
        "mixing_height": [[1000.0]],
        "precipitation_rate": [[0.0]],
    }
    terrain_fields = {
        "terrain_m": np.arange(cfg.grid.ny * cfg.grid.nx, dtype=float).reshape(cfg.grid.ny, cfg.grid.nx),
        "land_cover": np.full((cfg.grid.ny, cfg.grid.nx), 50.0),
    }
    rows = particles.simulate_particles(cfg, meteo, terrain_fields=terrain_fields)
    assert sorted({row["time"] for row in rows}) == [600.0, 1200.0]
    assert len(rows) == 2 * cfg.grid.nx * cfg.grid.ny
    first = [row["concentration"] for row in rows if row["time"] == 600.0]
    second = [row["concentration"] for row in rows if row["time"] == 1200.0]
    assert max(second) > 0.0
    assert first != second
    assert all("terrain_m" in row and "land_cover" in row for row in rows)


def test_particles_vertical_boundary_uses_local_dem():
    z, weights = particles._apply_vertical_boundary(
        np.asarray([95.0, 110.0, 190.0]),
        np.ones(3, dtype=float),
        ground_m=np.asarray([100.0, 150.0, 175.0]),
        top_m=300.0,
        ground_policy="reflect",
        top_policy="reflect",
    )

    np.testing.assert_allclose(z, [105.0, 190.0, 190.0])
    np.testing.assert_allclose(weights, [1.0, 1.0, 1.0])


def test_particles_terrain_sampler_handles_nonfinite_and_outside_points():
    grid = Grid(nx=2, ny=2, dx=100.0, dy=100.0, x0=0.0, y0=0.0)
    terrain = np.asarray([[10.0, 20.0], [30.0, 40.0]], dtype=float)

    sampled = particles._terrain_at_points(
        terrain,
        grid,
        np.asarray([np.nan, -1000.0, np.inf, 50.0]),
        np.asarray([np.nan, -1000.0, np.inf, 50.0]),
    )

    assert np.isfinite(sampled).all()
    np.testing.assert_allclose(sampled, [10.0, 10.0, 40.0, 25.0])


def test_particles_report_progress_after_each_output_time():
    base = load_config("examples/minimal.json")
    cfg = from_mapping(
        {
            **base.raw,
            "run": {
                **base.raw["run"],
                "output_interval_s": 600.0,
                "output_duration_s": 1200.0,
                "particles": 20,
            },
        }
    )
    meteo = {
        "u": [[2.0]],
        "v": [[0.0]],
        "temperature": [[293.15]],
        "mixing_height": [[1000.0]],
        "precipitation_rate": [[0.0]],
    }
    progress: list[tuple[int, float]] = []

    particles.simulate_particles(cfg, meteo, seed=1, progress_callback=lambda index, time_s: progress.append((index, time_s)))

    assert progress == [(1, 600.0), (2, 1200.0)]


def test_particle_backend_honors_heat_release_plume_rise():
    base = load_config("examples/minimal.json")
    cfg_base = {
        **base.raw,
        "grid": {
            **base.raw["grid"],
            "nx": 5,
            "ny": 5,
            "dx": 100.0,
            "dy": 100.0,
            "x0": -200.0,
            "y0": -200.0,
        },
        "sources": [
            {
                **base.raw["sources"][0],
                "x": 0.0,
                "y": 0.0,
                "z": 0.0,
                "stack_height": 0.0,
                "height": 1.0,
                "heat_release": 0.0,
            }
        ],
        "receptors": [],
        "run": {
            **base.raw["run"],
            "output_interval_s": 600.0,
            "output_duration_s": 600.0,
            "concentration_output": "grid",
            "field_z_levels": [1.5],
            "particles": 800,
            "particle_duration_s": 600.0,
            "particle_sigma_h": 20.0,
            "particle_sigma_z": 10.0,
            "particle_advection_steps": 2,
        },
    }
    meteo = {
        "u": [[1.0]],
        "v": [[0.0]],
        "temperature": [[293.15]],
        "mixing_height": [[1000.0]],
        "precipitation_rate": [[0.0]],
    }
    cool_rows = particles.simulate_particles(from_mapping(cfg_base), meteo, seed=4)
    hot_raw = {
        **cfg_base,
        "sources": [{**cfg_base["sources"][0], "heat_release": 10_000_000.0, "exit_temperature": 1123.15}],
    }
    hot_rows = particles.simulate_particles(from_mapping(hot_raw), meteo, seed=4)

    assert max(row["concentration"] for row in hot_rows) < max(row["concentration"] for row in cool_rows)


def test_particle_plume_rise_uses_particle_age():
    base = load_config("examples/minimal.json")
    src = from_mapping(base.raw).sources[0]
    hot_src = type(src)(
        **{
            **src.__dict__,
            "z": 0.0,
            "stack_height": 0.0,
            "heat_release": 10_000_000.0,
            "exit_temperature": 1123.15,
        }
    )
    heights = particles._particle_effective_release_heights(
        hot_src,
        wind_speed=2.0,
        downwind_distances=np.asarray([2.0, 200.0, 2000.0], dtype=float),
        ambient_temperature=293.15,
        downwash=True,
    )
    assert heights[0] < heights[1] < heights[2]
    assert heights[0] < 0.25 * heights[2]


def test_gaussian_and_particles_grid_fields_keep_config_center_coordinates():
    base = load_config("examples/minimal.json")
    cfg = from_mapping(
        {
            **base.raw,
            "metadata": {"center_lat": 40.827, "center_lon": 14.518},
            "grid": {
                **base.raw["grid"],
                "nx": 5,
                "ny": 5,
                "dx": 100.0,
                "dy": 100.0,
                "x0": -200.0,
                "y0": -200.0,
            },
            "sources": [{**base.raw["sources"][0], "x": 0.0, "y": 0.0, "latitude": 40.827, "longitude": 14.518}],
            "receptors": [],
            "run": {
                **base.raw["run"],
                "output_interval_s": 60.0,
                "output_duration_s": 60.0,
                "concentration_output": "grid",
                "field_z_levels": [1.5],
                "particles": 50,
                "particle_duration_s": 60.0,
                "particle_sigma_h": 20.0,
            },
        }
    )
    meteo = {
        "u": [[0.0]],
        "v": [[0.0]],
        "temperature": [[293.15]],
        "mixing_height": [[1000.0]],
        "precipitation_rate": [[0.0]],
    }

    for rows in (spritz.compute_concentrations(cfg, meteo), particles.simulate_particles(cfg, meteo, seed=2)):
        center = next(row for row in rows if row["x"] == 0.0 and row["y"] == 0.0)
        assert center["latitude"] == pytest.approx(40.827)
        assert center["longitude"] == pytest.approx(14.518)


def test_wind_sampler_interpolates_time_space_and_height():
    meteo = {
        "time": [0.0, 10.0],
        "z": [0.0, 100.0],
        "y": [0.0, 100.0],
        "x": [0.0, 100.0],
        "u": np.zeros((2, 2, 2, 2), dtype=float).tolist(),
        "v": np.zeros((2, 2, 2, 2), dtype=float).tolist(),
    }
    u = np.asarray(meteo["u"], dtype=float)
    v = np.asarray(meteo["v"], dtype=float)
    for it, time_value in enumerate(meteo["time"]):
        for iz, z_value in enumerate(meteo["z"]):
            for iy, y_value in enumerate(meteo["y"]):
                for ix, x_value in enumerate(meteo["x"]):
                    u[it, iz, iy, ix] = time_value + 0.01 * z_value + 0.001 * y_value + 0.0001 * x_value
                    v[it, iz, iy, ix] = -u[it, iz, iy, ix]
    meteo["u"] = u.tolist()
    meteo["v"] = v.tolist()

    sampler = spritz.WindSampler(meteo)
    sampled_u, sampled_v = sampler.sample(50.0, 50.0, 50.0, 5.0)
    assert float(sampled_u) == pytest.approx(5.555)
    assert float(sampled_v) == pytest.approx(-5.555)


def test_wind_sampler_uses_diagnostic_10m_below_first_model_level():
    meteo = {
        "time": [0.0],
        "z": [252.32, 500.0],
        "y": [0.0],
        "x": [0.0],
        "u": np.array([[[[20.0]], [[30.0]]]], dtype=float).tolist(),
        "v": np.array([[[[0.0]], [[0.0]]]], dtype=float).tolist(),
        "u10m": np.array([[[3.0]]], dtype=float).tolist(),
        "v10m": np.array([[[4.0]]], dtype=float).tolist(),
    }

    sampler = spritz.WindSampler(meteo)
    u_ground, v_ground = sampler.sample(0.0, 0.0, 1.5, 0.0)
    u_10m, v_10m = sampler.sample(0.0, 0.0, 10.0, 0.0)
    u_mid, v_mid = sampler.sample(0.0, 0.0, 131.16, 0.0)

    assert float(u_ground) == pytest.approx(3.0)
    assert float(v_ground) == pytest.approx(4.0)
    assert float(u_10m) == pytest.approx(3.0)
    assert float(v_10m) == pytest.approx(4.0)
    assert 3.0 < float(u_mid) < 20.0
    assert 0.0 < float(v_mid) < 4.0


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


def _small_wrf() -> spritzwrf.WRFWindField:
    lat = np.asarray([[40.0, 40.0], [40.01, 40.01]], dtype=float)
    lon = np.asarray([[14.0, 14.01], [14.0, 14.01]], dtype=float)
    return spritzwrf.WRFWindField(
        latitude=lat,
        longitude=lon,
        u=np.full((2, 2, 2, 2), 3.0),
        v=np.full((2, 2, 2, 2), 1.0),
        source_path=Path("synthetic_wrf.nc"),
        precipitation_rate=np.full((2, 2, 2), 0.5),
    )


def test_spritzmet_downscales_wind_as_4d_and_precipitation_as_3d() -> None:
    met = spritzmet.downscale_wrf_to_local_grid(
        _small_wrf(),
        center_lat=40.005,
        center_lon=14.005,
        nx=3,
        ny=3,
        dx_m=100.0,
        dy_m=100.0,
    )
    assert met.wind_4d[0].shape == (2, 2, 3, 3)
    assert met.wind_4d[1].shape == (2, 2, 3, 3)
    assert met.precipitation_3d.shape == (2, 3, 3)
    assert met.downscaling_metadata["downscaling_mode"] == "deterministic"
    assert met.downscaling_metadata["wind_dimensions"] == "time,z,y,x"
    assert met.downscaling_metadata["precipitation_dimensions"] == "time,y,x"


def _fortran_records(path: Path, endian: str = ">") -> list[bytes]:
    records = []
    data = path.read_bytes()
    offset = 0
    while offset < len(data):
        (size,) = struct.unpack_from(f"{endian}i", data, offset)
        offset += 4
        records.append(data[offset : offset + size])
        offset += size
        (trailer,) = struct.unpack_from(f"{endian}i", data, offset)
        offset += 4
        assert trailer == size
    return records


def test_spritzmet_writes_calmet_dat_binary_records(tmp_path: Path) -> None:
    met = spritzmet.downscale_wrf_to_local_grid(
        _small_wrf(),
        center_lat=40.005,
        center_lon=14.005,
        nx=3,
        ny=3,
        dx_m=100.0,
        dy_m=100.0,
    )
    out = tmp_path / "CALMET.DAT"

    assert spritzmet.write_calmet_dat(out, met) == "CALMET.DAT"

    records = _fortran_records(out)
    assert records[0][:80].rstrip() == b"CALMET.DAT"
    assert struct.unpack(">6i", records[1]) == (1, 3, 3, 2, 2, 1)
    assert struct.unpack(">4f", records[2]) == pytest.approx((100.0, 100.0, 40.005, 14.005))
    field_names = records[10].decode("ascii")
    assert "EASTWARD_WIND_M_S" in field_names
    assert "NORTHWARD_WIND_M_S" in field_names
    assert "PRECIP_MM_H" in field_names


def test_spritzmet_ai_and_diffusion_downscaling_hooks_are_optional() -> None:
    def model(payload):
        return {
            "u": payload["u"] + 2.0,
            "v": payload["v"],
            "precipitation_rate": payload["precipitation_rate"] + 0.25,
        }

    dem = np.asarray([[0.0, 20.0, 40.0], [10.0, 45.0, 80.0], [0.0, 15.0, 30.0]])
    land_cover = np.asarray([[50, 50, 30], [50, 30, 30], [80, 80, 30]])
    baseline = spritzmet.downscale_wrf_to_local_grid(
        _small_wrf(),
        center_lat=40.005,
        center_lon=14.005,
        nx=3,
        ny=3,
        dx_m=100.0,
        dy_m=100.0,
        downscaling_mode="ai",
        dem_elevation_m=dem,
        land_cover=land_cover,
    )
    diffusion_builtin = spritzmet.downscale_wrf_to_local_grid(
        _small_wrf(),
        center_lat=40.005,
        center_lon=14.005,
        nx=3,
        ny=3,
        dx_m=100.0,
        dy_m=100.0,
        downscaling_mode="diffusion",
        dem_elevation_m=dem,
        land_cover=land_cover,
    )
    assert baseline.downscaling_metadata["model_status"] == "applied_builtin"
    assert baseline.downscaling_metadata["model_family"] == "clean_room_feature_residual_ai"
    assert diffusion_builtin.downscaling_metadata["model_status"] == "applied_builtin"
    assert diffusion_builtin.downscaling_metadata["model_family"] == "clean_room_anisotropic_diffusion"
    assert not np.allclose(baseline.wind_4d[0], diffusion_builtin.wind_4d[0])

    ai = spritzmet.downscale_wrf_to_local_grid(
        _small_wrf(),
        center_lat=40.005,
        center_lon=14.005,
        nx=3,
        ny=3,
        dx_m=100.0,
        dy_m=100.0,
        downscaling_mode="ai",
        ai_model=model,
    )
    diffusion = spritzmet.downscale_wrf_to_local_grid(
        _small_wrf(),
        center_lat=40.005,
        center_lon=14.005,
        nx=3,
        ny=3,
        dx_m=100.0,
        dy_m=100.0,
        downscaling_mode="diffusion",
        diffusion_model=model,
    )
    callback_base = spritzmet.downscale_wrf_to_local_grid(
        _small_wrf(),
        center_lat=40.005,
        center_lon=14.005,
        nx=3,
        ny=3,
        dx_m=100.0,
        dy_m=100.0,
    )
    assert ai.downscaling_metadata["model_status"] == "applied"
    assert diffusion.downscaling_metadata["downscaling_mode"] == "diffusion"
    assert float(np.mean(ai.wind_4d[0] - callback_base.wind_4d[0])) == 2.0


def test_spritzmet_station_measurements_can_improve_any_downscaling_mode() -> None:
    plain = spritzmet.downscale_wrf_to_local_grid(
        _small_wrf(),
        center_lat=40.005,
        center_lon=14.005,
        nx=3,
        ny=3,
        dx_m=100.0,
        dy_m=100.0,
    )
    improved = spritzmet.downscale_wrf_to_local_grid(
        _small_wrf(),
        center_lat=40.005,
        center_lon=14.005,
        nx=3,
        ny=3,
        dx_m=100.0,
        dy_m=100.0,
        station_measurements=[{"x": 0.0, "y": 0.0, "wind_speed": 8.0, "wind_dir": 270.0, "precipitation_rate": 2.0}],
    )
    assert improved.downscaling_metadata["station_measurement_improvement"] is True
    assert not np.allclose(improved.wind_4d[0], plain.wind_4d[0])
    assert not np.allclose(improved.precipitation_3d, plain.precipitation_3d)


def test_spritzmet_reads_station_measurements_csv(tmp_path: Path) -> None:
    local_csv = tmp_path / "stations_local.csv"
    local_csv.write_text(
        "id,x,y,wind_speed,wind_dir,precipitation_rate\nS1,0,100,6,270,1.5\n",
        encoding="utf-8",
    )
    local = spritzmet.read_station_measurements_csv(local_csv)
    assert local == [{"x": 0.0, "y": 100.0, "id": "S1", "wind_speed": 6.0, "wind_dir": 270.0, "precipitation_rate": 1.5}]

    geo_csv = tmp_path / "stations_geo.csv"
    geo_csv.write_text(
        "station_id,latitude,longitude,wind_speed_m_s,wind_direction\nG1,40.005,14.005,5,180\n",
        encoding="utf-8",
    )
    geo = spritzmet.read_station_measurements_csv(geo_csv, center_lat=40.005, center_lon=14.005)
    assert geo[0]["id"] == "G1"
    assert geo[0]["wind_speed"] == 5.0
    assert abs(float(geo[0]["x"])) < 1.0e-6
    assert abs(float(geo[0]["y"])) < 1.0e-6

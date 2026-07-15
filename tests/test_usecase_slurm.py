from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _slurm_dir(usecase: str) -> Path:
    return ROOT / "usecases" / usecase / "slurm"


def test_staged_slurm_launchers_cover_requested_usecase_stages() -> None:
    expected = {
        "01_high_resolution_wind_field": {
            "01_download_weather.slurm",
            "02_download_dem.slurm",
            "03_download_landuse.slurm",
            "04_downscale_meteorology.slurm",
            "05_plot.slurm",
        },
        "02_wildfire_arson_effects": {
            "01_download_weather.slurm",
            "02_download_dem.slurm",
            "03_download_landuse.slurm",
            "04_downscale_meteorology.slurm",
            "05_run_particles.slurm",
            "06_run_gaussian.slurm",
            "07_plot.slurm",
        },
        "03_satellite_ai_evaluation": {
            "01_download_weather.slurm",
            "02_download_dem.slurm",
            "03_download_landuse.slurm",
            "04_downscale_meteorology.slurm",
            "05_run_particles.slurm",
            "06_run_gaussian.slurm",
            "07_plot.slurm",
        },
    }
    for usecase, launchers in expected.items():
        directory = _slurm_dir(usecase)
        assert launchers <= {path.name for path in directory.glob("*.slurm")}
        assert (directory / "submit.sh").is_file()


def test_compute_launchers_require_mpi_and_srun() -> None:
    for usecase in (
        "01_high_resolution_wind_field",
        "02_wildfire_arson_effects",
        "03_satellite_ai_evaluation",
    ):
        directory = _slurm_dir(usecase)
        compute = [directory / "04_downscale_meteorology.slurm"]
        compute.extend(directory.glob("0[56]_run_*.slurm"))
        for launcher in compute:
            text = launcher.read_text(encoding="utf-8")
            assert "srun " in text
            assert "--parallel mpi" in text


def test_submitters_are_non_blocking_and_dependency_aware() -> None:
    for usecase in (
        "01_high_resolution_wind_field",
        "02_wildfire_arson_effects",
        "03_satellite_ai_evaluation",
    ):
        text = (_slurm_dir(usecase) / "submit.sh").read_text(encoding="utf-8")
        assert "sbatch --parsable" in text
        assert "--dependency=" in text
        assert "--wait" not in text

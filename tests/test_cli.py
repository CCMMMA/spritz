from sprtz.cli import main, spritz_main, spritzmet_main
from sprtz.io.jsonio import read_json, write_json


def test_validate_cli(capsys):
    assert main(["validate", "examples/minimal.json"]) == 0
    assert "valid:" in capsys.readouterr().out


def test_run_cli_defaults_to_netcdf_interchange(tmp_path):
    assert main(["run", "examples/minimal.json", "--output-dir", str(tmp_path)]) == 0
    assert (tmp_path / "meteo.nc").exists()
    assert (tmp_path / "concentration.nc").exists()
    assert (tmp_path / "post.json").exists()


def test_run_cli_legacy_interchange(tmp_path):
    assert main(["run", "examples/minimal.inp", "--output-dir", str(tmp_path), "--interchange", "json"]) == 0
    assert (tmp_path / "meteo.json").exists()
    assert (tmp_path / "concentration.csv").exists()
    assert (tmp_path / "post.json").exists()


def test_run_cli_parallel_auto_fallback(tmp_path):
    assert main(["run", "examples/minimal.json", "--output-dir", str(tmp_path), "--parallel", "auto"]) == 0
    assert (tmp_path / "concentration.nc").exists()


def test_run_cli_output_interval(tmp_path):
    assert (
        main(
            [
                "run",
                "examples/minimal.json",
                "--output-dir",
                str(tmp_path),
                "--interchange",
                "json",
                "--output-interval",
                "600",
            ]
        )
        == 0
    )
    rows = list(__import__("csv").DictReader((tmp_path / "concentration.csv").open()))
    assert len(rows) == 12


def test_run_cli_uses_json_backend(tmp_path, capsys):
    data = read_json("examples/minimal.json")
    data["run"]["backend"] = "particles"
    data["run"]["particles"] = 100
    config_path = tmp_path / "particles.json"
    write_json(config_path, data)
    assert main(["run", str(config_path), "--output-dir", str(tmp_path), "--interchange", "json"]) == 0
    assert "backend: particles" in capsys.readouterr().out


def test_spritz_command_uses_json_backend(tmp_path):
    data = read_json("examples/minimal.json")
    data["run"]["backend"] = "particles"
    data["run"]["particles"] = 100
    config_path = tmp_path / "particles.json"
    meteo_path = tmp_path / "meteo.json"
    concentration_path = tmp_path / "concentration.csv"
    write_json(config_path, data)
    assert spritzmet_main(["--config", str(config_path), "--output", str(meteo_path), "--format", "json"]) == 0
    assert (
        spritz_main(
            [
                "--config",
                str(config_path),
                "--meteo",
                str(meteo_path),
                "--output",
                str(concentration_path),
                "--format",
                "csv",
            ]
        )
        == 0
    )
    rows = list(__import__("csv").DictReader(concentration_path.open()))
    assert rows[0]["output_kind"] == "receptor"

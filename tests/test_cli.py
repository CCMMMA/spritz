from sprtz.cli import main


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

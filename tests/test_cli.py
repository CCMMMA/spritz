from pypuff.cli import main


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

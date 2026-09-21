from typer.testing import CliRunner

from fanglei.cli import app


def test_subtitle_command_is_registered():
    result = CliRunner().invoke(app, ["subtitle", "--help"])
    assert result.exit_code == 0
    assert "subtitle" in result.stdout


def test_master_audio_command_is_registered():
    result = CliRunner().invoke(app, ["master-audio", "--help"])
    assert result.exit_code == 0
    assert "master-audio" in result.stdout

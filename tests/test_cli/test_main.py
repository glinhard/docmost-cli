"""Tests for the root CLI app: version and global options."""

import re

from typer.testing import CliRunner

from docmost_cli.cli.main import app, get_version, state

runner = CliRunner()

_VERSION_RE = re.compile(r"^docmost-cli \d+\.\d+\.\d+")


class TestVersion:
    def test_version_flag(self) -> None:
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert _VERSION_RE.match(result.output.strip())

    def test_version_short_flag(self) -> None:
        result = runner.invoke(app, ["-V"])
        assert result.exit_code == 0
        assert _VERSION_RE.match(result.output.strip())

    def test_version_subcommand(self, tmp_config) -> None:
        result = runner.invoke(app, ["--config", str(tmp_config), "version"])
        assert result.exit_code == 0
        assert _VERSION_RE.match(result.output.strip())

    def test_version_needs_no_config(self, monkeypatch, tmp_path) -> None:
        """The eager callback must fire before settings are loaded."""
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty"))
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0

    def test_short_v_is_still_verbose(self, tmp_config) -> None:
        """-v must stay --verbose; -V is the version flag."""
        result = runner.invoke(app, ["--config", str(tmp_config), "-v", "config", "show"])
        assert result.exit_code == 0
        assert not _VERSION_RE.match(result.output.strip())

    def test_get_version_returns_semver(self) -> None:
        assert re.match(r"^\d+\.\d+\.\d+", get_version())


class TestNoSessionCache:
    def test_flag_reaches_settings(self, tmp_config_session) -> None:
        result = runner.invoke(
            app,
            ["--config", str(tmp_config_session), "--no-session-cache", "config", "show"],
        )
        assert result.exit_code == 0
        assert state.settings is not None
        assert state.settings.no_session_cache is True

    def test_defaults_to_false(self, tmp_config_session) -> None:
        result = runner.invoke(app, ["--config", str(tmp_config_session), "config", "show"])
        assert result.exit_code == 0
        assert state.settings is not None
        assert state.settings.no_session_cache is False

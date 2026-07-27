"""Tests for config CLI commands."""

import json

from typer.testing import CliRunner

from docmost_cli.cli.main import app

runner = CliRunner()


class TestConfigShowJson:
    """Masking must apply identically to JSON — this is the one lossy-by-design path."""

    def test_json_is_valid_and_masks_api_key(self, tmp_config) -> None:
        result = runner.invoke(app, ["--config", str(tmp_config), "config", "show", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["url"] == "https://docs.example.com"
        assert payload["api_key"].startswith("dm_t")
        assert "dm_test1234567890" not in result.output

    def test_json_masks_password(self, tmp_config_session) -> None:
        result = runner.invoke(
            app, ["--config", str(tmp_config_session), "config", "show", "--json"]
        )
        assert result.exit_code == 0
        assert "secret123" not in result.output
        assert json.loads(result.output)["password"].startswith("secr")

    def test_no_session_cache_is_a_real_bool(self, tmp_config) -> None:
        """Not the string "false", which is truthy nearly everywhere."""
        result = runner.invoke(app, ["--config", str(tmp_config), "config", "show", "--json"])
        assert json.loads(result.output)["no_session_cache"] is False

    def test_table_still_shows_no_session_cache(self, tmp_config) -> None:
        result = runner.invoke(app, ["--config", str(tmp_config), "config", "show"])
        assert "no_session_cache" in result.output


class TestConfigShow:
    def test_show_with_config_file(self, tmp_config) -> None:
        result = runner.invoke(app, ["--config", str(tmp_config), "config", "show"])
        assert result.exit_code == 0
        assert "docs.example.com" in result.output
        # API key should be masked
        assert "dm_test1234567890" not in result.output
        assert "dm_t" in result.output  # First 4 chars visible

    def test_show_missing_config(self, tmp_path) -> None:
        config = tmp_path / "nonexistent.toml"
        result = runner.invoke(app, ["--config", str(config), "config", "show"])
        assert result.exit_code == 0


class TestConfigSet:
    def test_set_url(self, tmp_path) -> None:
        config = tmp_path / "config.toml"
        result = runner.invoke(
            app, ["--config", str(config), "config", "set", "url", "https://new.example.com"]
        )
        assert result.exit_code == 0

        # Verify by showing
        result = runner.invoke(app, ["--config", str(config), "config", "show"])
        assert "new.example.com" in result.output

    def test_set_invalid_key(self, tmp_path) -> None:
        config = tmp_path / "config.toml"
        result = runner.invoke(
            app, ["--config", str(config), "config", "set", "invalid_key", "value"]
        )
        assert result.exit_code != 0


class TestHelpOutput:
    def test_main_help(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "docmost-cli" in result.output.lower() or "CLI tool" in result.output

    def test_config_help(self) -> None:
        result = runner.invoke(app, ["config", "--help"])
        assert result.exit_code == 0
        assert "init" in result.output
        assert "show" in result.output
        assert "set" in result.output
        assert "test" in result.output

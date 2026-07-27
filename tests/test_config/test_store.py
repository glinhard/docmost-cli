"""Tests for config store (TOML read/write, load_settings)."""

from pathlib import Path

import pytest

from docmost_cli.config.store import (
    get_config_path,
    load_settings,
    read_config,
    read_profile,
    set_config_value,
    write_config,
)


class TestGetConfigPath:
    def test_override(self) -> None:
        result = get_config_path("/custom/path.toml")
        assert result == Path("/custom/path.toml")

    def test_xdg_config_home(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("XDG_CONFIG_HOME", "/tmp/xdg")
        result = get_config_path()
        assert result == Path("/tmp/xdg/docmost-cli/config.toml")

    def test_default_home(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        result = get_config_path()
        assert result.name == "config.toml"
        assert "docmost-cli" in str(result)


class TestReadConfig:
    def test_existing_file(self, tmp_config: Path) -> None:
        config = read_config(tmp_config)
        assert "default" in config
        assert config["default"]["url"] == "https://docs.example.com"
        assert config["default"]["api_key"] == "dm_test1234567890"

    def test_missing_file(self, tmp_path: Path) -> None:
        config = read_config(tmp_path / "nonexistent.toml")
        assert config == {}


class TestReadProfile:
    def test_existing_profile(self, tmp_config: Path) -> None:
        profile = read_profile("default", tmp_config)
        assert profile["url"] == "https://docs.example.com"

    def test_missing_profile(self, tmp_config: Path) -> None:
        profile = read_profile("nonexistent", tmp_config)
        assert profile == {}


class TestWriteConfig:
    def test_creates_dirs_and_writes(self, tmp_path: Path) -> None:
        config_path = tmp_path / "sub" / "dir" / "config.toml"
        config = {"default": {"url": "https://test.com"}}
        write_config(config, config_path)

        assert config_path.exists()
        result = read_config(config_path)
        assert result["default"]["url"] == "https://test.com"


class TestSetConfigValue:
    def test_set_new_key(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        set_config_value("url", "https://new.com", config_path=config_path)

        config = read_config(config_path)
        assert config["default"]["url"] == "https://new.com"

    def test_update_existing_key(self, tmp_config: Path) -> None:
        set_config_value("url", "https://updated.com", config_path=tmp_config)

        config = read_config(tmp_config)
        assert config["default"]["url"] == "https://updated.com"

    def test_different_profile(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        set_config_value("url", "https://staging.com", profile="staging", config_path=config_path)

        config = read_config(config_path)
        assert config["staging"]["url"] == "https://staging.com"


class TestLoadSettings:
    def test_from_config_file(self, tmp_config: Path) -> None:
        settings = load_settings(config_path=tmp_config)
        assert settings.url == "https://docs.example.com"
        assert settings.api_key == "dm_test1234567890"

    def test_missing_config(self, tmp_path: Path) -> None:
        settings = load_settings(config_path=tmp_path / "nope.toml")
        assert settings.url is None

    def test_cli_overrides_beat_config(self, tmp_config: Path) -> None:
        settings = load_settings(
            config_path=tmp_config,
            cli_overrides={"url": "https://cli-override.com"},
        )
        assert settings.url == "https://cli-override.com"

    def test_env_vars_beat_config(self, tmp_config: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DOCMOST_URL", "https://env-override.com")
        settings = load_settings(config_path=tmp_config)
        assert settings.url == "https://env-override.com"

    def test_cli_overrides_beat_env(
        self, tmp_config: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DOCMOST_URL", "https://env.com")
        settings = load_settings(
            config_path=tmp_config,
            cli_overrides={"url": "https://cli-wins.com"},
        )
        assert settings.url == "https://cli-wins.com"

    def test_profile_selection(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        config_path.write_text(
            '[default]\nurl = "https://prod.com"\n\n[staging]\nurl = "https://staging.com"\n'
        )
        settings = load_settings(profile="staging", config_path=config_path)
        assert settings.url == "https://staging.com"
        assert settings.profile == "staging"


class TestLoadSettingsBoolFields:
    """A bool field defaulting to False must still be settable from the config file."""

    @staticmethod
    def _write(tmp_path: Path, body: str) -> Path:
        config_path = tmp_path / "config.toml"
        config_path.write_text(body)
        return config_path

    def test_bool_from_config_file(self, tmp_path: Path) -> None:
        path = self._write(tmp_path, "[default]\nno_session_cache = true\n")
        assert load_settings(config_path=path).no_session_cache is True

    def test_bool_string_from_config_file_is_coerced(self, tmp_path: Path) -> None:
        path = self._write(tmp_path, '[default]\nno_session_cache = "true"\n')
        assert load_settings(config_path=path).no_session_cache is True

    def test_defaults_to_false(self, tmp_path: Path) -> None:
        path = self._write(tmp_path, '[default]\nurl = "https://x.com"\n')
        assert load_settings(config_path=path).no_session_cache is False

    def test_env_beats_config_for_bool(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DOCMOST_NO_SESSION_CACHE", "false")
        path = self._write(tmp_path, "[default]\nno_session_cache = true\n")
        assert load_settings(config_path=path).no_session_cache is False

    def test_cli_beats_env_for_bool(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DOCMOST_NO_SESSION_CACHE", "false")
        path = self._write(tmp_path, '[default]\nurl = "https://x.com"\n')
        settings = load_settings(config_path=path, cli_overrides={"no_session_cache": True})
        assert settings.no_session_cache is True

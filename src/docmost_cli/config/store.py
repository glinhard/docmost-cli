"""Config file read/write and settings factory.

Handles TOML config file at ~/.config/docmost-cli/config.toml
and session cache at ~/.cache/docmost-cli/session.json.
"""

import os
import tomllib
from pathlib import Path
from typing import Any

import tomli_w

from docmost_cli.config.settings import DocmostSettings

__all__ = [
    "get_cache_dir",
    "get_config_path",
    "load_settings",
    "read_config",
    "read_profile",
    "set_config_value",
    "write_config",
]

APP_NAME = "docmost-cli"


def get_config_path(override: str | None = None) -> Path:
    """Return the config file path.

    Args:
        override: Explicit path to use instead of the default.

    Returns:
        Path to the config TOML file.
    """
    if override:
        return Path(override)
    config_home = os.environ.get("XDG_CONFIG_HOME")
    base = Path(config_home) if config_home else Path.home() / ".config"
    return base / APP_NAME / "config.toml"


def get_cache_dir() -> Path:
    """Return the cache directory path for session tokens."""
    cache_home = os.environ.get("XDG_CACHE_HOME")
    base = Path(cache_home) if cache_home else Path.home() / ".cache"
    return base / APP_NAME


def read_config(config_path: Path | None = None) -> dict[str, dict[str, Any]]:
    """Read the full TOML config, returning all profiles.

    Args:
        config_path: Path to config file. Uses default if None.

    Returns:
        Dict of profile name → dict of key-value pairs.
    """
    path = config_path or get_config_path()
    if not path.exists():
        return {}
    with open(path, "rb") as f:
        return tomllib.load(f)


def read_profile(profile: str = "default", config_path: Path | None = None) -> dict[str, Any]:
    """Read a specific profile from the config file.

    Args:
        profile: Profile name to read.
        config_path: Path to config file. Uses default if None.

    Returns:
        Dict of config values for the profile. Empty dict if not found.
    """
    config = read_config(config_path)
    return config.get(profile, {})


def write_config(config: dict[str, dict[str, Any]], config_path: Path | None = None) -> None:
    """Write the full config dict to the TOML file.

    Creates parent directories if needed. Writes atomically via temp file.

    Args:
        config: Full config dict (profile name → key-value pairs).
        config_path: Path to config file. Uses default if None.
    """
    path = config_path or get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    with open(tmp_path, "wb") as f:
        tomli_w.dump(config, f)
    tmp_path.replace(path)


def set_config_value(
    key: str,
    value: str | bool,
    profile: str = "default",
    config_path: Path | None = None,
) -> None:
    """Set a single key in a profile, creating profile/file if needed.

    Args:
        key: Config key to set.
        value: Value to set.
        profile: Profile to update.
        config_path: Path to config file. Uses default if None.
    """
    config = read_config(config_path)
    if profile not in config:
        config[profile] = {}
    config[profile][key] = value
    write_config(config, config_path)


def load_settings(
    profile: str = "default",
    config_path: Path | None = None,
    cli_overrides: dict[str, Any] | None = None,
) -> DocmostSettings:
    """Load settings with full priority chain.

    Priority: CLI overrides > env vars > config file > defaults.

    In pydantic-settings v2, init kwargs beat env vars. So we construct
    with no kwargs first (picks up env vars), then fill in config file
    values only for fields that are still unset, then apply CLI overrides.

    Args:
        profile: Config profile name to load.
        config_path: Path to config file. Uses default if None.
        cli_overrides: Dict of CLI flag overrides (highest priority).

    Returns:
        Fully resolved DocmostSettings instance.
    """
    file_values = read_profile(profile, config_path)

    # Step 1: Construct with no init kwargs — picks up env vars.
    settings = DocmostSettings()

    # Step 2: Fill in config file values only where env didn't set a value.
    # `model_fields_set` is the reliable test: a sentinel check like
    # `getattr(...) is None` would never fire for a bool field defaulting to
    # False, silently ignoring the config file.
    updates: dict[str, Any] = {}
    for key, value in file_values.items():
        if key in DocmostSettings.model_fields and key not in settings.model_fields_set:
            updates[key] = value
    updates["profile"] = profile

    # Step 3: CLI overrides beat everything.
    if cli_overrides:
        updates.update({k: v for k, v in cli_overrides.items() if v is not None})

    if updates:
        # Re-validate rather than model_copy(update=...) so a TOML or CLI
        # string like "true" is coerced to the field's declared type.
        settings = DocmostSettings.model_validate({**settings.model_dump(), **updates})

    return settings

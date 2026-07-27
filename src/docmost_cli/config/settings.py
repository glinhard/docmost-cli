"""Pydantic settings model for Docmost CLI configuration.

Resolution order: CLI flags > env vars > config file > defaults.
The config file is loaded by store.py and merged separately.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["DocmostSettings"]


class DocmostSettings(BaseSettings):
    """Typed settings for a Docmost CLI session."""

    model_config = SettingsConfigDict(
        env_prefix="DOCMOST_",
    )

    url: str | None = None
    api_key: str | None = None
    email: str | None = None
    password: str | None = None
    profile: str = "default"
    # When true, the session JWT stays in memory and is never read from or
    # written to ~/.cache/docmost-cli/session.json.
    no_session_cache: bool = False

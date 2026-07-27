"""Tests for user CLI commands."""

import json

from typer.testing import CliRunner

from docmost_cli.cli.main import app

runner = CliRunner()

USER = {
    "id": "user-42",
    "email": "alice@example.com",
    "name": "Alice",
    "role": "admin",
    "createdAt": "2025-06-15T10:30:00Z",
    # Outside the curated key-value view:
    "locale": "en-US",
    "timezone": "Europe/Vienna",
}


class TestUserMe:
    @staticmethod
    def _mock(httpx_mock) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/users/me",
            json={"data": USER},
        )

    def test_shows_key_value_output(self, tmp_config, httpx_mock) -> None:
        self._mock(httpx_mock)
        result = runner.invoke(app, ["--config", str(tmp_config), "user", "me"])
        assert result.exit_code == 0
        assert "alice@example.com" in result.output
        assert "Alice" in result.output
        assert "user-42" in result.output
        # The human view stays curated.
        assert "timezone" not in result.output

    def test_json_emits_complete_object(self, tmp_config, httpx_mock) -> None:
        self._mock(httpx_mock)
        result = runner.invoke(app, ["--config", str(tmp_config), "user", "me", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["timezone"] == "Europe/Vienna"
        assert payload["locale"] == "en-US"

    def test_json_fields_projects(self, tmp_config, httpx_mock) -> None:
        self._mock(httpx_mock)
        result = runner.invoke(
            app, ["--config", str(tmp_config), "user", "me", "--json", "--fields", "email,role"]
        )
        assert result.exit_code == 0
        assert json.loads(result.output) == {"email": "alice@example.com", "role": "admin"}

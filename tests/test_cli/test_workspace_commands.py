"""Tests for workspace CLI commands."""

import json

from typer.testing import CliRunner

from docmost_cli.cli.main import app

runner = CliRunner()


WORKSPACE = {
    "id": "ws-1",
    "name": "Acme Wiki",
    "description": "Company wiki",
    "memberCount": 12,
    "createdAt": "2025-01-01T00:00:00Z",
    # Outside the curated key-value view:
    "hostname": "acme.docmost.com",
    "enforceSso": False,
}


class TestWorkspaceInfo:
    @staticmethod
    def _mock(httpx_mock) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/workspace/info",
            json={"data": WORKSPACE},
        )

    def test_shows_key_value_output(self, tmp_config, httpx_mock) -> None:
        self._mock(httpx_mock)
        result = runner.invoke(app, ["--config", str(tmp_config), "workspace", "info"])
        assert result.exit_code == 0
        assert "Acme Wiki" in result.output
        assert "ws-1" in result.output
        # The human view stays curated.
        assert "hostname" not in result.output

    def test_json_emits_complete_object(self, tmp_config, httpx_mock) -> None:
        self._mock(httpx_mock)
        result = runner.invoke(app, ["--config", str(tmp_config), "workspace", "info", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["hostname"] == "acme.docmost.com"
        assert payload["enforceSso"] is False

    def test_json_fields_projects(self, tmp_config, httpx_mock) -> None:
        self._mock(httpx_mock)
        result = runner.invoke(
            app,
            [
                "--config",
                str(tmp_config),
                "workspace",
                "info",
                "--json",
                "--fields",
                "name,hostname",
            ],
        )
        assert result.exit_code == 0
        assert json.loads(result.output) == {
            "name": "Acme Wiki",
            "hostname": "acme.docmost.com",
        }


class TestWorkspaceMembers:
    def test_members_json(self, tmp_config, httpx_mock) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/workspace/members",
            json={
                "data": {
                    "items": [
                        {
                            "id": "u1",
                            "email": "alice@example.com",
                            "name": "Alice",
                            "role": "admin",
                        },
                        {"id": "u2", "email": "bob@example.com", "name": "Bob", "role": "member"},
                    ]
                }
            },
        )
        result = runner.invoke(app, ["--config", str(tmp_config), "workspace", "members", "--json"])
        assert result.exit_code == 0
        assert "alice@example.com" in result.output
        assert "bob@example.com" in result.output
        assert "u1" in result.output
        assert "u2" in result.output

"""Tests for attachment CLI commands."""

import json

from typer.testing import CliRunner

from docmost_cli.cli.main import app

runner = CliRunner()


class TestAttachmentList:
    LIST_URL = "https://docs.example.com/api/pages/attachments"
    ITEMS = [
        {"id": "att-old", "fileName": "shot.png", "fileSize": 10, "createdAt": "2026-09-25"},
        {"id": "att-new", "fileName": "shot.png", "fileSize": 12, "createdAt": "2026-10-01"},
    ]

    def _invoke(self, tmp_config, *args):
        return runner.invoke(
            app, ["--config", str(tmp_config), "attachment", "list", "page-1", *args]
        )

    def test_lists_every_attachment(self, tmp_config, httpx_mock) -> None:
        httpx_mock.add_response(url=self.LIST_URL, json={"data": {"items": self.ITEMS}})
        result = self._invoke(tmp_config, "--json")
        assert result.exit_code == 0
        assert [item["id"] for item in json.loads(result.stdout)] == ["att-old", "att-new"]

    def test_unused_drops_what_the_page_embeds(self, tmp_config, httpx_mock) -> None:
        httpx_mock.add_response(url=self.LIST_URL, json={"data": {"items": self.ITEMS}})
        # Community: the body comes from /pages/info; there is no /pages/content.
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/info",
            json={
                "data": {
                    "id": "page-1",
                    "content": {
                        "type": "doc",
                        "content": [{"type": "image", "attrs": {"attachmentId": "att-new"}}],
                    },
                }
            },
        )
        result = self._invoke(tmp_config, "--unused", "--json")
        assert result.exit_code == 0
        assert [item["id"] for item in json.loads(result.stdout)] == ["att-old"]
        assert json.loads(httpx_mock.get_requests()[1].read())["includeContent"] is True

    def test_unused_on_a_page_never_written(self, tmp_config, httpx_mock) -> None:
        httpx_mock.add_response(url=self.LIST_URL, json={"data": {"items": self.ITEMS}})
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/info",
            json={"data": {"id": "page-1", "content": None}},
        )
        result = self._invoke(tmp_config, "--unused", "--json")
        assert result.exit_code == 0
        assert [item["id"] for item in json.loads(result.stdout)] == ["att-old", "att-new"]


class TestAttachmentSearch:
    def test_search_json(self, tmp_config, httpx_mock) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/search-attachments",
            json={
                "data": {
                    "items": [
                        {"id": "att-1", "fileName": "diagram.png", "type": "image/png"},
                        {"id": "att-2", "fileName": "screenshot.jpg", "type": "image/jpeg"},
                    ]
                }
            },
        )
        result = runner.invoke(
            app,
            ["--config", str(tmp_config), "attachment", "search", "diagram", "--json"],
        )
        assert result.exit_code == 0
        assert "att-1" in result.output
        assert "diagram.png" in result.output
        assert "att-2" in result.output

    def test_search_with_space(self, tmp_config, httpx_mock) -> None:
        # First call resolves space slug to ID via listing all spaces
        httpx_mock.add_response(
            url="https://docs.example.com/api/spaces",
            json={"data": {"items": [{"id": "space-uuid", "slug": "eng", "name": "Eng"}]}},
        )
        httpx_mock.add_response(
            url="https://docs.example.com/api/search-attachments",
            json={
                "data": {
                    "items": [
                        {"id": "att-3", "fileName": "logo.svg", "type": "image/svg+xml"},
                    ]
                }
            },
        )
        result = runner.invoke(
            app,
            [
                "--config",
                str(tmp_config),
                "attachment",
                "search",
                "logo",
                "--space",
                "eng",
                "--json",
            ],
        )
        assert result.exit_code == 0
        assert "att-3" in result.output
        assert "logo.svg" in result.output


class TestAttachmentUpload:
    UPLOAD_URL = "https://docs.example.com/api/files/upload"

    def _invoke(self, tmp_config, path):
        return runner.invoke(
            app,
            ["--config", str(tmp_config), "attachment", "upload", "page-1", "--file", str(path)],
        )

    def test_uploads_file(self, tmp_config, tmp_path, httpx_mock) -> None:
        image = tmp_path / "diagram.png"
        image.write_bytes(b"fake-png-bytes")
        httpx_mock.add_response(
            url=self.UPLOAD_URL,
            json={"id": "att-new", "fileName": "diagram.png", "type": "image/png"},
        )

        result = self._invoke(tmp_config, image)
        assert result.exit_code == 0
        assert "att-new" in result.output
        assert "/api/files/att-new/diagram.png" in result.output
        # The file itself is sent, not just its name.
        assert b"fake-png-bytes" in httpx_mock.get_requests()[0].read()

    def test_handles_the_envelope(self, tmp_config, tmp_path, httpx_mock) -> None:
        image = tmp_path / "diagram.png"
        image.write_bytes(b"x")
        httpx_mock.add_response(
            url=self.UPLOAD_URL,
            json={"success": True, "status": 200, "data": {"id": "att-e", "fileName": "d.png"}},
        )

        result = self._invoke(tmp_config, image)
        assert result.exit_code == 0
        assert "/api/files/att-e/d.png" in result.output

    def test_missing_file_errors(self, tmp_config, tmp_path) -> None:
        result = self._invoke(tmp_config, tmp_path / "missing.png")
        assert result.exit_code != 0
        assert "File not found" in result.output

    def test_directory_errors(self, tmp_config, tmp_path) -> None:
        """A directory exists but cannot be read as a file."""
        result = self._invoke(tmp_config, tmp_path)
        assert result.exit_code != 0
        assert "Not a file" in result.output

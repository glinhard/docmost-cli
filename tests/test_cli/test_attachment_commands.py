"""Tests for attachment CLI commands."""

from typer.testing import CliRunner

from docmost_cli.cli.main import app

runner = CliRunner()


class TestAttachmentSearch:
    def test_search_json(self, tmp_config, httpx_mock) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/attachments/search",
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
            url="https://docs.example.com/api/attachments/search",
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
    def test_uploads_file(self, tmp_config, tmp_path, httpx_mock) -> None:
        image_file = tmp_path / "diagram.png"
        image_file.write_bytes(b"fake-png-bytes")

        httpx_mock.add_response(
            url="https://docs.example.com/api/files/upload",
            json={"id": "att-new", "fileName": "diagram.png", "type": "image/png"},
        )
        result = runner.invoke(
            app,
            [
                "--config",
                str(tmp_config),
                "attachment",
                "upload",
                "page-1",
                "--file",
                str(image_file),
            ],
        )
        assert result.exit_code == 0
        assert "att-new" in result.output
        assert "/api/files/att-new/diagram.png" in result.output

    def test_missing_file_errors(self, tmp_config, tmp_path) -> None:
        missing_file = tmp_path / "missing.png"

        result = runner.invoke(
            app,
            [
                "--config",
                str(tmp_config),
                "attachment",
                "upload",
                "page-1",
                "--file",
                str(missing_file),
            ],
        )
        assert result.exit_code != 0
        assert "File not found" in result.output

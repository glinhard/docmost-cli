"""Tests for comment CLI commands."""

import json

from typer.testing import CliRunner

from docmost_cli.cli.main import app

runner = CliRunner()

# Import after app to avoid circular import
from docmost_cli.cli.comment import _extract_text_from_prosemirror  # noqa: E402


class TestExtractTextFromProsemirror:
    def test_simple_paragraph(self) -> None:
        doc = {
            "type": "doc",
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "Hello world"}]},
            ],
        }
        assert _extract_text_from_prosemirror(doc) == "Hello world"

    def test_multiple_paragraphs(self) -> None:
        doc = {
            "type": "doc",
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "Line 1"}]},
                {"type": "paragraph", "content": [{"type": "text", "text": "Line 2"}]},
            ],
        }
        assert _extract_text_from_prosemirror(doc) == "Line 1 Line 2"

    def test_truncates_long_text(self) -> None:
        doc = {
            "type": "doc",
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "x" * 200}]},
            ],
        }
        result = _extract_text_from_prosemirror(doc)
        assert len(result) == 100
        assert result.endswith("...")

    def test_empty_doc(self) -> None:
        doc = {"type": "doc", "content": []}
        assert _extract_text_from_prosemirror(doc) == ""


class TestCommentList:
    def test_list_json(self, tmp_config, httpx_mock) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/comments",
            json={
                "data": [
                    {"id": "c1", "content": "text", "creatorId": "u1", "createdAt": "2026-03-22"},
                ]
            },
        )
        result = runner.invoke(
            app, ["--config", str(tmp_config), "comment", "list", "page-1", "--json"]
        )
        assert result.exit_code == 0
        assert "c1" in result.output

    @staticmethod
    def _mock_prosemirror(httpx_mock) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/comments",
            json={
                "data": [
                    {
                        "id": "c1",
                        "content": {
                            "type": "doc",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "Looks good"}],
                                }
                            ],
                        },
                        "creatorId": "u1",
                        "createdAt": "2026-03-22",
                    },
                ]
            },
        )

    def test_json_keeps_raw_prosemirror(self, tmp_config, httpx_mock) -> None:
        """--json stays lossless: the flattening is a table-only convenience."""
        self._mock_prosemirror(httpx_mock)
        result = runner.invoke(
            app, ["--config", str(tmp_config), "comment", "list", "page-1", "--json"]
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload[0]["content"]["type"] == "doc"

    def test_table_flattens_prosemirror(self, tmp_config, httpx_mock) -> None:
        self._mock_prosemirror(httpx_mock)
        result = runner.invoke(app, ["--config", str(tmp_config), "comment", "list", "page-1"])
        assert result.exit_code == 0
        assert "Looks good" in result.output


class TestCommentCreate:
    def test_create(self, tmp_config, httpx_mock) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/comments/create",
            json={"id": "new-comment"},
        )
        result = runner.invoke(
            app,
            ["--config", str(tmp_config), "comment", "create", "page-1", "--content", "Nice!"],
        )
        assert result.exit_code == 0
        assert "new-comment" in result.output


class TestCommentUpdate:
    def test_update(self, tmp_config, httpx_mock) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/comments/update",
            json={"id": "c1"},
        )
        result = runner.invoke(
            app,
            ["--config", str(tmp_config), "comment", "update", "c1", "--content", "Updated"],
        )
        assert result.exit_code == 0
        assert "c1" in result.output

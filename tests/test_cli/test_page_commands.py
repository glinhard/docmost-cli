"""Tests for page CLI commands."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from docmost_cli.api.position import is_valid_position
from docmost_cli.cli.main import app
from docmost_cli.cli.page import _resolve_content

runner = CliRunner()


class TestResolveContent:
    def test_inline_content(self) -> None:
        result = _resolve_content("hello", None, False)
        assert result == "hello"

    def test_file_content(self, tmp_path: Path) -> None:
        f = tmp_path / "test.md"
        f.write_text("# File Content")
        result = _resolve_content(None, f, False)
        assert result == "# File Content"

    def test_no_content(self) -> None:
        result = _resolve_content(None, None, False)
        assert result is None

    def test_multiple_sources_exits(self) -> None:
        with pytest.raises(SystemExit):
            _resolve_content("inline", Path("file.md"), False)

    def test_file_not_found_exits(self) -> None:
        with pytest.raises(SystemExit):
            _resolve_content(None, Path("/nonexistent/file.md"), False)

    def test_content_escape_sequences(self) -> None:
        """Backslash-n in --content should become actual newline."""
        result = _resolve_content("Line 1\\n\\nLine 2", None, False)
        assert result == "Line 1\n\nLine 2"

    def test_content_escape_tab(self) -> None:
        """Backslash-t in --content should become actual tab."""
        result = _resolve_content("Col1\\tCol2", None, False)
        assert result == "Col1\tCol2"


class TestPageCreate:
    def test_create_with_content(self, tmp_config, httpx_mock) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/spaces",
            json={"data": {"items": [{"id": "space-1", "slug": "eng", "name": "Eng"}]}},
        )
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/import",
            json={"id": "page-new"},
        )
        # create_and_place_page now always applies the explicit title.
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/update",
            json={"data": {"id": "page-new"}},
        )
        result = runner.invoke(
            app,
            [
                "--config",
                str(tmp_config),
                "page",
                "create",
                "eng",
                "--title",
                "Test Page",
                "--content",
                "Hello world",
            ],
        )
        assert result.exit_code == 0
        assert "page-new" in result.output

    def test_create_with_parent_calls_move(self, tmp_config, httpx_mock) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/spaces",
            json={"data": {"items": [{"id": "space-1", "slug": "eng", "name": "Eng"}]}},
        )
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/import",
            json={"id": "child-page"},
        )
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/sidebar-pages",
            json={"data": {"items": [{"id": "sib-1", "position": "a1"}], "meta": {}}},
        )
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/move",
            json={"id": "child-page"},
        )
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/update",
            json={"data": {"id": "child-page"}},
        )
        result = runner.invoke(
            app,
            [
                "--config",
                str(tmp_config),
                "page",
                "create",
                "eng",
                "--title",
                "Child",
                "--content",
                "Content",
                "--parent",
                "parent-1",
            ],
        )
        assert result.exit_code == 0
        assert "child-page" in result.output
        # Verify move was called with a valid, sibling-aware position
        import json as json_mod

        move_requests = [r for r in httpx_mock.get_requests() if "/pages/move" in str(r.url)]
        assert len(move_requests) == 1
        move_body = json_mod.loads(move_requests[0].content)
        assert move_body["parentPageId"] == "parent-1"
        assert is_valid_position(move_body["position"])
        assert move_body["position"] < "a1"  # placed first

    def test_create_empty_page(self, tmp_config, httpx_mock) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/spaces",
            json={"data": {"items": [{"id": "space-1", "slug": "eng", "name": "Eng"}]}},
        )
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/import",
            json={"id": "empty-page"},
        )
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/update",
            json={"data": {"id": "empty-page"}},
        )
        result = runner.invoke(
            app,
            ["--config", str(tmp_config), "page", "create", "eng", "--title", "Empty"],
        )
        assert result.exit_code == 0
        assert "empty-page" in result.output

    def test_create_from_file(self, tmp_config, tmp_path, httpx_mock) -> None:
        content_file = tmp_path / "content.md"
        content_file.write_text("# From File\n\nContent here")

        httpx_mock.add_response(
            url="https://docs.example.com/api/spaces",
            json={"data": {"items": [{"id": "space-1", "slug": "eng", "name": "Eng"}]}},
        )
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/import",
            json={"id": "file-page"},
        )
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/update",
            json={"data": {"id": "file-page"}},
        )
        result = runner.invoke(
            app,
            [
                "--config",
                str(tmp_config),
                "page",
                "create",
                "eng",
                "--title",
                "File Page",
                "--file",
                str(content_file),
            ],
        )
        assert result.exit_code == 0
        assert "file-page" in result.output


class TestPageUpdate:
    def test_update_title(self, tmp_config, httpx_mock) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/info",
            json={"id": "page-1", "title": "Old Title"},
        )
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/update",
            json={"id": "page-1", "title": "New Title"},
        )
        result = runner.invoke(
            app,
            ["--config", str(tmp_config), "page", "update", "page-1", "--title", "New Title"],
        )
        assert result.exit_code == 0
        assert "page-1" in result.output

    def test_update_no_flags(self, tmp_config) -> None:
        result = runner.invoke(app, ["--config", str(tmp_config), "page", "update", "page-1"])
        assert result.exit_code != 0


class TestPageDelete:
    def test_delete_with_yes(self, tmp_config, httpx_mock) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/info",
            json={"id": "page-1", "title": "Doomed Page"},
        )
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/delete",
            json={"id": "page-1"},
        )
        result = runner.invoke(app, ["--config", str(tmp_config), "-y", "page", "delete", "page-1"])
        assert result.exit_code == 0
        assert "page-1" in result.output

    def test_delete_aborted(self, tmp_config, httpx_mock) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/info",
            json={"id": "page-1", "title": "Safe Page"},
        )
        result = runner.invoke(
            app,
            ["--config", str(tmp_config), "page", "delete", "page-1"],
            input="n\n",
        )
        assert result.exit_code != 0  # Aborted


class TestPageMove:
    @staticmethod
    def _mock_page_info(httpx_mock, **overrides) -> None:
        payload = {"id": "page-1", "title": "My Page", "spaceId": "space-1"}
        payload.update(overrides)
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/info", json={"data": payload}
        )

    @staticmethod
    def _mock_siblings(httpx_mock, items=None) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/sidebar-pages",
            json={"data": {"items": items or [], "meta": {"hasNextPage": False}}},
        )

    @staticmethod
    def _move_body(httpx_mock) -> dict:
        import json as json_mod

        requests = [r for r in httpx_mock.get_requests() if "/pages/move" in str(r.url)]
        assert len(requests) == 1
        return json_mod.loads(requests[0].content)

    def test_move_to_space(self, tmp_config, httpx_mock) -> None:
        self._mock_page_info(httpx_mock)
        httpx_mock.add_response(
            url="https://docs.example.com/api/spaces",
            json={"data": {"items": [{"id": "space-2", "slug": "staging", "name": "Staging"}]}},
        )
        self._mock_siblings(httpx_mock)
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/move",
            json={"id": "page-1"},
        )
        result = runner.invoke(
            app,
            ["--config", str(tmp_config), "page", "move", "page-1", "--space", "staging"],
        )
        assert result.exit_code == 0
        assert "page-1" in result.output

    def test_move_to_parent_sends_valid_position(self, tmp_config, httpx_mock) -> None:
        """Omitting --position must not produce the HTTP 400 the server used to send."""
        self._mock_page_info(httpx_mock)
        self._mock_siblings(httpx_mock, [{"id": "sib-1", "position": "a1AAA"}])
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/move", json={"id": "page-1"}
        )
        result = runner.invoke(
            app,
            ["--config", str(tmp_config), "page", "move", "page-1", "--parent", "parent-1"],
        )
        assert result.exit_code == 0
        body = self._move_body(httpx_mock)
        assert body["parentPageId"] == "parent-1"
        assert is_valid_position(body["position"])
        assert body["position"] < "a1AAA"

    def test_position_last_sorts_after_siblings(self, tmp_config, httpx_mock) -> None:
        self._mock_page_info(httpx_mock)
        self._mock_siblings(
            httpx_mock,
            [{"id": "sib-1", "position": "a1AAA"}, {"id": "sib-2", "position": "a2AAA"}],
        )
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/move", json={"id": "page-1"}
        )
        result = runner.invoke(
            app,
            [
                "--config",
                str(tmp_config),
                "page",
                "move",
                "page-1",
                "--parent",
                "parent-1",
                "--position",
                "last",
            ],
        )
        assert result.exit_code == 0
        assert self._move_body(httpx_mock)["position"] > "a2AAA"

    def test_raw_position_passes_through(self, tmp_config, httpx_mock) -> None:
        """An explicit key must be sent verbatim, with no sibling lookup."""
        self._mock_page_info(httpx_mock)
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/move", json={"id": "page-1"}
        )
        result = runner.invoke(
            app,
            [
                "--config",
                str(tmp_config),
                "page",
                "move",
                "page-1",
                "--parent",
                "parent-1",
                "--position",
                "a0V8f",
            ],
        )
        assert result.exit_code == 0
        assert self._move_body(httpx_mock)["position"] == "a0V8f"
        urls = [str(r.url) for r in httpx_mock.get_requests()]
        assert not any("sidebar-pages" in url for url in urls)

    def test_invalid_position_exits_2(self, tmp_config, httpx_mock) -> None:
        self._mock_page_info(httpx_mock)
        result = runner.invoke(
            app,
            [
                "--config",
                str(tmp_config),
                "page",
                "move",
                "page-1",
                "--parent",
                "parent-1",
                "--position",
                "abc",
            ],
        )
        assert result.exit_code == 2

    def test_root_moves_to_space_root(self, tmp_config, httpx_mock) -> None:
        self._mock_page_info(httpx_mock, parentPageId="old-parent")
        self._mock_siblings(httpx_mock, [{"id": "r1", "position": "a1AAA"}])
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/move", json={"id": "page-1"}
        )
        result = runner.invoke(
            app, ["--config", str(tmp_config), "page", "move", "page-1", "--root"]
        )
        assert result.exit_code == 0
        assert "parentPageId" not in self._move_body(httpx_mock)

    def test_root_with_parent_conflicts(self, tmp_config) -> None:
        result = runner.invoke(
            app,
            ["--config", str(tmp_config), "page", "move", "page-1", "--root", "--parent", "p1"],
        )
        assert result.exit_code == 2

    def test_move_no_flags(self, tmp_config) -> None:
        result = runner.invoke(app, ["--config", str(tmp_config), "page", "move", "page-1"])
        assert result.exit_code != 0


class TestPageList:
    def test_list_json(self, tmp_config, httpx_mock) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/spaces",
            json={"data": {"items": [{"id": "s1", "slug": "eng", "name": "Eng"}]}},
        )
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/recent",
            json={
                "data": {
                    "items": [
                        {
                            "id": "p1",
                            "title": "Page One",
                            "updatedAt": "2026-03-20",
                            # Outside the table's column list:
                            "slugId": "abc123",
                            "spaceId": "s1",
                            "isLocked": False,
                        },
                    ]
                }
            },
        )
        result = runner.invoke(app, ["--config", str(tmp_config), "page", "list", "eng", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload[0]["title"] == "Page One"
        # Lossless: fields outside the table columns survive.
        assert payload[0]["slugId"] == "abc123"
        assert payload[0]["spaceId"] == "s1"
        assert payload[0]["isLocked"] is False

    def test_list_table(self, tmp_config, httpx_mock) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/spaces",
            json={"data": {"items": [{"id": "s1", "slug": "eng", "name": "Eng"}]}},
        )
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/recent",
            json={
                "data": {
                    "items": [
                        {"id": "p1", "title": "Page One", "updatedAt": "2026-03-20"},
                    ]
                }
            },
        )
        result = runner.invoke(app, ["--config", str(tmp_config), "page", "list", "eng"])
        assert result.exit_code == 0
        assert "Page One" in result.output


class TestPageGet:
    def test_get_markdown(self, tmp_config, httpx_mock) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/content",
            json={
                "content": {
                    "type": "doc",
                    "content": [
                        {
                            "type": "heading",
                            "attrs": {"level": 1},
                            "content": [{"type": "text", "text": "Hello"}],
                        },
                        {"type": "paragraph", "content": [{"type": "text", "text": "World"}]},
                    ],
                }
            },
        )
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/info",
            json={"id": "page-1", "title": "Hello", "spaceId": "s1"},
        )
        result = runner.invoke(app, ["--config", str(tmp_config), "page", "get", "page-1"])
        assert result.exit_code == 0
        assert "# Hello" in result.output
        assert "World" in result.output

    def test_get_raw(self, tmp_config, httpx_mock) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/info",
            json={"id": "page-1", "title": "Hello", "spaceId": "s1"},
        )
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/content",
            json={"content": {"type": "doc", "content": []}},
        )
        result = runner.invoke(app, ["--config", str(tmp_config), "page", "get", "page-1", "--raw"])
        assert result.exit_code == 0
        assert '"type"' in result.output

    def test_get_meta(self, tmp_config, httpx_mock) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/content",
            json={
                "content": {
                    "type": "doc",
                    "content": [
                        {"type": "paragraph", "content": [{"type": "text", "text": "Content"}]},
                    ],
                }
            },
        )
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/info",
            json={
                "id": "page-1",
                "title": "Test",
                "spaceId": "s1",
                "createdAt": "2026-01-01",
                "updatedAt": "2026-03-20",
            },
        )
        result = runner.invoke(
            app, ["--config", str(tmp_config), "page", "get", "page-1", "--meta"]
        )
        assert result.exit_code == 0
        assert "---" in result.output
        assert "id: page-1" in result.output
        assert "Content" in result.output

    def test_get_with_emoji_content(self, tmp_config, httpx_mock) -> None:
        """Emoji in page content should not crash (Windows cp1252 fix)."""
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/content",
            json={
                "content": {
                    "type": "doc",
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [
                                {"type": "text", "text": "Status: "},
                                {"type": "text", "text": "\u2705 Done"},
                            ],
                        },
                    ],
                }
            },
        )
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/info",
            json={"id": "page-emoji", "title": "Test", "spaceId": "s1"},
        )
        result = runner.invoke(app, ["--config", str(tmp_config), "page", "get", "page-emoji"])
        assert result.exit_code == 0
        assert "Status:" in result.output
        assert "Done" in result.output


class TestPageDuplicate:
    def test_duplicate(self, tmp_config, httpx_mock) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/info",
            json={"id": "page-1", "title": "Original"},
        )
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/duplicate",
            json={"id": "page-dup"},
        )
        result = runner.invoke(app, ["--config", str(tmp_config), "page", "duplicate", "page-1"])
        assert result.exit_code == 0
        assert "page-dup" in result.output


class TestPageCopy:
    def test_copy(self, tmp_config, httpx_mock) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/info",
            json={"id": "page-1", "title": "Source Page"},
        )
        httpx_mock.add_response(
            url="https://docs.example.com/api/spaces",
            json={"data": {"items": [{"id": "space-2", "slug": "target", "name": "Target"}]}},
        )
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/copy",
            json={"id": "page-copy"},
        )
        result = runner.invoke(
            app, ["--config", str(tmp_config), "page", "copy", "page-1", "--space", "target"]
        )
        assert result.exit_code == 0
        assert "page-copy" in result.output


class TestPageChildren:
    def test_children_json(self, tmp_config, httpx_mock) -> None:
        # page children resolves space_id from page info first
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/info",
            json={"data": {"id": "parent-1", "spaceId": "s1"}},
        )
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/sidebar-pages",
            json={
                "data": {
                    "items": [
                        {"id": "child-1", "title": "Child One", "updatedAt": "2026-03-20"},
                    ]
                }
            },
        )
        result = runner.invoke(
            app, ["--config", str(tmp_config), "page", "children", "parent-1", "--json"]
        )
        assert result.exit_code == 0
        assert "Child One" in result.output


class TestPageHistory:
    def test_history_json(self, tmp_config, httpx_mock) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/history",
            json={
                "data": {
                    "items": [
                        {"id": "v1", "creatorId": "user-1", "createdAt": "2026-03-20"},
                    ]
                }
            },
        )
        result = runner.invoke(
            app, ["--config", str(tmp_config), "page", "history", "page-1", "--json"]
        )
        assert result.exit_code == 0
        assert "v1" in result.output


class TestPageExport:
    @staticmethod
    def _make_zip(content: str) -> bytes:
        """Create a ZIP file in memory containing a single markdown file."""
        import io
        import zipfile

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("export.md", content)
        return buf.getvalue()

    def test_export_stdout(self, tmp_config, httpx_mock) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/export",
            content=self._make_zip("# Exported Content\n\nHello world"),
        )
        result = runner.invoke(app, ["--config", str(tmp_config), "page", "export", "page-1"])
        assert result.exit_code == 0
        assert "Exported Content" in result.output

    def test_export_to_file(self, tmp_config, tmp_path, httpx_mock) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/export",
            content=self._make_zip("# File Content"),
        )
        output_file = tmp_path / "export.md"
        result = runner.invoke(
            app,
            ["--config", str(tmp_config), "page", "export", "page-1", "--output", str(output_file)],
        )
        assert result.exit_code == 0
        assert output_file.exists()
        assert "File Content" in output_file.read_text()


class TestPageImport:
    def test_import_with_title(self, tmp_config, tmp_path, httpx_mock) -> None:
        md_file = tmp_path / "doc.md"
        md_file.write_text("# Auto Title\n\nSome content")

        httpx_mock.add_response(
            url="https://docs.example.com/api/spaces",
            json={"data": {"items": [{"id": "s1", "slug": "eng", "name": "Eng"}]}},
        )
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/import",
            json={"id": "imported-page"},
        )
        result = runner.invoke(
            app,
            [
                "--config",
                str(tmp_config),
                "page",
                "import",
                "eng",
                "--file",
                str(md_file),
                "--title",
                "Custom Title",
            ],
        )
        assert result.exit_code == 0
        assert "imported-page" in result.output

    def test_import_auto_title_from_h1(self, tmp_config, tmp_path, httpx_mock) -> None:
        md_file = tmp_path / "doc.md"
        md_file.write_text("# My Page Title\n\nContent here")

        httpx_mock.add_response(
            url="https://docs.example.com/api/spaces",
            json={"data": {"items": [{"id": "s1", "slug": "eng", "name": "Eng"}]}},
        )
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/import",
            json={"id": "imported-page"},
        )
        result = runner.invoke(
            app,
            ["--config", str(tmp_config), "page", "import", "eng", "--file", str(md_file)],
        )
        assert result.exit_code == 0
        assert "imported-page" in result.output


class TestPageListTree:
    def test_tree(self, tmp_config, httpx_mock) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/spaces",
            json={"data": {"items": [{"id": "s1", "slug": "eng", "name": "Eng"}]}},
        )
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/sidebar-pages",
            json={
                "data": {
                    "items": [
                        {
                            "id": "p1",
                            "title": "Root Page",
                            "children": [
                                {"id": "p2", "title": "Child Page", "children": []},
                            ],
                        },
                    ]
                }
            },
        )
        result = runner.invoke(app, ["--config", str(tmp_config), "page", "list", "eng", "--tree"])
        assert result.exit_code == 0
        assert "Root Page" in result.output
        assert "Child Page" in result.output

    @staticmethod
    def _mock_tree(httpx_mock) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/spaces",
            json={"data": {"items": [{"id": "s1", "slug": "eng", "name": "Eng"}]}},
        )
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/sidebar-pages",
            json={
                "data": {
                    "items": [
                        {
                            "id": "p1",
                            "title": "Root Page",
                            "position": "a1AAA",
                            "children": [
                                {
                                    "id": "p2",
                                    "title": "Child Page",
                                    "position": "a2AAA",
                                    "children": [],
                                },
                            ],
                        },
                    ]
                }
            },
        )

    def test_tree_json_fields_projects_and_keeps_children(self, tmp_config, httpx_mock) -> None:
        self._mock_tree(httpx_mock)
        result = runner.invoke(
            app,
            [
                "--config",
                str(tmp_config),
                "page",
                "list",
                "eng",
                "--tree",
                "--json",
                "--fields",
                "id,title",
            ],
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert list(payload[0]) == ["id", "title", "children"]
        assert "position" not in payload[0]
        # The projection recurses.
        assert list(payload[0]["children"][0]) == ["id", "title", "children"]
        assert payload[0]["children"][0]["title"] == "Child Page"

    def test_tree_fields_without_json_exits_2(self, tmp_config, httpx_mock) -> None:
        result = runner.invoke(
            app,
            ["--config", str(tmp_config), "page", "list", "eng", "--tree", "--fields", "id"],
        )
        assert result.exit_code == 2

    def test_tree_rejects_page_size(self, tmp_config, httpx_mock) -> None:
        """The guard's message named --page-size but never checked it before 0.6.0."""
        result = runner.invoke(
            app,
            ["--config", str(tmp_config), "page", "list", "eng", "--tree", "--page-size", "5"],
        )
        assert result.exit_code == 2


class TestPageCreateTitleWins:
    """The import endpoint derives the title from the Markdown's first heading.

    An explicit --title must survive that, or the CLI reports one title and the
    page persists another.
    """

    @staticmethod
    def _mock_create(httpx_mock, page_id: str = "page-new") -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/spaces",
            json={"data": {"items": [{"id": "space-1", "slug": "eng", "name": "Eng"}]}},
        )
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/import",
            json={"id": page_id},
        )
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/update",
            json={"data": {"id": page_id, "title": "ignored"}},
        )

    @staticmethod
    def _create(tmp_config, *args: str):
        return runner.invoke(app, ["--config", str(tmp_config), "page", "create", "eng", *args])

    def test_explicit_title_beats_the_markdown_h1(self, tmp_config, httpx_mock) -> None:
        self._mock_create(httpx_mock)
        result = self._create(
            tmp_config, "--title", "Explicit CLI title", "--content", "# Markdown heading\n\nBody."
        )
        assert result.exit_code == 0

        update = httpx_mock.get_requests()[-1]
        assert str(update.url).endswith("/api/pages/update")
        assert json.loads(update.read())["title"] == "Explicit CLI title"

    def test_markdown_body_keeps_its_heading(self, tmp_config, httpx_mock) -> None:
        """Only the title metadata is overridden; the body is the user's."""
        self._mock_create(httpx_mock)
        self._create(
            tmp_config, "--title", "Explicit CLI title", "--content", "# Markdown heading\n\nBody."
        )
        imported = httpx_mock.get_requests()[1].read()
        assert b"# Markdown heading" in imported

    def test_title_applied_without_an_h1_too(self, tmp_config, httpx_mock) -> None:
        self._mock_create(httpx_mock)
        self._create(tmp_config, "--title", "Explicit CLI title", "--content", "Body with no head.")
        update = httpx_mock.get_requests()[-1]
        assert json.loads(update.read())["title"] == "Explicit CLI title"

    def test_message_reports_the_persisted_title(self, tmp_config, httpx_mock) -> None:
        self._mock_create(httpx_mock)
        result = self._create(
            tmp_config, "--title", "Explicit CLI title", "--content", "# Markdown heading"
        )
        assert "Explicit CLI title" in result.output
        assert "Markdown heading" not in result.output

    def test_icon_rides_along_in_one_request(self, tmp_config, httpx_mock) -> None:
        """Title and icon share the metadata call rather than costing two."""
        self._mock_create(httpx_mock)
        self._create(tmp_config, "--title", "T", "--content", "# H", "--icon", "🚀")

        updates = [r for r in httpx_mock.get_requests() if str(r.url).endswith("/pages/update")]
        assert len(updates) == 1
        body = json.loads(updates[0].read())
        assert body["title"] == "T"
        assert body["icon"] == "🚀"

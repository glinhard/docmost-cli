"""Tests for Page API methods."""

import json

import pytest

from docmost_cli.api.client import DocmostClient
from docmost_cli.api.pages import (
    copy_page,
    create_page_via_import,
    delete_page,
    duplicate_page,
    export_page,
    get_all_page_children,
    get_page_children,
    get_page_content,
    get_page_history,
    get_page_info,
    get_sidebar_pages,
    list_recent_pages,
    move_page,
    resolve_position,
    try_update_page_content,
    update_page_content,
    update_page_meta,
)
from docmost_cli.api.position import is_valid_position


class TestGetPageInfo:
    def test_returns_info(self, httpx_mock, api_key_settings) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/info",
            json={"id": "page-1", "title": "Test Page", "spaceId": "s1"},
        )
        with DocmostClient(api_key_settings) as client:
            result = get_page_info(client, "page-1")
        assert result["title"] == "Test Page"

    def test_not_found(self, httpx_mock, api_key_settings) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/info",
            status_code=404,
        )
        with DocmostClient(api_key_settings) as client, pytest.raises(SystemExit) as exc:
            get_page_info(client, "nonexistent")
        assert exc.value.code == 4


class TestCreatePageViaImport:
    def test_sends_multipart(self, httpx_mock, api_key_settings) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/import",
            json={"id": "new-page"},
        )
        with DocmostClient(api_key_settings) as client:
            result = create_page_via_import(
                client,
                space_id="space-1",
                title="New Page",
                content="Hello world",
            )
        assert result["id"] == "new-page"

        # Verify the request was sent
        request = httpx_mock.get_requests()[0]
        assert request.method == "POST"

    def test_empty_content(self, httpx_mock, api_key_settings) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/import",
            json={"id": "empty-page"},
        )
        with DocmostClient(api_key_settings) as client:
            result = create_page_via_import(
                client,
                space_id="space-1",
                title="Empty Page",
                content="",
            )
        assert result["id"] == "empty-page"

    def test_with_parent(self, httpx_mock, api_key_settings) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/import",
            json={"id": "child-page"},
        )
        with DocmostClient(api_key_settings) as client:
            result = create_page_via_import(
                client,
                space_id="space-1",
                title="Child",
                content="Content",
                parent_page_id="parent-1",
            )
        assert result["id"] == "child-page"


class TestUpdatePageMeta:
    def test_update_title(self, httpx_mock, api_key_settings) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/update",
            json={"id": "page-1", "title": "New Title"},
        )
        with DocmostClient(api_key_settings) as client:
            result = update_page_meta(client, page_id="page-1", title="New Title")
        assert result["title"] == "New Title"


class TestUpdatePageContent:
    def test_posts_to_pages_update(self, httpx_mock, api_key_settings) -> None:
        """Content goes through /pages/update; the server does the Yjs write."""
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/update",
            json={"data": {"id": "page-1", "content": "# Updated\n\nNew content"}},
        )
        with DocmostClient(api_key_settings) as client:
            update_page_content(client, page_id="page-1", content="# Updated\n\nNew content")
        body = json.loads(httpx_mock.get_requests()[0].read())
        assert body == {
            "pageId": "page-1",
            "content": "# Updated\n\nNew content",
            "format": "markdown",
            "operation": "replace",
        }

    @pytest.mark.parametrize("operation", ["append", "prepend"])
    def test_operation_is_sent(self, httpx_mock, api_key_settings, operation) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/update",
            json={"data": {"id": "page-1", "content": "# Updated"}},
        )
        with DocmostClient(api_key_settings) as client:
            update_page_content(client, page_id="page-1", content="# Updated", operation=operation)
        body = json.loads(httpx_mock.get_requests()[0].read())
        assert body["operation"] == operation

    def test_prosemirror_object_response_fails_loudly(
        self, httpx_mock, api_key_settings, capsys
    ) -> None:
        """A server that stripped `format` returns ProseMirror JSON, not Markdown."""
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/update",
            json={"data": {"id": "page-1", "content": {"type": "doc", "content": []}}},
        )
        with DocmostClient(api_key_settings) as client, pytest.raises(SystemExit) as exc:
            update_page_content(client, page_id="page-1", content="# New")
        assert exc.value.code == 1
        err = capsys.readouterr().err
        assert "did not apply the content" in err
        assert "v0.71" in err

    def test_absent_content_triggers_verification_read(self, httpx_mock, api_key_settings) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/update",
            json={"data": {"id": "page-1"}},
        )
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/info",
            json={"data": {"id": "page-1", "content": "# New\n\nbody"}},
        )
        with DocmostClient(api_key_settings) as client:
            update_page_content(client, page_id="page-1", content="# New\n\nbody")
        assert len(httpx_mock.get_requests()) == 2

    def test_absent_content_and_failed_verification_errors(
        self, httpx_mock, api_key_settings
    ) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/update",
            json={"data": {"id": "page-1"}},
        )
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/info",
            json={"data": {"id": "page-1", "content": "# Something else"}},
        )
        with DocmostClient(api_key_settings) as client, pytest.raises(SystemExit) as exc:
            update_page_content(client, page_id="page-1", content="# New")
        assert exc.value.code == 1

    def test_empty_content_needs_no_verification(self, httpx_mock, api_key_settings) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/update",
            json={"data": {"id": "page-1"}},
        )
        with DocmostClient(api_key_settings) as client:
            update_page_content(client, page_id="page-1", content="")
        assert len(httpx_mock.get_requests()) == 1


class TestTryUpdatePageContent:
    def test_true_on_string_content(self, httpx_mock, api_key_settings) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/update",
            json={"data": {"id": "page-1", "content": "# Updated"}},
        )
        with DocmostClient(api_key_settings) as client:
            assert try_update_page_content(client, page_id="page-1", content="# Updated") is True

    def test_false_on_stripped_content(self, httpx_mock, api_key_settings) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/update",
            json={"data": {"id": "page-1", "content": {"type": "doc"}}},
        )
        with DocmostClient(api_key_settings) as client:
            assert try_update_page_content(client, page_id="page-1", content="# Updated") is False

    def test_false_on_http_error(self, httpx_mock, api_key_settings) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/update",
            status_code=400,
        )
        with DocmostClient(api_key_settings) as client:
            assert try_update_page_content(client, page_id="page-1", content="x") is False


class TestDeletePage:
    def test_deletes(self, httpx_mock, api_key_settings) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/delete",
            json={"id": "page-1"},
        )
        with DocmostClient(api_key_settings) as client:
            result = delete_page(client, "page-1")
        assert result["id"] == "page-1"


class TestMovePage:
    def test_move_to_parent(self, httpx_mock, api_key_settings) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/move",
            json={"id": "page-1"},
        )
        with DocmostClient(api_key_settings) as client:
            result = move_page(
                client, page_id="page-1", position="a0V8f", parent_page_id="parent-1"
            )
        assert result["id"] == "page-1"

    def test_move_to_space(self, httpx_mock, api_key_settings) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/move",
            json={"id": "page-1"},
        )
        with DocmostClient(api_key_settings) as client:
            result = move_page(client, page_id="page-1", position="a0V8f", space_id="space-2")
        assert result["id"] == "page-1"

    def test_always_sends_position(self, httpx_mock, api_key_settings) -> None:
        """Docmost's MovePageDto requires `position`; omitting it is an HTTP 400."""
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/move",
            json={"id": "page-1"},
        )
        with DocmostClient(api_key_settings) as client:
            move_page(client, page_id="page-1", position="a0V8f", parent_page_id="parent-1")
        body = json.loads(httpx_mock.get_requests()[0].read())
        assert body["position"] == "a0V8f"


class TestResolvePosition:
    @staticmethod
    def _siblings(httpx_mock, items) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/sidebar-pages",
            json={"data": {"items": items, "meta": {"hasNextPage": False}}},
        )

    def test_first_sorts_before_existing_siblings(self, httpx_mock, api_key_settings) -> None:
        self._siblings(httpx_mock, [{"id": "c1", "position": "a1"}, {"id": "c2", "position": "a2"}])
        with DocmostClient(api_key_settings) as client:
            position = resolve_position(
                client, page_id="page-1", space_id="s1", parent_page_id="parent-1"
            )
        assert position < "a1"
        assert is_valid_position(position)

    def test_last_sorts_after_existing_siblings(self, httpx_mock, api_key_settings) -> None:
        self._siblings(httpx_mock, [{"id": "c1", "position": "a1"}, {"id": "c2", "position": "a2"}])
        with DocmostClient(api_key_settings) as client:
            position = resolve_position(
                client,
                page_id="page-1",
                space_id="s1",
                parent_page_id="parent-1",
                placement="last",
            )
        assert position > "a2"
        assert is_valid_position(position)

    def test_excludes_the_page_being_moved(self, httpx_mock, api_key_settings) -> None:
        self._siblings(
            httpx_mock,
            [{"id": "page-1", "position": "a0AAA"}, {"id": "c2", "position": "a5AAA"}],
        )
        with DocmostClient(api_key_settings) as client:
            position = resolve_position(
                client,
                page_id="page-1",
                space_id="s1",
                parent_page_id="parent-1",
                placement="last",
            )
        # "a5AAA" is the max once the moved page itself is ignored.
        assert position > "a5AAA"

    def test_empty_parent_returns_valid_key(self, httpx_mock, api_key_settings) -> None:
        self._siblings(httpx_mock, [])
        with DocmostClient(api_key_settings) as client:
            position = resolve_position(
                client, page_id="page-1", space_id="s1", parent_page_id="parent-1"
            )
        assert is_valid_position(position)

    def test_siblings_without_positions_warn(self, httpx_mock, api_key_settings, capsys) -> None:
        self._siblings(httpx_mock, [{"id": "c1"}, {"id": "c2"}])
        with DocmostClient(api_key_settings) as client:
            position = resolve_position(
                client, page_id="page-1", space_id="s1", parent_page_id="parent-1"
            )
        assert is_valid_position(position)
        assert "ordering keys" in capsys.readouterr().err

    def test_root_placement_uses_space_sidebar(self, httpx_mock, api_key_settings) -> None:
        self._siblings(httpx_mock, [{"id": "r1", "position": "a1"}])
        with DocmostClient(api_key_settings) as client:
            position = resolve_position(client, page_id="page-1", space_id="s1")
        body = json.loads(httpx_mock.get_requests()[0].read())
        assert body["spaceId"] == "s1"
        assert "pageId" not in body
        assert position < "a1"


class TestGetPageContent:
    def test_enterprise_content_endpoint(self, httpx_mock, api_key_settings) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/content",
            json={"content": {"type": "doc", "content": []}},
        )
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/info",
            json={"id": "page-1", "title": "Test", "spaceId": "s1"},
        )
        with DocmostClient(api_key_settings) as client:
            result = get_page_content(client, "page-1")
        assert result["id"] == "page-1"
        assert "content" in result

    def test_fallback_to_info(self, httpx_mock, api_key_settings) -> None:
        # Content endpoint returns 404 (Community edition)
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/content",
            status_code=404,
        )
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/info",
            json={"id": "page-1", "title": "Test", "content": {"type": "doc", "content": []}},
        )
        with DocmostClient(api_key_settings) as client:
            result = get_page_content(client, "page-1")
        assert result["id"] == "page-1"


class TestListRecentPages:
    def test_list_pages(self, httpx_mock, api_key_settings) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/recent",
            json={
                "data": {
                    "items": [
                        {"id": "p1", "title": "Page 1", "updatedAt": "2026-03-20"},
                    ]
                }
            },
        )
        with DocmostClient(api_key_settings) as client:
            result = list_recent_pages(client, "space-1")
        assert result["data"]["items"][0]["title"] == "Page 1"


class TestDuplicatePage:
    def test_duplicate(self, httpx_mock, api_key_settings) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/duplicate",
            json={"id": "dup-page"},
        )
        with DocmostClient(api_key_settings) as client:
            result = duplicate_page(client, "page-1")
        assert result["id"] == "dup-page"


class TestCopyPage:
    def test_copy(self, httpx_mock, api_key_settings) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/copy",
            json={"id": "copy-page"},
        )
        with DocmostClient(api_key_settings) as client:
            result = copy_page(client, "page-1", "space-2")
        assert result["id"] == "copy-page"


class TestGetPageChildren:
    def test_children_with_space_id(self, httpx_mock, api_key_settings) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/sidebar-pages",
            json={"data": {"items": [{"id": "c1", "title": "Child"}]}},
        )
        with DocmostClient(api_key_settings) as client:
            result = get_page_children(client, "parent-1", space_id="s1")
        assert result["data"]["items"][0]["id"] == "c1"

    def test_children_resolves_space_id(self, httpx_mock, api_key_settings) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/info",
            json={"data": {"id": "parent-1", "spaceId": "s1"}},
        )
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/sidebar-pages",
            json={"data": {"items": [{"id": "c1", "title": "Child"}]}},
        )
        with DocmostClient(api_key_settings) as client:
            result = get_page_children(client, "parent-1")
        assert result["data"]["items"][0]["id"] == "c1"

    def test_sends_pagination_params(self, httpx_mock, api_key_settings) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/sidebar-pages",
            json={"data": {"items": []}},
        )
        with DocmostClient(api_key_settings) as client:
            get_page_children(client, "parent-1", space_id="s1", limit=100, cursor="c2")
        body = json.loads(httpx_mock.get_requests()[0].read())
        assert body == {"spaceId": "s1", "pageId": "parent-1", "limit": 100, "cursor": "c2"}


class TestGetAllPageChildren:
    def test_follows_cursor_past_server_default(self, httpx_mock, api_key_settings) -> None:
        """The server's default page size is 20; every child must still come back."""
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/sidebar-pages",
            json={
                "data": {
                    "items": [{"id": f"c{n}"} for n in range(20)],
                    "meta": {"hasNextPage": True, "nextCursor": "c2"},
                }
            },
        )
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/sidebar-pages",
            json={
                "data": {
                    "items": [{"id": f"d{n}"} for n in range(20)],
                    "meta": {"hasNextPage": False, "nextCursor": None},
                }
            },
        )
        with DocmostClient(api_key_settings) as client:
            children = get_all_page_children(client, "parent-1", space_id="s1")
        assert len(children) == 40
        second = json.loads(httpx_mock.get_requests()[1].read())
        assert second["cursor"] == "c2"


class TestGetPageHistory:
    def test_history(self, httpx_mock, api_key_settings) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/history",
            json={"data": {"items": [{"id": "v1", "createdAt": "2026-03-20"}]}},
        )
        with DocmostClient(api_key_settings) as client:
            result = get_page_history(client, "page-1")
        assert result["data"]["items"][0]["id"] == "v1"


class TestExportPage:
    def test_export(self, httpx_mock, api_key_settings) -> None:
        import io
        import zipfile

        # export_page() expects a ZIP response containing the exported content
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zf:
            zf.writestr("export.md", "# Exported")
        zip_bytes = zip_buffer.getvalue()

        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/export",
            content=zip_bytes,
        )
        with DocmostClient(api_key_settings) as client:
            result = export_page(client, "page-1", fmt="md")
        assert result == "# Exported"


class TestGetSidebarPages:
    def test_sidebar(self, httpx_mock, api_key_settings) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/sidebar-pages",
            json={"data": {"items": [{"id": "p1", "title": "Root", "children": []}]}},
        )
        with DocmostClient(api_key_settings) as client:
            result = get_sidebar_pages(client, "space-1")
        assert result["data"]["items"][0]["title"] == "Root"

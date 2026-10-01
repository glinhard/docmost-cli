"""Tests for Attachment API methods."""

import json

import pytest

from docmost_cli.api.attachments import (
    build_attachment_url,
    find_unreferenced,
    list_page_attachments,
    search_attachments,
    upload_attachment,
)
from docmost_cli.api.client import DocmostClient

UPLOAD_URL = "https://docs.example.com/api/files/upload"
RECORD = {"id": "att-new", "fileName": "diagram.png", "type": "image/png"}


class TestSearchAttachments:
    def test_community_explains_the_missing_feature(
        self, httpx_mock, api_key_settings, capsys
    ) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/search-attachments",
            status_code=404,
            json={"message": "Cannot POST /api/search-attachments", "statusCode": 404},
        )
        with DocmostClient(api_key_settings) as client, pytest.raises(SystemExit) as exc:
            search_attachments(client, "diagram")
        assert exc.value.code == 4
        err = capsys.readouterr().err
        assert "Enterprise" in err
        assert "attachment list" in err

    def test_returns_results(self, httpx_mock, api_key_settings) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/search-attachments",
            json={
                "data": {
                    "items": [
                        {"id": "att-1", "fileName": "diagram.png", "type": "image/png"},
                        {"id": "att-2", "fileName": "report.pdf", "type": "application/pdf"},
                    ]
                }
            },
        )
        with DocmostClient(api_key_settings) as client:
            result = search_attachments(client, "diagram")
        items = result["data"]["items"]
        assert len(items) == 2
        assert items[0]["fileName"] == "diagram.png"

    def test_with_space_id_filter(self, httpx_mock, api_key_settings) -> None:
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
        with DocmostClient(api_key_settings) as client:
            result = search_attachments(client, "logo", space_id="space-abc")
        request = httpx_mock.get_requests()[0]
        body = request.read()
        assert b"spaceId" in body
        assert b"space-abc" in body
        items = result["data"]["items"]
        assert len(items) == 1
        assert items[0]["id"] == "att-3"


class TestListPageAttachments:
    URL = "https://docs.example.com/api/pages/attachments"

    def test_sends_page_id_and_filter(self, httpx_mock, api_key_settings) -> None:
        httpx_mock.add_response(url=self.URL, json={"data": {"items": [RECORD]}})
        with DocmostClient(api_key_settings) as client:
            result = list_page_attachments(client, "page-1", query="diag", limit=50)
        assert result["data"]["items"] == [RECORD]
        body = json.loads(httpx_mock.get_requests()[0].read())
        assert body == {"pageId": "page-1", "query": "diag", "limit": 50}

    def test_old_server_says_which_version(self, httpx_mock, api_key_settings, capsys) -> None:
        """A server without the route gets a version hint, not "check the ID"."""
        httpx_mock.add_response(
            url=self.URL,
            status_code=404,
            json={
                "message": "Cannot POST /api/pages/attachments",
                "error": "Not Found",
                "statusCode": 404,
            },
        )
        with DocmostClient(api_key_settings) as client, pytest.raises(SystemExit) as exc:
            list_page_attachments(client, "page-1")
        assert exc.value.code == 4
        err = capsys.readouterr().err
        assert "no POST /api/pages/attachments endpoint" in err
        assert "v0.96" in err

    def test_unknown_page_keeps_the_record_message(
        self, httpx_mock, api_key_settings, capsys
    ) -> None:
        httpx_mock.add_response(
            url=self.URL,
            status_code=404,
            json={"message": "Page not found", "error": "Not Found", "statusCode": 404},
        )
        with DocmostClient(api_key_settings) as client, pytest.raises(SystemExit):
            list_page_attachments(client, "nope")
        assert "Check the ID" in capsys.readouterr().err


class TestFindUnreferenced:
    OLD = {"id": "019a-old", "fileName": "shot.png"}
    NEW = {"id": "019a-new", "fileName": "shot.png"}

    def test_prosemirror_json(self) -> None:
        content = {
            "type": "doc",
            "content": [
                {
                    "type": "image",
                    "attrs": {"src": "/api/files/019a-new/shot.png", "attachmentId": "019a-new"},
                }
            ],
        }
        assert find_unreferenced([self.OLD, self.NEW], content) == [self.OLD]

    def test_markdown_string(self) -> None:
        content = "![shot](/api/files/019a-new/shot.png)"
        assert find_unreferenced([self.OLD, self.NEW], content) == [self.OLD]

    def test_empty_page_references_nothing(self) -> None:
        assert find_unreferenced([self.OLD], None) == [self.OLD]


class TestUploadAttachment:
    def test_uploads_file(self, httpx_mock, api_key_settings) -> None:
        httpx_mock.add_response(url=UPLOAD_URL, json=RECORD)
        with DocmostClient(api_key_settings) as client:
            result = upload_attachment(
                client,
                page_id="page-1",
                file_name="diagram.png",
                file_bytes=b"fake-bytes",
                mime_type="image/png",
            )
        assert result["id"] == "att-new"
        assert result["fileName"] == "diagram.png"

        body = httpx_mock.get_requests()[0].read()
        assert b"diagram.png" in body
        assert b"page-1" in body
        assert b"image/png" in body
        assert b"fake-bytes" in body

    def test_sends_multipart(self, httpx_mock, api_key_settings) -> None:
        """The endpoint takes a form upload, not a JSON body."""
        httpx_mock.add_response(url=UPLOAD_URL, json=RECORD)
        with DocmostClient(api_key_settings) as client:
            upload_attachment(client, page_id="page-1", file_name="diagram.png", file_bytes=b"x")
        request = httpx_mock.get_requests()[0]
        assert request.headers["content-type"].startswith("multipart/form-data")

    def test_defaults_mime_type(self, httpx_mock, api_key_settings) -> None:
        httpx_mock.add_response(url=UPLOAD_URL, json={"id": "att-new", "fileName": "notes.txt"})
        with DocmostClient(api_key_settings) as client:
            upload_attachment(
                client, page_id="page-1", file_name="notes.txt", file_bytes=b"fake-bytes"
            )
        assert b"application/octet-stream" in httpx_mock.get_requests()[0].read()


class TestBuildAttachmentUrl:
    def test_builds_url_from_bare_record(self) -> None:
        assert build_attachment_url(RECORD) == "/api/files/att-new/diagram.png"

    def test_builds_url_from_envelope(self) -> None:
        """Every other Docmost endpoint wraps its payload; this one is undocumented,
        so accept both rather than betting on one."""
        assert build_attachment_url({"data": RECORD}) == "/api/files/att-new/diagram.png"

    def test_escapes_the_file_name(self) -> None:
        url = build_attachment_url({"id": "att-1", "fileName": "my report (v2).png"})
        assert url == "/api/files/att-1/my%20report%20%28v2%29.png"

    def test_escapes_a_slash_in_the_file_name(self) -> None:
        """A slash must not be able to reshape the path."""
        url = build_attachment_url({"id": "att-1", "fileName": "a/b.png"})
        assert url == "/api/files/att-1/a%2Fb.png"

    @pytest.mark.parametrize(
        "response",
        [{}, {"id": "att-1"}, {"fileName": "x.png"}, {"id": 7, "fileName": "x.png"}],
        ids=["empty", "no-file-name", "no-id", "non-string-id"],
    )
    def test_unusable_response_exits_cleanly(self, response, capsys) -> None:
        """A missing field is a clear error, not a KeyError traceback."""
        with pytest.raises(SystemExit) as exc:
            build_attachment_url(response)
        assert exc.value.code == 1
        assert "no file reference" in capsys.readouterr().err

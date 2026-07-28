"""Tests for Attachment API methods."""

import pytest

from docmost_cli.api.attachments import (
    build_attachment_url,
    search_attachments,
    upload_attachment,
)
from docmost_cli.api.client import DocmostClient

UPLOAD_URL = "https://docs.example.com/api/files/upload"
RECORD = {"id": "att-new", "fileName": "diagram.png", "type": "image/png"}


class TestSearchAttachments:
    def test_returns_results(self, httpx_mock, api_key_settings) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/attachments/search",
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
            url="https://docs.example.com/api/attachments/search",
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

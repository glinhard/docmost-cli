"""Tests for Attachment API methods."""

from docmost_cli.api.attachments import build_attachment_url, search_attachments, upload_attachment
from docmost_cli.api.client import DocmostClient


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
        httpx_mock.add_response(
            url="https://docs.example.com/api/files/upload",
            json={"id": "att-new", "fileName": "diagram.png", "type": "image/png"},
        )
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

        request = httpx_mock.get_requests()[0]
        body = request.read()
        assert b"diagram.png" in body
        assert b"page-1" in body
        assert b"image/png" in body

    def test_defaults_mime_type(self, httpx_mock, api_key_settings) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/files/upload",
            json={"id": "att-new", "fileName": "notes.txt", "type": "text/plain"},
        )
        with DocmostClient(api_key_settings) as client:
            upload_attachment(
                client,
                page_id="page-1",
                file_name="notes.txt",
                file_bytes=b"fake-bytes",
            )
        request = httpx_mock.get_requests()[0]
        body = request.read()
        assert b"application/octet-stream" in body


class TestBuildAttachmentUrl:
    def test_builds_url(self) -> None:
        url = build_attachment_url({"id": "att-new", "fileName": "diagram.png"})
        assert url == "/api/files/att-new/diagram.png"

"""Attachment API methods."""

from typing import Any

from docmost_cli.api.client import DocmostClient
from docmost_cli.api.pagination import build_body

__all__ = [
    "build_attachment_url",
    "search_attachments",
    "upload_attachment",
]


def search_attachments(
    client: DocmostClient,
    query: str,
    *,
    space_id: str | None = None,
) -> dict[str, Any]:
    """Search attachments by query string.

    Args:
        client: Authenticated Docmost client.
        query: Search query string.
        space_id: Optional space UUID to scope the search.

    Returns:
        Raw API response dict with matching attachments.
    """
    body = build_body({"query": query}, spaceId=space_id)
    return client.post("/attachments/search", json=body)


def upload_attachment(
    client: DocmostClient,
    *,
    page_id: str,
    file_name: str,
    file_bytes: bytes,
    mime_type: str | None = None,
) -> dict[str, Any]:
    """Upload a file (e.g. an image) and attach it to a page.

    Sends the file via multipart upload to Docmost's file storage endpoint.
    The endpoint is not part of the documented REST API but is what the
    Docmost web editor itself uses for inline images and file attachments.

    Args:
        client: Authenticated Docmost client.
        page_id: UUID of the page to attach the file to.
        file_name: Original filename (sent to the server, echoed back in the
            response and used to build the file's URL).
        file_bytes: Raw file content.
        mime_type: MIME type to send with the upload. Defaults to
            "application/octet-stream" if not provided.

    Returns:
        Raw API response dict, e.g. {"id": ..., "fileName": ..., "type": ...}.
        Build the page-embeddable URL from it with `build_attachment_url`.
    """
    files = {"file": (file_name, file_bytes, mime_type or "application/octet-stream")}
    data = {"pageId": page_id}
    return client.post_multipart("/files/upload", data=data, files=files)


def build_attachment_url(attachment: dict[str, Any]) -> str:
    """Build the page-embeddable URL for an uploaded attachment.

    Docmost serves uploaded files at `/api/files/{attachmentId}/{fileName}`.
    Embed the result directly in Markdown, e.g. `![alt](<url>)`.

    Args:
        attachment: Response dict from `upload_attachment` (or any attachment
            record containing "id" and "fileName").

    Returns:
        A relative URL of the form "/api/files/{id}/{fileName}".
    """
    return f"/api/files/{attachment['id']}/{attachment['fileName']}"

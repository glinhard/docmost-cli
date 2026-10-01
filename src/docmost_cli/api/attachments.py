"""Attachment API methods."""

import json
from typing import Any
from urllib.parse import quote

from docmost_cli.api.client import DocmostClient
from docmost_cli.api.pagination import build_body, unwrap_data
from docmost_cli.output.formatter import print_error

__all__ = [
    "build_attachment_url",
    "find_unreferenced",
    "list_page_attachments",
    "search_attachments",
    "upload_attachment",
]


def list_page_attachments(
    client: DocmostClient,
    page_id: str,
    *,
    query: str | None = None,
    limit: int | None = None,
    cursor: str | None = None,
) -> dict[str, Any]:
    """List the files attached to a page (one page of results).

    Covers every file uploaded to the page, including ones its content no
    longer embeds. Available on Community and Enterprise alike, from Docmost
    v0.96.

    Args:
        client: Authenticated Docmost client.
        page_id: Page UUID.
        query: Optional case-insensitive filename filter.
        limit: Max results per request.
        cursor: Pagination cursor.

    Returns:
        Raw API response dict with the page's attachments.
    """
    body = build_body({"pageId": page_id}, query=query, limit=limit, cursor=cursor)
    return client.post(
        "/pages/attachments",
        json=body,
        missing_route_hint="Listing a page's attachments needs Docmost v0.96 or later.",
    )


def find_unreferenced(attachments: list[dict[str, Any]], content: Any) -> list[dict[str, Any]]:
    """Pick out the attachments a page's content does not reference.

    An upload stays attached to its page after the content stops embedding
    it, and Docmost has no endpoint to delete it, so these build up when a
    page's images are re-uploaded.

    Args:
        attachments: Attachment records carrying an "id".
        content: The page body, as ProseMirror JSON or a Markdown/HTML string.

    Returns:
        The attachments whose ID appears nowhere in the content.
    """
    # Every embed carries the ID: in the node's attachmentId attribute and in
    # its /api/files/<id>/... src. A substring test covers both, in any format.
    text = content if isinstance(content, str) else json.dumps(content)
    return [item for item in attachments if str(item.get("id", "")) not in text]


def search_attachments(
    client: DocmostClient,
    query: str,
    *,
    space_id: str | None = None,
    limit: int | None = None,
    cursor: str | None = None,
) -> dict[str, Any]:
    """Search attachments by filename and text content (one request).

    Needs Docmost Enterprise with attachment indexing; Community has no such
    route. The endpoint is not paginated, so ``cursor`` is accepted only to
    fit the shared list plumbing and the server ignores it.

    Args:
        client: Authenticated Docmost client.
        query: Search query string.
        space_id: Optional space UUID to scope the search.
        limit: Max results per request.
        cursor: Pagination cursor.

    Returns:
        Raw API response dict with matching attachments.
    """
    body = build_body({"query": query}, spaceId=space_id, limit=limit, cursor=cursor)
    return client.post(
        "/search-attachments",
        json=body,
        missing_route_hint=(
            "Attachment search needs Docmost Enterprise with attachment indexing. "
            "To see a page's files, use 'docmost-cli attachment list <page-id>'."
        ),
    )


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
        Raw API response dict carrying the attachment record. Build the
        page-embeddable URL from it with `build_attachment_url`.
    """
    files = {"file": (file_name, file_bytes, mime_type or "application/octet-stream")}
    data = {"pageId": page_id}
    return client.post_multipart("/files/upload", data=data, files=files)


def build_attachment_url(attachment: dict[str, Any]) -> str:
    """Build the page-embeddable URL for an uploaded attachment.

    Docmost serves uploaded files at `/api/files/{attachmentId}/{fileName}`.
    Embed the result directly in Markdown, e.g. `![alt](<url>)`.

    Args:
        attachment: Response dict from `upload_attachment`, either bare or
            inside Docmost's `{success, status, data}` envelope, or any
            attachment record carrying "id" and "fileName".

    Returns:
        A relative URL of the form "/api/files/{id}/{fileName}".
    """
    # Docmost Community returns this record bare, unlike every other endpoint,
    # which wraps its payload. The endpoint is undocumented, so that is not a
    # contract; unwrap_data costs nothing and keeps this working if it ever
    # moves under the standard interceptor.
    record = unwrap_data(attachment)
    attachment_id = record.get("id")
    file_name = record.get("fileName")
    if not isinstance(attachment_id, str) or not isinstance(file_name, str):
        print_error("Upload succeeded but the server returned no file reference.")
    # safe="" so a filename containing a slash cannot reshape the path.
    return f"/api/files/{quote(attachment_id, safe='')}/{quote(file_name, safe='')}"

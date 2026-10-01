"""Attachment subcommands."""

import mimetypes
from pathlib import Path

import typer

from docmost_cli.api.attachments import (
    build_attachment_url,
    find_unreferenced,
    list_page_attachments,
    search_attachments,
    upload_attachment,
)
from docmost_cli.api.pages import get_page_info
from docmost_cli.api.pagination import extract_id
from docmost_cli.api.spaces import resolve_space_id
from docmost_cli.cli._list_opts import (
    cursor_option,
    emit_list,
    envelope_option,
    fetch_list,
    fields_option,
    json_option,
    limit_option,
    no_follow_option,
    page_size_option,
)
from docmost_cli.cli.main import get_client
from docmost_cli.output.formatter import print_error, print_result

__all__ = ["attachment_app"]

attachment_app: typer.Typer = typer.Typer(name="attachment", help="Attachment operations.")


@attachment_app.command("list")
def attachment_list_cmd(
    page_id: str = typer.Argument(..., help="Page ID whose attachments to list"),
    query: str | None = typer.Option(None, "--query", help="Filter by filename substring"),
    unused: bool = typer.Option(
        False, "--unused", help="Only attachments the page's content no longer references"
    ),
    limit: int | None = limit_option(),
    page_size: int | None = page_size_option(),
    cursor: str | None = cursor_option(),
    no_follow: bool = no_follow_option(),
    json_mode: bool = json_option(),
    envelope: bool = envelope_option(),
    fields: str | None = fields_option(),
) -> None:
    """List the files attached to a page, including ones it no longer shows.

    Every upload creates a new attachment, and it stays on the page after the
    content stops embedding it. --unused picks those out. Docmost has no
    endpoint to delete a single attachment; they go only when the page itself
    is permanently deleted. Needs Docmost v0.96 or later.

    See also: docmost-cli attachment upload.
    """
    client = get_client()
    result = fetch_list(
        list_page_attachments,
        limit=limit,
        page_size=page_size,
        cursor=cursor,
        no_follow=no_follow,
        client=client,
        page_id=page_id,
        query=query,
    )
    if unused:
        # /pages/info returns the body on both editions; a page that was never
        # written has none, and then every attachment on it is unused.
        content = get_page_info(client, page_id, include_content=True).get("content")
        result.items = find_unreferenced(result.items, content)
    columns = ["id", "fileName", "fileSize", "createdAt"]
    emit_list(result, columns, json_mode=json_mode, envelope=envelope, fields=fields)


@attachment_app.command("search")
def attachment_search_cmd(
    query: str = typer.Argument(..., help="Search query string"),
    space: str | None = typer.Option(None, "--space", help="Space slug to scope search"),
    limit: int | None = limit_option(),
    page_size: int | None = page_size_option(),
    cursor: str | None = cursor_option(),
    no_follow: bool = no_follow_option(),
    json_mode: bool = json_option(),
    envelope: bool = envelope_option(),
    fields: str | None = fields_option(),
) -> None:
    """Search attachments by filename and content.

    Needs Docmost Enterprise with attachment indexing. On Community, use
    'attachment list <page-id> --query <text>' to filter a page's files.
    """
    client = get_client()
    space_id = None
    if space:
        space_id = resolve_space_id(client, space)
    result = fetch_list(
        search_attachments,
        limit=limit,
        page_size=page_size,
        cursor=cursor,
        no_follow=no_follow,
        client=client,
        query=query,
        space_id=space_id,
    )
    columns = ["id", "fileName", "type"]
    emit_list(result, columns, json_mode=json_mode, envelope=envelope, fields=fields)


@attachment_app.command("upload")
def attachment_upload_cmd(
    page_id: str = typer.Argument(..., help="Page ID to attach the file to"),
    file: Path = typer.Option(..., "--file", help="File to upload (e.g. an image)"),
) -> None:
    """Upload a file (e.g. an image) and attach it to a page.

    Prints the new attachment ID to stdout. To embed the file in the page's
    Markdown, reference the URL printed in the confirmation message, e.g.
    `![alt text](/api/files/<id>/<filename>)`.

    See also: docmost-cli attachment search, docmost-cli page update.
    """
    if not file.exists():
        print_error(f"File not found: {file}")
    if not file.is_file():
        print_error(f"Not a file: {file}")

    client = get_client()
    mime_type, _ = mimetypes.guess_type(file.name)
    result = upload_attachment(
        client,
        page_id=page_id,
        file_name=file.name,
        file_bytes=file.read_bytes(),
        mime_type=mime_type,
    )
    # build_attachment_url exits if the response carries no usable record, so
    # by this point extract_id is guaranteed to find the id.
    url = build_attachment_url(result)
    print_result(
        extract_id(result),
        f"Uploaded '{file.name}' to page {page_id}\nEmbed with: ![]({url})",
    )

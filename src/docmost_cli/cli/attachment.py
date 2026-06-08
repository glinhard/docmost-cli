"""Attachment subcommands."""

import mimetypes
from pathlib import Path

import typer

from docmost_cli.api.attachments import build_attachment_url, search_attachments, upload_attachment
from docmost_cli.api.pagination import extract_id, extract_items
from docmost_cli.api.spaces import resolve_space_id
from docmost_cli.cli.main import get_client
from docmost_cli.output.formatter import print_error, print_result, print_table

__all__ = ["attachment_app"]

attachment_app = typer.Typer(name="attachment", help="Attachment operations.")


@attachment_app.command("search")
def attachment_search_cmd(
    query: str = typer.Argument(..., help="Search query string"),
    space: str | None = typer.Option(None, "--space", help="Space slug to scope search"),
    json_mode: bool = typer.Option(False, "--json", help="Output as JSON array"),
) -> None:
    """Search attachments."""
    client = get_client()
    space_id = None
    if space:
        space_id = resolve_space_id(client, space)
    result = search_attachments(client, query, space_id=space_id)
    items = extract_items(result)
    columns = ["id", "fileName", "type"]
    print_table(items, columns, json_mode=json_mode)


@attachment_app.command("upload")
def attachment_upload_cmd(
    page_id: str = typer.Argument(..., help="Page ID to attach the file to"),
    file: Path = typer.Option(..., "--file", help="File to upload (e.g. an image)"),
) -> None:
    """Upload a file (e.g. an image) and attach it to a page.

    Prints the new attachment ID to stdout. To embed the file in the page's
    Markdown, reference the URL printed in the confirmation message, e.g.
    `![alt text](/api/files/<id>/<filename>)`.
    """
    if not file.exists():
        print_error(f"File not found: {file}")

    client = get_client()
    file_bytes = file.read_bytes()
    mime_type, _ = mimetypes.guess_type(file.name)

    result = upload_attachment(
        client,
        page_id=page_id,
        file_name=file.name,
        file_bytes=file_bytes,
        mime_type=mime_type,
    )
    attachment_id = extract_id(result)
    url = build_attachment_url(result)
    print_result(
        attachment_id,
        f"Uploaded '{file.name}' to page {page_id}\nEmbed with: ![]({url})",
    )

"""Attachment subcommands."""

import typer

from docmost_cli.api.attachments import search_attachments
from docmost_cli.api.spaces import resolve_space_id
from docmost_cli.cli._list_opts import (
    cursor_option,
    emit_list,
    envelope_option,
    fetch_list,
    json_option,
    limit_option,
    no_follow_option,
    page_size_option,
)
from docmost_cli.cli.main import get_client

__all__ = ["attachment_app"]

attachment_app = typer.Typer(name="attachment", help="Attachment operations.")


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
) -> None:
    """Search attachments."""
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
    emit_list(result, columns, json_mode=json_mode, envelope=envelope)

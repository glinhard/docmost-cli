"""Search subcommand."""

import typer

from docmost_cli.api.search import search
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

__all__ = ["search_app"]

search_app: typer.Typer = typer.Typer(name="search", help="Search across the wiki.")


@search_app.command("query")
def search_cmd(
    query: str = typer.Argument(help="Search query"),
    space: str | None = typer.Option(None, "--space", help="Filter by space slug"),
    type_filter: str | None = typer.Option(None, "--type", help="Filter: page or attachment"),
    limit: int | None = limit_option(),
    page_size: int | None = page_size_option(),
    cursor: str | None = cursor_option(),
    no_follow: bool = no_follow_option(),
    json_mode: bool = json_option(),
    envelope: bool = envelope_option(),
) -> None:
    """Full-text search across the wiki."""
    client = get_client()
    space_id = None
    if space is not None:
        space_id = resolve_space_id(client, space)

    result = fetch_list(
        search,
        limit=limit,
        page_size=page_size,
        cursor=cursor,
        no_follow=no_follow,
        client=client,
        query=query,
        space_id=space_id,
        result_type=type_filter,
    )
    columns = ["id", "title", "highlight"]
    emit_list(result, columns, json_mode=json_mode, envelope=envelope)

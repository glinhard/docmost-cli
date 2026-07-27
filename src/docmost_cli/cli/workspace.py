"""Workspace subcommands."""

import typer

from docmost_cli.api.pagination import unwrap_data
from docmost_cli.api.workspace import get_workspace_info, list_workspace_members
from docmost_cli.cli._list_opts import (
    cursor_option,
    emit_item,
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

__all__ = ["workspace_app"]

workspace_app: typer.Typer = typer.Typer(name="workspace", help="Workspace info.")


@workspace_app.command("info")
def workspace_info_cmd(
    json_mode: bool = json_option("Output as a JSON object"),
    fields: str | None = fields_option(),
) -> None:
    """Show workspace details.

    The key-value view shows a curated set; --json emits the complete object.
    """
    client = get_client()
    result = get_workspace_info(client)
    emit_item(
        unwrap_data(result),
        ["name", "id", "description", "memberCount", "createdAt"],
        json_mode=json_mode,
        fields=fields,
    )


@workspace_app.command("members")
def workspace_members_cmd(
    limit: int | None = limit_option(),
    page_size: int | None = page_size_option(),
    cursor: str | None = cursor_option(),
    no_follow: bool = no_follow_option(),
    json_mode: bool = json_option(),
    envelope: bool = envelope_option(),
    fields: str | None = fields_option(),
) -> None:
    """List workspace members."""
    client = get_client()
    result = fetch_list(
        list_workspace_members,
        limit=limit,
        page_size=page_size,
        cursor=cursor,
        no_follow=no_follow,
        client=client,
    )
    columns = ["id", "email", "name", "role"]
    emit_list(result, columns, json_mode=json_mode, envelope=envelope, fields=fields)

"""Workspace subcommands."""

from typing import Any

import typer

from docmost_cli.api.workspace import get_workspace_info, list_workspace_members
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
from docmost_cli.output.formatter import print_key_value

__all__ = ["workspace_app"]

workspace_app: typer.Typer = typer.Typer(name="workspace", help="Workspace info.")


@workspace_app.command("info")
def workspace_info_cmd() -> None:
    """Show workspace details."""
    client = get_client()
    result = get_workspace_info(client)
    data = result.get("data", result)
    display: dict[str, Any] = {}
    for key in ["name", "id", "description", "memberCount", "createdAt"]:
        if key in data:
            display[key] = data[key]
    print_key_value(display)


@workspace_app.command("members")
def workspace_members_cmd(
    limit: int | None = limit_option(),
    page_size: int | None = page_size_option(),
    cursor: str | None = cursor_option(),
    no_follow: bool = no_follow_option(),
    json_mode: bool = json_option(),
    envelope: bool = envelope_option(),
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
    emit_list(result, columns, json_mode=json_mode, envelope=envelope)

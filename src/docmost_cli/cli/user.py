"""User subcommands."""

import typer

from docmost_cli.api.users import get_current_user
from docmost_cli.cli._list_opts import emit_item, fields_option, json_option
from docmost_cli.cli.main import get_client

__all__ = ["user_app"]

user_app: typer.Typer = typer.Typer(name="user", help="Current user info.")


@user_app.command("me")
def user_me_cmd(
    json_mode: bool = json_option("Output as a JSON object"),
    fields: str | None = fields_option(),
) -> None:
    """Show authenticated user info.

    The key-value view shows a curated set; --json emits the complete user
    object. Workspace details live under 'workspace info'.
    """
    client = get_client()
    emit_item(
        get_current_user(client),
        ["email", "name", "id", "role", "createdAt"],
        json_mode=json_mode,
        fields=fields,
    )

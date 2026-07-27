"""User subcommands."""

from typing import Any

import typer

from docmost_cli.api.users import get_current_user
from docmost_cli.cli.main import get_client
from docmost_cli.output.formatter import print_key_value

__all__ = ["user_app"]

user_app: typer.Typer = typer.Typer(name="user", help="Current user info.")


@user_app.command("me")
def user_me_cmd() -> None:
    """Show authenticated user info."""
    client = get_client()
    result = get_current_user(client)
    display: dict[str, Any] = {}
    for key in ["email", "name", "id", "role", "createdAt"]:
        if key in result:
            display[key] = result[key]
    print_key_value(display)

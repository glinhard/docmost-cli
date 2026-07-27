"""Space subcommands."""

import typer

from docmost_cli.api.pagination import extract_id
from docmost_cli.api.spaces import (
    create_space,
    list_spaces,
    resolve_space_id,
    update_space,
)
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
from docmost_cli.output.formatter import print_error, print_result

__all__ = ["space_app"]

space_app: typer.Typer = typer.Typer(name="space", help="Space operations.")


@space_app.command("list")
def space_list_cmd(
    limit: int | None = limit_option(),
    page_size: int | None = page_size_option(),
    cursor: str | None = cursor_option(),
    no_follow: bool = no_follow_option(),
    json_mode: bool = json_option(),
    envelope: bool = envelope_option(),
) -> None:
    """List all spaces."""
    client = get_client()
    result = fetch_list(
        list_spaces,
        limit=limit,
        page_size=page_size,
        cursor=cursor,
        no_follow=no_follow,
        client=client,
    )
    columns = ["id", "name", "slug", "description"]
    emit_list(result, columns, json_mode=json_mode, envelope=envelope)


@space_app.command("create")
def space_create_cmd(
    name: str = typer.Option(..., "--name", help="Space name (required)"),
    slug: str | None = typer.Option(None, "--slug", help="Space slug (auto-generated if omitted)"),
    description: str | None = typer.Option(None, "--description", help="Space description"),
) -> None:
    """Create a new space."""
    client = get_client()
    result = create_space(client, name=name, slug=slug, description=description)
    space_id = extract_id(result)
    print_result(space_id, f"Created space '{name}'")


@space_app.command("update")
def space_update_cmd(
    space_slug: str = typer.Argument(help="Space slug to update"),
    name: str | None = typer.Option(None, "--name", help="New space name"),
    description: str | None = typer.Option(None, "--description", help="New description"),
) -> None:
    """Update an existing space."""
    if name is None and description is None:
        print_error("At least one of --name or --description is required.")
    client = get_client()
    space_id = resolve_space_id(client, space_slug)
    update_space(client, space_id=space_id, name=name, description=description)
    print_result(space_id, f"Updated space '{space_slug}'")

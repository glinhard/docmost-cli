"""Comment subcommands."""

from typing import Any

import typer

from docmost_cli.api.comments import create_comment, list_comments, update_comment
from docmost_cli.api.pagination import extract_id
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
from docmost_cli.output.formatter import print_result

__all__ = ["comment_app"]

comment_app: typer.Typer = typer.Typer(name="comment", help="Comment operations.")


def _extract_text_from_prosemirror(doc: dict[str, Any]) -> str:
    """Extract plain text from a ProseMirror document for display.

    Args:
        doc: ProseMirror document dict.

    Returns:
        Plain text string, truncated to ~100 chars.
    """
    texts: list[str] = []

    def walk(node: dict[str, Any]) -> None:
        if node.get("type") == "text":
            texts.append(node.get("text", ""))
        for child in node.get("content", []):
            if isinstance(child, dict):
                walk(child)

    walk(doc)
    full = " ".join(texts)
    if len(full) > 100:
        return full[:97] + "..."
    return full


@comment_app.command("list")
def comment_list_cmd(
    page_id: str = typer.Argument(help="Page ID to list comments for"),
    limit: int | None = limit_option(),
    page_size: int | None = page_size_option(),
    cursor: str | None = cursor_option(),
    no_follow: bool = no_follow_option(),
    json_mode: bool = json_option(),
    envelope: bool = envelope_option(),
    fields: str | None = fields_option(),
) -> None:
    """List comments on a page."""
    client = get_client()
    result = fetch_list(
        list_comments,
        limit=limit,
        page_size=page_size,
        cursor=cursor,
        no_follow=no_follow,
        client=client,
        page_id=page_id,
    )

    # For table display, extract text from ProseMirror content
    if not json_mode:
        for item in result.items:
            content = item.get("content")
            if isinstance(content, dict):
                item["content"] = _extract_text_from_prosemirror(content)

    columns = ["id", "content", "creatorId", "createdAt"]
    emit_list(result, columns, json_mode=json_mode, envelope=envelope, fields=fields)


@comment_app.command("create")
def comment_create_cmd(
    page_id: str = typer.Argument(help="Page ID to comment on"),
    content: str = typer.Option(..., "--content", help="Comment text (required)"),
) -> None:
    """Add a comment to a page."""
    client = get_client()
    result = create_comment(client, page_id=page_id, content=content)
    comment_id = extract_id(result)
    print_result(comment_id, f"Created comment on page '{page_id}'")


@comment_app.command("update")
def comment_update_cmd(
    comment_id: str = typer.Argument(help="Comment ID to update"),
    content: str = typer.Option(..., "--content", help="New comment text (required)"),
) -> None:
    """Update an existing comment."""
    client = get_client()
    update_comment(client, comment_id=comment_id, content=content)
    print_result(comment_id, f"Updated comment '{comment_id}'")

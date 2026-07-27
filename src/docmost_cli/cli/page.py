"""Page subcommands."""

import json
import sys
from pathlib import Path

import typer

from docmost_cli.api.pages import (
    build_page_tree,
    copy_page,
    create_and_place_page,
    delete_page,
    duplicate_page,
    export_page,
    get_page_children,
    get_page_content,
    get_page_history,
    get_page_info,
    import_page,
    list_recent_pages,
    move_page,
    resolve_position,
    update_page_content,
    update_page_meta,
)
from docmost_cli.api.pagination import extract_id
from docmost_cli.api.position import MAX_POSITION_LEN, MIN_POSITION_LEN, is_valid_position
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
from docmost_cli.cli.main import get_client, state
from docmost_cli.output.formatter import (
    print_content,
    print_content_with_meta,
    print_error,
    print_result,
)
from docmost_cli.output.tree import print_tree

__all__ = ["page_app"]

page_app = typer.Typer(name="page", help="Page operations.")


def _resolve_content(
    content: str | None,
    file: Path | None,
    stdin: bool,
) -> str | None:
    """Resolve content from --content, --file, or --stdin.

    These are mutually exclusive. Returns None if no source provided.

    Args:
        content: Inline content string.
        file: Path to content file.
        stdin: Whether to read from stdin.

    Returns:
        Resolved content string, or None.
    """
    sources = sum([content is not None, file is not None, stdin])
    if sources > 1:
        print_error("Only one of --content, --file, or --stdin may be specified.")
    if sources == 0:
        return None
    if content is not None:
        # Interpret common escape sequences so --content "Line 1\n\nLine 2" works
        return content.replace("\\n", "\n").replace("\\t", "\t")
    if file is not None:
        if not file.exists():
            print_error(f"File not found: {file}")
        return file.read_text(encoding="utf-8")
    # stdin
    if sys.stdin.isatty():
        print_error(
            "No input piped to stdin. "
            "Use --content or --file instead, or pipe input: "
            "echo '# Page' | docmost-cli page create ..."
        )
    return sys.stdin.read()


@page_app.command("create")
def page_create_cmd(
    space_slug: str = typer.Argument(help="Space slug to create the page in"),
    title: str = typer.Option(..., "--title", help="Page title (required)"),
    content: str | None = typer.Option(None, "--content", help="Markdown content string"),
    file: Path | None = typer.Option(None, "--file", help="Read content from file"),
    stdin: bool = typer.Option(False, "--stdin", help="Read content from stdin"),
    parent: str | None = typer.Option(None, "--parent", help="Parent page ID"),
    icon: str | None = typer.Option(None, "--icon", help="Page icon emoji"),
) -> None:
    """Create a new page via Markdown import.

    See also: page move (reposition), page children (list children).
    """
    resolved = _resolve_content(content, file, stdin) or ""
    client = get_client()
    space_id = resolve_space_id(client, space_slug)

    page_id = create_and_place_page(
        client,
        space_id=space_id,
        title=title,
        content=resolved,
        parent_page_id=parent,
        icon=icon,
    )

    msg = f"Created page '{title}' in space '{space_slug}'"
    if not resolved:
        msg = f"Created empty page '{title}' in space '{space_slug}'"
    print_result(page_id, msg)


@page_app.command("update")
def page_update_cmd(
    page_id: str = typer.Argument(help="Page ID to update"),
    title: str | None = typer.Option(None, "--title", help="New title"),
    icon: str | None = typer.Option(None, "--icon", help="Page icon emoji"),
    content: str | None = typer.Option(None, "--content", help="New content (Markdown)"),
    file: Path | None = typer.Option(None, "--file", help="Read content from file"),
    stdin: bool = typer.Option(False, "--stdin", help="Read content from stdin"),
    append: bool = typer.Option(False, "--append", help="Append instead of replacing content"),
    prepend: bool = typer.Option(
        False, "--prepend", help="Insert at the start instead of replacing content"
    ),
) -> None:
    """Update an existing page's title, icon, and/or content.

    Content updates are applied in place: the page keeps its ID, slug, history
    and inbound links. Requires Docmost v0.71 or newer.

    See also: page move (reposition), page get (view current content).
    """
    resolved = _resolve_content(content, file, stdin)
    if title is None and icon is None and resolved is None:
        print_error("At least one of --title, --icon, --content, --file, or --stdin is required.")
    if append and prepend:
        print_error("--append and --prepend are mutually exclusive.", exit_code=2)
    if (append or prepend) and resolved is None:
        flag = "--append" if append else "--prepend"
        print_error(f"{flag} requires --content, --file, or --stdin.", exit_code=2)

    operation = "append" if append else "prepend" if prepend else "replace"

    client = get_client()
    info = get_page_info(client, page_id)
    page_title = info.get("title", page_id)

    if title is not None or icon is not None:
        update_page_meta(client, page_id=page_id, title=title, icon=icon)
        if title is not None:
            page_title = title

    if resolved is not None:
        update_page_content(client, page_id=page_id, content=resolved, operation=operation)

    print_result(page_id, f"Updated page '{page_title}'")


@page_app.command("delete")
def page_delete_cmd(
    page_id: str = typer.Argument(help="Page ID to delete"),
) -> None:
    """Delete a page (requires confirmation unless --yes).

    See also: page duplicate (copy before deleting).
    """
    client = get_client()
    info = get_page_info(client, page_id)
    page_title = info.get("title", page_id)

    if not state.yes:
        typer.confirm(f"Delete page '{page_title}' ({page_id})?", abort=True)

    delete_page(client, page_id)
    print_result(page_id, f"Deleted page '{page_title}'")


@page_app.command("move")
def page_move_cmd(
    page_id: str = typer.Argument(help="Page ID to move"),
    parent: str | None = typer.Option(None, "--parent", help="New parent page ID"),
    space: str | None = typer.Option(None, "--space", help="Target space slug"),
    root: bool = typer.Option(False, "--root", help="Move to the space root (clear the parent)"),
    position: str = typer.Option(
        "first",
        "--position",
        help="Placement among siblings: 'first', 'last', or a 5-12 character ordering key",
    ),
) -> None:
    """Move a page to a new location.

    Docmost requires an ordering key on every move, so one is computed from the
    destination's existing children unless an explicit key is given.

    See also: page children (find targets), page list --tree (view hierarchy).
    """
    if parent is None and space is None and not root and position == "first":
        print_error("At least one of --parent, --space, --root, or --position is required.")
    if root and parent is not None:
        print_error("--root and --parent are mutually exclusive.", exit_code=2)

    client = get_client()
    info = get_page_info(client, page_id)

    target_space_id = resolve_space_id(client, space) if space is not None else None
    space_id = target_space_id or str(info.get("spaceId", ""))

    if root:
        parent_page_id = None
    elif parent is not None:
        parent_page_id = parent
    else:
        current_parent = info.get("parentPageId")
        parent_page_id = str(current_parent) if current_parent else None

    placement = position.lower()
    if placement in ("first", "last"):
        resolved_position = resolve_position(
            client,
            page_id=page_id,
            space_id=space_id,
            parent_page_id=parent_page_id,
            placement=placement,
        )
    elif is_valid_position(position):
        resolved_position = position
    else:
        print_error(
            f"Invalid --position '{position}'. Expected 'first', 'last', or a "
            f"{MIN_POSITION_LEN}-{MAX_POSITION_LEN} character ordering key using "
            "only 0-9, A-Z, a-z.",
            exit_code=2,
        )

    move_page(
        client,
        page_id=page_id,
        position=resolved_position,
        parent_page_id=parent_page_id,
        space_id=target_space_id,
    )
    print_result(page_id, f"Moved page '{info.get('title', page_id)}'")


@page_app.command("list")
def page_list_cmd(
    space_slug: str = typer.Argument(help="Space slug to list pages in"),
    limit: int | None = limit_option(),
    page_size: int | None = page_size_option(),
    cursor: str | None = cursor_option(),
    no_follow: bool = no_follow_option(),
    tree: bool = typer.Option(False, "--tree", help="Show as indented tree"),
    json_mode: bool = json_option(),
    envelope: bool = envelope_option(),
) -> None:
    """List pages in a space.

    Follows pagination automatically; use --limit to cap the total, or
    --cursor/--no-follow to fetch a single page.

    See also: page children (list by parent), page get (single page).
    """
    client = get_client()

    if tree:
        if limit is not None or cursor is not None or no_follow or envelope:
            print_error(
                "--tree cannot be combined with --limit, --page-size, --cursor, "
                "--no-follow or --envelope.",
                exit_code=2,
            )
        space_id = resolve_space_id(client, space_slug)
        pages = build_page_tree(client, space_id)
        if json_mode:
            sys.stdout.write(json.dumps(pages, indent=2, default=str) + "\n")
        else:
            print_tree(pages)
        return

    space_id = resolve_space_id(client, space_slug)
    result = fetch_list(
        list_recent_pages,
        limit=limit,
        page_size=page_size,
        cursor=cursor,
        no_follow=no_follow,
        client=client,
        space_id=space_id,
    )
    columns = ["id", "title", "icon", "updatedAt", "parentPageId"]
    emit_list(result, columns, json_mode=json_mode, envelope=envelope)


@page_app.command("get")
def page_get_cmd(
    page_id: str = typer.Argument(help="Page ID to retrieve"),
    raw: bool = typer.Option(False, "--raw", help="Output ProseMirror JSON instead of Markdown"),
    meta: bool = typer.Option(False, "--meta", help="Prepend YAML frontmatter with metadata"),
) -> None:
    """Get page content as Markdown.

    See also: page list --json (batch retrieval), page export (to file).
    """
    client = get_client()

    if raw:
        # Raw mode: reuse get_page_content which handles Enterprise/Community fallback
        info = get_page_content(client, page_id)
        pm_content = info.get("content")
        if not pm_content:
            print_error("No content available for raw output.", exit_code=1)
        sys.stdout.write(json.dumps(pm_content, indent=2) + "\n")
        return

    # Normal mode: get content and convert to Markdown
    info = get_page_content(client, page_id)
    pm_content = info.get("content")
    if not pm_content:
        print_error("Page has no content.", exit_code=1)

    from docmost_cli.convert.prosemirror_to_md import convert_to_markdown

    markdown = convert_to_markdown(pm_content)

    if meta:
        metadata = {
            "id": info.get("id", ""),
            "title": info.get("title", ""),
            "parent_id": info.get("parentPageId", ""),
            "space_id": info.get("spaceId", ""),
            "created": info.get("createdAt", ""),
            "updated": info.get("updatedAt", ""),
        }
        print_content_with_meta(markdown, metadata)
    else:
        print_content(markdown)


@page_app.command("duplicate")
def page_duplicate_cmd(
    page_id: str = typer.Argument(help="Page ID to duplicate"),
) -> None:
    """Duplicate a page."""
    client = get_client()
    info = get_page_info(client, page_id)
    page_title = info.get("title", page_id)
    result = duplicate_page(client, page_id)
    new_id = extract_id(result)
    print_result(new_id, f"Duplicated page '{page_title}'")


@page_app.command("copy")
def page_copy_cmd(
    page_id: str = typer.Argument(help="Page ID to copy"),
    space: str = typer.Option(..., "--space", help="Target space slug (required)"),
) -> None:
    """Copy a page to a different space."""
    client = get_client()
    info = get_page_info(client, page_id)
    page_title = info.get("title", page_id)
    target_space_id = resolve_space_id(client, space)
    result = copy_page(client, page_id, target_space_id)
    new_id = extract_id(result)
    print_result(new_id, f"Copied page '{page_title}' to space '{space}'")


@page_app.command("children")
def page_children_cmd(
    page_id: str = typer.Argument(help="Page ID to list children for"),
    limit: int | None = limit_option(),
    page_size: int | None = page_size_option(),
    cursor: str | None = cursor_option(),
    no_follow: bool = no_follow_option(),
    json_mode: bool = json_option(),
    envelope: bool = envelope_option(),
) -> None:
    """List child pages of a parent.

    Follows pagination automatically — the server's default page size is 20.

    See also: page list --tree (full hierarchy), page move (reposition).
    """
    client = get_client()
    # Resolve the space once so paginated requests don't re-fetch page info.
    space_id = get_page_info(client, page_id).get("spaceId", "")
    result = fetch_list(
        get_page_children,
        limit=limit,
        page_size=page_size,
        cursor=cursor,
        no_follow=no_follow,
        client=client,
        page_id=page_id,
        space_id=space_id,
    )
    columns = ["id", "title", "icon", "updatedAt"]
    emit_list(result, columns, json_mode=json_mode, envelope=envelope)


@page_app.command("history")
def page_history_cmd(
    page_id: str = typer.Argument(help="Page ID to show history for"),
    limit: int | None = limit_option(),
    page_size: int | None = page_size_option(),
    cursor: str | None = cursor_option(),
    no_follow: bool = no_follow_option(),
    json_mode: bool = json_option(),
    envelope: bool = envelope_option(),
) -> None:
    """Show page version history."""
    client = get_client()
    result = fetch_list(
        get_page_history,
        limit=limit,
        page_size=page_size,
        cursor=cursor,
        no_follow=no_follow,
        client=client,
        page_id=page_id,
    )
    columns = ["id", "creatorId", "createdAt"]
    emit_list(result, columns, json_mode=json_mode, envelope=envelope)


@page_app.command("export")
def page_export_cmd(
    page_id: str = typer.Argument(help="Page ID to export"),
    fmt: str = typer.Option("md", "--format", help="Export format: md or html"),
    output: Path | None = typer.Option(None, "--output", help="Write to file instead of stdout"),
) -> None:
    """Export page content."""
    client = get_client()
    content = export_page(client, page_id, fmt=fmt)

    if output:
        if output.exists() and not state.yes:
            typer.confirm(f"File '{output}' already exists. Overwrite?", abort=True)
        output.write_text(str(content), encoding="utf-8")
        from rich.console import Console

        Console(stderr=True).print(f"Exported to {output}")
    else:
        print_content(str(content))


@page_app.command("import")
def page_import_cmd(
    space_slug: str = typer.Argument(help="Space slug to import into"),
    file: Path = typer.Option(..., "--file", help="Markdown or HTML file to import"),
    title: str | None = typer.Option(None, "--title", help="Override page title"),
    parent: str | None = typer.Option(None, "--parent", help="Parent page ID"),
) -> None:
    """Import a file as a new page."""
    if not file.exists():
        print_error(f"File not found: {file}")

    client = get_client()
    space_id = resolve_space_id(client, space_slug)

    # Read file once
    file_bytes = file.read_bytes()
    file_text = file_bytes.decode("utf-8", errors="replace")

    # Auto-detect title: flag > H1 in file > filename stem
    detected_title = title
    if not detected_title:
        for line in file_text.split("\n"):
            stripped = line.strip()
            if stripped.startswith("# ") and not stripped.startswith("## "):
                detected_title = stripped[2:].strip()
                break
    if not detected_title:
        detected_title = file.stem

    result = import_page(
        client,
        space_id=space_id,
        file_name=file.name,
        file_bytes=file_bytes,
        parent_page_id=parent,
    )
    new_id = extract_id(result)
    print_result(new_id, f"Imported '{detected_title}' from {file.name}")

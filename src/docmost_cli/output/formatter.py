"""Output dispatch: stdout/stderr separation for all command types."""

import json
import sys
from typing import Any, NoReturn

from rich.console import Console, RenderableType
from rich.table import Table

__all__ = [
    "print_content",
    "print_content_with_meta",
    "print_error",
    "print_json",
    "print_key_value",
    "print_progress",
    "print_rendered",
    "print_result",
    "print_table",
    "print_warning",
]

# The two consoles every renderer in the project writes through. Keeping them
# here — rather than letting each module build its own — is what makes the
# stdout/stderr split a property of this module instead of a convention each
# caller has to remember.
_out_console = Console()
_err_console = Console(stderr=True)


def print_content(content: str) -> None:
    """Print content (Markdown) directly to stdout."""
    sys.stdout.write(content)


def print_json(payload: Any) -> None:
    """Print a JSON document to stdout.

    The single JSON writer: every ``--json`` path goes through here so
    indentation and the non-serializable fallback stay consistent.
    """
    sys.stdout.write(json.dumps(payload, indent=2, default=str) + "\n")


def print_content_with_meta(content: str, meta: dict[str, Any]) -> None:
    """Print YAML frontmatter + Markdown content to stdout."""
    lines = ["---"]
    for key, value in meta.items():
        lines.append(f"{key}: {value}")
    lines.append("---")
    lines.append("")
    sys.stdout.write("\n".join(lines))
    sys.stdout.write(content)


def print_key_value(data: dict[str, Any], key_style: str = "bold") -> None:
    """Print key-value pairs for single-item info display.

    Args:
        data: Dictionary of key-value pairs to display.
        key_style: Rich style string for keys column.
    """
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style=key_style)
    table.add_column()
    for key, value in data.items():
        if value is not None and value != "":
            table.add_row(str(key), str(value))

    _out_console.print(table)


def _cell(value: Any) -> str:
    """Render one table cell: None as blank, containers as compact JSON."""
    if value is None:
        return ""
    if isinstance(value, dict | list):
        return json.dumps(value, default=str)
    return str(value)


def print_table(
    rows: list[dict[str, Any]],
    columns: list[str],
    json_mode: bool = False,
    *,
    meta: dict[str, Any] | None = None,
    fields: list[str] | None = None,
) -> None:
    """Print as a Rich table or JSON depending on mode.

    Args:
        rows: Item dicts to render.
        columns: Table columns. A display choice only — it does not narrow JSON
            output. Ignored when ``fields`` is given.
        json_mode: Emit JSON instead of a Rich table. JSON is lossless: each
            element is the item dict as received, unfiltered, so a key the
            server omitted is absent rather than null.
        meta: Pagination metadata. When None (the default), JSON output is a
            bare array — the documented contract. When provided, JSON output
            becomes ``{"items": [...], "meta": {...}}`` and table output gains
            a stderr footer with the next cursor.
        fields: Explicit projection. Replaces ``columns`` for the table and
            narrows JSON to exactly these keys, in this order. A named field an
            item lacks is emitted as ``null`` so the shape stays rectangular
            across rows — the caller asked for that column by name.
    """
    render_rows = rows
    render_columns = columns
    if fields is not None:
        # Rebind rather than mutate: `rows` is the caller's live server data.
        render_rows = [{name: row.get(name) for name in fields} for row in rows]
        render_columns = fields

    if json_mode:
        payload: Any = render_rows if meta is None else {"items": render_rows, "meta": meta}
        print_json(payload)
        return

    table = Table()
    for col in render_columns:
        table.add_column(col)
    for row in render_rows:
        table.add_row(*(_cell(row.get(col)) for col in render_columns))

    _out_console.print(table)

    if meta is not None and meta.get("hasNextPage"):
        _err_console.print(f"More results available. Next cursor: {meta.get('nextCursor')}")


def print_result(resource_id: str, message: str) -> None:
    """Print resource ID to stdout, confirmation to stderr."""
    sys.stdout.write(resource_id + "\n")
    _err_console.print(message)


def print_rendered(renderable: RenderableType) -> None:
    """Print a Rich renderable — a table, or a markup string — to stdout.

    For primary output that needs Rich's layout rather than the byte-faithful
    passthrough of :func:`print_content`. Callers build the renderable; this is
    the one place that owns the console it goes to.
    """
    _out_console.print(renderable)


def print_progress(message: str) -> None:
    """Print a progress or confirmation line to stderr.

    The public entry point for the running commentary that long operations
    (``sync pull``, ``sync push``) emit while they work, so those modules do not
    have to reach for a console of their own. Rich markup is interpreted.
    """
    _err_console.print(message)


def print_warning(message: str) -> None:
    """Print a warning to stderr without exiting."""
    _err_console.print(f"[yellow]Warning:[/yellow] {message}")


def print_error(message: str, exit_code: int = 1) -> NoReturn:
    """Print error to stderr and exit with given code."""
    _err_console.print(f"[red]Error:[/red] {message}")
    raise SystemExit(exit_code)

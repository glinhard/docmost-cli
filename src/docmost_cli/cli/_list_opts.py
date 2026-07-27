"""Shared output and pagination flags for list-shaped and single-item commands.

Every list command exposes the same flags. Defining them here keeps the surface
consistent and keeps `fetch_list`/`emit_list` as the single place that decides
between auto-follow and single-page mode, and `emit_list`/`emit_item` as the
single place that decides between JSON and a rendered table.
"""

from collections.abc import Callable
from typing import Any

import typer

from docmost_cli.api.pagination import extract_items, get_meta, paginate_all
from docmost_cli.models.common import SERVER_MAX_LIMIT, PaginatedResult
from docmost_cli.output.formatter import (
    print_error,
    print_json,
    print_key_value,
    print_table,
    print_warning,
)

__all__ = [
    "cursor_option",
    "emit_item",
    "emit_list",
    "envelope_option",
    "fetch_list",
    "fields_option",
    "json_option",
    "limit_option",
    "no_follow_option",
    "page_size_option",
    "parse_fields",
    "validate_fields",
]


def limit_option() -> Any:
    """--limit: total cap across all pages."""
    return typer.Option(None, "--limit", help="Max total results across pages (default: all)")


def page_size_option() -> Any:
    """--page-size: per-request page size."""
    return typer.Option(
        None,
        "--page-size",
        min=1,
        max=SERVER_MAX_LIMIT,
        help=f"Results per request, 1-{SERVER_MAX_LIMIT} (default: {SERVER_MAX_LIMIT})",
    )


def cursor_option() -> Any:
    """--cursor: resume from a cursor (single page)."""
    return typer.Option(None, "--cursor", help="Fetch a single page starting at this cursor")


def no_follow_option() -> Any:
    """--no-follow: fetch exactly one page."""
    return typer.Option(
        False, "--no-follow", help="Fetch a single page instead of following all pages"
    )


def json_option(help_text: str = "Output as JSON array") -> Any:
    """--json: emit JSON instead of a table."""
    return typer.Option(False, "--json", help=help_text)


def envelope_option() -> Any:
    """--envelope: wrap JSON output with pagination metadata."""
    return typer.Option(
        False,
        "--envelope",
        help='With --json, emit {"items": [...], "meta": {...}} instead of a bare array',
    )


def fields_option() -> Any:
    """--fields: project the output to a comma-separated field list."""
    return typer.Option(
        None,
        "--fields",
        metavar="a,b,c",
        help="Comma-separated fields to output; also replaces the table columns",
    )


def parse_fields(raw: str | None) -> list[str] | None:
    """Parse a --fields value into an ordered, de-duplicated name list.

    Args:
        raw: The raw flag value, or None when the flag was not given.

    Returns:
        The requested field names, or None when --fields was not given — so
        callers can tell "no projection" apart from "projection to nothing".
    """
    if raw is None:
        return None
    names = [part.strip() for part in raw.split(",") if part.strip()]
    if not names:
        print_error("--fields requires at least one field name.", exit_code=2)
    # Dedup: duplicates would render two identical table columns but a
    # single-key dict, so the two renderers would disagree on width.
    deduped: list[str] = []
    for name in names:
        if name not in deduped:
            deduped.append(name)
    return deduped


def validate_fields(selected: list[str], items: list[dict[str, Any]]) -> None:
    """Reject --fields names absent from every fetched item.

    Without this a typo yields a full-length column of nulls and a script that
    *succeeds* with no data — the silent-wrong-output failure this whole flag
    exists to avoid. The reported list is also the only discovery mechanism for
    these undocumented, endpoint-specific server field names.

    Skipped when nothing came back: an empty result carries no information about
    which names are valid, and erroring there would turn a legitimate "no
    matches" into a usage error.
    """
    if not items:
        return
    available: set[str] = set()
    for item in items:
        available.update(item)
    unknown = [name for name in selected if name not in available]
    if unknown:
        print_error(
            f"Unknown --fields name(s): {', '.join(unknown)}. "
            f"Available: {', '.join(sorted(available))}",
            exit_code=2,
        )


def fetch_list(
    fetch_func: Callable[..., dict[str, Any]],
    *,
    limit: int | None = None,
    page_size: int | None = None,
    cursor: str | None = None,
    no_follow: bool = False,
    **kwargs: Any,
) -> PaginatedResult:
    """Fetch a list, following pagination unless a single page was requested.

    Args:
        fetch_func: API function accepting ``limit=`` and ``cursor=`` keywords.
        limit: Max total results across pages.
        page_size: Per-request size (defaults to the server maximum).
        cursor: Start cursor. Implies single-page mode.
        no_follow: Fetch exactly one page.
        **kwargs: Extra arguments forwarded to fetch_func.

    Returns:
        A PaginatedResult with the collected items and the final metadata.
    """
    if limit is not None and limit < 1:
        print_error("--limit must be a positive integer.", exit_code=2)

    effective_page_size = min(page_size or SERVER_MAX_LIMIT, SERVER_MAX_LIMIT)

    if cursor is not None or no_follow:
        per_request = effective_page_size if limit is None else min(effective_page_size, limit)
        response = fetch_func(**kwargs, limit=per_request, cursor=cursor)
        items = extract_items(response)
        meta = get_meta(response)
        if limit is not None and len(items) > limit:
            items = items[:limit]
        return PaginatedResult(
            items=items, meta=meta, pages_fetched=1, truncated=meta.has_next_page
        )

    return paginate_all(fetch_func, limit=limit, page_size=effective_page_size, **kwargs)


def emit_list(
    result: PaginatedResult,
    columns: list[str],
    *,
    json_mode: bool = False,
    envelope: bool = False,
    fields: str | None = None,
) -> None:
    """Render a PaginatedResult as a table or JSON.

    Args:
        result: The fetched items and metadata.
        columns: Table columns. Display only — JSON emits complete objects.
        json_mode: Emit JSON instead of a Rich table.
        envelope: Include pagination metadata in the output.
        fields: Raw --fields value. Projects both renderers when given.
    """
    if envelope and not json_mode:
        print_error("--envelope requires --json.", exit_code=2)

    selected = parse_fields(fields)
    if selected is not None:
        validate_fields(selected, result.items)

    meta = result.meta.model_dump(by_alias=True) if envelope else None
    print_table(result.items, columns, json_mode=json_mode, meta=meta, fields=selected)

    if not envelope and result.truncated and result.meta.has_next_page:
        print_warning(
            "More results are available. Raise --limit, or add --envelope to get the next cursor."
        )


def emit_item(
    data: dict[str, Any],
    display_keys: list[str],
    *,
    json_mode: bool = False,
    fields: str | None = None,
) -> None:
    """Render one server object as JSON or a key-value table.

    The single-item mirror of :func:`emit_list`.

    Args:
        data: The server object, unmodified.
        display_keys: Curated keys for the human key-value view. Display only —
            JSON emits the complete object.
        json_mode: Emit JSON instead of a key-value table.
        fields: Raw --fields value. Projects both renderers when given.
    """
    selected = parse_fields(fields)
    if selected is not None:
        validate_fields(selected, [data])
        projected = {name: data.get(name) for name in selected}
        if json_mode:
            print_json(projected)
        else:
            print_key_value(projected)
        return

    if json_mode:
        print_json(data)
        return

    print_key_value({key: data[key] for key in display_keys if key in data})

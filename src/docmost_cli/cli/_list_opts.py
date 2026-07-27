"""Shared pagination flags and plumbing for list-shaped commands.

Every list command exposes the same five flags. Defining them here keeps the
surface consistent and keeps `fetch_list`/`emit_list` as the single place that
decides between auto-follow and single-page mode.
"""

from collections.abc import Callable
from typing import Any

import typer

from docmost_cli.api.pagination import extract_items, get_meta, paginate_all
from docmost_cli.models.common import SERVER_MAX_LIMIT, PaginatedResult
from docmost_cli.output.formatter import print_error, print_table, print_warning

__all__ = [
    "cursor_option",
    "emit_list",
    "envelope_option",
    "fetch_list",
    "json_option",
    "limit_option",
    "no_follow_option",
    "page_size_option",
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


def json_option() -> Any:
    """--json: emit JSON instead of a table."""
    return typer.Option(False, "--json", help="Output as JSON array")


def envelope_option() -> Any:
    """--envelope: wrap JSON output with pagination metadata."""
    return typer.Option(
        False,
        "--envelope",
        help='With --json, emit {"items": [...], "meta": {...}} instead of a bare array',
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
) -> None:
    """Render a PaginatedResult as a table or JSON.

    Args:
        result: The fetched items and metadata.
        columns: Column whitelist.
        json_mode: Emit JSON instead of a Rich table.
        envelope: Include pagination metadata in the output.
    """
    if envelope and not json_mode:
        print_error("--envelope requires --json.", exit_code=2)

    meta = result.meta.model_dump(by_alias=True) if envelope else None
    print_table(result.items, columns, json_mode=json_mode, meta=meta)

    if not envelope and result.truncated and result.meta.has_next_page:
        print_warning(
            "More results are available. Raise --limit, or add --envelope to get the next cursor."
        )

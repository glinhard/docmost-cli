"""Pagination utilities for cursor-based API responses.

Provides shared helpers for extracting items and metadata from varying
response shapes, and for auto-following pagination cursors.

Docmost wraps every paginated response as::

    {"data": {"items": [...], "meta": {"limit": 100, "hasNextPage": true,
                                       "hasPrevPage": false,
                                       "nextCursor": "...", "prevCursor": null}}}
"""

from collections.abc import Callable, Iterator
from typing import Any

from docmost_cli.models.common import SERVER_MAX_LIMIT, PaginatedResult, PaginationMeta
from docmost_cli.output.formatter import print_warning

__all__ = [
    "SERVER_MAX_LIMIT",
    "build_body",
    "extract_id",
    "extract_items",
    "get_cursor",
    "get_meta",
    "paginate_all",
    "paginate_iter",
]

# Safety guard: stop after this many requests even if the server keeps
# claiming there is more data.
MAX_PAGES = 1000


def extract_id(response: dict[str, Any]) -> str:
    """Extract resource ID from API response, handling nested shapes."""
    return response.get("id") or response.get("data", {}).get("id", "")


def build_body(required: dict[str, Any], **optional: Any) -> dict[str, Any]:
    """Build API request body, filtering out None optional values."""
    body = dict(required)
    for key, value in optional.items():
        if value is not None:
            body[key] = value
    return body


def extract_items(response: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract items list from API response, handling nested shapes.

    Handles: {data: {items: [...]}}, {data: [...]}, {items: [...]}, and flat dicts.

    Args:
        response: Raw API response dict.

    Returns:
        List of item dicts.
    """
    if "data" in response and isinstance(response["data"], dict):
        return response["data"].get("items", [])
    if "data" in response and isinstance(response["data"], list):
        return response["data"]
    return response.get("items", [response] if "id" in response else [])


def get_cursor(response: dict[str, Any]) -> str | None:
    """Extract the next pagination cursor from an API response.

    Docmost puts it at ``data.meta.nextCursor``. The other locations are
    checked for robustness against older/newer response shapes.

    Args:
        response: Raw API response dict.

    Returns:
        Next cursor string, or None if there are no more pages.
    """
    data = response.get("data")
    containers: list[dict[str, Any]] = []
    if isinstance(data, dict):
        meta = data.get("meta")
        if isinstance(meta, dict):
            containers.append(meta)
        containers.append(data)
    top_meta = response.get("meta")
    if isinstance(top_meta, dict):
        containers.append(top_meta)
    containers.append(response)

    for container in containers:
        for key in ("nextCursor", "cursor"):
            value = container.get(key)
            if value:
                return str(value)
    return None


def get_meta(response: dict[str, Any]) -> PaginationMeta:
    """Extract pagination metadata from an API response.

    Falls back to synthesizing metadata from a bare cursor, and finally to
    empty defaults so unpaginated endpoints degrade to a single request.

    Args:
        response: Raw API response dict.

    Returns:
        A PaginationMeta instance (never None).
    """
    data = response.get("data")
    raw: Any = None
    if isinstance(data, dict) and isinstance(data.get("meta"), dict):
        raw = data["meta"]
    elif isinstance(response.get("meta"), dict):
        raw = response["meta"]

    if raw is not None:
        return PaginationMeta.model_validate(raw)

    cursor = get_cursor(response)
    return PaginationMeta.model_validate({"nextCursor": cursor, "hasNextPage": cursor is not None})


def paginate_iter(
    fetch_func: Callable[..., dict[str, Any]],
    *,
    limit: int | None = None,
    page_size: int = SERVER_MAX_LIMIT,
    max_pages: int = MAX_PAGES,
    on_result: Callable[[PaginatedResult], None] | None = None,
    **kwargs: Any,
) -> Iterator[dict[str, Any]]:
    """Yield items across pages, following the cursor until exhausted.

    Lazily fetches: callers that stop early (a slug lookup, say) never pay for
    the remaining pages.

    Args:
        fetch_func: API function accepting ``limit=`` and ``cursor=`` keywords.
        limit: Maximum total items to yield (None = all).
        page_size: Per-request size, clamped to the server maximum of 100.
        max_pages: Safety cap on the number of requests.
        on_result: Called once when iteration finishes, with the final
            PaginatedResult (items empty — the caller already has them).
        **kwargs: Extra arguments forwarded to fetch_func.

    Yields:
        Item dicts, in server order.

    Raises:
        TypeError: If ``limit`` or ``cursor`` are passed via **kwargs, which
            would collide with the ones this function supplies.
    """
    for reserved in ("limit", "cursor"):
        if reserved in kwargs:
            raise TypeError(f"paginate_iter() supplies '{reserved}'; do not pass it in kwargs")

    cursor: str | None = None
    seen_cursors: set[str] = set()
    previous_first_id: str | None = None
    yielded = 0
    pages = 0
    meta = PaginationMeta()
    truncated = False

    while True:
        per_request = min(page_size, SERVER_MAX_LIMIT)
        if limit is not None:
            per_request = min(per_request, max(limit - yielded, 1))

        response = fetch_func(**kwargs, limit=per_request, cursor=cursor)
        pages += 1
        items = extract_items(response)
        meta = get_meta(response)

        # A server that ignores `cursor` re-serves page 1 forever. Detect it
        # before yielding duplicates.
        first_id = str(items[0].get("id", "")) if items else None
        if cursor is not None and first_id is not None and first_id == previous_first_id:
            print_warning(
                f"Server returned the same page twice while paginating; stopped after "
                f"{yielded} item(s). Results may be incomplete."
            )
            truncated = True
            break
        previous_first_id = first_id

        for item in items:
            yield item
            yielded += 1
            if limit is not None and yielded >= limit:
                truncated = True
                break

        if truncated or not items or not meta.has_next_page:
            break

        next_cursor = meta.next_cursor
        if not next_cursor:
            break
        if next_cursor in seen_cursors:
            print_warning(
                f"Server returned a repeated pagination cursor; stopped after {yielded} "
                "item(s) to avoid an infinite loop. Results may be incomplete."
            )
            truncated = True
            break
        seen_cursors.add(next_cursor)
        cursor = next_cursor

        if pages >= max_pages:
            print_warning(
                f"Stopped after {max_pages} pages. Results may be incomplete — "
                "narrow the query or use --limit."
            )
            truncated = True
            break

    if on_result is not None:
        on_result(PaginatedResult(items=[], meta=meta, pages_fetched=pages, truncated=truncated))


def paginate_all(
    fetch_func: Callable[..., dict[str, Any]],
    *,
    limit: int | None = None,
    page_size: int = SERVER_MAX_LIMIT,
    max_pages: int = MAX_PAGES,
    **kwargs: Any,
) -> PaginatedResult:
    """Auto-follow pagination until exhausted or ``limit`` is reached.

    Args:
        fetch_func: API function accepting ``limit=`` and ``cursor=`` keywords.
        limit: Maximum total items to collect (None = all).
        page_size: Per-request size, clamped to the server maximum of 100.
        max_pages: Safety cap on the number of requests.
        **kwargs: Extra arguments forwarded to fetch_func.

    Returns:
        A PaginatedResult with every collected item and the final metadata.
    """
    collected: PaginatedResult = PaginatedResult()

    def _capture(result: PaginatedResult) -> None:
        collected.meta = result.meta
        collected.pages_fetched = result.pages_fetched
        collected.truncated = result.truncated

    collected.items = list(
        paginate_iter(
            fetch_func,
            limit=limit,
            page_size=page_size,
            max_pages=max_pages,
            on_result=_capture,
            **kwargs,
        )
    )
    return collected

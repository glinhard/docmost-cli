"""Page API methods."""

import random
from typing import Any

from docmost_cli.api.client import DocmostClient
from docmost_cli.api.pagination import build_body
from docmost_cli.api.position import PositionError, generate_key_between
from docmost_cli.output.formatter import print_error, print_warning

__all__ = [
    "CONTENT_OPERATIONS",
    "CONTENT_UNSUPPORTED_MESSAGE",
    "build_page_tree",
    "copy_page",
    "create_and_place_page",
    "create_page_via_import",
    "delete_page",
    "duplicate_page",
    "export_page",
    "get_all_page_children",
    "get_all_sidebar_pages",
    "get_page_children",
    "get_page_content",
    "get_page_history",
    "get_page_info",
    "get_sidebar_pages",
    "import_page",
    "list_recent_pages",
    "move_page",
    "resolve_position",
    "try_update_page_content",
    "update_page_content",
    "update_page_meta",
]


def get_page_info(
    client: DocmostClient,
    page_id: str,
    *,
    include_space: bool = False,
    include_content: bool = False,
    fmt: str | None = None,
) -> dict[str, Any]:
    """Get page metadata by ID.

    Args:
        client: Authenticated Docmost client.
        page_id: Page UUID.
        include_space: Include the parent space in the response.
        include_content: Include the page body in the response.
        fmt: Content format ("json", "markdown" or "html"). Only meaningful
            together with include_content.

    Returns:
        Page info dict (unwrapped from data envelope).
    """
    body = build_body(
        {"pageId": page_id},
        includeSpace=include_space or None,
        includeContent=include_content or None,
        format=fmt,
    )
    result = client.post("/pages/info", json=body)
    return result.get("data", result)


def create_page_via_import(
    client: DocmostClient,
    *,
    space_id: str,
    title: str,
    content: str,
    parent_page_id: str | None = None,
) -> dict[str, Any]:
    """Create a page using the import endpoint (server-side MD→ProseMirror).

    Sends Markdown as a .md file via multipart upload. Available on both
    Community and Enterprise editions.

    Args:
        client: Authenticated Docmost client.
        space_id: Target space UUID.
        title: Page title.
        content: Markdown content.
        parent_page_id: Parent page UUID (optional).

    Returns:
        Raw API response dict (should contain page ID).
    """
    # Ensure content has the title as H1 if not already present
    md_content = content
    if md_content and not md_content.lstrip().startswith("#"):
        md_content = f"# {title}\n\n{md_content}"
    elif not md_content:
        md_content = f"# {title}\n"

    file_bytes = md_content.encode("utf-8")
    files = {"file": (f"{title}.md", file_bytes, "text/markdown")}
    data = build_body({"spaceId": space_id}, parentPageId=parent_page_id)

    return client.post_multipart("/pages/import", data=data, files=files)


def update_page_meta(
    client: DocmostClient,
    *,
    page_id: str,
    title: str | None = None,
    icon: str | None = None,
) -> dict[str, Any]:
    """Update page metadata (title, icon).

    Available on both Community and Enterprise editions.

    Args:
        client: Authenticated Docmost client.
        page_id: Page UUID.
        title: New title.
        icon: New icon emoji.

    Returns:
        Raw API response dict.
    """
    body = build_body({"pageId": page_id}, title=title, icon=icon)
    return client.post("/pages/update", json=body)


CONTENT_OPERATIONS = ("replace", "append", "prepend")

CONTENT_UNSUPPORTED_MESSAGE = (
    "This Docmost server accepted the request but did not apply the content "
    "(POST /api/pages/update silently ignored 'content'). In-place content "
    "updates require Docmost v0.71 or newer. Upgrade the server, or use "
    "'docmost-cli sync push --allow-recreate' to replace pages by "
    "delete+recreate — that assigns NEW page IDs and breaks inbound links, "
    "permissions, comments and page history."
)


def _content_body(page_id: str, content: str, fmt: str, operation: str) -> dict[str, Any]:
    """Build the /pages/update request body for a content update."""
    return {
        "pageId": page_id,
        "content": content,
        "format": fmt,
        "operation": operation,
    }


def _content_was_applied(
    client: DocmostClient,
    response: dict[str, Any],
    *,
    page_id: str,
    sent_content: str,
) -> bool:
    """Decide whether the server actually applied a content update.

    Docmost's global ValidationPipe uses ``whitelist: true`` without
    ``forbidNonWhitelisted``, so a server too old to know about ``content``
    strips the field and returns HTTP 200 — a silent no-op. The tell is the
    shape of the returned content: a server that honoured ``format:
    "markdown"`` converts it to a Markdown **string**, while one that stripped
    our fields returns ProseMirror JSON (an **object**) or nothing at all.

    Args:
        client: Authenticated Docmost client, for the ambiguous-case re-read.
        response: Raw response from POST /pages/update.
        page_id: Page UUID.
        sent_content: The content we asked the server to store.

    Returns:
        True if the content was applied.
    """
    data = response.get("data", response)
    if not isinstance(data, dict):
        return False

    returned = data.get("content")
    if isinstance(returned, str):
        return True
    if returned is not None:
        # ProseMirror JSON came back: `format` was stripped, so `content` was too.
        return False

    # No content in the response. Empty input legitimately yields nothing;
    # otherwise confirm with a single read-back.
    probe = sent_content.strip()
    if not probe:
        return True

    info = get_page_info(client, page_id, include_content=True, fmt="markdown")
    stored = info.get("content")
    if not isinstance(stored, str):
        return False
    first_line = next((line for line in probe.splitlines() if line.strip()), "")
    return first_line.strip() in stored


def update_page_content(
    client: DocmostClient,
    *,
    page_id: str,
    content: str,
    fmt: str = "markdown",
    operation: str = "replace",
) -> dict[str, Any]:
    """Update page content in place.

    Sends the content through POST /pages/update, which Docmost routes to its
    collaboration gateway (`handleYjsEvent`) server-side. The page keeps its
    ID, slug, history, comments and inbound links — no WebSocket client is
    needed on this end.

    Available on Community and Enterprise alike, from Docmost v0.71.

    Args:
        client: Authenticated Docmost client.
        page_id: Page UUID.
        content: Markdown or HTML content.
        fmt: Content format ("markdown" or "html").
        operation: One of "replace", "append", "prepend".

    Returns:
        Raw API response dict.
    """
    if operation not in CONTENT_OPERATIONS:
        print_error(
            f"Invalid content operation '{operation}'. "
            f"Expected one of: {', '.join(CONTENT_OPERATIONS)}.",
            exit_code=2,
        )
    response = client.post("/pages/update", json=_content_body(page_id, content, fmt, operation))
    if not _content_was_applied(client, response, page_id=page_id, sent_content=content):
        print_error(CONTENT_UNSUPPORTED_MESSAGE, exit_code=1)
    return response


def try_update_page_content(
    client: DocmostClient,
    *,
    page_id: str,
    content: str,
    fmt: str = "markdown",
    operation: str = "replace",
) -> bool:
    """Probe whether this server supports in-place content updates.

    Performs the update and reports success without raising, so callers can
    decide what to do about a server that cannot apply content.

    Args:
        client: Authenticated Docmost client.
        page_id: Page UUID.
        content: Markdown or HTML content.
        fmt: Content format ("markdown" or "html").
        operation: One of "replace", "append", "prepend".

    Returns:
        True if the content was applied.
    """
    raw = client.post_raw(
        "/pages/update",
        json=_content_body(page_id, content, fmt, operation),
        raise_on_error=False,
    )
    if not raw.is_success:
        return False
    try:
        response = raw.json()
    except ValueError:
        return False
    if not isinstance(response, dict):
        return False
    return _content_was_applied(client, response, page_id=page_id, sent_content=content)


def create_and_place_page(
    client: DocmostClient,
    *,
    space_id: str,
    title: str,
    content: str,
    parent_page_id: str | None = None,
    icon: str | None = None,
) -> str:
    """Create a page via import, then move to parent and set icon.

    Combines the three-step create+move+icon workflow that the import
    endpoint requires (it ignores parentPageId and icon).

    Args:
        client: Authenticated Docmost client.
        space_id: Target space UUID.
        title: Page title.
        content: Markdown content.
        parent_page_id: Parent page UUID (optional).
        icon: Page icon emoji (optional).

    Returns:
        The new page's UUID.
    """
    from docmost_cli.api.pagination import extract_id

    result = create_page_via_import(client, space_id=space_id, title=title, content=content)
    page_id = extract_id(result)

    if parent_page_id:
        move_page(
            client,
            page_id=page_id,
            parent_page_id=parent_page_id,
            position=resolve_position(
                client,
                page_id=page_id,
                space_id=space_id,
                parent_page_id=parent_page_id,
                placement="first",
            ),
        )
    if icon:
        update_page_meta(client, page_id=page_id, icon=icon)

    return page_id


def delete_page(client: DocmostClient, page_id: str) -> dict[str, Any]:
    """Delete a page by ID.

    Available on both Community and Enterprise editions.

    Args:
        client: Authenticated Docmost client.
        page_id: Page UUID.

    Returns:
        Raw API response dict.
    """
    return client.post("/pages/delete", json={"pageId": page_id})


def move_page(
    client: DocmostClient,
    *,
    page_id: str,
    position: str,
    parent_page_id: str | None = None,
    space_id: str | None = None,
) -> dict[str, Any]:
    """Move a page to a new location.

    Available on both Community and Enterprise editions.

    ``position`` is required: Docmost's MovePageDto declares it
    ``@IsString @MinLength(5) @MaxLength(12)``, so omitting it is an HTTP 400.
    Use resolve_position() to compute one from the destination's siblings.

    Args:
        client: Authenticated Docmost client.
        page_id: Page UUID.
        position: Fractional index among siblings (5-12 characters).
        parent_page_id: New parent page UUID (omit for root).
        space_id: Target space UUID (for cross-space moves).

    Returns:
        Raw API response dict.
    """
    body = build_body(
        {"pageId": page_id, "position": position},
        parentPageId=parent_page_id,
        spaceId=space_id,
    )
    return client.post("/pages/move", json=body)


def resolve_position(
    client: DocmostClient,
    *,
    page_id: str,
    space_id: str,
    parent_page_id: str | None = None,
    placement: str = "first",
    rng: random.Random | None = None,
) -> str:
    """Compute a fractional index placing a page first or last among siblings.

    Reads the destination's existing children (following pagination, so a
    parent with more than one page of children still yields the true extremes)
    and generates a key before the smallest or after the largest.

    Args:
        client: Authenticated Docmost client.
        page_id: The page being moved, excluded from the sibling scan.
        space_id: Space UUID of the destination.
        parent_page_id: Destination parent, or None for the space root.
        placement: "first" or "last".
        rng: Random source, injectable for deterministic tests.

    Returns:
        A position string accepted by POST /pages/move.
    """
    if parent_page_id:
        siblings = get_all_page_children(client, parent_page_id, space_id=space_id)
    else:
        siblings = get_all_sidebar_pages(client, space_id)

    positions = sorted(
        str(sibling["position"])
        for sibling in siblings
        if sibling.get("id") != page_id and sibling.get("position")
    )

    if not positions:
        if siblings:
            print_warning(
                "Could not read sibling ordering keys from this server; placing the "
                "page using a default position."
            )
        return generate_key_between(None, None, rng=rng)

    try:
        if placement == "last":
            return generate_key_between(positions[-1], None, rng=rng)
        return generate_key_between(None, positions[0], rng=rng)
    except PositionError as exc:
        print_error(
            f"Cannot compute a position among the destination's pages ({exc}). "
            "Reorder the pages in the Docmost web UI, or pass an explicit "
            "--position key.",
            exit_code=1,
        )


def get_page_content(client: DocmostClient, page_id: str) -> dict[str, Any]:
    """Get page content and metadata.

    Tries POST /pages/content (Enterprise v0.70+) first, then falls back
    to POST /pages/info which may include content on both editions.

    Args:
        client: Authenticated Docmost client.
        page_id: Page UUID.

    Returns:
        Dict with page metadata and content (ProseMirror JSON).
    """
    # Get page info first (needed for metadata and fallback content)
    info = get_page_info(client, page_id)

    # Try Enterprise content endpoint (silently — may not exist on Community)
    response = client.post_raw("/pages/content", json={"pageId": page_id}, raise_on_error=False)
    if response.is_success:
        try:
            content_data = response.json()
            data = content_data.get("data", content_data)
            info["content"] = data.get("content", data)
            return info
        except (ValueError, KeyError):
            pass

    # Fall back to content from /pages/info (already fetched)
    if "content" in info and info["content"]:
        return info

    print_error(
        "Page content not available via REST on this instance. "
        "This may require Enterprise edition (v0.70+). "
        "Try 'docmost-cli page get <id> --raw' or access the page in the web UI.",
        exit_code=1,
    )


def list_recent_pages(
    client: DocmostClient,
    space_id: str,
    *,
    limit: int | None = None,
    cursor: str | None = None,
) -> dict[str, Any]:
    """List recent pages in a space with cursor-based pagination.

    Args:
        client: Authenticated Docmost client.
        space_id: Space UUID.
        limit: Max results to return.
        cursor: Pagination cursor.

    Returns:
        Raw API response dict.
    """
    body = build_body({"spaceId": space_id}, limit=limit, cursor=cursor)
    return client.post("/pages/recent", json=body)


def duplicate_page(client: DocmostClient, page_id: str) -> dict[str, Any]:
    """Duplicate a page.

    Args:
        client: Authenticated Docmost client.
        page_id: Page UUID to duplicate.

    Returns:
        Raw API response dict (should contain new page ID).
    """
    return client.post("/pages/duplicate", json={"pageId": page_id})


def copy_page(client: DocmostClient, page_id: str, space_id: str) -> dict[str, Any]:
    """Copy a page to a different space.

    Args:
        client: Authenticated Docmost client.
        page_id: Page UUID to copy.
        space_id: Target space UUID.

    Returns:
        Raw API response dict (should contain new page ID).
    """
    return client.post("/pages/copy", json={"pageId": page_id, "spaceId": space_id})


def get_page_children(
    client: DocmostClient,
    page_id: str,
    *,
    space_id: str | None = None,
    limit: int | None = None,
    cursor: str | None = None,
) -> dict[str, Any]:
    """List direct child pages (one page of results).

    Uses /pages/sidebar-pages with pageId (works on Community edition), which
    merges PaginationOptions into the same request body. Without an explicit
    limit the server returns only its default page size (20), so callers that
    need every child should use get_all_page_children().

    If space_id is not provided, resolves it from the page's metadata.

    Args:
        client: Authenticated Docmost client.
        page_id: Parent page UUID.
        space_id: Space UUID (resolved from page info if not provided).
        limit: Max results per request.
        cursor: Pagination cursor.

    Returns:
        Raw API response dict.
    """
    if not space_id:
        info = get_page_info(client, page_id)
        space_id = info.get("spaceId", "")
    body = build_body({"spaceId": space_id, "pageId": page_id}, limit=limit, cursor=cursor)
    return client.post("/pages/sidebar-pages", json=body)


def get_all_page_children(
    client: DocmostClient,
    page_id: str,
    *,
    space_id: str | None = None,
) -> list[dict[str, Any]]:
    """List every direct child page, following pagination.

    Args:
        client: Authenticated Docmost client.
        page_id: Parent page UUID.
        space_id: Space UUID (resolved from page info if not provided).

    Returns:
        List of child page dicts.
    """
    from docmost_cli.api.pagination import paginate_all

    if not space_id:
        info = get_page_info(client, page_id)
        space_id = info.get("spaceId", "")
    return paginate_all(get_page_children, client=client, page_id=page_id, space_id=space_id).items


def get_all_sidebar_pages(client: DocmostClient, space_id: str) -> list[dict[str, Any]]:
    """List every root-level page in a space, following pagination.

    Args:
        client: Authenticated Docmost client.
        space_id: Space UUID.

    Returns:
        List of root page dicts.
    """
    from docmost_cli.api.pagination import paginate_all

    return paginate_all(get_sidebar_pages, client=client, space_id=space_id).items


def get_page_history(
    client: DocmostClient,
    page_id: str,
    *,
    limit: int | None = None,
    cursor: str | None = None,
) -> dict[str, Any]:
    """Get page version history.

    Args:
        client: Authenticated Docmost client.
        page_id: Page UUID.
        limit: Max results.
        cursor: Pagination cursor.

    Returns:
        Raw API response dict.
    """
    body = build_body({"pageId": page_id}, limit=limit, cursor=cursor)
    return client.post("/pages/history", json=body)


def export_page(client: DocmostClient, page_id: str, fmt: str = "md") -> str:
    """Export page content.

    Docmost returns a ZIP file containing the exported content.
    This function extracts the content from the ZIP.

    Args:
        client: Authenticated Docmost client.
        page_id: Page UUID.
        fmt: Export format ("md" or "html"). Accepts "md" as alias for "markdown".

    Returns:
        Exported content as a string.
    """
    import io
    import zipfile

    # Docmost expects "markdown" not "md"
    api_format = "markdown" if fmt == "md" else fmt
    response = client.post_raw("/pages/export", json={"pageId": page_id, "format": api_format})

    # Response is a ZIP file — extract content from it
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        names = zf.namelist()
        if not names:
            print_error("Export ZIP is empty.", exit_code=1)
        return zf.read(names[0]).decode("utf-8")


def get_sidebar_pages(
    client: DocmostClient,
    space_id: str,
    *,
    limit: int | None = None,
    cursor: str | None = None,
) -> dict[str, Any]:
    """Get one page of root-level pages for a space.

    Returns nested structure with children arrays, used for --tree view.

    Args:
        client: Authenticated Docmost client.
        space_id: Space UUID.
        limit: Max results per request.
        cursor: Pagination cursor.

    Returns:
        Raw API response dict with nested page tree.
    """
    body = build_body({"spaceId": space_id}, limit=limit, cursor=cursor)
    return client.post("/pages/sidebar-pages", json=body)


def import_page(
    client: DocmostClient,
    *,
    space_id: str,
    file_name: str,
    file_bytes: bytes,
    parent_page_id: str | None = None,
) -> dict[str, Any]:
    """Import a file as a new page via multipart upload.

    Args:
        client: Authenticated Docmost client.
        space_id: Target space UUID.
        file_name: Original filename (used for MIME detection and upload).
        file_bytes: Raw file content bytes.
        parent_page_id: Parent page UUID (optional).

    Returns:
        Raw API response dict (should contain new page ID).
    """
    mime = "text/html" if file_name.lower().endswith((".html", ".htm")) else "text/markdown"
    files = {"file": (file_name, file_bytes, mime)}
    data = build_body({"spaceId": space_id}, parentPageId=parent_page_id)
    return client.post_multipart("/pages/import", data=data, files=files)


def build_page_tree(
    client: DocmostClient,
    space_id: str,
    *,
    max_depth: int = 10,
) -> list[dict[str, Any]]:
    """Build full page tree, filling in missing children recursively.

    Starts with /pages/sidebar-pages, then uses /pages/children to
    fill in any empty children arrays (sidebar API may not return them).

    Args:
        client: Authenticated Docmost client.
        space_id: Space UUID.
        max_depth: Maximum recursion depth to prevent runaway.

    Returns:
        List of page dicts with populated children arrays.
    """
    pages = get_all_sidebar_pages(client, space_id)

    for page in pages:
        _fill_children(client, page, space_id=space_id, depth=0, max_depth=max_depth)

    return pages


def _fill_children(
    client: DocmostClient,
    page: dict[str, Any],
    *,
    space_id: str,
    depth: int,
    max_depth: int,
) -> None:
    """Recursively fetch children if the sidebar API returned them empty."""
    if depth >= max_depth:
        return

    children = page.get("children", [])

    # If sidebar returned empty children, fetch via sidebar-pages with pageId
    if not children and page.get("hasChildren", False):
        try:
            children = get_all_page_children(client, page["id"], space_id=space_id)
            page["children"] = children
        except SystemExit as exc:
            if exc.code not in (4,):
                raise
            page["children"] = []
            return

    for child in children:
        _fill_children(client, child, space_id=space_id, depth=depth + 1, max_depth=max_depth)

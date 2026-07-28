"""Tree view rendering for hierarchical page lists.

Renders nested page structures using Unicode box-drawing characters.
"""

from typing import Any

from docmost_cli.output.formatter import print_rendered

__all__ = ["print_tree"]

MAX_TITLE_LEN = 60


def print_tree(pages: list[dict[str, Any]]) -> None:
    """Render a nested page tree using box-drawing characters.

    Expects pages with nested 'children' arrays, as returned by
    POST /pages/sidebar-pages.

    Args:
        pages: List of page dicts, each may have a 'children' key.
    """
    for i, page in enumerate(pages):
        is_last = i == len(pages) - 1
        _print_node(page, "", is_last)


def _print_node(
    page: dict[str, Any],
    prefix: str,
    is_last: bool,
) -> None:
    """Print a single tree node and recurse into children."""
    connector = "\\-- " if is_last else "+-- "

    icon = page.get("icon", "") or ""
    title = page.get("title", page.get("id", "???"))

    # Truncate long titles
    if len(title) > MAX_TITLE_LEN:
        title = title[: MAX_TITLE_LEN - 3] + "..."

    # Rich uses LegacyWindowsRenderer which bypasses sys.stdout encoding.
    # Strip emoji that can't be encoded on Windows cp1252.
    safe_icon = ""
    if icon:
        try:
            icon.encode("cp1252")
            safe_icon = icon
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass

    label = f"{safe_icon} {title}".strip() if safe_icon else title
    print_rendered(f"{prefix}{connector}{label}")

    # Recurse into children
    children = page.get("children", [])
    if not children:
        return

    child_prefix = prefix + ("    " if is_last else "|   ")
    for j, child in enumerate(children):
        child_is_last = j == len(children) - 1
        _print_node(child, child_prefix, child_is_last)

"""Pull space pages from Docmost server to local directory."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from docmost_cli.api.client import DocmostClient
from docmost_cli.api.pages import build_page_tree, get_page_content
from docmost_cli.api.spaces import resolve_space_id
from docmost_cli.convert.prosemirror_to_md import convert_to_markdown
from docmost_cli.output.formatter import print_error, print_progress
from docmost_cli.sync.frontmatter import write_sync_file
from docmost_cli.sync.manifest import (
    build_manifest,
    build_page_entry,
    compute_content_hash,
    load_manifest,
    sanitize_filename,
    save_manifest,
)

__all__ = ["PullResult", "flatten_tree", "pull_space"]


@dataclass
class PullResult:
    """Result of a pull operation."""

    pages_pulled: int
    dir_path: Path


def flatten_tree(
    pages: list[dict[str, Any]],
    parent_id: str | None = None,
) -> list[dict[str, Any]]:
    """Flatten nested page tree into a flat list with parent_id.

    Args:
        pages: Nested page tree from build_page_tree.
        parent_id: Parent page ID for current level.

    Returns:
        Flat list of dicts with: id, title, icon, parent_id
    """
    result: list[dict[str, Any]] = []
    for page in pages:
        result.append(
            {
                "id": page["id"],
                "title": page.get("title", ""),
                "icon": page.get("icon") or "",
                "parent_id": parent_id,
            }
        )
        children = page.get("children", [])
        if children:
            result.extend(flatten_tree(children, parent_id=page["id"]))
    return result


def pull_space(
    client: DocmostClient,
    space_slug: str,
    dir_path: Path,
    *,
    force: bool = False,
) -> PullResult:
    """Pull all pages from a space to a local directory.

    Algorithm:
    1. Resolve space slug to ID
    2. Build full page tree
    3. Flatten tree to list with parent_id
    4. For each page: fetch content, convert to markdown, write file
    5. Write manifest LAST (atomic commit point)

    Args:
        client: Authenticated Docmost client.
        space_slug: Space slug identifier.
        dir_path: Target directory path.
        force: Overwrite existing files without warning.

    Returns:
        PullResult with count and path.
    """
    # 1. Resolve space
    space_id = resolve_space_id(client, space_slug)

    # 2. Build page tree
    print_progress(f"Fetching page tree for '{space_slug}'...")
    tree = build_page_tree(client, space_id)

    # 3. Flatten
    flat_pages = flatten_tree(tree)
    total = len(flat_pages)

    if total == 0:
        # Empty space -- create dir + empty manifest
        dir_path.mkdir(parents=True, exist_ok=True)
        manifest = build_manifest(space_slug, space_id, [])
        save_manifest(dir_path, manifest)
        print_progress(f"Pulled 0 pages from '{space_slug}' -> {dir_path}")
        return PullResult(pages_pulled=0, dir_path=dir_path)

    # 4. Check target directory
    if dir_path.exists():
        existing_manifest = load_manifest(dir_path)
        if existing_manifest and not force:
            print_error(
                f"Directory '{dir_path}' already has synced data. Use --force to overwrite."
            )
        # If dir exists with no manifest OR force is set, proceed

    dir_path.mkdir(parents=True, exist_ok=True)

    # 5. Fetch content and write files
    page_entries: list[dict[str, Any]] = []
    for i, page_info in enumerate(flat_pages, 1):
        page_id = page_info["id"]
        title = page_info.get("title") or "Untitled"
        print_progress(f"Pulling {i}/{total}: {title}")

        # Fetch content
        content_data = get_page_content(client, page_id)
        pm_content = content_data.get("content")

        markdown = convert_to_markdown(pm_content) if pm_content else ""

        # Generate filename and write file
        filename = sanitize_filename(title, page_id)
        metadata = {
            "id": page_id,
            "title": title,
            "parent_id": page_info["parent_id"] or "",
            "icon": page_info["icon"],
        }
        write_sync_file(dir_path / filename, metadata, markdown)

        # Build manifest entry
        content_hash = compute_content_hash(markdown)
        entry = build_page_entry(
            title=title,
            filename=filename,
            parent_id=page_info["parent_id"],
            icon=page_info["icon"],
            content_hash=content_hash,
        )
        page_entries.append({"id": page_id, **entry})

    # 6. Write manifest LAST
    manifest = build_manifest(space_slug, space_id, page_entries)
    save_manifest(dir_path, manifest)

    print_progress(f"Pulled {total} pages from '{space_slug}' -> {dir_path}")
    return PullResult(pages_pulled=total, dir_path=dir_path)

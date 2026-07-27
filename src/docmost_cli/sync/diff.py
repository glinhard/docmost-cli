"""Compute diff between local sync files and manifest state."""

import enum
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = ["ChangeType", "PageChange", "SyncDiff", "compute_diff"]


class ChangeType(enum.Enum):
    """Types of changes detected between local and manifest."""

    NEW = "new"
    CONTENT_CHANGED = "content_changed"
    TITLE_CHANGED = "title_changed"
    MOVED = "moved"
    ICON_CHANGED = "icon_changed"
    DELETED = "deleted"


@dataclass
class PageChange:
    """A detected change for a single page."""

    page_id: str  # Empty string for NEW pages
    filename: str
    changes: set[ChangeType] = field(default_factory=set)
    local_meta: dict[str, str] | None = None  # From frontmatter
    local_body: str | None = None  # Markdown body
    manifest_entry: dict[str, Any] | None = None  # From manifest


@dataclass
class SyncDiff:
    """Summary of all changes between local files and manifest."""

    new: list[PageChange] = field(default_factory=list)
    modified: list[PageChange] = field(default_factory=list)
    moved: list[PageChange] = field(default_factory=list)
    deleted: list[PageChange] = field(default_factory=list)
    unchanged: int = 0

    @property
    def has_changes(self) -> bool:
        """Return True if any changes were detected."""
        return bool(self.new or self.modified or self.moved or self.deleted)


def compute_diff(manifest: dict[str, Any], dir_path: Path) -> SyncDiff:
    """Compute diff between local files and manifest.

    Algorithm:
    1. Load manifest pages dict (keyed by page_id)
    2. Scan dir for .md files, parse frontmatter of each
    3. For each local file:
       - If has id AND id in manifest: compare hash, title, parent_id, icon
       - If has no id (empty string): NEW
       - If has id NOT in manifest: treat as existing, classify changes
    4. For each manifest entry not matched by any local file: DELETED

    A single page can appear in BOTH modified and moved if content AND parent changed.

    Args:
        manifest: Loaded manifest dict.
        dir_path: Directory containing .md files.

    Returns:
        SyncDiff summarizing all changes.
    """
    from docmost_cli.sync.frontmatter import read_sync_file
    from docmost_cli.sync.manifest import compute_content_hash

    diff = SyncDiff()
    manifest_pages = manifest.get("pages", {})
    seen_ids: set[str] = set()

    # Scan local .md files
    for md_file in sorted(dir_path.glob("*.md")):
        meta, body = read_sync_file(md_file)
        page_id = meta.get("id", "").strip()

        if not page_id:
            # NEW page -- no server ID yet
            change = PageChange(
                page_id="",
                filename=md_file.name,
                changes={ChangeType.NEW},
                local_meta=meta,
                local_body=body,
            )
            diff.new.append(change)
            continue

        seen_ids.add(page_id)
        manifest_entry = manifest_pages.get(page_id)

        # Compute current content hash
        current_hash = compute_content_hash(body)

        # Determine changes
        changes: set[ChangeType] = set()

        if manifest_entry:
            if current_hash != manifest_entry.get("content_hash", ""):
                changes.add(ChangeType.CONTENT_CHANGED)
            if meta.get("title", "") != manifest_entry.get("title", ""):
                changes.add(ChangeType.TITLE_CHANGED)
            if meta.get("icon", "") != manifest_entry.get("icon", ""):
                changes.add(ChangeType.ICON_CHANGED)

            # Compare parent_id (normalize empty string and None)
            local_parent = meta.get("parent_id", "").strip() or None
            manifest_parent = manifest_entry.get("parent_id") or None
            if local_parent != manifest_parent:
                changes.add(ChangeType.MOVED)
        else:
            # ID not in manifest -- treat as content-changed to trigger update
            changes.add(ChangeType.CONTENT_CHANGED)

        if not changes:
            diff.unchanged += 1
            continue

        page_change = PageChange(
            page_id=page_id,
            filename=md_file.name,
            changes=changes,
            local_meta=meta,
            local_body=body,
            manifest_entry=manifest_entry,
        )

        # Categorize: if content or title or icon changed -> modified
        # If parent changed -> moved (can be both modified AND moved)
        if changes & {
            ChangeType.CONTENT_CHANGED,
            ChangeType.TITLE_CHANGED,
            ChangeType.ICON_CHANGED,
        }:
            diff.modified.append(page_change)
        if ChangeType.MOVED in changes:
            diff.moved.append(page_change)

    # Check for deleted pages (in manifest but no local file)
    for page_id, entry in manifest_pages.items():
        if page_id not in seen_ids:
            change = PageChange(
                page_id=page_id,
                filename=entry.get("filename", ""),
                changes={ChangeType.DELETED},
                manifest_entry=entry,
            )
            diff.deleted.append(change)

    return diff

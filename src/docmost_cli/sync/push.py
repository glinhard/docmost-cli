"""Push local changes to Docmost server."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from docmost_cli.output.formatter import _err_console as _err
from docmost_cli.sync.diff import ChangeType, PageChange, SyncDiff

if TYPE_CHECKING:
    from pathlib import Path

    from docmost_cli.api.client import DocmostClient

__all__ = ["PushResult", "push_space"]


@dataclass
class PushResult:
    """Result of a push operation."""

    created: int = 0
    updated: int = 0
    moved: int = 0
    deleted: int = 0
    unchanged: int = 0
    id_remaps: dict[str, str] = field(default_factory=dict)  # old_id -> new_id


def push_space(
    client: DocmostClient,
    space_slug: str,
    dir_path: Path,
    *,
    dry_run: bool = False,
    delete: bool = False,
    allow_recreate: bool = False,
    diff: SyncDiff | None = None,
) -> PushResult:
    """Push local changes to Docmost server.

    Args:
        client: Authenticated Docmost client.
        space_slug: Space slug identifier.
        dir_path: Directory containing synced files.
        dry_run: If True, show plan without executing changes.
        delete: If True, delete server pages not found locally.
        allow_recreate: If True, fall back to delete+recreate on servers that
            cannot update content in place. This assigns new page IDs.
        diff: Pre-computed diff (avoids recomputing if caller already has it).

    Returns:
        PushResult with counts and any ID remaps.
    """
    from docmost_cli.api.spaces import resolve_space_id
    from docmost_cli.output.formatter import print_error
    from docmost_cli.sync.diff import compute_diff
    from docmost_cli.sync.manifest import load_manifest, save_manifest

    space_id = resolve_space_id(client, space_slug)

    manifest = load_manifest(dir_path)
    if manifest is None:
        print_error(f"No manifest found in '{dir_path}'. Run 'sync pull' first.")

    if diff is None:
        diff = compute_diff(manifest, dir_path)
    result = PushResult(unchanged=diff.unchanged)

    if not diff.has_changes:
        _err.print("No changes to push.")
        return result

    # Display summary
    _print_summary(diff)

    if dry_run:
        _print_dry_run(diff)
        return result

    # --- Execute changes ---

    id_remap: dict[str, str] = {}  # old_id -> new_id

    try:
        _execute_push(
            client,
            space_id=space_id,
            dir_path=dir_path,
            diff=diff,
            manifest=manifest,
            result=result,
            delete=delete,
            allow_recreate=allow_recreate,
            id_remap=id_remap,
        )
    finally:
        result.id_remaps = id_remap
        # Always persist progress: a mid-push abort must not lose the record of
        # pages already created, or the next push would duplicate them.
        save_manifest(dir_path, manifest)

    if id_remap:
        _err.print(
            f"[yellow]{len(id_remap)} page(s) were recreated and got new IDs. "
            "Inbound wiki links, comments and page history for those pages are "
            "gone.[/yellow]"
        )

    _err.print(
        f"Pushed to '{space_slug}': "
        f"{result.created} created, {result.updated} updated, "
        f"{result.moved} moved, {result.deleted} deleted"
    )
    return result


def _execute_push(
    client: DocmostClient,
    *,
    space_id: str,
    dir_path: Path,
    diff: SyncDiff,
    manifest: dict[str, Any],
    result: PushResult,
    delete: bool,
    allow_recreate: bool,
    id_remap: dict[str, str],
) -> None:
    """Run the create/update/move/delete phases of a push.

    Mutates ``manifest``, ``result`` and ``id_remap`` in place so the caller
    can persist partial progress if a phase aborts.
    """
    from docmost_cli.api.pages import (
        CONTENT_UNSUPPORTED_MESSAGE,
        create_and_place_page,
        delete_page,
        move_page,
        resolve_position,
        try_update_page_content,
        update_page_content,
        update_page_meta,
    )
    from docmost_cli.output.formatter import print_error
    from docmost_cli.sync.frontmatter import write_sync_file
    from docmost_cli.sync.manifest import build_page_entry, compute_content_hash

    # Whether this server applies content sent to POST /pages/update (v0.71+).
    # Probed once on the first content change, then cached.
    content_update_ok: bool | None = None
    recreate_warned = False
    content_change_count = sum(
        1 for change in diff.modified if ChangeType.CONTENT_CHANGED in change.changes
    )

    # Phase A: Create new pages (topological order)
    existing_ids = set(manifest.get("pages", {}).keys())
    sorted_new = _topological_sort(diff.new, existing_ids)

    for change in sorted_new:
        meta = change.local_meta or {}
        body = change.local_body or ""
        title = meta.get("title", "Untitled")
        parent_id = meta.get("parent_id", "").strip() or None
        icon = meta.get("icon", "").strip()

        # Resolve parent_id through remap table
        if parent_id and parent_id in id_remap:
            parent_id = id_remap[parent_id]

        _err.print(f"  Creating: {title}")
        new_id = create_and_place_page(
            client,
            space_id=space_id,
            title=title,
            content=body,
            parent_page_id=parent_id,
            icon=icon,
        )

        # Write ID back to frontmatter
        meta["id"] = new_id
        write_sync_file(dir_path / change.filename, meta, body)

        # Update manifest
        content_hash = compute_content_hash(body)
        manifest["pages"][new_id] = build_page_entry(
            title=title,
            filename=change.filename,
            parent_id=parent_id,
            icon=icon,
            content_hash=content_hash,
        )
        existing_ids.add(new_id)
        result.created += 1

    # Phase B: Update modified pages
    for change in diff.modified:
        meta = change.local_meta or {}
        body = change.local_body or ""
        page_id = change.page_id
        title = meta.get("title", "")
        parent_id = meta.get("parent_id", "").strip() or None
        icon = meta.get("icon", "").strip()

        has_content_change = ChangeType.CONTENT_CHANGED in change.changes
        has_meta_change = bool(change.changes & {ChangeType.TITLE_CHANGED, ChangeType.ICON_CHANGED})

        # Content update
        if has_content_change:
            if content_update_ok is None:
                # First attempt doubles as the capability probe.
                content_update_ok = try_update_page_content(client, page_id=page_id, content=body)
                if content_update_ok:
                    _err.print(f"  Updated: {title}")
            elif content_update_ok:
                update_page_content(client, page_id=page_id, content=body)
                _err.print(f"  Updated: {title}")

            if not content_update_ok:
                if not allow_recreate:
                    print_error(CONTENT_UNSUPPORTED_MESSAGE, exit_code=1)
                if not recreate_warned:
                    _err.print(
                        f"[yellow]Warning: this server cannot update page content in "
                        f"place. --allow-recreate will DELETE and RE-CREATE "
                        f"{content_change_count} page(s). Their page IDs change; "
                        f"inbound wiki links, comments, page history and shared URLs "
                        f"to those pages will break.[/yellow]"
                    )
                    recreate_warned = True
                _err.print(f"  Replacing: {title}")
                new_id = _recreate_page(
                    client,
                    space_id=space_id,
                    old_page_id=page_id,
                    title=title,
                    content=body,
                    parent_id=parent_id,
                    icon=icon,
                )
                id_remap[page_id] = new_id
                meta["id"] = new_id
                write_sync_file(dir_path / change.filename, meta, body)
                manifest["pages"].pop(page_id, None)
                page_id = new_id

        # Meta update (title/icon) — skip if the page was just recreated with them
        if has_meta_change and not (has_content_change and not content_update_ok):
            _err.print(f"  Metadata: {title}")
            update_page_meta(
                client,
                page_id=page_id,
                title=title if ChangeType.TITLE_CHANGED in change.changes else None,
                icon=icon if ChangeType.ICON_CHANGED in change.changes else None,
            )

        # Update manifest entry
        content_hash = compute_content_hash(body)
        manifest["pages"][page_id] = build_page_entry(
            title=title,
            filename=change.filename,
            parent_id=parent_id,
            icon=icon,
            content_hash=content_hash,
        )
        result.updated += 1

    # Phase B2: Move pages (that weren't already handled as part of modified)
    modified_ids = {c.page_id for c in diff.modified}
    for change in diff.moved:
        if change.page_id in modified_ids:
            continue

        meta = change.local_meta or {}
        page_id = change.page_id
        parent_id = meta.get("parent_id", "").strip() or None
        title = meta.get("title", page_id)

        # Check remap
        if page_id in id_remap:
            page_id = id_remap[page_id]
        if parent_id and parent_id in id_remap:
            parent_id = id_remap[parent_id]

        _err.print(f"  Moving: {title}")
        move_page(
            client,
            page_id=page_id,
            position=resolve_position(
                client,
                page_id=page_id,
                space_id=space_id,
                parent_page_id=parent_id,
                placement="first",
            ),
            parent_page_id=parent_id,
        )

        # Update manifest
        if page_id in manifest["pages"]:
            manifest["pages"][page_id]["parent_id"] = parent_id
        result.moved += 1

    # Phase C: Deletions
    if diff.deleted:
        if delete:
            for change in diff.deleted:
                entry = change.manifest_entry or {}
                _err.print(f"  Deleting: {entry.get('title', change.page_id)}")
                delete_page(client, change.page_id)
                manifest["pages"].pop(change.page_id, None)
                result.deleted += 1
        else:
            _err.print(
                f"  [yellow]{len(diff.deleted)} page(s) on server not found locally. "
                "Use --delete to remove.[/yellow]"
            )


def _recreate_page(
    client: DocmostClient,
    *,
    space_id: str,
    old_page_id: str,
    title: str,
    content: str,
    parent_id: str | None,
    icon: str,
) -> str:
    """Destructive content replacement: create the new page, then delete the old.

    Only reachable behind ``--allow-recreate``, for servers older than v0.71
    that cannot apply content through POST /pages/update. The old page is only
    deleted once the new one is confirmed created, but the page ID and slug
    still change and history, comments and inbound links are lost.

    Returns:
        New page ID.
    """
    from docmost_cli.api.pages import create_and_place_page, delete_page

    new_id = create_and_place_page(
        client,
        space_id=space_id,
        title=title,
        content=content,
        parent_page_id=parent_id,
        icon=icon,
    )
    delete_page(client, old_page_id)
    return new_id


def _topological_sort(new_changes: list[PageChange], existing_ids: set[str]) -> list[PageChange]:
    """Sort new pages so parents are created before children.

    Pages with no parent or whose parent already exists on the server
    are placed first. Pages whose parent_id references a server ID not
    yet in the resolved set are deferred. Note: new pages have empty
    page_id, so cross-references between new pages are not supported —
    only references to existing server IDs are resolved.

    Args:
        new_changes: List of PageChange with NEW type.
        existing_ids: Set of page IDs already on the server.

    Returns:
        Sorted list of PageChange.
    """
    result = []
    remaining = list(new_changes)
    resolved = set(existing_ids)

    max_iterations = len(remaining) + 1
    for _ in range(max_iterations):
        if not remaining:
            break
        next_remaining = []
        for change in remaining:
            meta = change.local_meta or {}
            parent_id = meta.get("parent_id", "").strip() or None
            if parent_id is None or parent_id in resolved:
                result.append(change)
            else:
                next_remaining.append(change)
        if len(next_remaining) == len(remaining):
            # No progress — circular or broken parent reference — add remaining
            result.extend(next_remaining)
            break
        remaining = next_remaining

    return result


def _print_summary(diff: SyncDiff) -> None:
    """Print change summary to stderr."""
    lines: list[str] = []
    if diff.new:
        lines.append(f"  Create:    {len(diff.new)} page(s)")
    if diff.modified:
        lines.append(f"  Update:    {len(diff.modified)} page(s)")
    if diff.moved:
        move_only = [c for c in diff.moved if c not in diff.modified]
        if move_only:
            lines.append(f"  Move:      {len(move_only)} page(s)")
    if diff.deleted:
        lines.append(f"  Delete:    {len(diff.deleted)} page(s)")
    lines.append(f"  Unchanged: {diff.unchanged} page(s)")
    _err.print("Push plan:")
    for line in lines:
        _err.print(line)


def _print_dry_run(diff: SyncDiff) -> None:
    """Print detailed plan to stdout for scripting."""
    import sys

    for change in diff.new:
        meta = change.local_meta or {}
        sys.stdout.write(f"CREATE {change.filename} ({meta.get('title', '?')})\n")
    for change in diff.modified:
        types = ", ".join(c.value for c in change.changes if c != ChangeType.MOVED)
        sys.stdout.write(f"UPDATE {change.filename} ({types})\n")
    for change in diff.moved:
        if change not in diff.modified:
            meta = change.local_meta or {}
            sys.stdout.write(
                f"MOVE   {change.filename} -> parent:{meta.get('parent_id', 'root')}\n"
            )
    for change in diff.deleted:
        entry = change.manifest_entry or {}
        sys.stdout.write(f"DELETE {entry.get('filename', '?')} ({entry.get('title', '?')})\n")

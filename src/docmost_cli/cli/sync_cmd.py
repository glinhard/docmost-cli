"""Sync subcommands."""

import sys
from pathlib import Path

import typer

from docmost_cli.cli.main import get_client, state

__all__ = ["sync_app"]

sync_app: typer.Typer = typer.Typer(name="sync", help="Sync space pages to/from local directory.")


@sync_app.command("pull")
def sync_pull_cmd(
    space_slug: str = typer.Argument(help="Space slug to pull pages from"),
    dir_path: Path = typer.Option(
        None, "--dir", help="Target directory (default: ./<space-slug>/)"
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite local changes without warning"),
) -> None:
    """Download all pages from a space to local Markdown files.

    Creates a directory with one .md file per page (with YAML frontmatter)
    and a .docmost-manifest.json tracking sync state.

    See also: sync push (upload changes), sync status (show changes).
    """
    from docmost_cli.sync.pull import pull_space

    client = get_client()
    target = dir_path or Path(space_slug)
    pull_space(client, space_slug, target, force=force)


@sync_app.command("status")
def sync_status_cmd(
    space_slug: str = typer.Argument(help="Space slug to check"),
    dir_path: Path = typer.Option(
        None, "--dir", help="Directory to check (default: ./<space-slug>/)"
    ),
) -> None:
    """Show changes between local files and last-pulled state.

    See also: sync push (upload changes), sync pull (download from server).
    """
    from docmost_cli.sync.diff import compute_diff, describe_changes
    from docmost_cli.sync.manifest import require_manifest

    target = dir_path or Path(space_slug)
    diff = compute_diff(require_manifest(target), target)

    if not diff.has_changes:
        sys.stdout.write("No changes.\n")
        return

    if diff.new:
        sys.stdout.write(f"  New:       {len(diff.new)} file(s)\n")
        for c in diff.new:
            sys.stdout.write(f"    + {c.filename}\n")
    if diff.modified:
        sys.stdout.write(f"  Modified:  {len(diff.modified)} file(s)\n")
        for c in diff.modified:
            sys.stdout.write(f"    ~ {c.filename} ({describe_changes(c.changes)})\n")
    move_only = diff.move_only
    if move_only:
        sys.stdout.write(f"  Moved:     {len(move_only)} file(s)\n")
        for c in move_only:
            sys.stdout.write(f"    -> {c.filename}\n")
    if diff.deleted:
        sys.stdout.write(f"  Deleted:   {len(diff.deleted)} file(s)\n")
        for c in diff.deleted:
            entry = c.manifest_entry or {}
            sys.stdout.write(f"    - {entry.get('filename', '?')}\n")
    sys.stdout.write(f"  Unchanged: {diff.unchanged} file(s)\n")


@sync_app.command("push")
def sync_push_cmd(
    space_slug: str = typer.Argument(help="Space slug to push changes to"),
    dir_path: Path = typer.Option(
        None, "--dir", help="Source directory (default: ./<space-slug>/)"
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show changes without executing"),
    delete: bool = typer.Option(False, "--delete", help="Delete server pages not found locally"),
    allow_recreate: bool = typer.Option(
        False,
        "--allow-recreate",
        help=(
            "On servers older than Docmost v0.71, replace pages by delete+recreate "
            "instead of aborting (ASSIGNS NEW PAGE IDs and breaks links and history)"
        ),
    ),
) -> None:
    """Upload local changes to Docmost server.

    Requires a prior 'sync pull' to establish the manifest.
    Use --dry-run to preview changes before applying.

    Content is updated in place on Docmost v0.71 and newer, so page IDs are
    preserved. Older servers abort unless --allow-recreate is given.

    See also: sync status (preview changes), sync pull (download from server).
    """
    from docmost_cli.sync.diff import compute_diff
    from docmost_cli.sync.manifest import require_manifest
    from docmost_cli.sync.push import push_space

    client = get_client()
    target = dir_path or Path(space_slug)

    # Pre-compute diff once — reused for confirmation prompt and push_space
    pre_diff = None
    if not dry_run and not state.yes:
        pre_diff = compute_diff(require_manifest(target), target)
        if pre_diff.has_changes:
            typer.confirm("Push changes?", abort=True)

    push_space(
        client,
        space_slug,
        target,
        dry_run=dry_run,
        delete=delete,
        allow_recreate=allow_recreate,
        diff=pre_diff,
    )

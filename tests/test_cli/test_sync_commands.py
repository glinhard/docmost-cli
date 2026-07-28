"""Tests for sync CLI commands (pull, status, push)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from typer.testing import CliRunner

if TYPE_CHECKING:
    from pathlib import Path

from docmost_cli.cli.main import app
from docmost_cli.sync.frontmatter import write_sync_file
from docmost_cli.sync.manifest import (
    MANIFEST_FILENAME,
    build_page_entry,
    compute_content_hash,
    save_manifest,
)

runner = CliRunner()

_TEST_URL = "https://docs.example.com"
FAKE_PAGE_ID = "019a2a69-bbbb-cccc-dddd-eeeeeeeeeeee"
FAKE_SPACE_ID = "space-uuid-123"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_manifest(pages: dict | None = None) -> dict:
    return {
        "version": 1,
        "space_slug": "eng",
        "space_id": FAKE_SPACE_ID,
        "synced_at": "2026-01-01T00:00:00+00:00",
        "pages": pages or {},
    }


def _write_page(
    dir_path: Path,
    filename: str,
    *,
    page_id: str = "",
    title: str = "Test Page",
    parent_id: str = "",
    icon: str = "",
    body: str = "Some content.\n",
) -> None:
    meta: dict[str, str] = {}
    if page_id is not None:
        meta["id"] = page_id
    meta["title"] = title
    if parent_id:
        meta["parent_id"] = parent_id
    if icon:
        meta["icon"] = icon
    write_sync_file(dir_path / filename, meta, body)


def _setup_synced_dir(
    tmp_path: Path,
    pages: dict | None = None,
    dir_name: str = "eng",
) -> Path:
    target = tmp_path / dir_name
    target.mkdir(parents=True, exist_ok=True)
    manifest = _make_manifest(pages)
    save_manifest(target, manifest)
    return target


def _mock_resolve_space(httpx_mock, slug: str = "eng") -> None:
    httpx_mock.add_response(
        url=f"{_TEST_URL}/api/spaces",
        json={"data": {"items": [{"id": FAKE_SPACE_ID, "slug": slug, "name": slug.capitalize()}]}},
    )


def _mock_sidebar_pages(httpx_mock, pages: list[dict]) -> None:
    httpx_mock.add_response(
        url=f"{_TEST_URL}/api/pages/sidebar-pages",
        json={"data": {"items": pages}},
    )


# ---------------------------------------------------------------------------
# sync pull (CLI)
# ---------------------------------------------------------------------------


class TestSyncPullCommand:
    """Basic CLI tests for 'sync pull'."""

    def test_pull_empty_space(self, tmp_config, httpx_mock, tmp_path: Path) -> None:
        _mock_resolve_space(httpx_mock)
        _mock_sidebar_pages(httpx_mock, [])

        result = runner.invoke(
            app,
            [
                "--config",
                str(tmp_config),
                "sync",
                "pull",
                "eng",
                "--dir",
                str(tmp_path / "eng"),
            ],
        )
        assert result.exit_code == 0
        assert (tmp_path / "eng" / MANIFEST_FILENAME).exists()


# ---------------------------------------------------------------------------
# sync status (CLI)
# ---------------------------------------------------------------------------


class TestSyncStatusCommand:
    """Tests for 'sync status' command."""

    def test_status_no_changes(self, tmp_config, tmp_path: Path) -> None:
        body = "Content.\n"
        content_hash = compute_content_hash(body)
        target = _setup_synced_dir(
            tmp_path,
            pages={
                FAKE_PAGE_ID: build_page_entry(
                    title="My Page",
                    filename="my-page.md",
                    parent_id=None,
                    icon="",
                    content_hash=content_hash,
                )
            },
        )
        _write_page(
            target,
            "my-page.md",
            page_id=FAKE_PAGE_ID,
            title="My Page",
            body=body,
        )

        result = runner.invoke(
            app,
            [
                "--config",
                str(tmp_config),
                "sync",
                "status",
                "eng",
                "--dir",
                str(target),
            ],
        )
        assert result.exit_code == 0
        assert "No changes" in result.output

    def test_status_with_changes(self, tmp_config, tmp_path: Path) -> None:
        target = _setup_synced_dir(
            tmp_path,
            pages={
                FAKE_PAGE_ID: build_page_entry(
                    title="Old Title",
                    filename="page.md",
                    parent_id=None,
                    icon="",
                    content_hash=compute_content_hash("Old body.\n"),
                )
            },
        )
        _write_page(
            target,
            "page.md",
            page_id=FAKE_PAGE_ID,
            title="Old Title",
            body="New body.\n",
        )

        result = runner.invoke(
            app,
            [
                "--config",
                str(tmp_config),
                "sync",
                "status",
                "eng",
                "--dir",
                str(target),
            ],
        )
        assert result.exit_code == 0
        assert "Modified" in result.output

    def test_status_new_file(self, tmp_config, tmp_path: Path) -> None:
        target = _setup_synced_dir(tmp_path, pages={})
        _write_page(
            target,
            "new-page.md",
            page_id="",
            title="New Page",
            body="Fresh.\n",
        )

        result = runner.invoke(
            app,
            [
                "--config",
                str(tmp_config),
                "sync",
                "status",
                "eng",
                "--dir",
                str(target),
            ],
        )
        assert result.exit_code == 0
        assert "New" in result.output
        assert "new-page.md" in result.output

    def test_status_deleted_file(self, tmp_config, tmp_path: Path) -> None:
        target = _setup_synced_dir(
            tmp_path,
            pages={
                FAKE_PAGE_ID: build_page_entry(
                    title="Gone Page",
                    filename="gone.md",
                    parent_id=None,
                    icon="",
                    content_hash="sha256:abc",
                )
            },
        )
        # No .md files at all

        result = runner.invoke(
            app,
            [
                "--config",
                str(tmp_config),
                "sync",
                "status",
                "eng",
                "--dir",
                str(target),
            ],
        )
        assert result.exit_code == 0
        assert "Deleted" in result.output

    def test_status_no_manifest(self, tmp_config, tmp_path: Path) -> None:
        target = tmp_path / "eng"
        target.mkdir(parents=True)

        result = runner.invoke(
            app,
            [
                "--config",
                str(tmp_config),
                "sync",
                "status",
                "eng",
                "--dir",
                str(target),
            ],
        )
        assert result.exit_code != 0  # Should fail with error


# ---------------------------------------------------------------------------
# sync push --dry-run (CLI)
# ---------------------------------------------------------------------------


class TestSyncPushDryRunCommand:
    """Tests for 'sync push --dry-run'."""

    def test_push_dry_run_no_changes(self, tmp_config, httpx_mock, tmp_path: Path) -> None:
        body = "Same.\n"
        content_hash = compute_content_hash(body)
        target = _setup_synced_dir(
            tmp_path,
            pages={
                FAKE_PAGE_ID: build_page_entry(
                    title="My Page",
                    filename="page.md",
                    parent_id=None,
                    icon="",
                    content_hash=content_hash,
                )
            },
        )
        _write_page(
            target,
            "page.md",
            page_id=FAKE_PAGE_ID,
            title="My Page",
            body=body,
        )

        _mock_resolve_space(httpx_mock)

        result = runner.invoke(
            app,
            [
                "--config",
                str(tmp_config),
                "sync",
                "push",
                "eng",
                "--dir",
                str(target),
                "--dry-run",
            ],
        )
        assert result.exit_code == 0

    def test_push_dry_run_with_changes(self, tmp_config, httpx_mock, tmp_path: Path) -> None:
        target = _setup_synced_dir(
            tmp_path,
            pages={
                FAKE_PAGE_ID: build_page_entry(
                    title="My Page",
                    filename="page.md",
                    parent_id=None,
                    icon="",
                    content_hash=compute_content_hash("Old.\n"),
                )
            },
        )
        _write_page(
            target,
            "page.md",
            page_id=FAKE_PAGE_ID,
            title="My Page",
            body="New body.\n",
        )

        _mock_resolve_space(httpx_mock)

        result = runner.invoke(
            app,
            [
                "--config",
                str(tmp_config),
                "sync",
                "push",
                "eng",
                "--dir",
                str(target),
                "--dry-run",
            ],
        )
        assert result.exit_code == 0
        assert "UPDATE" in result.output

    def test_push_dry_run_new_page(self, tmp_config, httpx_mock, tmp_path: Path) -> None:
        target = _setup_synced_dir(tmp_path, pages={})
        _write_page(
            target,
            "new.md",
            page_id="",
            title="Brand New",
            body="Hello.\n",
        )

        _mock_resolve_space(httpx_mock)

        result = runner.invoke(
            app,
            [
                "--config",
                str(tmp_config),
                "sync",
                "push",
                "eng",
                "--dir",
                str(target),
                "--dry-run",
            ],
        )
        assert result.exit_code == 0
        assert "CREATE" in result.output


# ---------------------------------------------------------------------------
# Output stability
# ---------------------------------------------------------------------------


class TestChangeListOrdering:
    """The same working tree must print the same plan on every run.

    `PageChange.changes` is a set of enum members, whose hash derives from the
    member name — so plain iteration reorders itself as PYTHONHASHSEED changes.
    These pin the rendered order rather than the seed the suite happens to run
    under; the cross-seed proof lives in the CI matrix and in
    test_diff.py::TestDescribeChanges.
    """

    @staticmethod
    def _dir_with_three_changes(tmp_path: Path) -> Path:
        target = _setup_synced_dir(
            tmp_path,
            pages={
                FAKE_PAGE_ID: build_page_entry(
                    title="Old Title",
                    filename="page.md",
                    parent_id=None,
                    icon="",
                    content_hash=compute_content_hash("Old body.\n"),
                )
            },
        )
        _write_page(
            target,
            "page.md",
            page_id=FAKE_PAGE_ID,
            title="New Title",
            icon="🚀",
            body="New body.\n",
        )
        return target

    def test_status_lists_types_in_declaration_order(self, tmp_config, tmp_path: Path) -> None:
        target = self._dir_with_three_changes(tmp_path)
        result = runner.invoke(
            app, ["--config", str(tmp_config), "sync", "status", "eng", "--dir", str(target)]
        )
        assert result.exit_code == 0
        assert "(content_changed, title_changed, icon_changed)" in result.output

    def test_dry_run_lists_types_in_declaration_order(
        self, tmp_config, httpx_mock, tmp_path: Path
    ) -> None:
        target = self._dir_with_three_changes(tmp_path)
        _mock_resolve_space(httpx_mock)
        result = runner.invoke(
            app,
            [
                "--config",
                str(tmp_config),
                "sync",
                "push",
                "eng",
                "--dir",
                str(target),
                "--dry-run",
            ],
        )
        assert result.exit_code == 0
        assert "UPDATE page.md (content_changed, title_changed, icon_changed)" in result.output

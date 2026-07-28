"""Tests for docmost_cli.sync.diff module."""

from pathlib import Path

from docmost_cli.sync.diff import (
    ChangeType,
    PageChange,
    SyncDiff,
    compute_diff,
    describe_changes,
)
from docmost_cli.sync.frontmatter import write_sync_file
from docmost_cli.sync.manifest import compute_content_hash

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_PAGE_ID = "019a2a69-bbbb-cccc-dddd-eeeeeeeeeeee"
FAKE_PAGE_ID_2 = "029b3b79-aaaa-bbbb-cccc-ffffffffffff"
FAKE_PAGE_ID_3 = "039c4c89-1111-2222-3333-444444444444"


def _make_manifest(pages: dict | None = None) -> dict:
    """Build a minimal manifest dict for testing."""
    return {
        "version": 1,
        "space_slug": "eng",
        "space_id": "space-uuid-123",
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
    """Write a sync file with given metadata and body."""
    meta: dict[str, str] = {}
    if page_id is not None:
        meta["id"] = page_id
    meta["title"] = title
    if parent_id:
        meta["parent_id"] = parent_id
    if icon:
        meta["icon"] = icon
    write_sync_file(dir_path / filename, meta, body)


# ---------------------------------------------------------------------------
# SyncDiff.has_changes property
# ---------------------------------------------------------------------------


class TestHasChanges:
    """Tests for SyncDiff.has_changes property."""

    def test_empty_diff_has_no_changes(self) -> None:
        diff = SyncDiff()
        assert diff.has_changes is False

    def test_unchanged_only_has_no_changes(self) -> None:
        diff = SyncDiff(unchanged=5)
        assert diff.has_changes is False

    def test_new_pages_means_has_changes(self) -> None:
        diff = SyncDiff(new=[PageChange(page_id="", filename="new.md")])
        assert diff.has_changes is True

    def test_modified_pages_means_has_changes(self) -> None:
        diff = SyncDiff(modified=[PageChange(page_id="abc", filename="a.md")])
        assert diff.has_changes is True

    def test_moved_pages_means_has_changes(self) -> None:
        diff = SyncDiff(moved=[PageChange(page_id="abc", filename="a.md")])
        assert diff.has_changes is True

    def test_deleted_pages_means_has_changes(self) -> None:
        diff = SyncDiff(deleted=[PageChange(page_id="abc", filename="a.md")])
        assert diff.has_changes is True


# ---------------------------------------------------------------------------
# compute_diff — no changes
# ---------------------------------------------------------------------------


class TestComputeDiffNoChanges:
    """Tests for compute_diff when local files match the manifest exactly."""

    def test_no_changes(self, tmp_path: Path) -> None:
        """Files matching manifest produce no changes."""
        body = "Hello world.\n"
        content_hash = compute_content_hash(body)

        manifest = _make_manifest(
            {
                FAKE_PAGE_ID: {
                    "title": "My Page",
                    "filename": f"My-Page--{FAKE_PAGE_ID[:8]}.md",
                    "parent_id": None,
                    "icon": "",
                    "content_hash": content_hash,
                }
            }
        )

        _write_page(
            tmp_path,
            f"My-Page--{FAKE_PAGE_ID[:8]}.md",
            page_id=FAKE_PAGE_ID,
            title="My Page",
            body=body,
        )

        diff = compute_diff(manifest, tmp_path)

        assert diff.has_changes is False
        assert diff.unchanged == 1
        assert diff.new == []
        assert diff.modified == []
        assert diff.moved == []
        assert diff.deleted == []

    def test_multiple_unchanged_files(self, tmp_path: Path) -> None:
        """Multiple unchanged files are all counted."""
        body1 = "Content one.\n"
        body2 = "Content two.\n"

        manifest = _make_manifest(
            {
                FAKE_PAGE_ID: {
                    "title": "Page One",
                    "filename": "page-one.md",
                    "parent_id": None,
                    "icon": "",
                    "content_hash": compute_content_hash(body1),
                },
                FAKE_PAGE_ID_2: {
                    "title": "Page Two",
                    "filename": "page-two.md",
                    "parent_id": None,
                    "icon": "",
                    "content_hash": compute_content_hash(body2),
                },
            }
        )

        _write_page(
            tmp_path,
            "page-one.md",
            page_id=FAKE_PAGE_ID,
            title="Page One",
            body=body1,
        )
        _write_page(
            tmp_path,
            "page-two.md",
            page_id=FAKE_PAGE_ID_2,
            title="Page Two",
            body=body2,
        )

        diff = compute_diff(manifest, tmp_path)
        assert diff.has_changes is False
        assert diff.unchanged == 2


# ---------------------------------------------------------------------------
# compute_diff — new files
# ---------------------------------------------------------------------------


class TestComputeDiffNew:
    """Tests for compute_diff detecting new pages."""

    def test_new_page_empty_id(self, tmp_path: Path) -> None:
        """File with empty id in frontmatter is detected as NEW."""
        manifest = _make_manifest()

        _write_page(
            tmp_path,
            "brand-new.md",
            page_id="",
            title="Brand New Page",
            body="New content.\n",
        )

        diff = compute_diff(manifest, tmp_path)

        assert len(diff.new) == 1
        assert diff.new[0].page_id == ""
        assert diff.new[0].filename == "brand-new.md"
        assert ChangeType.NEW in diff.new[0].changes
        assert diff.new[0].local_meta is not None
        assert diff.new[0].local_meta["title"] == "Brand New Page"
        assert diff.new[0].local_body == "New content.\n"

    def test_new_page_no_id_key(self, tmp_path: Path) -> None:
        """File without an id key at all is detected as NEW."""
        manifest = _make_manifest()

        # Write a file with no id in metadata
        meta = {"title": "No ID Page"}
        write_sync_file(tmp_path / "no-id.md", meta, "Body.\n")

        diff = compute_diff(manifest, tmp_path)

        assert len(diff.new) == 1
        assert diff.new[0].page_id == ""


# ---------------------------------------------------------------------------
# compute_diff — content changed
# ---------------------------------------------------------------------------


class TestComputeDiffContentChanged:
    """Tests for compute_diff detecting content changes."""

    def test_content_changed(self, tmp_path: Path) -> None:
        """Different body hash triggers CONTENT_CHANGED."""
        old_body = "Old content.\n"
        new_body = "Updated content.\n"

        manifest = _make_manifest(
            {
                FAKE_PAGE_ID: {
                    "title": "My Page",
                    "filename": "my-page.md",
                    "parent_id": None,
                    "icon": "",
                    "content_hash": compute_content_hash(old_body),
                }
            }
        )

        _write_page(
            tmp_path,
            "my-page.md",
            page_id=FAKE_PAGE_ID,
            title="My Page",
            body=new_body,
        )

        diff = compute_diff(manifest, tmp_path)

        assert len(diff.modified) == 1
        assert ChangeType.CONTENT_CHANGED in diff.modified[0].changes
        assert diff.modified[0].page_id == FAKE_PAGE_ID
        assert diff.modified[0].local_body == new_body
        assert diff.modified[0].manifest_entry is not None

    def test_trailing_whitespace_not_a_change(self, tmp_path: Path) -> None:
        """Trailing whitespace differences are normalized by hash, not a change."""
        body_no_trailing = "Content"
        body_with_trailing = "Content\n\n"

        manifest = _make_manifest(
            {
                FAKE_PAGE_ID: {
                    "title": "My Page",
                    "filename": "my-page.md",
                    "parent_id": None,
                    "icon": "",
                    "content_hash": compute_content_hash(body_no_trailing),
                }
            }
        )

        _write_page(
            tmp_path,
            "my-page.md",
            page_id=FAKE_PAGE_ID,
            title="My Page",
            body=body_with_trailing,
        )

        diff = compute_diff(manifest, tmp_path)
        # compute_content_hash strips trailing whitespace, so these should match
        assert diff.unchanged == 1
        assert diff.has_changes is False


# ---------------------------------------------------------------------------
# compute_diff — title changed
# ---------------------------------------------------------------------------


class TestComputeDiffTitleChanged:
    """Tests for compute_diff detecting title changes."""

    def test_title_changed(self, tmp_path: Path) -> None:
        """Different title triggers TITLE_CHANGED."""
        body = "Same content.\n"

        manifest = _make_manifest(
            {
                FAKE_PAGE_ID: {
                    "title": "Old Title",
                    "filename": "old-title.md",
                    "parent_id": None,
                    "icon": "",
                    "content_hash": compute_content_hash(body),
                }
            }
        )

        _write_page(
            tmp_path,
            "old-title.md",
            page_id=FAKE_PAGE_ID,
            title="New Title",
            body=body,
        )

        diff = compute_diff(manifest, tmp_path)

        assert len(diff.modified) == 1
        assert ChangeType.TITLE_CHANGED in diff.modified[0].changes
        assert ChangeType.CONTENT_CHANGED not in diff.modified[0].changes


# ---------------------------------------------------------------------------
# compute_diff — icon changed
# ---------------------------------------------------------------------------


class TestComputeDiffIconChanged:
    """Tests for compute_diff detecting icon changes."""

    def test_icon_changed(self, tmp_path: Path) -> None:
        """Different icon triggers ICON_CHANGED."""
        body = "Same content.\n"

        manifest = _make_manifest(
            {
                FAKE_PAGE_ID: {
                    "title": "My Page",
                    "filename": "my-page.md",
                    "parent_id": None,
                    "icon": "old-icon",
                    "content_hash": compute_content_hash(body),
                }
            }
        )

        _write_page(
            tmp_path,
            "my-page.md",
            page_id=FAKE_PAGE_ID,
            title="My Page",
            icon="new-icon",
            body=body,
        )

        diff = compute_diff(manifest, tmp_path)

        assert len(diff.modified) == 1
        assert ChangeType.ICON_CHANGED in diff.modified[0].changes
        assert ChangeType.CONTENT_CHANGED not in diff.modified[0].changes

    def test_icon_added(self, tmp_path: Path) -> None:
        """Adding an icon where there was none triggers ICON_CHANGED."""
        body = "Content.\n"

        manifest = _make_manifest(
            {
                FAKE_PAGE_ID: {
                    "title": "My Page",
                    "filename": "my-page.md",
                    "parent_id": None,
                    "icon": "",
                    "content_hash": compute_content_hash(body),
                }
            }
        )

        _write_page(
            tmp_path,
            "my-page.md",
            page_id=FAKE_PAGE_ID,
            title="My Page",
            icon="rocket",
            body=body,
        )

        diff = compute_diff(manifest, tmp_path)
        assert len(diff.modified) == 1
        assert ChangeType.ICON_CHANGED in diff.modified[0].changes


# ---------------------------------------------------------------------------
# compute_diff — moved (parent changed)
# ---------------------------------------------------------------------------


class TestComputeDiffMoved:
    """Tests for compute_diff detecting parent changes (moves)."""

    def test_parent_changed(self, tmp_path: Path) -> None:
        """Different parent_id triggers MOVED."""
        body = "Content.\n"

        manifest = _make_manifest(
            {
                FAKE_PAGE_ID: {
                    "title": "Child Page",
                    "filename": "child-page.md",
                    "parent_id": "old-parent-id",
                    "icon": "",
                    "content_hash": compute_content_hash(body),
                }
            }
        )

        _write_page(
            tmp_path,
            "child-page.md",
            page_id=FAKE_PAGE_ID,
            title="Child Page",
            parent_id="new-parent-id",
            body=body,
        )

        diff = compute_diff(manifest, tmp_path)

        assert len(diff.moved) == 1
        assert ChangeType.MOVED in diff.moved[0].changes
        assert diff.moved[0].page_id == FAKE_PAGE_ID
        # Should NOT be in modified (only parent changed, not content/title/icon)
        assert len(diff.modified) == 0

    def test_moved_to_root(self, tmp_path: Path) -> None:
        """Moving from a parent to root (empty parent_id) triggers MOVED."""
        body = "Content.\n"

        manifest = _make_manifest(
            {
                FAKE_PAGE_ID: {
                    "title": "Page",
                    "filename": "page.md",
                    "parent_id": "some-parent",
                    "icon": "",
                    "content_hash": compute_content_hash(body),
                }
            }
        )

        # No parent_id in local file means root
        _write_page(
            tmp_path,
            "page.md",
            page_id=FAKE_PAGE_ID,
            title="Page",
            parent_id="",
            body=body,
        )

        diff = compute_diff(manifest, tmp_path)
        assert len(diff.moved) == 1
        assert ChangeType.MOVED in diff.moved[0].changes


# ---------------------------------------------------------------------------
# compute_diff — multiple changes on same page
# ---------------------------------------------------------------------------


class TestComputeDiffMultipleChanges:
    """Tests for pages with multiple simultaneous changes."""

    def test_content_and_moved(self, tmp_path: Path) -> None:
        """Content + parent changed: appears in BOTH modified AND moved."""
        old_body = "Old content.\n"
        new_body = "New content.\n"

        manifest = _make_manifest(
            {
                FAKE_PAGE_ID: {
                    "title": "My Page",
                    "filename": "my-page.md",
                    "parent_id": "old-parent",
                    "icon": "",
                    "content_hash": compute_content_hash(old_body),
                }
            }
        )

        _write_page(
            tmp_path,
            "my-page.md",
            page_id=FAKE_PAGE_ID,
            title="My Page",
            parent_id="new-parent",
            body=new_body,
        )

        diff = compute_diff(manifest, tmp_path)

        # Same page in both lists
        assert len(diff.modified) == 1
        assert len(diff.moved) == 1
        assert diff.modified[0].page_id == FAKE_PAGE_ID
        assert diff.moved[0].page_id == FAKE_PAGE_ID
        assert ChangeType.CONTENT_CHANGED in diff.modified[0].changes
        assert ChangeType.MOVED in diff.moved[0].changes

    def test_title_and_icon_changed(self, tmp_path: Path) -> None:
        """Title + icon changed: single entry in modified with both flags."""
        body = "Same.\n"

        manifest = _make_manifest(
            {
                FAKE_PAGE_ID: {
                    "title": "Old Title",
                    "filename": "page.md",
                    "parent_id": None,
                    "icon": "old",
                    "content_hash": compute_content_hash(body),
                }
            }
        )

        _write_page(
            tmp_path,
            "page.md",
            page_id=FAKE_PAGE_ID,
            title="New Title",
            icon="new",
            body=body,
        )

        diff = compute_diff(manifest, tmp_path)

        assert len(diff.modified) == 1
        changes = diff.modified[0].changes
        assert ChangeType.TITLE_CHANGED in changes
        assert ChangeType.ICON_CHANGED in changes


# ---------------------------------------------------------------------------
# compute_diff — deleted pages
# ---------------------------------------------------------------------------


class TestComputeDiffDeleted:
    """Tests for compute_diff detecting deleted pages."""

    def test_page_in_manifest_but_no_local_file(self, tmp_path: Path) -> None:
        """Manifest entry with no matching local file is DELETED."""
        manifest = _make_manifest(
            {
                FAKE_PAGE_ID: {
                    "title": "Gone Page",
                    "filename": "gone-page.md",
                    "parent_id": None,
                    "icon": "",
                    "content_hash": "sha256:whatever",
                }
            }
        )

        # No files in tmp_path
        diff = compute_diff(manifest, tmp_path)

        assert len(diff.deleted) == 1
        assert diff.deleted[0].page_id == FAKE_PAGE_ID
        assert diff.deleted[0].filename == "gone-page.md"
        assert ChangeType.DELETED in diff.deleted[0].changes
        assert diff.deleted[0].manifest_entry is not None
        assert diff.deleted[0].local_meta is None
        assert diff.deleted[0].local_body is None

    def test_multiple_deleted(self, tmp_path: Path) -> None:
        """Multiple manifest entries with no local files are all DELETED."""
        manifest = _make_manifest(
            {
                FAKE_PAGE_ID: {
                    "title": "Page One",
                    "filename": "page-one.md",
                    "parent_id": None,
                    "icon": "",
                    "content_hash": "sha256:aaa",
                },
                FAKE_PAGE_ID_2: {
                    "title": "Page Two",
                    "filename": "page-two.md",
                    "parent_id": None,
                    "icon": "",
                    "content_hash": "sha256:bbb",
                },
            }
        )

        diff = compute_diff(manifest, tmp_path)
        assert len(diff.deleted) == 2
        deleted_ids = {d.page_id for d in diff.deleted}
        assert deleted_ids == {FAKE_PAGE_ID, FAKE_PAGE_ID_2}


# ---------------------------------------------------------------------------
# compute_diff — id not in manifest
# ---------------------------------------------------------------------------


class TestComputeDiffIdNotInManifest:
    """Tests for files with an id that is not present in the manifest."""

    def test_id_not_in_manifest_treated_as_content_changed(self, tmp_path: Path) -> None:
        """File with id not in manifest is classified as CONTENT_CHANGED."""
        manifest = _make_manifest()  # Empty pages

        _write_page(
            tmp_path,
            "existing-page.md",
            page_id=FAKE_PAGE_ID,
            title="Existing Page",
            body="Content.\n",
        )

        diff = compute_diff(manifest, tmp_path)

        assert len(diff.modified) == 1
        assert ChangeType.CONTENT_CHANGED in diff.modified[0].changes
        assert diff.modified[0].page_id == FAKE_PAGE_ID
        assert diff.modified[0].manifest_entry is None


# ---------------------------------------------------------------------------
# compute_diff — empty parent normalization
# ---------------------------------------------------------------------------


class TestComputeDiffParentNormalization:
    """Tests for parent_id normalization between empty string and None."""

    def test_empty_string_matches_none(self, tmp_path: Path) -> None:
        """Local parent_id='' and manifest parent_id=None should NOT trigger MOVED."""
        body = "Content.\n"

        manifest = _make_manifest(
            {
                FAKE_PAGE_ID: {
                    "title": "Root Page",
                    "filename": "root-page.md",
                    "parent_id": None,
                    "icon": "",
                    "content_hash": compute_content_hash(body),
                }
            }
        )

        # Local file has empty parent_id (no parent_id key in frontmatter)
        _write_page(
            tmp_path,
            "root-page.md",
            page_id=FAKE_PAGE_ID,
            title="Root Page",
            parent_id="",
            body=body,
        )

        diff = compute_diff(manifest, tmp_path)

        assert diff.has_changes is False
        assert diff.unchanged == 1

    def test_none_manifest_empty_string_local_no_move(self, tmp_path: Path) -> None:
        """Manifest parent_id=None, local parent_id missing entirely: no MOVED."""
        body = "Content.\n"

        manifest = _make_manifest(
            {
                FAKE_PAGE_ID: {
                    "title": "Page",
                    "filename": "page.md",
                    "parent_id": None,
                    "icon": "",
                    "content_hash": compute_content_hash(body),
                }
            }
        )

        # Write file without parent_id at all in metadata
        meta = {"id": FAKE_PAGE_ID, "title": "Page"}
        write_sync_file(tmp_path / "page.md", meta, body)

        diff = compute_diff(manifest, tmp_path)

        assert diff.has_changes is False
        assert diff.unchanged == 1


# ---------------------------------------------------------------------------
# compute_diff — mixed scenario
# ---------------------------------------------------------------------------


class TestComputeDiffMixed:
    """Tests with a mix of new, modified, moved, deleted, unchanged pages."""

    def test_mixed_scenario(self, tmp_path: Path) -> None:
        """Comprehensive test with all change types present."""
        unchanged_body = "Unchanged.\n"
        modified_body_old = "Old body.\n"
        modified_body_new = "New body.\n"
        moved_body = "Moved body.\n"

        manifest = _make_manifest(
            {
                FAKE_PAGE_ID: {
                    "title": "Unchanged Page",
                    "filename": "unchanged.md",
                    "parent_id": None,
                    "icon": "",
                    "content_hash": compute_content_hash(unchanged_body),
                },
                FAKE_PAGE_ID_2: {
                    "title": "Modified Page",
                    "filename": "modified.md",
                    "parent_id": None,
                    "icon": "",
                    "content_hash": compute_content_hash(modified_body_old),
                },
                FAKE_PAGE_ID_3: {
                    "title": "Moved Page",
                    "filename": "moved.md",
                    "parent_id": "old-parent",
                    "icon": "",
                    "content_hash": compute_content_hash(moved_body),
                },
                "deleted-page-id": {
                    "title": "Deleted Page",
                    "filename": "deleted.md",
                    "parent_id": None,
                    "icon": "",
                    "content_hash": "sha256:xxx",
                },
            }
        )

        # Unchanged
        _write_page(
            tmp_path,
            "unchanged.md",
            page_id=FAKE_PAGE_ID,
            title="Unchanged Page",
            body=unchanged_body,
        )
        # Modified (content changed)
        _write_page(
            tmp_path,
            "modified.md",
            page_id=FAKE_PAGE_ID_2,
            title="Modified Page",
            body=modified_body_new,
        )
        # Moved (parent changed)
        _write_page(
            tmp_path,
            "moved.md",
            page_id=FAKE_PAGE_ID_3,
            title="Moved Page",
            parent_id="new-parent",
            body=moved_body,
        )
        # New page
        _write_page(
            tmp_path,
            "brand-new.md",
            page_id="",
            title="Brand New",
            body="New.\n",
        )
        # "deleted.md" intentionally NOT created

        diff = compute_diff(manifest, tmp_path)

        assert diff.unchanged == 1
        assert len(diff.new) == 1
        assert len(diff.modified) == 1
        assert len(diff.moved) == 1
        assert len(diff.deleted) == 1

        assert diff.new[0].filename == "brand-new.md"
        assert diff.modified[0].page_id == FAKE_PAGE_ID_2
        assert diff.moved[0].page_id == FAKE_PAGE_ID_3
        assert diff.deleted[0].page_id == "deleted-page-id"

        assert diff.has_changes is True


# ---------------------------------------------------------------------------
# compute_diff — empty directory
# ---------------------------------------------------------------------------


class TestComputeDiffEmptyDir:
    """Tests for compute_diff with an empty directory."""

    def test_empty_dir_empty_manifest(self, tmp_path: Path) -> None:
        """Empty dir + empty manifest = no changes."""
        manifest = _make_manifest()
        diff = compute_diff(manifest, tmp_path)

        assert diff.has_changes is False
        assert diff.unchanged == 0

    def test_empty_dir_with_manifest_pages(self, tmp_path: Path) -> None:
        """Empty dir + manifest with pages = all deleted."""
        manifest = _make_manifest(
            {
                FAKE_PAGE_ID: {
                    "title": "Page",
                    "filename": "page.md",
                    "parent_id": None,
                    "icon": "",
                    "content_hash": "sha256:abc",
                },
            }
        )

        diff = compute_diff(manifest, tmp_path)
        assert len(diff.deleted) == 1
        assert diff.deleted[0].page_id == FAKE_PAGE_ID


# ---------------------------------------------------------------------------
# compute_diff — non-md files ignored
# ---------------------------------------------------------------------------


class TestComputeDiffIgnoresNonMd:
    """Tests that non-.md files in the directory are ignored."""

    def test_non_md_files_ignored(self, tmp_path: Path) -> None:
        """Files that are not .md are not processed."""
        manifest = _make_manifest()

        # Create some non-.md files
        (tmp_path / "notes.txt").write_text("Not a markdown sync file.\n")
        (tmp_path / "data.json").write_text("{}\n")
        (tmp_path / ".docmost-manifest.json").write_text("{}\n")

        diff = compute_diff(manifest, tmp_path)
        assert diff.has_changes is False
        assert diff.unchanged == 0
        assert diff.new == []


# ---------------------------------------------------------------------------
# PageChange dataclass
# ---------------------------------------------------------------------------


class TestPageChange:
    """Tests for PageChange dataclass defaults."""

    def test_defaults(self) -> None:
        """PageChange has sensible defaults for optional fields."""
        pc = PageChange(page_id="abc", filename="test.md")
        assert pc.changes == set()
        assert pc.local_meta is None
        assert pc.local_body is None
        assert pc.manifest_entry is None


# ---------------------------------------------------------------------------
# ChangeType enum
# ---------------------------------------------------------------------------


class TestChangeType:
    """Tests for ChangeType enum values."""

    def test_all_values(self) -> None:
        """All expected change types exist."""
        assert ChangeType.NEW.value == "new"
        assert ChangeType.CONTENT_CHANGED.value == "content_changed"
        assert ChangeType.TITLE_CHANGED.value == "title_changed"
        assert ChangeType.MOVED.value == "moved"
        assert ChangeType.ICON_CHANGED.value == "icon_changed"
        assert ChangeType.DELETED.value == "deleted"

    def test_enum_count(self) -> None:
        """Exactly 6 change types."""
        assert len(ChangeType) == 6


# ---------------------------------------------------------------------------
# describe_changes / SyncDiff.move_only
# ---------------------------------------------------------------------------


class TestDescribeChanges:
    """Change-type lists reach users, so their order cannot come from a set.

    `Enum.__hash__` hashes the member name, and Python's string hash is seeded
    per process — so iterating `PageChange.changes` reorders itself between
    runs. `sync push --dry-run` puts this list on stdout as a scripting-facing
    plan; a diff of two runs must not show phantom changes.
    """

    def test_declaration_order_not_set_order(self) -> None:
        every_order = {
            ChangeType.ICON_CHANGED,
            ChangeType.CONTENT_CHANGED,
            ChangeType.TITLE_CHANGED,
        }
        assert describe_changes(every_order) == "content_changed, title_changed, icon_changed"

    def test_moved_is_excluded(self) -> None:
        """Both callers report moves on their own line."""
        changes = {ChangeType.CONTENT_CHANGED, ChangeType.MOVED}
        assert describe_changes(changes) == "content_changed"

    def test_move_only_change_set_renders_empty(self) -> None:
        assert describe_changes({ChangeType.MOVED}) == ""

    def test_empty(self) -> None:
        assert describe_changes(set()) == ""


class TestMoveOnly:
    """One property, so the reported plan and the executed plan cannot diverge.

    push's Phase B2 skipped by page ID while the summary and dry-run printers
    subtracted whole PageChange objects — two predicates for one question.
    """

    @staticmethod
    def _change(page_id: str, filename: str, changes: set[ChangeType]) -> PageChange:
        return PageChange(page_id=page_id, filename=filename, changes=changes)

    def test_page_that_also_changed_is_excluded(self) -> None:
        both = self._change("p1", "a.md", {ChangeType.CONTENT_CHANGED, ChangeType.MOVED})
        diff = SyncDiff(modified=[both], moved=[both])
        assert diff.move_only == []

    def test_pure_move_is_kept(self) -> None:
        moved = self._change("p2", "b.md", {ChangeType.MOVED})
        diff = SyncDiff(moved=[moved])
        assert diff.move_only == [moved]

    def test_matches_on_page_id_not_object_identity(self) -> None:
        """A rebuilt PageChange for the same page is still the same page.

        Object equality compared every field, including the whole Markdown body
        — so a caller holding a differently-populated copy got a different
        answer from the one push acted on.
        """
        modified = PageChange(
            page_id="p3",
            filename="c.md",
            changes={ChangeType.CONTENT_CHANGED},
            local_body="new body",
        )
        moved = PageChange(
            page_id="p3",
            filename="c.md",
            changes={ChangeType.MOVED},
            local_body="old body",
        )
        assert SyncDiff(modified=[modified], moved=[moved]).move_only == []

    def test_mixed(self) -> None:
        both = self._change("p1", "a.md", {ChangeType.TITLE_CHANGED, ChangeType.MOVED})
        pure = self._change("p2", "b.md", {ChangeType.MOVED})
        diff = SyncDiff(modified=[both], moved=[both, pure])
        assert [c.page_id for c in diff.move_only] == ["p2"]

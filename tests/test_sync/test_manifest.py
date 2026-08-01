"""Tests for the sync manifest module."""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from docmost_cli.sync.manifest import (
    MANIFEST_FILENAME,
    MANIFEST_VERSION,
    build_manifest,
    build_page_entry,
    compute_content_hash,
    load_manifest,
    sanitize_filename,
    save_manifest,
)

# ---------------------------------------------------------------------------
# sanitize_filename
# ---------------------------------------------------------------------------

FAKE_ID = "019a2a69-bbbb-cccc-dddd-eeeeeeeeeeee"


class TestSanitizeFilename:
    """Tests for sanitize_filename."""

    def test_normal_title(self) -> None:
        result = sanitize_filename("Heizungssteuerung", FAKE_ID)
        assert result == "Heizungssteuerung--019a2a69.md"

    def test_special_chars_collapsed(self) -> None:
        result = sanitize_filename("AC/DC: The Best?", FAKE_ID)
        # / → -, : → -, ? → -  then collapse, spaces preserved
        assert result == "AC-DC- The Best--019a2a69.md"

    def test_very_long_title_truncated(self) -> None:
        long_title = "A" * 120
        result = sanitize_filename(long_title, FAKE_ID)
        # Title portion should be at most 80 chars
        stem = result.removesuffix(f"--{FAKE_ID[:8]}.md")
        assert len(stem) <= 80

    def test_empty_after_sanitize_gives_untitled(self) -> None:
        result = sanitize_filename("***", FAKE_ID)
        assert result == f"untitled--{FAKE_ID[:8]}.md"

    def test_null_title_gives_untitled(self) -> None:
        result = sanitize_filename(None, FAKE_ID)
        assert result == f"untitled--{FAKE_ID[:8]}.md"

    def test_unicode_preserved(self) -> None:
        result = sanitize_filename("Über Änderungen", FAKE_ID)
        assert "Über Änderungen" in result
        assert result.endswith(f"--{FAKE_ID[:8]}.md")

    def test_leading_trailing_spaces_and_dashes(self) -> None:
        result = sanitize_filename("  --Hello World--  ", FAKE_ID)
        # Strips leading/trailing whitespace and dashes
        assert result.startswith("Hello World")
        assert result.endswith(f"--{FAKE_ID[:8]}.md")

    def test_all_dashes_gives_untitled(self) -> None:
        result = sanitize_filename("---", FAKE_ID)
        assert result == f"untitled--{FAKE_ID[:8]}.md"

    def test_truncation_strips_trailing_dash(self) -> None:
        # Build a title where char 80 would be right after a dash
        title = "A" * 79 + "-B"
        result = sanitize_filename(title, FAKE_ID)
        stem = result.removesuffix(f"--{FAKE_ID[:8]}.md")
        assert not stem.endswith("-")


# ---------------------------------------------------------------------------
# compute_content_hash
# ---------------------------------------------------------------------------


class TestComputeContentHash:
    """Tests for compute_content_hash."""

    def test_deterministic(self) -> None:
        h1 = compute_content_hash("hello world")
        h2 = compute_content_hash("hello world")
        assert h1 == h2

    def test_trailing_whitespace_ignored(self) -> None:
        h1 = compute_content_hash("hello")
        h2 = compute_content_hash("hello\n\n")
        assert h1 == h2

    def test_different_content_different_hash(self) -> None:
        h1 = compute_content_hash("hello")
        h2 = compute_content_hash("world")
        assert h1 != h2

    def test_empty_string_valid_hash(self) -> None:
        h = compute_content_hash("")
        assert h.startswith("sha256:")
        assert len(h) == len("sha256:") + 64  # SHA-256 hex is 64 chars

    def test_prefix_format(self) -> None:
        h = compute_content_hash("test")
        assert h.startswith("sha256:")


# ---------------------------------------------------------------------------
# load_manifest / save_manifest roundtrip
# ---------------------------------------------------------------------------


class TestLoadSaveManifest:
    """Tests for load_manifest and save_manifest."""

    def test_roundtrip(self, tmp_path: Path) -> None:
        manifest = {
            "version": MANIFEST_VERSION,
            "space_slug": "eng",
            "space_id": "abc-123",
            "synced_at": "2026-01-01T00:00:00+00:00",
            "pages": {
                "page-1": {
                    "title": "Test",
                    "filename": "Test--page-1.md",
                    "parent_id": None,
                    "icon": "",
                    "content_hash": "sha256:abc",
                }
            },
        }
        save_manifest(tmp_path, manifest)
        loaded = load_manifest(tmp_path)
        assert loaded == manifest

    def test_load_nonexistent_returns_none(self, tmp_path: Path) -> None:
        result = load_manifest(tmp_path / "does-not-exist")
        assert result is None

    def test_load_future_version_exits(self, tmp_path: Path) -> None:
        manifest = {"version": MANIFEST_VERSION + 999, "pages": {}}
        manifest_path = tmp_path / MANIFEST_FILENAME
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with pytest.raises(SystemExit):
            load_manifest(tmp_path)

    def test_save_creates_file(self, tmp_path: Path) -> None:
        save_manifest(tmp_path, {"version": MANIFEST_VERSION, "pages": {}})
        assert (tmp_path / MANIFEST_FILENAME).exists()

    def test_save_atomic_no_tmp_leftover(self, tmp_path: Path) -> None:
        save_manifest(tmp_path, {"version": MANIFEST_VERSION, "pages": {}})
        tmp_file = tmp_path / (MANIFEST_FILENAME + ".tmp")
        assert not tmp_file.exists()

    def test_save_pretty_printed(self, tmp_path: Path) -> None:
        save_manifest(tmp_path, {"version": MANIFEST_VERSION, "pages": {}})
        raw = (tmp_path / MANIFEST_FILENAME).read_text(encoding="utf-8")
        # indent=2 means there should be lines starting with spaces
        assert "\n  " in raw

    def test_load_current_version_succeeds(self, tmp_path: Path) -> None:
        manifest = {"version": MANIFEST_VERSION, "pages": {}}
        manifest_path = tmp_path / MANIFEST_FILENAME
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        result = load_manifest(tmp_path)
        assert result is not None
        assert result["version"] == MANIFEST_VERSION


# ---------------------------------------------------------------------------
# build_manifest
# ---------------------------------------------------------------------------


class TestBuildManifest:
    """Tests for build_manifest."""

    def test_correct_structure(self) -> None:
        pages = [
            {
                "id": "page-1",
                "title": "First Page",
                "filename": "First-Page--page-1.md",
                "parent_id": None,
                "icon": "📄",
                "content_hash": "sha256:aaa",
            },
            {
                "id": "page-2",
                "title": "Second Page",
                "filename": "Second-Page--page-2.md",
                "parent_id": "page-1",
                "icon": "",
                "content_hash": "sha256:bbb",
            },
        ]
        manifest = build_manifest("eng", "space-uuid-123", pages)

        assert manifest["version"] == MANIFEST_VERSION
        assert manifest["space_slug"] == "eng"
        assert manifest["space_id"] == "space-uuid-123"
        assert "synced_at" in manifest
        assert "page-1" in manifest["pages"]
        assert "page-2" in manifest["pages"]
        assert manifest["pages"]["page-1"]["title"] == "First Page"
        assert manifest["pages"]["page-2"]["parent_id"] == "page-1"

    def test_synced_at_is_iso_format(self) -> None:
        manifest = build_manifest("eng", "space-uuid", [])
        # Should parse as a valid ISO datetime
        dt = datetime.fromisoformat(manifest["synced_at"])
        assert dt is not None

    def test_pages_keyed_by_id(self) -> None:
        pages = [
            {
                "id": "abc-123",
                "title": "Test",
                "filename": "Test--abc-123.md",
                "parent_id": None,
                "icon": "",
                "content_hash": "sha256:xyz",
            }
        ]
        manifest = build_manifest("eng", "space-uuid", pages)
        assert set(manifest["pages"].keys()) == {"abc-123"}

    def test_empty_pages(self) -> None:
        manifest = build_manifest("eng", "space-uuid", [])
        assert manifest["pages"] == {}


# ---------------------------------------------------------------------------
# build_page_entry
# ---------------------------------------------------------------------------


class TestBuildPageEntry:
    """Tests for build_page_entry."""

    def test_correct_shape(self) -> None:
        entry = build_page_entry(
            title="My Page",
            filename="My-Page--abcd1234.md",
            parent_id="parent-id-xyz",
            icon="🏠",
            content_hash="sha256:deadbeef",
        )
        assert entry == {
            "title": "My Page",
            "filename": "My-Page--abcd1234.md",
            "parent_id": "parent-id-xyz",
            "icon": "🏠",
            "content_hash": "sha256:deadbeef",
        }

    def test_none_parent_id(self) -> None:
        entry = build_page_entry(
            title="Root Page",
            filename="Root-Page--abcd1234.md",
            parent_id=None,
            icon="",
            content_hash="sha256:abc",
        )
        assert entry["parent_id"] is None

    def test_empty_icon(self) -> None:
        entry = build_page_entry(
            title="No Icon",
            filename="No-Icon--abcd1234.md",
            parent_id=None,
            icon="",
            content_hash="sha256:abc",
        )
        assert entry["icon"] == ""

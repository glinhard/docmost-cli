"""Tests for the sync pull module."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from docmost_cli.api.client import DocmostClient
from docmost_cli.config.settings import DocmostSettings
from docmost_cli.sync.manifest import MANIFEST_FILENAME, MANIFEST_VERSION
from docmost_cli.sync.pull import PullResult, flatten_tree, pull_space

# ---------------------------------------------------------------------------
# Helper: create a client for integration tests
# ---------------------------------------------------------------------------

_TEST_URL = "https://docs.example.com"


def _make_client() -> DocmostClient:
    settings = DocmostSettings(url=_TEST_URL, api_key="dm_test1234567890")
    return DocmostClient(settings)


# ---------------------------------------------------------------------------
# flatten_tree — pure unit tests (no mocking needed)
# ---------------------------------------------------------------------------


class TestFlattenTreeFlat:
    """Three root pages produce a flat list with parent_id=None."""

    def test_flat_list(self) -> None:
        tree = [
            {"id": "p1", "title": "Page One", "icon": "", "children": []},
            {"id": "p2", "title": "Page Two", "icon": "X", "children": []},
            {"id": "p3", "title": "Page Three", "children": []},
        ]
        result = flatten_tree(tree)
        assert len(result) == 3
        for item in result:
            assert item["parent_id"] is None
        assert result[0]["id"] == "p1"
        assert result[1]["id"] == "p2"
        assert result[2]["id"] == "p3"
        assert result[0]["title"] == "Page One"
        # Missing icon defaults to ""
        assert result[2]["icon"] == ""


class TestFlattenTreeNested:
    """Nested children are flattened with correct parent_ids."""

    def test_nested(self) -> None:
        tree = [
            {
                "id": "root",
                "title": "Root",
                "icon": "",
                "children": [
                    {
                        "id": "child-1",
                        "title": "Child 1",
                        "icon": "",
                        "children": [
                            {
                                "id": "grandchild",
                                "title": "Grandchild",
                                "icon": "",
                                "children": [],
                            }
                        ],
                    },
                    {
                        "id": "child-2",
                        "title": "Child 2",
                        "icon": "",
                        "children": [],
                    },
                ],
            }
        ]
        result = flatten_tree(tree)
        assert len(result) == 4

        ids_and_parents = [(r["id"], r["parent_id"]) for r in result]
        assert ("root", None) in ids_and_parents
        assert ("child-1", "root") in ids_and_parents
        assert ("child-2", "root") in ids_and_parents
        assert ("grandchild", "child-1") in ids_and_parents


class TestFlattenTreeEmpty:
    """Empty list produces empty result."""

    def test_empty(self) -> None:
        assert flatten_tree([]) == []


# ---------------------------------------------------------------------------
# pull_space — integration tests with httpx_mock
# ---------------------------------------------------------------------------

# Shared ProseMirror doc for mock responses
_PM_DOC = {
    "type": "doc",
    "content": [
        {
            "type": "paragraph",
            "content": [{"type": "text", "text": "Hello world"}],
        }
    ],
}


def _mock_resolve_space(httpx_mock, slug: str = "test", space_id: str = "space-1") -> None:
    """Add mock for resolve_space_id (which calls list_spaces -> POST /spaces)."""
    httpx_mock.add_response(
        url=f"{_TEST_URL}/api/spaces",
        json={"data": {"items": [{"id": space_id, "slug": slug, "name": slug.capitalize()}]}},
    )


def _mock_sidebar_pages(httpx_mock, pages: list[dict]) -> None:
    """Add mock for build_page_tree (POST /pages/sidebar-pages)."""
    httpx_mock.add_response(
        url=f"{_TEST_URL}/api/pages/sidebar-pages",
        json={"data": {"items": pages}},
    )


def _mock_page_content(
    httpx_mock,
    page_id: str,
    title: str | None,
    pm_content: dict | None = None,
) -> None:
    """Add mocks for get_page_content (calls /pages/info then /pages/content)."""
    content = pm_content or _PM_DOC
    # get_page_info -> POST /pages/info
    httpx_mock.add_response(
        url=f"{_TEST_URL}/api/pages/info",
        json={
            "id": page_id,
            "title": title,
            "spaceId": "space-1",
            "content": content,
        },
    )
    # post_raw -> POST /pages/content (Enterprise endpoint — return 404 to use fallback)
    httpx_mock.add_response(
        url=f"{_TEST_URL}/api/pages/content",
        status_code=404,
    )


class TestPullEmptySpace:
    """Space with no pages creates dir + empty manifest."""

    def test_empty_space(self, httpx_mock, tmp_path: Path) -> None:
        target = tmp_path / "test"
        _mock_resolve_space(httpx_mock)
        _mock_sidebar_pages(httpx_mock, [])

        with _make_client() as client:
            result = pull_space(client, "test", target)

        assert isinstance(result, PullResult)
        assert result.pages_pulled == 0
        assert result.dir_path == target
        assert target.exists()

        # Manifest should exist and be empty
        manifest_path = target / MANIFEST_FILENAME
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["version"] == MANIFEST_VERSION
        assert manifest["space_slug"] == "test"
        assert manifest["space_id"] == "space-1"
        assert manifest["pages"] == {}


class TestPullCreatesFiles:
    """Two pages produce 2 .md files + manifest on disk."""

    def test_creates_files(self, httpx_mock, tmp_path: Path) -> None:
        target = tmp_path / "test"

        _mock_resolve_space(httpx_mock)
        _mock_sidebar_pages(
            httpx_mock,
            [
                {"id": "p1", "title": "Page One", "icon": "", "hasChildren": False, "children": []},
                {"id": "p2", "title": "Page Two", "icon": "", "hasChildren": False, "children": []},
            ],
        )

        # Mock content fetch for page 1
        _mock_page_content(httpx_mock, "p1", "Page One")
        # Mock content fetch for page 2
        _mock_page_content(httpx_mock, "p2", "Page Two")

        with _make_client() as client:
            result = pull_space(client, "test", target)

        assert result.pages_pulled == 2

        # Check .md files exist
        md_files = list(target.glob("*.md"))
        assert len(md_files) == 2

        # Check manifest exists and has 2 pages
        manifest_path = target / MANIFEST_FILENAME
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert len(manifest["pages"]) == 2
        assert "p1" in manifest["pages"]
        assert "p2" in manifest["pages"]


class TestPullNullTitle:
    """A page without a title is pulled using a stable fallback."""

    def test_uses_untitled_fallback(self, httpx_mock, tmp_path: Path) -> None:
        target = tmp_path / "test"

        _mock_resolve_space(httpx_mock)
        _mock_sidebar_pages(
            httpx_mock,
            [
                {
                    "id": "page-null-title",
                    "title": None,
                    "icon": "",
                    "hasChildren": False,
                    "children": [],
                }
            ],
        )
        _mock_page_content(httpx_mock, "page-null-title", None)

        with _make_client() as client:
            result = pull_space(client, "test", target)

        assert result.pages_pulled == 1
        page_path = target / "Untitled--page-nul.md"
        assert page_path.exists()
        assert "title: Untitled" in page_path.read_text(encoding="utf-8")

        manifest = json.loads((target / MANIFEST_FILENAME).read_text(encoding="utf-8"))
        entry = manifest["pages"]["page-null-title"]
        assert entry["title"] == "Untitled"
        assert entry["filename"] == page_path.name


class TestPullWritesCorrectFrontmatter:
    """Verify frontmatter has id, title, parent_id, icon."""

    def test_frontmatter_fields(self, httpx_mock, tmp_path: Path) -> None:
        target = tmp_path / "test"

        _mock_resolve_space(httpx_mock)
        _mock_sidebar_pages(
            httpx_mock,
            [
                {
                    "id": "root-1",
                    "title": "Root Page",
                    "icon": "",
                    "hasChildren": True,
                    "children": [
                        {
                            "id": "child-1",
                            "title": "Child Page",
                            "icon": "",
                            "hasChildren": False,
                            "children": [],
                        }
                    ],
                },
            ],
        )

        # Mock content for root page
        _mock_page_content(httpx_mock, "root-1", "Root Page")
        # Mock content for child page
        _mock_page_content(httpx_mock, "child-1", "Child Page")

        with _make_client() as client:
            result = pull_space(client, "test", target)

        assert result.pages_pulled == 2

        # Find child file (its filename contains "child-1" prefix)
        child_files = [f for f in target.glob("*.md") if "child-1" in f.name]
        assert len(child_files) == 1

        content = child_files[0].read_text(encoding="utf-8")
        # Check frontmatter contains expected fields
        assert "---" in content
        assert "id: child-1" in content
        assert "title: Child Page" in content
        assert "parent_id: root-1" in content

        # Find root file
        root_files = [f for f in target.glob("*.md") if "root-1" in f.name]
        assert len(root_files) == 1
        root_content = root_files[0].read_text(encoding="utf-8")
        assert "id: root-1" in root_content
        # Root page has no parent, so parent_id is empty string
        assert "parent_id:" in root_content


class TestPullRefusesWithoutForce:
    """Existing manifest without --force should SystemExit."""

    def test_refuses(self, httpx_mock, tmp_path: Path) -> None:
        target = tmp_path / "test"
        target.mkdir(parents=True)

        # Pre-create a manifest in the target directory
        manifest = {
            "version": MANIFEST_VERSION,
            "space_slug": "test",
            "space_id": "space-1",
            "synced_at": "2026-01-01T00:00:00+00:00",
            "pages": {"old-page": {"title": "Old", "filename": "Old--old-page.md"}},
        }
        (target / MANIFEST_FILENAME).write_text(json.dumps(manifest), encoding="utf-8")

        _mock_resolve_space(httpx_mock)
        _mock_sidebar_pages(
            httpx_mock,
            [
                {"id": "p1", "title": "Page One", "icon": "", "hasChildren": False, "children": []},
            ],
        )

        with _make_client() as client, pytest.raises(SystemExit):
            pull_space(client, "test", target, force=False)


class TestPullOverwritesWithForce:
    """Existing manifest with --force should succeed."""

    def test_overwrites(self, httpx_mock, tmp_path: Path) -> None:
        target = tmp_path / "test"
        target.mkdir(parents=True)

        # Pre-create a manifest in the target directory
        manifest = {
            "version": MANIFEST_VERSION,
            "space_slug": "test",
            "space_id": "space-1",
            "synced_at": "2026-01-01T00:00:00+00:00",
            "pages": {"old-page": {"title": "Old", "filename": "Old--old-page.md"}},
        }
        (target / MANIFEST_FILENAME).write_text(json.dumps(manifest), encoding="utf-8")

        _mock_resolve_space(httpx_mock)
        _mock_sidebar_pages(
            httpx_mock,
            [
                {"id": "p1", "title": "New Page", "icon": "", "hasChildren": False, "children": []},
            ],
        )
        _mock_page_content(httpx_mock, "p1", "New Page")

        with _make_client() as client:
            result = pull_space(client, "test", target, force=True)

        assert result.pages_pulled == 1

        # New manifest should have just the new page
        manifest_path = target / MANIFEST_FILENAME
        new_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert "p1" in new_manifest["pages"]
        assert "old-page" not in new_manifest["pages"]

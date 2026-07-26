"""Guards against docs drifting out of sync with the code."""

import re
import tomllib
from pathlib import Path

import pytest

from docmost_cli import __version__

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MAN_DIR = _REPO_ROOT / "man" / "man1"

_TH_RE = re.compile(r'^\.TH\s+\S+\s+\d+\s+"[^"]*"\s+"docmost\\-cli ([^"]+)"')


def _man_pages() -> list[Path]:
    if not _MAN_DIR.is_dir():
        pytest.skip("man pages not present (running from an installed package)")
    return sorted(_MAN_DIR.glob("*.1"))


class TestManPages:
    def test_th_version_matches_package_version(self) -> None:
        for page in _man_pages():
            matches = (_TH_RE.match(line) for line in page.read_text().splitlines())
            match = next((m for m in matches if m is not None), None)
            assert match is not None, f"{page.name} has no parseable .TH line"
            assert match.group(1) == __version__, (
                f"{page.name} .TH says {match.group(1)}, package says {__version__}"
            )

    def test_no_stale_position_docs(self) -> None:
        """--position takes an ordering key, not a zero-based index."""
        for page in _man_pages():
            assert "zero\\-based index" not in page.read_text(), page.name

    def test_no_stale_content_update_endpoint(self) -> None:
        """/pages/content/update does not exist in Docmost."""
        for page in _man_pages():
            assert "content/update" not in page.read_text(), page.name


class TestPyprojectVersion:
    def test_version_is_dynamic(self) -> None:
        """__init__.py must stay the single source of truth for the version."""
        with open(_REPO_ROOT / "pyproject.toml", "rb") as handle:
            pyproject = tomllib.load(handle)
        project = pyproject["project"]
        assert "version" not in project
        assert "version" in project.get("dynamic", [])
        assert pyproject["tool"]["hatch"]["version"]["path"] == "src/docmost_cli/__init__.py"

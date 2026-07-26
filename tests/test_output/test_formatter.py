"""Tests for output formatting."""

import json

from docmost_cli.output.formatter import print_table, print_warning

ROWS = [{"id": "1", "title": "One", "extra": "dropped"}]
COLUMNS = ["id", "title"]


class TestPrintTableJson:
    def test_json_without_meta_is_bare_array(self, capsys) -> None:
        """The documented contract: `--json` pipes straight into `jq '.[]'`."""
        print_table(ROWS, COLUMNS, json_mode=True)
        payload = json.loads(capsys.readouterr().out)
        assert isinstance(payload, list)
        assert payload == [{"id": "1", "title": "One"}]

    def test_json_with_meta_is_envelope(self, capsys) -> None:
        meta = {"limit": 100, "hasNextPage": True, "nextCursor": "c2"}
        print_table(ROWS, COLUMNS, json_mode=True, meta=meta)
        payload = json.loads(capsys.readouterr().out)
        assert isinstance(payload, dict)
        assert payload["items"] == [{"id": "1", "title": "One"}]
        assert payload["meta"]["nextCursor"] == "c2"

    def test_json_empty_meta_still_envelopes(self, capsys) -> None:
        print_table([], COLUMNS, json_mode=True, meta={})
        payload = json.loads(capsys.readouterr().out)
        assert payload == {"items": [], "meta": {}}


class TestPrintTableTable:
    def test_table_mode_renders_columns(self, capsys) -> None:
        print_table(ROWS, COLUMNS)
        out = capsys.readouterr().out
        assert "title" in out
        assert "One" in out

    def test_table_footer_on_stderr_when_more_pages(self, capsys) -> None:
        print_table(ROWS, COLUMNS, meta={"hasNextPage": True, "nextCursor": "c2"})
        captured = capsys.readouterr()
        assert "c2" in captured.err
        assert "c2" not in captured.out

    def test_no_footer_when_no_more_pages(self, capsys) -> None:
        print_table(ROWS, COLUMNS, meta={"hasNextPage": False, "nextCursor": None})
        assert capsys.readouterr().err == ""


class TestPrintWarning:
    def test_goes_to_stderr(self, capsys) -> None:
        print_warning("careful")
        captured = capsys.readouterr()
        assert "careful" in captured.err
        assert captured.out == ""

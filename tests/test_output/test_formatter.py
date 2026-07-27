"""Tests for output formatting."""

import copy
import json
from datetime import datetime

from docmost_cli.output.formatter import print_json, print_table, print_warning

# "extra" is outside COLUMNS on purpose: --json must keep it.
ROWS = [{"id": "1", "title": "One", "extra": "kept"}]
COLUMNS = ["id", "title"]


class TestPrintTableJson:
    def test_json_without_meta_is_bare_array(self, capsys) -> None:
        """`--json` is a bare array of complete server objects."""
        print_table(ROWS, COLUMNS, json_mode=True)
        payload = json.loads(capsys.readouterr().out)
        assert isinstance(payload, list)
        assert payload == [{"id": "1", "title": "One", "extra": "kept"}]

    def test_json_with_meta_is_envelope(self, capsys) -> None:
        meta = {"limit": 100, "hasNextPage": True, "nextCursor": "c2"}
        print_table(ROWS, COLUMNS, json_mode=True, meta=meta)
        payload = json.loads(capsys.readouterr().out)
        assert isinstance(payload, dict)
        assert payload["items"][0]["extra"] == "kept"
        assert payload["meta"]["nextCursor"] == "c2"

    def test_json_empty_meta_still_envelopes(self, capsys) -> None:
        print_table([], COLUMNS, json_mode=True, meta={})
        payload = json.loads(capsys.readouterr().out)
        assert payload == {"items": [], "meta": {}}

    def test_json_ignores_columns(self, capsys) -> None:
        """The column list is a display choice and must not narrow JSON."""
        print_table(ROWS, ["id"], json_mode=True)
        payload = json.loads(capsys.readouterr().out)
        assert set(payload[0]) == {"id", "title", "extra"}

    def test_json_does_not_invent_missing_keys(self, capsys) -> None:
        print_table([{"id": "1"}], ["id", "title"], json_mode=True)
        payload = json.loads(capsys.readouterr().out)
        assert "title" not in payload[0]


class TestPrintTableFields:
    def test_fields_projects_and_preserves_order(self, capsys) -> None:
        print_table(ROWS, COLUMNS, json_mode=True, fields=["title", "id"])
        payload = json.loads(capsys.readouterr().out)
        assert list(payload[0]) == ["title", "id"]
        assert "extra" not in payload[0]

    def test_fields_emits_null_for_absent_key(self, capsys) -> None:
        """An explicitly named field stays rectangular across rows."""
        print_table([{"id": "1"}], COLUMNS, json_mode=True, fields=["id", "nope"])
        payload = json.loads(capsys.readouterr().out)
        assert payload == [{"id": "1", "nope": None}]

    def test_fields_applies_inside_envelope(self, capsys) -> None:
        meta = {"hasNextPage": False, "nextCursor": None}
        print_table(ROWS, COLUMNS, json_mode=True, meta=meta, fields=["id"])
        payload = json.loads(capsys.readouterr().out)
        assert payload["items"] == [{"id": "1"}]
        assert payload["meta"] == meta

    def test_fields_does_not_mutate_input(self, capsys) -> None:
        """`rows` is the caller's live server data — project a copy."""
        rows = copy.deepcopy(ROWS)
        print_table(rows, COLUMNS, json_mode=True, fields=["id"])
        capsys.readouterr()
        assert rows == ROWS

    def test_fields_overrides_table_columns(self, capsys) -> None:
        print_table(ROWS, COLUMNS, fields=["extra"])
        out = capsys.readouterr().out
        assert "extra" in out
        assert "kept" in out
        assert "One" not in out


class TestPrintTableTable:
    def test_table_mode_renders_columns(self, capsys) -> None:
        print_table(ROWS, COLUMNS)
        out = capsys.readouterr().out
        assert "title" in out
        assert "One" in out

    def test_table_renders_missing_field_as_blank(self, capsys) -> None:
        """Not the literal string "None" — the pre-0.6.0 behaviour."""
        print_table([{"id": "1"}], COLUMNS, fields=["id", "nope"])
        assert "None" not in capsys.readouterr().out

    def test_table_renders_explicit_null_as_blank(self, capsys) -> None:
        print_table([{"id": "1", "parentPageId": None}], ["id", "parentPageId"])
        assert "None" not in capsys.readouterr().out

    def test_table_renders_container_as_json(self, capsys) -> None:
        print_table([{"content": {"type": "doc"}}], ["content"])
        assert '"type"' in capsys.readouterr().out

    def test_table_footer_on_stderr_when_more_pages(self, capsys) -> None:
        print_table(ROWS, COLUMNS, meta={"hasNextPage": True, "nextCursor": "c2"})
        captured = capsys.readouterr()
        assert "c2" in captured.err
        assert "c2" not in captured.out

    def test_no_footer_when_no_more_pages(self, capsys) -> None:
        print_table(ROWS, COLUMNS, meta={"hasNextPage": False, "nextCursor": None})
        assert capsys.readouterr().err == ""


class TestPrintJson:
    def test_writes_indented_json_to_stdout(self, capsys) -> None:
        print_json({"a": 1})
        captured = capsys.readouterr()
        assert json.loads(captured.out) == {"a": 1}
        assert captured.err == ""

    def test_serializes_non_json_types(self, capsys) -> None:
        print_json({"when": datetime(2026, 1, 1)})
        payload = json.loads(capsys.readouterr().out)
        assert payload["when"].startswith("2026-01-01")


class TestPrintWarning:
    def test_goes_to_stderr(self, capsys) -> None:
        print_warning("careful")
        captured = capsys.readouterr()
        assert "careful" in captured.err
        assert captured.out == ""

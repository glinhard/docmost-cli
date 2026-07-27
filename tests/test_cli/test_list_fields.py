"""Tests for lossless --json and the --fields projection.

`emit_list` is the single funnel from all eight list commands, so `space list`
exercises the shared behaviour for all of them.

These assert on parsed JSON rather than output substrings: substring assertions
are what let the pre-0.6.0 lossy projection go unnoticed.
"""

import json

from typer.testing import CliRunner

from docmost_cli.cli.main import app

runner = CliRunner()

# `visibility`, `defaultRole` and `createdAt` sit outside space list's
# ["id", "name", "slug", "description"] table columns.
SPACE = {
    "id": "s1",
    "name": "Engineering",
    "slug": "eng",
    "description": "Eng space",
    "visibility": "open",
    "defaultRole": "writer",
    "createdAt": "2026-07-01T00:00:00Z",
}


def _combined(result) -> str:
    """Command output regardless of whether click separates stderr."""
    try:
        return result.output + result.stderr
    except ValueError:
        return result.output


def _mock_spaces(httpx_mock, items=None, *, has_next=False) -> None:
    httpx_mock.add_response(
        url="https://docs.example.com/api/spaces",
        json={
            "data": {
                "items": [SPACE] if items is None else items,
                "meta": {"hasNextPage": has_next, "nextCursor": "c2" if has_next else None},
            }
        },
    )


def _run(tmp_config, *args):
    return runner.invoke(app, ["--config", str(tmp_config), "space", "list", *args])


class TestJsonIsLossless:
    def test_json_keeps_fields_outside_columns(self, tmp_config, httpx_mock) -> None:
        _mock_spaces(httpx_mock)
        result = _run(tmp_config, "--json")
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload[0]["visibility"] == "open"
        assert payload[0]["defaultRole"] == "writer"

    def test_json_is_still_a_bare_array(self, tmp_config, httpx_mock) -> None:
        _mock_spaces(httpx_mock)
        payload = json.loads(_run(tmp_config, "--json").output)
        assert isinstance(payload, list)

    def test_table_keeps_curated_columns(self, tmp_config, httpx_mock) -> None:
        _mock_spaces(httpx_mock)
        result = _run(tmp_config)
        assert result.exit_code == 0
        assert "visibility" not in result.output


class TestFieldsProjection:
    def test_projects_json(self, tmp_config, httpx_mock) -> None:
        _mock_spaces(httpx_mock)
        payload = json.loads(_run(tmp_config, "--json", "--fields", "slug,visibility").output)
        assert list(payload[0]) == ["slug", "visibility"]

    def test_overrides_table_columns(self, tmp_config, httpx_mock) -> None:
        _mock_spaces(httpx_mock)
        result = _run(tmp_config, "--fields", "slug,visibility")
        assert result.exit_code == 0
        assert "visibility" in result.output
        assert "description" not in result.output

    def test_tolerates_whitespace_and_empty_segments(self, tmp_config, httpx_mock) -> None:
        _mock_spaces(httpx_mock)
        payload = json.loads(_run(tmp_config, "--json", "--fields", " slug , , name ").output)
        assert list(payload[0]) == ["slug", "name"]

    def test_deduplicates(self, tmp_config, httpx_mock) -> None:
        _mock_spaces(httpx_mock)
        payload = json.loads(_run(tmp_config, "--json", "--fields", "slug,slug").output)
        assert list(payload[0]) == ["slug"]


class TestFieldsValidation:
    def test_unknown_field_exits_2(self, tmp_config, httpx_mock) -> None:
        _mock_spaces(httpx_mock)
        result = _run(tmp_config, "--json", "--fields", "slugg")
        assert result.exit_code == 2
        combined = _combined(result)
        assert "slugg" in combined
        assert "slug" in combined  # the Available: list

    def test_unknown_field_rejected_in_table_mode_too(self, tmp_config, httpx_mock) -> None:
        _mock_spaces(httpx_mock)
        assert _run(tmp_config, "--fields", "slugg").exit_code == 2

    def test_empty_result_skips_validation(self, tmp_config, httpx_mock) -> None:
        """No items means no information about which names are valid."""
        _mock_spaces(httpx_mock, items=[])
        result = _run(tmp_config, "--json", "--fields", "whatever")
        assert result.exit_code == 0
        assert json.loads(result.output) == []

    def test_bare_comma_exits_2(self, tmp_config, httpx_mock) -> None:
        _mock_spaces(httpx_mock)
        assert _run(tmp_config, "--json", "--fields", ",").exit_code == 2


class TestEnvelope:
    def test_envelope_wraps_complete_objects(self, tmp_config, httpx_mock) -> None:
        _mock_spaces(httpx_mock)
        result = _run(tmp_config, "--no-follow", "--json", "--envelope")
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["items"][0]["visibility"] == "open"
        assert payload["meta"]["hasNextPage"] is False

    def test_envelope_with_fields_projects_items_only(self, tmp_config, httpx_mock) -> None:
        _mock_spaces(httpx_mock)
        result = _run(tmp_config, "--no-follow", "--json", "--envelope", "--fields", "slug")
        payload = json.loads(result.output)
        assert payload["items"] == [{"slug": "eng"}]
        assert "hasNextPage" in payload["meta"]

"""Tests for pagination utilities."""

from typing import Any

import pytest

from docmost_cli.api.pagination import (
    extract_items,
    get_cursor,
    get_meta,
    paginate_all,
    paginate_iter,
)


def _page(
    items: list[dict[str, Any]],
    *,
    has_next: bool = False,
    next_cursor: str | None = None,
) -> dict[str, Any]:
    """Build a Docmost-shaped paginated response."""
    return {
        "data": {
            "items": items,
            "meta": {
                "limit": 100,
                "hasNextPage": has_next,
                "hasPrevPage": False,
                "nextCursor": next_cursor,
                "prevCursor": None,
            },
        }
    }


class _FakeApi:
    """Records calls and serves canned pages in order."""

    def __init__(self, pages: list[dict[str, Any]]) -> None:
        self._pages = pages
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        index = min(len(self.calls) - 1, len(self._pages) - 1)
        return self._pages[index]


class TestExtractItems:
    def test_data_items_shape(self) -> None:
        response = {"data": {"items": [{"id": "1"}, {"id": "2"}]}}
        result = extract_items(response)
        assert result == [{"id": "1"}, {"id": "2"}]

    def test_data_list_shape(self) -> None:
        response = {"data": [{"id": "a"}, {"id": "b"}]}
        result = extract_items(response)
        assert result == [{"id": "a"}, {"id": "b"}]

    def test_items_shape(self) -> None:
        response = {"items": [{"id": "x"}, {"id": "y"}]}
        result = extract_items(response)
        assert result == [{"id": "x"}, {"id": "y"}]

    def test_flat_dict_shape(self) -> None:
        response = {"id": "flat-123", "name": "Single Item"}
        result = extract_items(response)
        assert result == [{"id": "flat-123", "name": "Single Item"}]

    def test_empty_data_items(self) -> None:
        response = {"data": {"items": []}}
        result = extract_items(response)
        assert result == []

    def test_no_items_no_id(self) -> None:
        response = {"status": "ok"}
        result = extract_items(response)
        assert result == []


class TestGetCursor:
    def test_data_meta_next_cursor(self) -> None:
        """The shape Docmost actually returns."""
        response = _page([], has_next=True, next_cursor="c2")
        assert get_cursor(response) == "c2"

    def test_meta_next_cursor_beats_legacy_cursor(self) -> None:
        response = {"data": {"items": [], "cursor": "legacy", "meta": {"nextCursor": "c2"}}}
        assert get_cursor(response) == "c2"

    def test_top_level_meta_next_cursor(self) -> None:
        response = {"items": [], "meta": {"nextCursor": "c9"}}
        assert get_cursor(response) == "c9"

    def test_nested_cursor(self) -> None:
        response = {"data": {"items": [], "cursor": "abc123"}}
        cursor = get_cursor(response)
        assert cursor == "abc123"

    def test_top_level_cursor(self) -> None:
        response = {"items": [], "cursor": "next-page"}
        cursor = get_cursor(response)
        assert cursor == "next-page"

    def test_returns_none_when_no_cursor(self) -> None:
        response = {"data": {"items": []}}
        cursor = get_cursor(response)
        assert cursor is None

    def test_returns_none_for_empty_response(self) -> None:
        response: dict[str, Any] = {}
        cursor = get_cursor(response)
        assert cursor is None

    def test_returns_none_when_cursor_is_none(self) -> None:
        response = {"data": {"items": [], "cursor": None}}
        cursor = get_cursor(response)
        assert cursor is None


class TestGetMeta:
    def test_parses_camel_case_aliases(self) -> None:
        meta = get_meta(_page([], has_next=True, next_cursor="c2"))
        assert meta.has_next_page is True
        assert meta.next_cursor == "c2"
        assert meta.limit == 100
        assert meta.has_prev_page is False

    def test_missing_meta_returns_defaults(self) -> None:
        meta = get_meta({"data": {"items": []}})
        assert meta.has_next_page is False
        assert meta.next_cursor is None

    def test_synthesized_from_legacy_cursor(self) -> None:
        meta = get_meta({"data": {"items": [], "cursor": "x"}})
        assert meta.has_next_page is True
        assert meta.next_cursor == "x"

    def test_round_trips_to_camel_case(self) -> None:
        meta = get_meta(_page([], has_next=True, next_cursor="c2"))
        dumped = meta.model_dump(by_alias=True)
        assert dumped["hasNextPage"] is True
        assert dumped["nextCursor"] == "c2"


class TestPaginateAll:
    def test_follows_two_pages(self) -> None:
        api = _FakeApi(
            [
                _page([{"id": "1"}, {"id": "2"}], has_next=True, next_cursor="c2"),
                _page([{"id": "3"}]),
            ]
        )
        result = paginate_all(api)
        assert [item["id"] for item in result.items] == ["1", "2", "3"]
        assert result.pages_fetched == 2
        assert result.truncated is False
        assert api.calls[0]["cursor"] is None
        assert api.calls[0]["limit"] == 100
        assert api.calls[1]["cursor"] == "c2"

    def test_stops_when_has_next_page_false(self) -> None:
        api = _FakeApi([_page([{"id": "1"}], has_next=False, next_cursor="ignored")])
        result = paginate_all(api)
        assert len(api.calls) == 1
        assert result.truncated is False

    def test_repeated_cursor_guard(self) -> None:
        """A server that ignores `cursor` must not loop forever."""
        api = _FakeApi([_page([{"id": "1"}], has_next=True, next_cursor="same")])
        result = paginate_all(api)
        assert len(api.calls) == 2
        assert [item["id"] for item in result.items] == ["1"]
        assert result.truncated is True

    def test_honors_total_limit(self) -> None:
        api = _FakeApi(
            [
                _page([{"id": str(n)} for n in range(100)], has_next=True, next_cursor="c2"),
                _page([{"id": "x"}]),
            ]
        )
        result = paginate_all(api, limit=5)
        assert len(result.items) == 5
        assert result.truncated is True
        assert api.calls[0]["limit"] == 5

    def test_limit_spans_multiple_requests(self) -> None:
        api = _FakeApi(
            [
                _page([{"id": f"a{n}"} for n in range(100)], has_next=True, next_cursor="c2"),
                _page([{"id": f"b{n}"} for n in range(100)], has_next=True, next_cursor="c3"),
            ]
        )
        result = paginate_all(api, limit=150)
        assert len(result.items) == 150
        assert api.calls[0]["limit"] == 100
        assert api.calls[1]["limit"] == 50

    def test_clamps_page_size_to_server_max(self) -> None:
        api = _FakeApi([_page([{"id": "1"}])])
        paginate_all(api, page_size=500)
        assert api.calls[0]["limit"] == 100

    def test_rejects_limit_in_kwargs(self) -> None:
        api = _FakeApi([_page([])])
        with pytest.raises(TypeError):
            paginate_all(api, foo=1, **{"cursor": "x"})

    def test_max_pages_guard(self) -> None:
        pages = [_page([{"id": str(n)}], has_next=True, next_cursor=f"c{n}") for n in range(10)]
        api = _FakeApi(pages)
        result = paginate_all(api, max_pages=3)
        assert len(api.calls) == 3
        assert result.truncated is True

    def test_stops_on_empty_page(self) -> None:
        api = _FakeApi(
            [
                _page([{"id": "1"}], has_next=True, next_cursor="c2"),
                _page([], has_next=True, next_cursor="c3"),
            ]
        )
        result = paginate_all(api)
        assert len(result.items) == 1
        assert len(api.calls) == 2


class TestPaginateIter:
    def test_lazy_stops_early(self) -> None:
        api = _FakeApi(
            [
                _page([{"id": "1"}, {"id": "2"}], has_next=True, next_cursor="c2"),
                _page([{"id": "3"}]),
            ]
        )
        first = next(iter(paginate_iter(api)))
        assert first["id"] == "1"
        assert len(api.calls) == 1

    def test_yields_across_pages(self) -> None:
        api = _FakeApi(
            [
                _page([{"id": "1"}], has_next=True, next_cursor="c2"),
                _page([{"id": "2"}]),
            ]
        )
        assert [item["id"] for item in paginate_iter(api)] == ["1", "2"]

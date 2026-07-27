"""Tests for Space API methods."""

import pytest

from docmost_cli.api.client import DocmostClient
from docmost_cli.api.spaces import (
    create_space,
    get_space_info,
    list_all_spaces,
    list_spaces,
    resolve_space_id,
    update_space,
)


class TestListSpaces:
    def test_returns_spaces(self, httpx_mock, api_key_settings) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/spaces",
            json={"data": {"items": [{"id": "s1", "name": "Eng", "slug": "eng"}]}},
        )
        with DocmostClient(api_key_settings) as client:
            result = list_spaces(client)
        assert result["data"]["items"][0]["slug"] == "eng"

    def test_with_limit(self, httpx_mock, api_key_settings) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/spaces",
            json={"data": {"items": [], "cursor": None}},
        )
        with DocmostClient(api_key_settings) as client:
            list_spaces(client, limit=10)
        request = httpx_mock.get_requests()[0]
        body = request.read()
        assert b'"limit":10' in body or b'"limit": 10' in body


class TestGetSpaceInfo:
    def test_by_slug(self, httpx_mock, api_key_settings) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/spaces",
            json={"data": {"items": [{"id": "space-123", "name": "Engineering", "slug": "eng"}]}},
        )
        with DocmostClient(api_key_settings) as client:
            result = get_space_info(client, slug="eng")
        assert result["id"] == "space-123"

    def test_by_id(self, httpx_mock, api_key_settings) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/spaces/info",
            json={"id": "space-123", "name": "Engineering", "slug": "eng"},
        )
        with DocmostClient(api_key_settings) as client:
            result = get_space_info(client, space_id="space-123")
        assert result["slug"] == "eng"


class TestResolveSpaceId:
    def test_returns_id(self, httpx_mock, api_key_settings) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/spaces",
            json={"data": {"items": [{"id": "space-uuid", "slug": "eng", "name": "Eng"}]}},
        )
        with DocmostClient(api_key_settings) as client:
            space_id = resolve_space_id(client, "eng")
        assert space_id == "space-uuid"

    def test_nested_response(self, httpx_mock, api_key_settings) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/spaces",
            json={"data": {"items": [{"id": "space-nested", "slug": "eng", "name": "Eng"}]}},
        )
        with DocmostClient(api_key_settings) as client:
            space_id = resolve_space_id(client, "eng")
        assert space_id == "space-nested"

    def test_not_found(self, httpx_mock, api_key_settings) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/spaces",
            json={"data": {"items": []}},
        )
        with DocmostClient(api_key_settings) as client, pytest.raises(SystemExit) as exc:
            resolve_space_id(client, "nonexistent")
        assert exc.value.code == 4


class TestFindSpaceBySlug:
    def test_found_on_second_page(self, httpx_mock, api_key_settings) -> None:
        """Slug resolution must follow pagination, not scan only page 1."""
        httpx_mock.add_response(
            url="https://docs.example.com/api/spaces",
            json={
                "data": {
                    "items": [{"id": "s1", "slug": "other", "name": "Other"}],
                    "meta": {"hasNextPage": True, "nextCursor": "c2"},
                }
            },
        )
        httpx_mock.add_response(
            url="https://docs.example.com/api/spaces",
            json={
                "data": {
                    "items": [{"id": "s2", "slug": "eng", "name": "Eng"}],
                    "meta": {"hasNextPage": False, "nextCursor": None},
                }
            },
        )
        with DocmostClient(api_key_settings) as client:
            space_id = resolve_space_id(client, "eng")
        assert space_id == "s2"
        assert len(httpx_mock.get_requests()) == 2

    def test_stops_at_first_match(self, httpx_mock, api_key_settings) -> None:
        """A match on page 1 must not cost a second request."""
        httpx_mock.add_response(
            url="https://docs.example.com/api/spaces",
            json={
                "data": {
                    "items": [{"id": "s1", "slug": "eng", "name": "Eng"}],
                    "meta": {"hasNextPage": True, "nextCursor": "c2"},
                }
            },
        )
        with DocmostClient(api_key_settings) as client:
            space_id = resolve_space_id(client, "eng")
        assert space_id == "s1"
        assert len(httpx_mock.get_requests()) == 1

    def test_list_all_spaces_follows_pages(self, httpx_mock, api_key_settings) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/spaces",
            json={
                "data": {
                    "items": [{"id": "s1", "slug": "a"}],
                    "meta": {"hasNextPage": True, "nextCursor": "c2"},
                }
            },
        )
        httpx_mock.add_response(
            url="https://docs.example.com/api/spaces",
            json={
                "data": {
                    "items": [{"id": "s2", "slug": "b"}],
                    "meta": {"hasNextPage": False, "nextCursor": None},
                }
            },
        )
        with DocmostClient(api_key_settings) as client:
            spaces = list_all_spaces(client)
        assert [s["id"] for s in spaces] == ["s1", "s2"]


class TestCreateSpace:
    def test_creates_space(self, httpx_mock, api_key_settings) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/spaces/create",
            json={"id": "new-space", "name": "Test", "slug": "test"},
        )
        with DocmostClient(api_key_settings) as client:
            result = create_space(client, name="Test", slug="test")
        assert result["id"] == "new-space"


class TestUpdateSpace:
    def test_updates_space(self, httpx_mock, api_key_settings) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/spaces/update",
            json={"id": "space-123", "name": "Updated"},
        )
        with DocmostClient(api_key_settings) as client:
            result = update_space(client, space_id="space-123", name="Updated")
        assert result["name"] == "Updated"

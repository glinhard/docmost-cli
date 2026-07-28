"""Tests for DocmostClient."""

import pytest

from docmost_cli.api.client import DocmostClient
from docmost_cli.config.settings import DocmostSettings


class TestDocmostClient:
    def test_successful_post(self, httpx_mock, api_key_settings) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/users/me",
            json={"name": "Test User", "email": "test@example.com"},
        )
        with DocmostClient(api_key_settings) as client:
            result = client.post("/users/me")
        assert result["name"] == "Test User"

    def test_auth_header_sent(self, httpx_mock, api_key_settings) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/users/me",
            json={"name": "Test"},
        )
        with DocmostClient(api_key_settings) as client:
            client.post("/users/me")

        request = httpx_mock.get_requests()[0]
        assert request.headers["Authorization"] == "Bearer dm_test1234567890"

    def test_401_exits_with_code_3(self, httpx_mock, api_key_settings) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/users/me",
            status_code=401,
        )
        with DocmostClient(api_key_settings) as client, pytest.raises(SystemExit) as exc_info:
            client.post("/users/me")
        assert exc_info.value.code == 3

    def test_404_exits_with_code_4(self, httpx_mock, api_key_settings) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/info",
            status_code=404,
        )
        with DocmostClient(api_key_settings) as client, pytest.raises(SystemExit) as exc_info:
            client.post("/pages/info", json={"pageId": "nonexistent"})
        assert exc_info.value.code == 4

    def test_422_exits_with_message(self, httpx_mock, api_key_settings, capsys) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/create",
            status_code=422,
            json={"message": "Title is required"},
        )
        with DocmostClient(api_key_settings) as client, pytest.raises(SystemExit) as exc_info:
            client.post("/pages/create", json={})
        assert exc_info.value.code == 1

    def test_500_exits_with_code_1(self, httpx_mock, api_key_settings, monkeypatch) -> None:
        monkeypatch.setattr("time.sleep", lambda _: None)
        # Need 1 initial + 3 retries = 4 responses for 500
        for _ in range(4):
            httpx_mock.add_response(
                url="https://docs.example.com/api/users/me",
                status_code=500,
            )
        with DocmostClient(api_key_settings) as client, pytest.raises(SystemExit) as exc_info:
            client.post("/users/me")
        assert exc_info.value.code == 1

    def test_no_url_exits(self) -> None:
        settings = DocmostSettings(api_key="dm_key")
        with pytest.raises(SystemExit):
            DocmostClient(settings)

    def test_session_auth_401_retry(self, httpx_mock, session_settings) -> None:
        # First request returns 401
        httpx_mock.add_response(
            url="https://docs.example.com/api/users/me",
            status_code=401,
        )
        # Login succeeds
        httpx_mock.add_response(
            url="https://docs.example.com/api/auth/login",
            json={"token": "new_jwt"},
        )
        # Retry succeeds
        httpx_mock.add_response(
            url="https://docs.example.com/api/users/me",
            json={"name": "Retry User"},
        )

        with DocmostClient(session_settings) as client:
            result = client.post("/users/me")
        assert result["name"] == "Retry User"

    def test_context_manager(self, api_key_settings) -> None:
        with DocmostClient(api_key_settings) as client:
            assert client is not None

    def test_429_retries_then_succeeds(self, httpx_mock, api_key_settings, monkeypatch) -> None:
        monkeypatch.setattr("time.sleep", lambda _: None)
        # First two return 429, third succeeds
        httpx_mock.add_response(
            url="https://docs.example.com/api/users/me",
            status_code=429,
        )
        httpx_mock.add_response(
            url="https://docs.example.com/api/users/me",
            status_code=429,
        )
        httpx_mock.add_response(
            url="https://docs.example.com/api/users/me",
            json={"name": "Success"},
        )
        with DocmostClient(api_key_settings) as client:
            result = client.post("/users/me")
        assert result["name"] == "Success"

    def test_429_all_retries_exhausted(self, httpx_mock, api_key_settings, monkeypatch) -> None:
        monkeypatch.setattr("time.sleep", lambda _: None)
        for _ in range(4):
            httpx_mock.add_response(
                url="https://docs.example.com/api/users/me",
                status_code=429,
            )
        with DocmostClient(api_key_settings) as client, pytest.raises(SystemExit) as exc:
            client.post("/users/me")
        assert exc.value.code == 1

    def test_base_url_is_public(self, api_key_settings) -> None:
        with DocmostClient(api_key_settings) as client:
            assert client.base_url == "https://docs.example.com"

    def test_verbose_mode(self, httpx_mock, api_key_settings, capfd) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/users/me",
            json={"name": "Test"},
        )
        with DocmostClient(api_key_settings, verbose=True) as client:
            client.post("/users/me")
        captured = capfd.readouterr()
        assert "POST" in captured.err
        assert "200" in captured.err


class TestPostRaw:
    """`post_raw` is the one method that used to skip the shared retry path.

    With `raise_on_error` it must behave like every other call — same 401
    re-authentication, same backoff — because `page export`, its only such
    caller, is otherwise the one command a Community-edition user cannot run
    with an expired session. Probes keep the old single-shot behaviour, which
    the Enterprise/Community fallbacks depend on.
    """

    def test_401_triggers_reauth_and_retries(self, httpx_mock, session_settings) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/export",
            status_code=401,
        )
        httpx_mock.add_response(
            url="https://docs.example.com/api/auth/login",
            json={"token": "fresh_jwt"},
        )
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/export",
            content=b"ZIPBYTES",
        )

        with DocmostClient(session_settings) as client:
            response = client.post_raw("/pages/export", json={"pageId": "p1"})

        assert response.content == b"ZIPBYTES"
        assert response.request.headers["Authorization"] == "Bearer fresh_jwt"

    def test_transient_5xx_is_retried(self, httpx_mock, api_key_settings, monkeypatch) -> None:
        monkeypatch.setattr("time.sleep", lambda _: None)
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/export",
            status_code=503,
        )
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/export",
            content=b"ZIPBYTES",
        )

        with DocmostClient(api_key_settings) as client:
            response = client.post_raw("/pages/export", json={"pageId": "p1"})

        assert response.content == b"ZIPBYTES"

    def test_error_status_still_exits(self, httpx_mock, api_key_settings) -> None:
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/export",
            status_code=404,
        )
        with DocmostClient(api_key_settings) as client, pytest.raises(SystemExit) as exc:
            client.post_raw("/pages/export", json={"pageId": "nope"})
        assert exc.value.code == 4

    def test_probe_does_not_retry_or_exit(self, httpx_mock, api_key_settings) -> None:
        """A single 404 response is enough: no retry, no SystemExit."""
        httpx_mock.add_response(
            url="https://docs.example.com/api/pages/content",
            status_code=404,
        )
        with DocmostClient(api_key_settings) as client:
            response = client.post_raw(
                "/pages/content", json={"pageId": "p1"}, raise_on_error=False
            )

        assert response.status_code == 404
        assert len(httpx_mock.get_requests()) == 1

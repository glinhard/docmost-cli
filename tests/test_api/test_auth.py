"""Tests for authentication strategies."""

import httpx
import pytest

from docmost_cli.api.auth import (
    ApiKeyAuth,
    AuthError,
    SessionAuth,
    create_auth,
)
from docmost_cli.config.settings import DocmostSettings


class TestApiKeyAuth:
    def test_apply_sets_bearer_header(self) -> None:
        auth = ApiKeyAuth("dm_testkey123")
        request = httpx.Request("POST", "https://example.com/api/test")
        auth.apply(request)
        assert request.headers["Authorization"] == "Bearer dm_testkey123"

    def test_can_retry_is_false(self) -> None:
        auth = ApiKeyAuth("dm_testkey123")
        assert auth.can_retry() is False

    def test_refresh_raises(self) -> None:
        auth = ApiKeyAuth("dm_testkey123")
        with pytest.raises(AuthError, match="API key"):
            auth.refresh(httpx.Client())


class TestSessionAuth:
    def test_apply_with_no_token(self) -> None:
        auth = SessionAuth("https://example.com", "user@test.com", "pass")
        request = httpx.Request("POST", "https://example.com/api/test")
        auth.apply(request)
        assert "Authorization" not in request.headers

    def test_can_retry_is_true(self) -> None:
        auth = SessionAuth("https://example.com", "user@test.com", "pass")
        assert auth.can_retry() is True

    def test_refresh_success(self, httpx_mock) -> None:
        httpx_mock.add_response(
            url="https://example.com/api/auth/login",
            json={"token": "jwt_test_token"},
        )
        auth = SessionAuth("https://example.com", "user@test.com", "pass")
        client = httpx.Client()
        auth.refresh(client)
        client.close()

        # Verify token is now applied
        request = httpx.Request("POST", "https://example.com/api/test")
        auth.apply(request)
        assert request.headers["Authorization"] == "Bearer jwt_test_token"

    def test_refresh_failure(self, httpx_mock) -> None:
        httpx_mock.add_response(
            url="https://example.com/api/auth/login",
            status_code=401,
        )
        auth = SessionAuth("https://example.com", "user@test.com", "pass")
        client = httpx.Client()
        with pytest.raises(AuthError, match="Authentication failed"):
            auth.refresh(client)
        client.close()

    def test_cached_token_roundtrip(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))

        # Create auth and manually set token, then save
        auth = SessionAuth("https://example.com", "user@test.com", "pass")
        auth._token = "cached_jwt"
        auth._save_cached_token()

        # New instance should load cached token
        auth2 = SessionAuth("https://example.com", "user@test.com", "pass")
        assert auth2._token == "cached_jwt"

    def test_cached_token_wrong_url(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))

        auth = SessionAuth("https://example.com", "user@test.com", "pass")
        auth._token = "cached_jwt"
        auth._save_cached_token()

        # Different URL should not load the cached token
        auth2 = SessionAuth("https://other.com", "user@test.com", "pass")
        assert auth2._token is None


class TestSessionAuthNoCache:
    """With use_cache=False the JWT must never touch disk."""

    def test_does_not_read_existing_cache(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
        seeded = SessionAuth("https://example.com", "user@test.com", "pass")
        seeded._token = "cached_jwt"
        seeded._save_cached_token()

        auth = SessionAuth("https://example.com", "user@test.com", "pass", use_cache=False)
        assert auth._token is None

    def test_does_not_write_cache(self, tmp_path, monkeypatch, httpx_mock) -> None:
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
        httpx_mock.add_response(
            url="https://example.com/api/auth/login",
            json={"token": "jwt_test_token"},
        )
        auth = SessionAuth("https://example.com", "user@test.com", "pass", use_cache=False)
        client = httpx.Client()
        auth.refresh(client)
        client.close()

        assert not (tmp_path / "docmost-cli" / "session.json").exists()

        # The token still works in memory for this process.
        request = httpx.Request("GET", "https://example.com/api/pages/info")
        auth.apply(request)
        assert request.headers["Authorization"] == "Bearer jwt_test_token"


class TestCreateAuth:
    def test_api_key_preferred(self) -> None:
        settings = DocmostSettings(
            url="https://example.com",
            api_key="dm_key",
            email="user@test.com",
            password="pass",
        )
        auth = create_auth(settings)
        assert isinstance(auth, ApiKeyAuth)

    def test_session_when_no_api_key(self) -> None:
        settings = DocmostSettings(
            url="https://example.com",
            email="user@test.com",
            password="pass",
        )
        auth = create_auth(settings)
        assert isinstance(auth, SessionAuth)

    def test_api_key_only(self) -> None:
        settings = DocmostSettings(
            url="https://example.com",
            api_key="dm_key",
        )
        auth = create_auth(settings)
        assert isinstance(auth, ApiKeyAuth)

    def test_no_credentials_raises(self) -> None:
        settings = DocmostSettings(url="https://example.com")
        with pytest.raises(AuthError, match="No authentication configured"):
            create_auth(settings)

    def test_session_without_url_raises(self) -> None:
        settings = DocmostSettings(email="user@test.com", password="pass")
        with pytest.raises(AuthError, match="URL is required"):
            create_auth(settings)

    def test_no_session_cache_is_threaded_through(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
        settings = DocmostSettings(
            url="https://example.com",
            email="user@test.com",
            password="pass",
            no_session_cache=True,
        )
        auth = create_auth(settings)
        assert isinstance(auth, SessionAuth)
        assert auth._use_cache is False

    def test_session_cache_on_by_default(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
        settings = DocmostSettings(
            url="https://example.com",
            email="user@test.com",
            password="pass",
        )
        auth = create_auth(settings)
        assert isinstance(auth, SessionAuth)
        assert auth._use_cache is True

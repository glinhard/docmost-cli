"""DocmostClient: central HTTP client with auth, retry, and error handling.

All API calls go through this client. It handles:
- Auth header injection via AuthStrategy
- 401 retry (session auth re-authentication)
- Exponential backoff retry for transient errors (429, 5xx)
- HTTP error translation to user-friendly messages with exit codes
- Optional verbose debug logging
"""

import logging
import sys
import time
from typing import Any, cast

import httpx

from docmost_cli.api.auth import AuthError, AuthStrategy, create_auth
from docmost_cli.config.settings import DocmostSettings
from docmost_cli.output.formatter import print_error

__all__ = ["DocmostClient"]

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_MAX_RETRIES = 3
_BASE_BACKOFF = 1.0
_BACKOFF_FACTOR = 2.0


class DocmostClient:
    """HTTP client for the Docmost API.

    Uses httpx.Client for connection pooling. Provides authenticated
    request methods with automatic error handling and retry logic.
    """

    def __init__(self, settings: DocmostSettings, *, verbose: bool = False) -> None:
        if not settings.url:
            print_error(
                "No Docmost URL configured. Run 'docmost-cli config init' or set DOCMOST_URL.",
                exit_code=1,
            )

        self._settings = settings
        self._base_url = settings.url.rstrip("/")
        self._auth: AuthStrategy = create_auth(settings)
        self._http = httpx.Client(timeout=30.0)
        self._verbose = verbose

        # Set up logging
        self._log = logging.getLogger("docmost_cli")
        if verbose and not self._log.handlers:
            handler = logging.StreamHandler(sys.stderr)
            handler.setFormatter(logging.Formatter("[docmost] %(message)s"))
            self._log.addHandler(handler)
            self._log.setLevel(logging.DEBUG)

    @property
    def base_url(self) -> str:
        """The Docmost base URL this client talks to, without a trailing slash."""
        return self._base_url

    def _rebuild(self, request: httpx.Request) -> httpx.Request:
        """Clone a request and re-apply auth, ready to be sent again.

        httpx requests are single-use once their body stream is consumed, so
        both the 401-refresh path and the backoff path need a fresh copy
        carrying whatever header the (possibly refreshed) strategy now supplies.
        """
        rebuilt = self._http.build_request(
            request.method,
            str(request.url),
            headers=dict(request.headers),
            content=request.content,
        )
        self._auth.apply(rebuilt)
        return rebuilt

    def _send_with_retry(self, request: httpx.Request) -> httpx.Response:
        """Send a request with auth, retry on 401/429/5xx, and error handling.

        Args:
            request: The prepared httpx request.

        Returns:
            The HTTP response (success only; errors raise SystemExit).
        """
        self._auth.apply(request)

        if self._verbose:
            self._log.debug("%s %s", request.method, request.url)

        start = time.monotonic()

        try:
            response = self._http.send(request)
        except httpx.ConnectError:
            print_error(
                f"Cannot connect to {self._base_url}. Check the URL and your network.",
                exit_code=1,
            )
        except httpx.TimeoutException:
            print_error(
                f"Request timed out connecting to {self._base_url}.",
                exit_code=1,
            )

        if self._verbose:
            elapsed = (time.monotonic() - start) * 1000
            self._log.debug("  → %s (%dms)", response.status_code, elapsed)

        # Handle 401 retry for session auth
        if response.status_code == 401 and self._auth.can_retry():
            try:
                self._auth.refresh(self._http)
            except AuthError as exc:
                print_error(str(exc), exit_code=3)

            request = self._rebuild(request)
            try:
                response = self._http.send(request)
            except httpx.HTTPError:
                print_error("Request failed after re-authentication.", exit_code=1)

        # Exponential backoff retry for transient errors
        for attempt in range(_MAX_RETRIES):
            if response.status_code not in _RETRYABLE_STATUS:
                break

            # Parse Retry-After header for 429
            wait = _BASE_BACKOFF * (_BACKOFF_FACTOR**attempt)
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    wait = min(float(retry_after), 60.0)

            if self._verbose:
                self._log.debug(
                    "  Retrying in %.1fs (attempt %d/%d)...",
                    wait,
                    attempt + 1,
                    _MAX_RETRIES,
                )

            time.sleep(wait)

            request = self._rebuild(request)
            try:
                response = self._http.send(request)
            except httpx.HTTPError:
                if attempt == _MAX_RETRIES - 1:
                    print_error(
                        f"Request failed after {_MAX_RETRIES} retries.",
                        exit_code=1,
                    )
                continue

            if self._verbose:
                self._log.debug("  → %s (retry)", response.status_code)

        # Translate HTTP errors
        self._handle_error(response)

        return response

    def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        """Make an authenticated API request with error handling.

        Args:
            method: HTTP method (GET, POST, etc.).
            path: API path relative to /api/ (e.g., "/pages/info").
            **kwargs: Additional arguments passed to httpx (json, params, etc.).

        Returns:
            Parsed JSON response body.
        """
        url = f"{self._base_url}/api{path}"
        request = self._http.build_request(method, url, **kwargs)
        response = self._send_with_retry(request)
        # Every Docmost endpoint returns a JSON object envelope.
        return cast("dict[str, Any]", response.json())

    def post(self, path: str, json: dict[str, Any] | None = None) -> dict[str, Any]:
        """Convenience method for POST requests.

        Most Docmost API endpoints use POST.

        Args:
            path: API path relative to /api/.
            json: JSON body to send.

        Returns:
            Parsed JSON response body.
        """
        return self.request("POST", path, json=json)

    def post_multipart(
        self,
        path: str,
        data: dict[str, str] | None = None,
        files: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """POST with multipart/form-data for file uploads.

        Args:
            path: API path relative to /api/.
            data: Form fields.
            files: File fields (httpx files format).

        Returns:
            Parsed JSON response body.
        """
        url = f"{self._base_url}/api{path}"
        request = self._http.build_request("POST", url, data=data, files=files)
        response = self._send_with_retry(request)
        # Every Docmost endpoint returns a JSON object envelope.
        return cast("dict[str, Any]", response.json())

    def post_raw(
        self, path: str, json: dict[str, Any] | None = None, *, raise_on_error: bool = True
    ) -> httpx.Response:
        """POST request returning raw httpx.Response.

        Use for binary/non-JSON responses or silent probes.

        With ``raise_on_error`` this behaves like every other call — same
        401 re-authentication, same backoff on 429/5xx — and only the response
        parsing differs. A probe (``raise_on_error=False``) deliberately gets
        none of that: it is one attempt, and any failure has to come back as a
        plain non-success response so the caller can fall back in silence.

        Args:
            path: API path relative to /api/.
            json: JSON body to send.
            raise_on_error: If False, skip retry and error handling (probes).
        """
        url = f"{self._base_url}/api{path}"
        request = self._http.build_request("POST", url, json=json)
        if raise_on_error:
            return self._send_with_retry(request)

        self._auth.apply(request)
        try:
            return self._http.send(request)
        except httpx.HTTPError:
            return httpx.Response(status_code=0)  # Sentinel for failed probe

    def get(self, path: str, **kwargs: Any) -> dict[str, Any]:
        """Convenience method for GET requests.

        Args:
            path: API path relative to /api/.
            **kwargs: Additional arguments (params, etc.).

        Returns:
            Parsed JSON response body.
        """
        return self.request("GET", path, **kwargs)

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._http.close()

    def __enter__(self) -> "DocmostClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    @staticmethod
    def _handle_error(response: httpx.Response) -> None:
        """Translate HTTP error responses to user-friendly messages.

        Args:
            response: The HTTP response to check.
        """
        if response.is_success:
            return

        status = response.status_code

        if status == 401:
            print_error(
                "Authentication failed. Run 'docmost-cli config test' to verify.",
                exit_code=3,
            )
        elif status == 403:
            print_error("Permission denied.", exit_code=1)
        elif status == 404:
            print_error(
                "Resource not found. Check the ID or slug.",
                exit_code=4,
            )
        elif status == 422:
            try:
                detail = response.json().get("message", "Validation error")
            except (ValueError, AttributeError):
                detail = "Validation error"
            print_error(f"Validation error: {detail}", exit_code=1)
        elif status == 429:
            print_error("Rate limited. Try again later.", exit_code=1)
        elif status >= 500:
            print_error(
                f"Server error ({status}). Check Docmost logs.",
                exit_code=1,
            )
        else:
            print_error(
                f"Unexpected error (HTTP {status}).",
                exit_code=1,
            )

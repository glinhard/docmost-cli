"""User API methods."""

from typing import Any

from docmost_cli.api.client import DocmostClient
from docmost_cli.api.pagination import unwrap_data

__all__ = [
    "get_current_user",
]


def get_current_user(client: DocmostClient) -> dict[str, Any]:
    """Get the currently authenticated user's info.

    Args:
        client: Authenticated Docmost client.

    Returns:
        Unwrapped user info dict.
    """
    result = client.post("/users/me", json={})
    data = unwrap_data(result)
    user = data.get("user")
    return user if isinstance(user, dict) else data

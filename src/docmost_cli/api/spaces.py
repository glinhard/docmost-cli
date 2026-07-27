"""Space API methods."""

from typing import Any

from docmost_cli.api.client import DocmostClient
from docmost_cli.api.pagination import build_body, unwrap_data
from docmost_cli.output.formatter import print_error

__all__ = [
    "create_space",
    "get_space_info",
    "list_all_spaces",
    "list_spaces",
    "resolve_space_id",
    "update_space",
]


def list_spaces(
    client: DocmostClient,
    *,
    limit: int | None = None,
    cursor: str | None = None,
) -> dict[str, Any]:
    """List spaces with optional pagination.

    Args:
        client: Authenticated Docmost client.
        limit: Max results to return.
        cursor: Pagination cursor.

    Returns:
        Raw API response dict.
    """
    body = build_body({}, limit=limit, cursor=cursor)
    return client.post("/spaces", json=body)


def get_space_info(
    client: DocmostClient,
    *,
    slug: str | None = None,
    space_id: str | None = None,
) -> dict[str, Any]:
    """Get space info by slug or ID.

    Args:
        client: Authenticated Docmost client.
        slug: Space slug (e.g., "engineering").
        space_id: Space UUID.

    Returns:
        Space info dict.
    """
    if space_id:
        result = client.post("/spaces/info", json={"spaceId": space_id})
        return unwrap_data(result)
    if slug:
        # /spaces/info only accepts spaceId, so search by slug in the full list
        return _find_space_by_slug(client, slug)
    print_error("Either slug or space_id is required.", exit_code=1)


def list_all_spaces(client: DocmostClient) -> list[dict[str, Any]]:
    """List every space, following pagination.

    Args:
        client: Authenticated Docmost client.

    Returns:
        List of space dicts.
    """
    from docmost_cli.api.pagination import paginate_all

    return paginate_all(list_spaces, client=client).items


def _find_space_by_slug(client: DocmostClient, slug: str) -> dict[str, Any]:
    """Find a space by slug from the spaces list.

    Follows pagination lazily and returns as soon as the slug matches, so a
    workspace with hundreds of spaces costs only as many requests as needed.

    Args:
        client: Authenticated Docmost client.
        slug: Space slug to find.

    Returns:
        Space info dict.
    """
    from docmost_cli.api.pagination import paginate_iter

    for space in paginate_iter(list_spaces, client=client):
        if space.get("slug") == slug:
            return space
    print_error(f"Space '{slug}' not found.", exit_code=4)


def resolve_space_id(client: DocmostClient, slug: str) -> str:
    """Resolve a space slug to its UUID.

    Args:
        client: Authenticated Docmost client.
        slug: Space slug.

    Returns:
        Space UUID string.
    """
    info = get_space_info(client, slug=slug)
    space_id = info.get("id")
    if not isinstance(space_id, str) or not space_id:
        print_error(f"Space '{slug}' not found.", exit_code=4)
    return space_id


def create_space(
    client: DocmostClient,
    *,
    name: str,
    slug: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """Create a new space.

    Args:
        client: Authenticated Docmost client.
        name: Space name.
        slug: Space slug (auto-generated if omitted).
        description: Space description.

    Returns:
        Raw API response dict.
    """
    body = build_body({"name": name}, slug=slug, description=description)
    return client.post("/spaces/create", json=body)


def update_space(
    client: DocmostClient,
    *,
    space_id: str,
    name: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """Update an existing space.

    Args:
        client: Authenticated Docmost client.
        space_id: Space UUID.
        name: New space name.
        description: New description.

    Returns:
        Raw API response dict.
    """
    body = build_body({"spaceId": space_id}, name=name, description=description)
    return client.post("/spaces/update", json=body)

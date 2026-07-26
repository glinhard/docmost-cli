"""Shared data models used across the project."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["SERVER_MAX_LIMIT", "PaginatedResult", "PaginationMeta"]

# Docmost rejects `limit` values above this with HTTP 400.
SERVER_MAX_LIMIT = 100


class PaginationMeta(BaseModel):
    """Cursor-pagination metadata from a Docmost response (``data.meta``).

    Docmost returns ``{"data": {"items": [...], "meta": {...}}}`` for every
    paginated endpoint. Field names are camelCase on the wire and snake_case
    here; dump with ``by_alias=True`` to round-trip the server's names.
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    limit: int | None = None
    has_next_page: bool = Field(default=False, alias="hasNextPage")
    has_prev_page: bool = Field(default=False, alias="hasPrevPage")
    next_cursor: str | None = Field(default=None, alias="nextCursor")
    prev_cursor: str | None = Field(default=None, alias="prevCursor")


class PaginatedResult(BaseModel):
    """Items collected across one or more pages, plus the last page's metadata.

    Attributes:
        items: Every item collected, in server order.
        meta: Pagination metadata from the final response.
        pages_fetched: Number of HTTP requests made.
        truncated: True when collection stopped early (``limit`` reached, page
            cap hit, or a broken-server guard tripped) rather than because the
            server reported no further pages.
    """

    model_config = ConfigDict(populate_by_name=True)

    items: list[dict[str, Any]] = Field(default_factory=list)
    meta: PaginationMeta = Field(default_factory=PaginationMeta)
    pages_fetched: int = 0
    truncated: bool = False

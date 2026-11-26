"""Shared SQLAlchemy pagination helper."""

from math import ceil
from typing import TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

T = TypeVar("T")


def paginate_select(
    db: Session,
    stmt: Select[tuple[T]],
    *,
    page: int,
    page_size: int,
) -> tuple[list[T], int, int]:
    """Execute a paginated SQLAlchemy 2.x select query and return (items, total, total_pages)."""
    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = int(db.scalar(count_stmt) or 0)
    total_pages = max(1, ceil(total / page_size)) if total > 0 else 1
    offset = (page - 1) * page_size
    items = list(db.scalars(stmt.offset(offset).limit(page_size)).all())
    return items, total, total_pages

"""Private helpers shared by service modules."""

from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Iterator

import duckdb

from src.services.errors import NotFoundError, ValidationError


MONEY_PLACES = Decimal("0.01")


def row_to_dict(cursor: duckdb.DuckDBPyConnection, row: tuple[Any, ...] | None) -> dict[str, Any] | None:
    """Convert one DuckDB result row into a plain dictionary."""
    if row is None:
        return None
    columns = [item[0] for item in cursor.description]
    return dict(zip(columns, row))


def fetch_one(cursor: duckdb.DuckDBPyConnection) -> dict[str, Any] | None:
    """Fetch one result row as a dictionary."""
    return row_to_dict(cursor, cursor.fetchone())


def fetch_all(cursor: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    """Fetch every result row as dictionaries."""
    columns = [item[0] for item in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def require_record(record: dict[str, Any] | None, label: str) -> dict[str, Any]:
    """Return a record or raise a consistent not-found error."""
    if record is None:
        raise NotFoundError(f"{label} not found")
    return record


def money(value: Decimal | int | str, field: str = "amount") -> Decimal:
    """Validate and quantize a monetary value without using float."""
    if isinstance(value, float):
        raise ValidationError(f"{field} must be supplied as Decimal, string, or integer")
    try:
        return Decimal(value).quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError(f"Invalid {field}") from exc


@contextmanager
def transaction(conn: duckdb.DuckDBPyConnection) -> Iterator[None]:
    """Commit a service write atomically and roll it back on any exception."""
    conn.execute("BEGIN TRANSACTION")
    try:
        yield
    except Exception:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")

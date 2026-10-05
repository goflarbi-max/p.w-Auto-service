"""Customer business operations."""

from __future__ import annotations

import re
from typing import Any

import duckdb

from src.services._common import fetch_all, fetch_one, require_record, transaction
from src.services.errors import ValidationError


def normalize_ghana_phone(phone: str) -> str:
    """Normalize common Ghana phone formats to +233XXXXXXXXX."""
    compact = re.sub(r"[\s()-]", "", phone or "")
    if re.fullmatch(r"0\d{9}", compact):
        compact = "+233" + compact[1:]
    elif re.fullmatch(r"233\d{9}", compact):
        compact = "+" + compact
    if not re.fullmatch(r"\+233\d{9}", compact):
        raise ValidationError("Phone must be a valid Ghana number")
    return compact


def get_customer(conn: duckdb.DuckDBPyConnection, customer_id: int) -> dict[str, Any]:
    """Retrieve one customer."""
    return require_record(
        fetch_one(conn.execute("SELECT * FROM customers WHERE id = ?", [customer_id])),
        "Customer",
    )


def create_customer(
    conn: duckdb.DuckDBPyConnection,
    name: str,
    phone: str,
    email: str | None = None,
    address: str | None = None,
    user_id: int | None = None,
) -> dict[str, Any]:
    """Create a customer or return the record with the same normalized phone."""
    del user_id
    if not name.strip():
        raise ValidationError("Customer name is required")
    canonical = normalize_ghana_phone(phone)
    existing = fetch_one(conn.execute("SELECT * FROM customers WHERE phone = ?", [canonical]))
    if existing:
        return existing
    with transaction(conn):
        customer_id = conn.execute(
            """
            INSERT INTO customers (name, phone, email, address)
            VALUES (?, ?, ?, ?) RETURNING id
            """,
            [name.strip(), canonical, email, address],
        ).fetchone()[0]
    return get_customer(conn, customer_id)


def update_customer(
    conn: duckdb.DuckDBPyConnection,
    customer_id: int,
    *,
    name: str | None = None,
    phone: str | None = None,
    email: str | None = None,
    address: str | None = None,
    user_id: int | None = None,
) -> dict[str, Any]:
    """Update supplied customer fields."""
    del user_id
    current = get_customer(conn, customer_id)
    canonical = normalize_ghana_phone(phone) if phone is not None else current["phone"]
    duplicate = conn.execute(
        "SELECT id FROM customers WHERE phone = ? AND id <> ?", [canonical, customer_id]
    ).fetchone()
    if duplicate:
        raise ValidationError("Another customer already uses this phone number")
    with transaction(conn):
        conn.execute(
            """
            UPDATE customers SET name = ?, phone = ?, email = ?, address = ?,
                updated_at = CURRENT_TIMESTAMP WHERE id = ?
            """,
            [name.strip() if name is not None else current["name"], canonical,
             email if email is not None else current["email"],
             address if address is not None else current["address"], customer_id],
        )
    return get_customer(conn, customer_id)


def search_customers(conn: duckdb.DuckDBPyConnection, query: str) -> list[dict[str, Any]]:
    """Search customers by name, phone, or email."""
    pattern = f"%{query.strip()}%"
    return fetch_all(conn.execute(
        """
        SELECT * FROM customers
        WHERE name ILIKE ? OR phone ILIKE ? OR coalesce(email, '') ILIKE ?
        ORDER BY name
        """,
        [pattern, pattern, pattern],
    ))

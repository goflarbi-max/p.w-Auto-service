"""User lookup and simple role-based permissions."""

from __future__ import annotations

from typing import Any, Mapping

import duckdb

from src.config import DEFAULT_USER_EMAIL, ROLE_PERMISSIONS
from src.services._common import fetch_all, fetch_one, require_record


def get_user(conn: duckdb.DuckDBPyConnection, user_id: int | None = None) -> dict[str, Any]:
    """Return a user, defaulting to the seeded owner."""
    if user_id is None:
        cursor = conn.execute(
            """
            SELECT u.*, r.name AS role_name FROM users u JOIN roles r ON r.id = u.role_id
            WHERE lower(u.email) = lower(?)
            """, [DEFAULT_USER_EMAIL]
        )
    else:
        cursor = conn.execute(
            """
            SELECT u.*, r.name AS role_name FROM users u JOIN roles r ON r.id = u.role_id
            WHERE u.id = ?
            """, [user_id]
        )
    return require_record(fetch_one(cursor), "User")


def list_users(conn: duckdb.DuckDBPyConnection, *, active_only: bool = True) -> list[dict[str, Any]]:
    """List users with role names."""
    return fetch_all(conn.execute(
        """
        SELECT u.*, r.name AS role_name FROM users u JOIN roles r ON r.id = u.role_id
        WHERE (? = FALSE OR u.is_active = TRUE) ORDER BY u.name
        """, [active_only]
    ))


def has_permission(user: Mapping[str, Any], action: str) -> bool:
    """Evaluate the configured permission matrix."""
    if not user.get("is_active", True):
        return False
    permissions = ROLE_PERMISSIONS.get(str(user.get("role_name")), set())
    return "*" in permissions or action in permissions

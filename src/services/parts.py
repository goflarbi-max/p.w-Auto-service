"""Parts catalogue, usage, stock, and ordering operations."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import duckdb

from src.services._common import fetch_all, fetch_one, money, require_record, transaction
from src.services.errors import InsufficientStockError, ValidationError
from src.services.job_cards import _get_job, _recalculate_totals


def _get_part(conn: duckdb.DuckDBPyConnection, part_id: int) -> dict[str, Any]:
    return require_record(fetch_one(conn.execute("SELECT * FROM parts WHERE id = ?", [part_id])), "Part")


def add_part(
    conn: duckdb.DuckDBPyConnection, part_name: str, selling_price: Decimal, *,
    part_number: str | None = None, brand: str | None = None,
    part_type: str = "Aftermarket", quantity: Decimal = Decimal("0"),
    cost_price: Decimal = Decimal("0"), supplier: str | None = None,
    reorder_level: Decimal = Decimal("0"), needs_ordering: bool = False,
    user_id: int | None = None,
) -> dict[str, Any]:
    del user_id
    if not part_name.strip():
        raise ValidationError("Part name is required")
    values = [money(value, field) for value, field in (
        (selling_price, "selling_price"), (quantity, "quantity"),
        (cost_price, "cost_price"), (reorder_level, "reorder_level"))]
    if any(value < 0 for value in values):
        raise ValidationError("Part prices and quantities cannot be negative")
    with transaction(conn):
        part_id = conn.execute(
            """
            INSERT INTO parts (part_name, part_number, brand, type, quantity, cost_price,
                               selling_price, supplier, reorder_level, needs_ordering)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id
            """, [part_name.strip(), part_number, brand, part_type, values[1], values[2],
                    values[0], supplier, values[3], needs_ordering]
        ).fetchone()[0]
    return _get_part(conn, part_id)


def update_part(
    conn: duckdb.DuckDBPyConnection, part_id: int, *, part_name: str | None = None,
    part_number: str | None = None, brand: str | None = None,
    part_type: str | None = None, cost_price: Decimal | None = None,
    selling_price: Decimal | None = None, supplier: str | None = None,
    reorder_level: Decimal | None = None, user_id: int | None = None,
) -> dict[str, Any]:
    del user_id
    current = _get_part(conn, part_id)
    cost = money(cost_price, "cost_price") if cost_price is not None else current["cost_price"]
    selling = money(selling_price, "selling_price") if selling_price is not None else current["selling_price"]
    reorder = money(reorder_level, "reorder_level") if reorder_level is not None else current["reorder_level"]
    if min(cost, selling, reorder) < 0:
        raise ValidationError("Part prices and reorder level cannot be negative")
    with transaction(conn):
        conn.execute(
            """
            UPDATE parts SET part_name = ?, part_number = ?, brand = ?, type = ?,
                cost_price = ?, selling_price = ?, supplier = ?, reorder_level = ?,
                updated_at = CURRENT_TIMESTAMP WHERE id = ?
            """, [part_name or current["part_name"], part_number if part_number is not None else current["part_number"],
                    brand if brand is not None else current["brand"], part_type or current["type"], cost,
                    selling, supplier if supplier is not None else current["supplier"], reorder, part_id]
        )
    return _get_part(conn, part_id)


def search_parts(conn: duckdb.DuckDBPyConnection, query: str) -> list[dict[str, Any]]:
    pattern = f"%{query.strip()}%"
    return fetch_all(conn.execute(
        "SELECT * FROM parts WHERE part_name ILIKE ? OR coalesce(part_number, '') ILIKE ? OR coalesce(brand, '') ILIKE ? ORDER BY part_name",
        [pattern, pattern, pattern],
    ))


def record_part_used(
    conn: duckdb.DuckDBPyConnection, job_card_id: int, part_id: int,
    quantity: Decimal, unit_price: Decimal | None = None,
    user_id: int | None = None,
) -> dict[str, Any]:
    del user_id
    job = _get_job(conn, job_card_id)
    if job["status"] == "Delivered":
        raise ValidationError("Parts cannot be added to a Delivered job")
    part = _get_part(conn, part_id)
    used = money(quantity, "quantity")
    price = money(unit_price, "unit_price") if unit_price is not None else part["selling_price"]
    if used <= 0:
        raise ValidationError("Quantity must be positive")
    if part["quantity"] < used:
        raise InsufficientStockError(f"Only {part['quantity']} of {part['part_name']} is available")
    with transaction(conn):
        usage_id = conn.execute(
            "INSERT INTO parts_used (job_card_id, part_id, quantity, unit_price) VALUES (?, ?, ?, ?) RETURNING id",
            [job_card_id, part_id, used, price],
        ).fetchone()[0]
        conn.execute(
            "UPDATE parts SET quantity = quantity - ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            [used, part_id],
        )
        _recalculate_totals(conn, job_card_id)
    return require_record(fetch_one(conn.execute(
        "SELECT * FROM parts_used WHERE id = ?", [usage_id]
    )), "Part usage")


def remove_part_used(
    conn: duckdb.DuckDBPyConnection, parts_used_id: int,
    user_id: int | None = None,
) -> dict[str, Any]:
    del user_id
    usage = require_record(fetch_one(conn.execute(
        "SELECT * FROM parts_used WHERE id = ?", [parts_used_id]
    )), "Part usage")
    if _get_job(conn, usage["job_card_id"])["status"] == "Delivered":
        raise ValidationError("Parts cannot be removed from a Delivered job")
    with transaction(conn):
        conn.execute("DELETE FROM parts_used WHERE id = ?", [parts_used_id])
        conn.execute(
            "UPDATE parts SET quantity = quantity + ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            [usage["quantity"], usage["part_id"]],
        )
        totals = _recalculate_totals(conn, usage["job_card_id"])
    return {"removed": usage, "job_totals": totals}


def _adjust_stock(
    conn: duckdb.DuckDBPyConnection, part_id: int, delta: Decimal, reason: str,
    adjustment_type: str, user_id: int | None, parts_order_id: int | None = None,
) -> None:
    part = _get_part(conn, part_id)
    change = money(delta, "delta")
    if change == 0 or not reason.strip():
        raise ValidationError("A non-zero delta and reason are required")
    if part["quantity"] + change < 0:
        raise InsufficientStockError("Stock adjustment would make quantity negative")
    conn.execute(
        "UPDATE parts SET quantity = quantity + ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        [change, part_id],
    )
    conn.execute(
        """
        INSERT INTO stock_adjustments
            (part_id, delta, reason, adjustment_type, parts_order_id, recorded_by)
        VALUES (?, ?, ?, ?, ?, ?)
        """, [part_id, change, reason.strip(), adjustment_type, parts_order_id, user_id]
    )


def adjust_stock(
    conn: duckdb.DuckDBPyConnection, part_id: int, delta: Decimal, reason: str,
    user_id: int | None = None,
) -> dict[str, Any]:
    with transaction(conn):
        _adjust_stock(conn, part_id, delta, reason, "Manual", user_id)
    return _get_part(conn, part_id)


def flag_needs_ordering(
    conn: duckdb.DuckDBPyConnection, part_id: int, flag: bool,
    user_id: int | None = None,
) -> dict[str, Any]:
    del user_id
    _get_part(conn, part_id)
    with transaction(conn):
        conn.execute(
            "UPDATE parts SET needs_ordering = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            [flag, part_id],
        )
    return _get_part(conn, part_id)


def get_reorder_list(conn: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    return fetch_all(conn.execute("SELECT * FROM v_parts_to_reorder ORDER BY part_name"))


def create_order(
    conn: duckdb.DuckDBPyConnection, part_id: int, quantity: Decimal, *,
    unit_cost: Decimal | None = None, supplier: str | None = None,
    expected_date: date | None = None, notes: str | None = None,
    user_id: int | None = None,
) -> dict[str, Any]:
    del user_id
    _get_part(conn, part_id)
    ordered = money(quantity, "quantity")
    cost = money(unit_cost, "unit_cost") if unit_cost is not None else None
    if ordered <= 0:
        raise ValidationError("Order quantity must be positive")
    with transaction(conn):
        order_id = conn.execute(
            """
            INSERT INTO parts_orders (part_id, quantity_ordered, unit_cost, supplier, expected_date, notes)
            VALUES (?, ?, ?, ?, ?, ?) RETURNING id
            """, [part_id, ordered, cost, supplier, expected_date, notes]
        ).fetchone()[0]
    return require_record(fetch_one(conn.execute(
        "SELECT * FROM parts_orders WHERE id = ?", [order_id]
    )), "Parts order")


def receive_order(
    conn: duckdb.DuckDBPyConnection, order_id: int,
    quantity_received: Decimal | None = None, user_id: int | None = None,
) -> dict[str, Any]:
    order = require_record(fetch_one(conn.execute(
        "SELECT * FROM parts_orders WHERE id = ?", [order_id]
    )), "Parts order")
    if order["status"] in {"Received", "Cancelled"}:
        raise ValidationError("This order cannot receive more stock")
    remaining = order["quantity_ordered"] - order["quantity_received"]
    received = money(quantity_received, "quantity_received") if quantity_received is not None else remaining
    if received <= 0 or received > remaining:
        raise ValidationError("Received quantity must be positive and no greater than outstanding quantity")
    new_received = order["quantity_received"] + received
    completed = new_received == order["quantity_ordered"]
    with transaction(conn):
        conn.execute(
            """
            UPDATE parts_orders SET quantity_received = ?, status = ?, received_date = ? WHERE id = ?
            """, [new_received, "Received" if completed else "Partially Received",
                    date.today() if completed else None, order_id]
        )
        _adjust_stock(conn, order["part_id"], received, f"Receipt for parts order {order_id}",
                      "Order Receipt", user_id, order_id)
    return require_record(fetch_one(conn.execute(
        "SELECT * FROM parts_orders WHERE id = ?", [order_id]
    )), "Parts order")


def list_orders(
    conn: duckdb.DuckDBPyConnection, status: str | None = None,
) -> list[dict[str, Any]]:
    """List parts orders with their part details."""
    return fetch_all(conn.execute(
        """
        SELECT po.*, p.part_name, p.part_number FROM parts_orders po
        JOIN parts p ON p.id = po.part_id
        WHERE (? IS NULL OR po.status = ?) ORDER BY po.ordered_date DESC, po.id DESC
        """, [status, status]
    ))

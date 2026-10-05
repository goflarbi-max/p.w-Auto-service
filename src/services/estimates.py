"""Estimate versioning and approval workflow."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Sequence, TypedDict

import duckdb

from src.services._common import fetch_all, fetch_one, money, require_record, transaction
from src.services.errors import ValidationError
from src.services.job_cards import _change_status, _recalculate_totals
from src.config import BUSINESS_DETAILS, CURRENCY


class EstimateItemInput(TypedDict, total=False):
    item_type: str
    description: str
    part_id: int | None
    quantity: Decimal
    unit_price: Decimal


def _get_estimate(conn: duckdb.DuckDBPyConnection, estimate_id: int) -> dict[str, Any]:
    return require_record(fetch_one(conn.execute(
        "SELECT * FROM estimates WHERE id = ?", [estimate_id]
    )), "Estimate")


def _insert_items(conn: duckdb.DuckDBPyConnection, estimate_id: int, items: Sequence[EstimateItemInput]) -> None:
    if not items:
        raise ValidationError("An estimate requires at least one item")
    for item in items:
        item_type = str(item.get("item_type", ""))
        description = str(item.get("description", "")).strip()
        if item_type not in {"Labour", "Part"} or not description:
            raise ValidationError("Each estimate item requires a valid type and description")
        part_id = item.get("part_id")
        if item_type == "Labour" and part_id is not None:
            raise ValidationError("Labour items cannot reference a part")
        if part_id is not None and conn.execute("SELECT id FROM parts WHERE id = ?", [part_id]).fetchone() is None:
            raise ValidationError("Estimate part not found")
        quantity = money(item.get("quantity", Decimal("1")), "quantity")
        unit_price = money(item.get("unit_price", Decimal("0")), "unit_price")
        if quantity <= 0 or unit_price < 0:
            raise ValidationError("Estimate quantity must be positive and price non-negative")
        conn.execute(
            """
            INSERT INTO estimate_items (estimate_id, item_type, description, part_id, quantity, unit_price)
            VALUES (?, ?, ?, ?, ?, ?)
            """, [estimate_id, item_type, description, part_id, quantity, unit_price]
        )


def _estimate_full(conn: duckdb.DuckDBPyConnection, estimate_id: int) -> dict[str, Any]:
    estimate = _get_estimate(conn, estimate_id)
    estimate["items"] = fetch_all(conn.execute(
        "SELECT * FROM estimate_items WHERE estimate_id = ? ORDER BY id", [estimate_id]
    ))
    estimate["totals"] = estimate_totals(conn, estimate_id)
    return estimate


def get_estimate_full(conn: duckdb.DuckDBPyConnection, estimate_id: int) -> dict[str, Any]:
    """Return an estimate with lines and calculated totals."""
    return _estimate_full(conn, estimate_id)


def get_estimate_document_full(
    conn: duckdb.DuckDBPyConnection, estimate_id: int,
) -> dict[str, Any]:
    """Return the complete customer, vehicle, job, and estimate document aggregate."""
    estimate = require_record(fetch_one(conn.execute(
        """
        SELECT e.*, jc.job_no, jc.mileage, jc.tax_rate,
               c.name AS customer_name, c.phone, c.email, c.address,
               v.brand, v.model, v.year, v.vin, v.reg_number
        FROM estimates e JOIN job_cards jc ON jc.id = e.job_card_id
        JOIN customers c ON c.id = jc.customer_id
        JOIN vehicles v ON v.id = jc.vehicle_id
        WHERE e.id = ?
        """, [estimate_id]
    )), "Estimate")
    estimate["items"] = fetch_all(conn.execute(
        """
        SELECT ei.*, p.part_name, p.part_number,
               ei.quantity * ei.unit_price AS line_total
        FROM estimate_items ei LEFT JOIN parts p ON p.id = ei.part_id
        WHERE ei.estimate_id = ? ORDER BY ei.id
        """, [estimate_id]
    ))
    estimate["job_types"] = fetch_all(conn.execute(
        """
        SELECT jt.id, jt.name FROM job_card_job_types j
        JOIN job_types jt ON jt.id = j.job_type_id
        WHERE j.job_card_id = ? ORDER BY jt.name
        """, [estimate["job_card_id"]]
    ))
    estimate["totals"] = estimate_totals(conn, estimate_id)
    estimate["business"] = BUSINESS_DETAILS.copy()
    estimate["currency"] = CURRENCY
    return estimate


def create_estimate(
    conn: duckdb.DuckDBPyConnection, job_card_id: int,
    items: Sequence[EstimateItemInput], user_id: int | None = None,
) -> dict[str, Any]:
    """Create version one of a job estimate."""
    del user_id
    if conn.execute("SELECT id FROM job_cards WHERE id = ?", [job_card_id]).fetchone() is None:
        raise ValidationError("Job card not found")
    if conn.execute("SELECT id FROM estimates WHERE job_card_id = ?", [job_card_id]).fetchone():
        raise ValidationError("Use revise_estimate for a job that already has an estimate")
    with transaction(conn):
        estimate_id = conn.execute(
            "INSERT INTO estimates (job_card_id, version, status) VALUES (?, 1, 'Draft') RETURNING id",
            [job_card_id],
        ).fetchone()[0]
        _insert_items(conn, estimate_id, items)
    return _estimate_full(conn, estimate_id)


def revise_estimate(
    conn: duckdb.DuckDBPyConnection, job_card_id: int,
    items: Sequence[EstimateItemInput], user_id: int | None = None,
) -> dict[str, Any]:
    """Supersede the latest estimate and create its next version."""
    del user_id
    previous = fetch_one(conn.execute(
        "SELECT * FROM estimates WHERE job_card_id = ? ORDER BY version DESC LIMIT 1", [job_card_id]
    ))
    previous = require_record(previous, "Estimate")
    if previous["status"] == "Approved":
        raise ValidationError("An approved estimate cannot be revised")
    with transaction(conn):
        conn.execute(
            "UPDATE estimates SET status = 'Superseded', approved_at = NULL WHERE id = ?",
            [previous["id"]],
        )
        estimate_id = conn.execute(
            "INSERT INTO estimates (job_card_id, version, status) VALUES (?, ?, 'Draft') RETURNING id",
            [job_card_id, previous["version"] + 1],
        ).fetchone()[0]
        _insert_items(conn, estimate_id, items)
    return _estimate_full(conn, estimate_id)


def send_estimate(
    conn: duckdb.DuckDBPyConnection, estimate_id: int,
    user_id: int | None = None,
) -> dict[str, Any]:
    """Send a draft estimate and move its job to Estimate Sent."""
    estimate = _get_estimate(conn, estimate_id)
    if estimate["status"] != "Draft":
        raise ValidationError("Only a Draft estimate can be sent")
    with transaction(conn):
        conn.execute("UPDATE estimates SET status = 'Sent' WHERE id = ?", [estimate_id])
        _change_status(conn, estimate["job_card_id"], "Estimate Sent", user_id)
    return _estimate_full(conn, estimate_id)


def approve_estimate(
    conn: duckdb.DuckDBPyConnection, estimate_id: int,
    user_id: int | None = None,
) -> dict[str, Any]:
    """Approve a sent estimate and move the job into progress."""
    estimate = _get_estimate(conn, estimate_id)
    if estimate["status"] != "Sent":
        raise ValidationError("Only a Sent estimate can be approved")
    with transaction(conn):
        conn.execute(
            "UPDATE estimates SET status = 'Approved', approved_at = CURRENT_TIMESTAMP WHERE id = ?",
            [estimate_id],
        )
        _change_status(conn, estimate["job_card_id"], "Approved", user_id)
        _change_status(conn, estimate["job_card_id"], "In Progress", user_id)
        _recalculate_totals(conn, estimate["job_card_id"])
    return _estimate_full(conn, estimate_id)


def decline_estimate(
    conn: duckdb.DuckDBPyConnection, estimate_id: int,
    user_id: int | None = None,
) -> dict[str, Any]:
    """Decline a sent estimate and close its job as Declined."""
    estimate = _get_estimate(conn, estimate_id)
    if estimate["status"] != "Sent":
        raise ValidationError("Only a Sent estimate can be declined")
    with transaction(conn):
        conn.execute("UPDATE estimates SET status = 'Declined' WHERE id = ?", [estimate_id])
        _change_status(conn, estimate["job_card_id"], "Declined", user_id)
    return _estimate_full(conn, estimate_id)


def estimate_totals(conn: duckdb.DuckDBPyConnection, estimate_id: int) -> dict[str, Decimal]:
    """Calculate estimate totals using Decimal values."""
    estimate = _get_estimate(conn, estimate_id)
    rows = conn.execute(
        """
        SELECT item_type, coalesce(sum(quantity * unit_price), 0)
        FROM estimate_items WHERE estimate_id = ? GROUP BY item_type
        """, [estimate_id]
    ).fetchall()
    values = {row[0]: money(row[1]) for row in rows}
    labour, parts = values.get("Labour", Decimal("0.00")), values.get("Part", Decimal("0.00"))
    tax_rate = conn.execute(
        "SELECT tax_rate FROM job_cards WHERE id = ?", [estimate["job_card_id"]]
    ).fetchone()[0]
    tax = money((labour + parts) * Decimal(tax_rate) / Decimal("100"))
    return {"labour": labour, "parts": parts, "tax": tax, "total": money(labour + parts + tax)}

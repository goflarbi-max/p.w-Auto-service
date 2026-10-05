"""Invoice creation, synchronization, payment, and rendering data."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import duckdb

from src.config import BUSINESS_DETAILS, CURRENCY, PAYMENT_METHODS
from src.database.connection import next_document_number
from src.services._common import fetch_all, fetch_one, money, require_record, transaction
from src.services.errors import ValidationError
from src.services.job_cards import _get_job, _recalculate_totals


ALLOWED_INVOICE_STATUSES = {"In Progress", "Quality Check", "Ready for Delivery", "Delivered"}


def _get_invoice(conn: duckdb.DuckDBPyConnection, invoice_id: int) -> dict[str, Any]:
    return require_record(fetch_one(conn.execute(
        "SELECT * FROM invoices WHERE id = ?", [invoice_id]
    )), "Invoice")


def create_invoice(
    conn: duckdb.DuckDBPyConnection, job_card_id: int,
    user_id: int | None = None,
) -> dict[str, Any]:
    """Return the job's invoice or create one from current job totals."""
    del user_id
    existing = fetch_one(conn.execute("SELECT * FROM invoices WHERE job_card_id = ?", [job_card_id]))
    if existing:
        return existing
    job = _get_job(conn, job_card_id)
    if job["status"] not in ALLOWED_INVOICE_STATUSES:
        raise ValidationError("The job is not in an invoiceable status")
    issue_date = date.today()
    with transaction(conn):
        totals = _recalculate_totals(conn, job_card_id)
        invoice_no = next_document_number(conn, "Invoice", issue_date.year)
        invoice_id = conn.execute(
            """
            INSERT INTO invoices (
                invoice_no, job_card_id, issue_date, labour_total, parts_total,
                tax_amount, total, payment_status, amount_paid
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'Unpaid', 0) RETURNING id
            """, [invoice_no, job_card_id, issue_date, totals["labour_cost"],
                    totals["parts_total"], totals["tax_amount"], totals["total_cost"]]
        ).fetchone()[0]
    return _get_invoice(conn, invoice_id)


def _normalize_method(method: str) -> str:
    matches = {value.casefold(): value for value in PAYMENT_METHODS}
    normalized = matches.get(method.strip().casefold())
    if normalized is None:
        raise ValidationError(f"Payment method must be one of: {', '.join(PAYMENT_METHODS)}")
    return normalized


def record_payment(
    conn: duckdb.DuckDBPyConnection, invoice_id: int, amount: Decimal,
    method: str, user_id: int | None = None,
) -> dict[str, Any]:
    """Record a controlled-method payment and update invoice aggregates."""
    invoice = _get_invoice(conn, invoice_id)
    payment = money(amount)
    payment_method = _normalize_method(method)
    if payment <= 0:
        raise ValidationError("Payment must be positive")
    new_paid = invoice["amount_paid"] + payment
    if new_paid > invoice["total"]:
        raise ValidationError("Payment exceeds the outstanding invoice balance")
    status = "Paid" if new_paid == invoice["total"] else "Partial"
    with transaction(conn):
        payment_id = conn.execute(
            """
            INSERT INTO invoice_payments (invoice_id, amount, method, recorded_by)
            VALUES (?, ?, ?, ?) RETURNING id
            """, [invoice_id, payment, payment_method, user_id]
        ).fetchone()[0]
        conn.execute(
            """
            UPDATE invoices SET amount_paid = ?, payment_status = ?,
                updated_at = CURRENT_TIMESTAMP WHERE id = ?
            """, [new_paid, status, invoice_id]
        )
    result = _get_invoice(conn, invoice_id)
    result["payment_id"] = payment_id
    return result


def refresh_invoice_totals(
    conn: duckdb.DuckDBPyConnection, invoice_id: int,
    user_id: int | None = None,
) -> dict[str, Any]:
    """Synchronize a non-paid invoice with current job totals."""
    del user_id
    invoice = _get_invoice(conn, invoice_id)
    if invoice["payment_status"] == "Paid":
        raise ValidationError("Paid invoice totals are frozen")
    with transaction(conn):
        totals = _recalculate_totals(conn, invoice["job_card_id"])
        if totals["total_cost"] < invoice["amount_paid"]:
            raise ValidationError("New invoice total cannot be below the amount already paid")
        status = "Partial" if invoice["amount_paid"] > 0 else "Unpaid"
        conn.execute(
            """
            UPDATE invoices SET labour_total = ?, parts_total = ?, tax_amount = ?, total = ?,
                payment_status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?
            """, [totals["labour_cost"], totals["parts_total"], totals["tax_amount"],
                    totals["total_cost"], status, invoice_id]
        )
    return _get_invoice(conn, invoice_id)


def get_invoice_full(conn: duckdb.DuckDBPyConnection, invoice_id: int) -> dict[str, Any]:
    """Return all information needed for later invoice rendering."""
    invoice = require_record(fetch_one(conn.execute(
        """
        SELECT i.*, jc.job_no, jc.status AS job_status, c.id AS customer_id,
               c.name AS customer_name, c.phone, c.email, c.address,
               v.id AS vehicle_id, v.brand, v.model, v.year, v.vin, v.reg_number,
               jc.mileage
        FROM invoices i JOIN job_cards jc ON jc.id = i.job_card_id
        JOIN customers c ON c.id = jc.customer_id JOIN vehicles v ON v.id = jc.vehicle_id
        WHERE i.id = ?
        """, [invoice_id]
    )), "Invoice")
    invoice["business"] = BUSINESS_DETAILS.copy()
    invoice["currency"] = CURRENCY
    invoice["job_types"] = fetch_all(conn.execute(
        """
        SELECT jt.id, jt.name FROM job_card_job_types j
        JOIN job_types jt ON jt.id = j.job_type_id
        WHERE j.job_card_id = ? ORDER BY jt.name
        """, [invoice["job_card_id"]]
    ))
    invoice["parts"] = fetch_all(conn.execute(
        """
        SELECT pu.*, p.part_name, p.part_number FROM parts_used pu
        JOIN parts p ON p.id = pu.part_id WHERE pu.job_card_id = ? ORDER BY pu.id
        """, [invoice["job_card_id"]]
    ))
    invoice["payments"] = fetch_all(conn.execute(
        "SELECT * FROM invoice_payments WHERE invoice_id = ? ORDER BY paid_at, id", [invoice_id]
    ))
    invoice["labour_lines"] = fetch_all(conn.execute(
        """
        SELECT ei.description, ei.quantity, ei.unit_price,
               ei.quantity * ei.unit_price AS line_total
        FROM estimates e JOIN estimate_items ei ON ei.estimate_id = e.id
        WHERE e.job_card_id = ? AND e.status = 'Approved' AND ei.item_type = 'Labour'
        ORDER BY ei.id
        """, [invoice["job_card_id"]]
    ))
    if not invoice["labour_lines"] and invoice["labour_total"] > 0:
        invoice["labour_lines"] = [{
            "description": "Labour", "quantity": Decimal("1.00"),
            "unit_price": invoice["labour_total"], "line_total": invoice["labour_total"],
        }]
    return invoice

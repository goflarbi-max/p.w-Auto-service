"""Appointment scheduling and conversion operations."""

from __future__ import annotations

from datetime import date
from typing import Any, Sequence

import duckdb

from src.services._common import fetch_all, fetch_one, require_record, transaction
from src.services.errors import ValidationError
from src.services.job_cards import _open_job_card, get_job_card_full


def _get_appointment(conn: duckdb.DuckDBPyConnection, appointment_id: int) -> dict[str, Any]:
    return require_record(fetch_one(conn.execute(
        "SELECT * FROM appointments WHERE id = ?", [appointment_id]
    )), "Appointment")


def _validate_owner(conn: duckdb.DuckDBPyConnection, customer_id: int, vehicle_id: int) -> None:
    owner = conn.execute("SELECT customer_id FROM vehicles WHERE id = ?", [vehicle_id]).fetchone()
    if owner is None or owner[0] != customer_id:
        raise ValidationError("Vehicle does not belong to the customer")


def create_appointment(
    conn: duckdb.DuckDBPyConnection, source: str, appointment_date: date,
    customer_id: int, vehicle_id: int, *, notes: str | None = None,
    status: str = "Booked", user_id: int | None = None,
) -> dict[str, Any]:
    """Create a validated appointment."""
    del user_id
    _validate_owner(conn, customer_id, vehicle_id)
    with transaction(conn):
        appointment_id = conn.execute(
            """
            INSERT INTO appointments (source, appointment_date, customer_id, vehicle_id, notes, status)
            VALUES (?, ?, ?, ?, ?, ?) RETURNING id
            """, [source, appointment_date, customer_id, vehicle_id, notes, status]
        ).fetchone()[0]
    return _get_appointment(conn, appointment_id)


def update_appointment(
    conn: duckdb.DuckDBPyConnection, appointment_id: int, *, source: str | None = None,
    appointment_date: date | None = None, customer_id: int | None = None,
    vehicle_id: int | None = None, notes: str | None = None, status: str | None = None,
    user_id: int | None = None,
) -> dict[str, Any]:
    """Update supplied appointment fields."""
    del user_id
    current = _get_appointment(conn, appointment_id)
    customer = customer_id if customer_id is not None else current["customer_id"]
    vehicle = vehicle_id if vehicle_id is not None else current["vehicle_id"]
    _validate_owner(conn, customer, vehicle)
    with transaction(conn):
        conn.execute(
            """
            UPDATE appointments SET source = ?, appointment_date = ?, customer_id = ?,
                vehicle_id = ?, notes = ?, status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?
            """, [source or current["source"], appointment_date or current["appointment_date"],
                    customer, vehicle, notes if notes is not None else current["notes"],
                    status or current["status"], appointment_id]
        )
    return _get_appointment(conn, appointment_id)


def cancel_appointment(
    conn: duckdb.DuckDBPyConnection, appointment_id: int,
    user_id: int | None = None,
) -> dict[str, Any]:
    """Cancel an appointment."""
    return update_appointment(conn, appointment_id, status="Cancelled", user_id=user_id)


def list_appointments(
    conn: duckdb.DuckDBPyConnection, *, date_from: date | None = None,
    date_to: date | None = None, source: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    """List appointments using optional filters."""
    return fetch_all(conn.execute(
        """
        SELECT a.*, c.name AS customer_name, v.reg_number, v.brand, v.model
        FROM appointments a JOIN customers c ON c.id = a.customer_id
        JOIN vehicles v ON v.id = a.vehicle_id
        WHERE (? IS NULL OR a.appointment_date >= ?) AND (? IS NULL OR a.appointment_date <= ?)
          AND (? IS NULL OR a.source = ?) AND (? IS NULL OR a.status = ?)
        ORDER BY a.appointment_date, a.id
        """, [date_from, date_from, date_to, date_to, source, source, status, status]
    ))


def convert_to_job_card(
    conn: duckdb.DuckDBPyConnection, appointment_id: int, *,
    customer_complaint: str | None = None, mileage: int | None = None,
    technician_id: int | None = None, job_type_ids: Sequence[int] = (),
    expected_delivery: date | None = None, user_id: int | None = None,
) -> dict[str, Any]:
    """Create one job card from an appointment and complete it atomically."""
    del user_id
    appointment = _get_appointment(conn, appointment_id)
    existing = conn.execute(
        "SELECT id FROM job_cards WHERE appointment_id = ?", [appointment_id]
    ).fetchone()
    if existing:
        return get_job_card_full(conn, existing[0])
    if appointment["status"] in {"Cancelled", "No Show"}:
        raise ValidationError("Cancelled or missed appointments cannot be converted")
    complaint = customer_complaint or appointment["notes"] or "Workshop visit"
    with transaction(conn):
        job_card_id = _open_job_card(
            conn, customer_id=appointment["customer_id"], vehicle_id=appointment["vehicle_id"],
            customer=None, vehicle=None, appointment_id=appointment_id,
            technician_id=technician_id, mileage=mileage, customer_complaint=complaint,
            current_condition=None, inspection_notes=None, expected_delivery=expected_delivery,
            job_type_ids=job_type_ids, date_received=date.today(),
        )
        conn.execute(
            "UPDATE appointments SET status = 'Completed', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            [appointment_id],
        )
    return get_job_card_full(conn, job_card_id)

"""Job-card workflow and aggregate queries."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Mapping, Sequence

import duckdb

from src.database.connection import next_document_number
from src.services._common import fetch_all, fetch_one, money, require_record, transaction
from src.services.customers import normalize_ghana_phone
from src.services.errors import InvalidStatusTransition, ValidationError
from src.services.users import get_user


STATUS_FLOW: dict[str, set[str]] = {
    "Received": {"Diagnosed", "Cancelled"},
    "Diagnosed": {"Estimate Sent", "Cancelled"},
    "Estimate Sent": {"Approved", "Declined", "Cancelled"},
    "Approved": {"In Progress", "Cancelled"},
    "In Progress": {"Quality Check", "Cancelled"},
    "Quality Check": {"Ready for Delivery", "Cancelled"},
    "Ready for Delivery": {"Delivered", "Cancelled"},
    "Delivered": set(),
    "Declined": {"Received"},
    "Cancelled": {"Received"},
}


def _get_job(conn: duckdb.DuckDBPyConnection, job_card_id: int) -> dict[str, Any]:
    return require_record(
        fetch_one(conn.execute("SELECT * FROM job_cards WHERE id = ?", [job_card_id])),
        "Job card",
    )


def _validate_job_types(conn: duckdb.DuckDBPyConnection, job_type_ids: Sequence[int]) -> list[int]:
    values = list(dict.fromkeys(job_type_ids))
    for job_type_id in values:
        found = conn.execute(
            "SELECT id FROM job_types WHERE id = ? AND is_active", [job_type_id]
        ).fetchone()
        if found is None:
            raise ValidationError(f"Active job type {job_type_id} not found")
    return values


def _set_job_types(conn: duckdb.DuckDBPyConnection, job_card_id: int, job_type_ids: Sequence[int]) -> None:
    values = _validate_job_types(conn, job_type_ids)
    conn.execute("DELETE FROM job_card_job_types WHERE job_card_id = ?", [job_card_id])
    for job_type_id in values:
        conn.execute(
            "INSERT INTO job_card_job_types (job_card_id, job_type_id) VALUES (?, ?)",
            [job_card_id, job_type_id],
        )


def _resolve_walk_in(
    conn: duckdb.DuckDBPyConnection,
    customer_id: int | None,
    vehicle_id: int | None,
    customer: Mapping[str, Any] | None,
    vehicle: Mapping[str, Any] | None,
) -> tuple[int, int]:
    if customer_id is not None or vehicle_id is not None:
        if customer_id is None or vehicle_id is None or customer or vehicle:
            raise ValidationError("Supply both IDs or customer and vehicle payloads")
        owner = conn.execute("SELECT customer_id FROM vehicles WHERE id = ?", [vehicle_id]).fetchone()
        if owner is None or owner[0] != customer_id:
            raise ValidationError("Vehicle does not belong to the customer")
        return customer_id, vehicle_id
    if customer is None or vehicle is None:
        raise ValidationError("Walk-in customer and vehicle details are required")
    phone = normalize_ghana_phone(str(customer.get("phone", "")))
    existing = conn.execute("SELECT id FROM customers WHERE phone = ?", [phone]).fetchone()
    if existing:
        resolved_customer_id = existing[0]
    else:
        if not str(customer.get("name", "")).strip():
            raise ValidationError("Customer name is required")
        resolved_customer_id = conn.execute(
            """
            INSERT INTO customers (name, phone, email, address)
            VALUES (?, ?, ?, ?) RETURNING id
            """,
            [str(customer["name"]).strip(), phone, customer.get("email"), customer.get("address")],
        ).fetchone()[0]
    registration = str(vehicle.get("reg_number", "")).strip().upper()
    if not registration or not str(vehicle.get("brand", "")).strip() or not str(vehicle.get("model", "")).strip():
        raise ValidationError("Vehicle brand, model, and registration are required")
    if conn.execute("SELECT id FROM vehicles WHERE reg_number = ?", [registration]).fetchone():
        raise ValidationError("Registration number already exists")
    clean_vin = str(vehicle["vin"]).strip().upper() if vehicle.get("vin") else None
    if clean_vin and conn.execute("SELECT id FROM vehicles WHERE vin = ?", [clean_vin]).fetchone():
        raise ValidationError("VIN already exists")
    resolved_vehicle_id = conn.execute(
        """
        INSERT INTO vehicles (customer_id, brand, model, year, vin, reg_number)
        VALUES (?, ?, ?, ?, ?, ?) RETURNING id
        """,
        [resolved_customer_id, str(vehicle["brand"]).strip(), str(vehicle["model"]).strip(),
         vehicle.get("year"), clean_vin, registration],
    ).fetchone()[0]
    return resolved_customer_id, resolved_vehicle_id


def _open_job_card(
    conn: duckdb.DuckDBPyConnection, *, customer_id: int | None,
    vehicle_id: int | None, customer: Mapping[str, Any] | None,
    vehicle: Mapping[str, Any] | None, appointment_id: int | None,
    technician_id: int | None, mileage: int | None, customer_complaint: str,
    current_condition: str | None, inspection_notes: str | None,
    expected_delivery: date | None, job_type_ids: Sequence[int],
    date_received: date | None,
) -> int:
    if not customer_complaint.strip():
        raise ValidationError("Customer complaint is required")
    received = date_received or date.today()
    resolved_customer, resolved_vehicle = _resolve_walk_in(
        conn, customer_id, vehicle_id, customer, vehicle
    )
    if appointment_id is not None:
        appointment = conn.execute(
            "SELECT customer_id, vehicle_id FROM appointments WHERE id = ?", [appointment_id]
        ).fetchone()
        if appointment is None:
            raise ValidationError("Appointment not found")
        if appointment != (resolved_customer, resolved_vehicle):
            raise ValidationError("Appointment customer or vehicle does not match")
    number = next_document_number(conn, "Job Card", received.year)
    job_card_id = conn.execute(
        """
        INSERT INTO job_cards (
            job_no, appointment_id, customer_id, vehicle_id, technician_id, mileage,
            customer_complaint, current_condition, inspection_notes, date_received,
            expected_delivery, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Received') RETURNING id
        """,
        [number, appointment_id, resolved_customer, resolved_vehicle, technician_id, mileage,
         customer_complaint.strip(), current_condition, inspection_notes, received, expected_delivery],
    ).fetchone()[0]
    _set_job_types(conn, job_card_id, job_type_ids)
    conn.execute(
        "INSERT INTO job_status_history (job_card_id, status) VALUES (?, 'Received')",
        [job_card_id],
    )
    return job_card_id


def open_job_card(
    conn: duckdb.DuckDBPyConnection, *, customer_id: int | None = None,
    vehicle_id: int | None = None, customer: Mapping[str, Any] | None = None,
    vehicle: Mapping[str, Any] | None = None, appointment_id: int | None = None,
    technician_id: int | None = None, mileage: int | None = None,
    customer_complaint: str, current_condition: str | None = None,
    inspection_notes: str | None = None, expected_delivery: date | None = None,
    job_type_ids: Sequence[int] = (), date_received: date | None = None,
    user_id: int | None = None,
) -> dict[str, Any]:
    """Open a Received job, including the optional walk-in flow."""
    del user_id
    with transaction(conn):
        job_card_id = _open_job_card(
            conn, customer_id=customer_id, vehicle_id=vehicle_id, customer=customer,
            vehicle=vehicle, appointment_id=appointment_id, technician_id=technician_id,
            mileage=mileage, customer_complaint=customer_complaint,
            current_condition=current_condition, inspection_notes=inspection_notes,
            expected_delivery=expected_delivery, job_type_ids=job_type_ids,
            date_received=date_received,
        )
    return get_job_card_full(conn, job_card_id)


def update_job_card(
    conn: duckdb.DuckDBPyConnection, job_card_id: int, *,
    customer_complaint: str | None = None, current_condition: str | None = None,
    inspection_notes: str | None = None, diagnosis: str | None = None,
    mileage: int | None = None, expected_delivery: date | None = None,
    job_type_ids: Sequence[int] | None = None, technician_id: int | None = None,
    user_id: int | None = None,
) -> dict[str, Any]:
    """Update editable job-card details."""
    del user_id
    current = _get_job(conn, job_card_id)
    with transaction(conn):
        conn.execute(
            """
            UPDATE job_cards SET customer_complaint = ?, current_condition = ?,
                inspection_notes = ?, diagnosis = ?, mileage = ?, expected_delivery = ?,
                technician_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?
            """,
            [customer_complaint if customer_complaint is not None else current["customer_complaint"],
             current_condition if current_condition is not None else current["current_condition"],
             inspection_notes if inspection_notes is not None else current["inspection_notes"],
             diagnosis if diagnosis is not None else current["diagnosis"],
             mileage if mileage is not None else current["mileage"],
             expected_delivery if expected_delivery is not None else current["expected_delivery"],
             technician_id if technician_id is not None else current["technician_id"], job_card_id],
        )
        if job_type_ids is not None:
            _set_job_types(conn, job_card_id, job_type_ids)
    return get_job_card_full(conn, job_card_id)


def _change_status(
    conn: duckdb.DuckDBPyConnection, job_card_id: int, new_status: str,
    user_id: int | None,
) -> None:
    job = _get_job(conn, job_card_id)
    current = job["status"]
    if new_status not in STATUS_FLOW.get(current, set()):
        raise InvalidStatusTransition(f"Cannot change job from {current} to {new_status}")
    if current in {"Declined", "Cancelled"}:
        user = get_user(conn, user_id)
        if user["role_name"] not in {"Admin", "Manager"}:
            raise InvalidStatusTransition("Only Admin or Manager can reopen this job")
    delivered = date.today() if new_status == "Delivered" else job["date_delivered"]
    conn.execute(
        "UPDATE job_cards SET status = ?, date_delivered = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        [new_status, delivered, job_card_id],
    )
    conn.execute(
        "INSERT INTO job_status_history (job_card_id, status, changed_by) VALUES (?, ?, ?)",
        [job_card_id, new_status, user_id],
    )
    if new_status == "Delivered":
        from src.services.reminders import _auto_schedule_on_delivery

        _auto_schedule_on_delivery(conn, job_card_id)


def change_status(
    conn: duckdb.DuckDBPyConnection, job_card_id: int, new_status: str,
    user_id: int | None = None,
) -> dict[str, Any]:
    """Validate and apply one job-card status transition."""
    with transaction(conn):
        _change_status(conn, job_card_id, new_status, user_id)
    return get_job_card_full(conn, job_card_id)


def _recalculate_totals(conn: duckdb.DuckDBPyConnection, job_card_id: int) -> dict[str, Decimal]:
    job = _get_job(conn, job_card_id)
    labour_row = conn.execute(
        """
        SELECT sum(ei.quantity * ei.unit_price) FROM estimates e
        JOIN estimate_items ei ON ei.estimate_id = e.id
        WHERE e.job_card_id = ? AND e.status = 'Approved' AND ei.item_type = 'Labour'
        """, [job_card_id]
    ).fetchone()[0]
    labour = money(labour_row if labour_row is not None else job["labour_cost"])
    parts = money(conn.execute(
        "SELECT coalesce(sum(quantity * unit_price), 0) FROM parts_used WHERE job_card_id = ?",
        [job_card_id],
    ).fetchone()[0])
    tax = money((labour + parts) * Decimal(job["tax_rate"]) / Decimal("100"))
    total = money(labour + parts + tax)
    conn.execute(
        """
        UPDATE job_cards SET labour_cost = ?, parts_total = ?, tax_amount = ?, total_cost = ?,
            updated_at = CURRENT_TIMESTAMP WHERE id = ?
        """, [labour, parts, tax, total, job_card_id]
    )
    return {"labour_cost": labour, "parts_total": parts, "tax_amount": tax, "total_cost": total}


def recalculate_totals(
    conn: duckdb.DuckDBPyConnection, job_card_id: int,
    user_id: int | None = None,
) -> dict[str, Decimal]:
    """Recalculate labour, parts, tax, and total cost."""
    del user_id
    with transaction(conn):
        result = _recalculate_totals(conn, job_card_id)
    return result


def list_job_cards(
    conn: duckdb.DuckDBPyConnection, *, status: str | None = None,
    customer_id: int | None = None, vehicle_id: int | None = None,
    technician_id: int | None = None, date_from: date | None = None,
    date_to: date | None = None, query: str | None = None,
) -> list[dict[str, Any]]:
    """Return filtered job-card summaries."""
    pattern = f"%{query or ''}%"
    return fetch_all(conn.execute(
        """
        SELECT jc.*, c.name AS customer_name, v.reg_number, v.brand, v.model
        FROM job_cards jc JOIN customers c ON c.id = jc.customer_id
        JOIN vehicles v ON v.id = jc.vehicle_id
        WHERE (? IS NULL OR jc.status = ?) AND (? IS NULL OR jc.customer_id = ?)
          AND (? IS NULL OR jc.vehicle_id = ?) AND (? IS NULL OR jc.technician_id = ?)
          AND (? IS NULL OR jc.date_received >= ?) AND (? IS NULL OR jc.date_received <= ?)
          AND (? IS NULL OR jc.job_no ILIKE ? OR c.name ILIKE ? OR v.reg_number ILIKE ?
               OR coalesce(v.vin, '') ILIKE ?)
        ORDER BY jc.date_received DESC, jc.id DESC
        """, [status, status, customer_id, customer_id, vehicle_id, vehicle_id,
                technician_id, technician_id, date_from, date_from, date_to, date_to,
                query, pattern, pattern, pattern, pattern]
    ))


def list_job_types(
    conn: duckdb.DuckDBPyConnection, *, active_only: bool = True,
) -> list[dict[str, Any]]:
    """List job types for selection widgets."""
    return fetch_all(conn.execute(
        "SELECT * FROM job_types WHERE (? = FALSE OR is_active = TRUE) ORDER BY name",
        [active_only],
    ))


def get_allowed_status_transitions(
    conn: duckdb.DuckDBPyConnection, job_card_id: int,
    user_id: int | None = None,
) -> list[str]:
    """Return legal next statuses for the current user and job state."""
    job = _get_job(conn, job_card_id)
    allowed = sorted(STATUS_FLOW[job["status"]])
    if job["status"] in {"Declined", "Cancelled"}:
        user = get_user(conn, user_id)
        if user["role_name"] not in {"Admin", "Manager"}:
            return []
    return allowed


def list_due_deliveries(
    conn: duckdb.DuckDBPyConnection, as_of: date | None = None,
) -> list[dict[str, Any]]:
    """List non-final jobs due for delivery on or before a date."""
    target = as_of or date.today()
    return fetch_all(conn.execute(
        """
        SELECT jc.*, c.name AS customer_name, v.reg_number, v.brand, v.model
        FROM job_cards jc JOIN customers c ON c.id = jc.customer_id
        JOIN vehicles v ON v.id = jc.vehicle_id
        WHERE jc.expected_delivery <= ?
          AND jc.status NOT IN ('Delivered', 'Declined', 'Cancelled')
        ORDER BY jc.expected_delivery, jc.id
        """, [target]
    ))


def get_job_status_history(
    conn: duckdb.DuckDBPyConnection, job_card_id: int,
) -> list[dict[str, Any]]:
    """Return the recorded status timeline for a job."""
    _get_job(conn, job_card_id)
    return fetch_all(conn.execute(
        """
        SELECT h.*, u.name AS changed_by_name FROM job_status_history h
        LEFT JOIN users u ON u.id = h.changed_by
        WHERE h.job_card_id = ? ORDER BY h.changed_at, h.id
        """, [job_card_id]
    ))


def get_job_card_full(conn: duckdb.DuckDBPyConnection, job_card_id: int) -> dict[str, Any]:
    """Return a complete nested job-card aggregate."""
    job = require_record(fetch_one(conn.execute(
        """
        SELECT jc.*, c.name AS customer_name, c.phone, c.email, c.address,
               v.brand, v.model, v.year, v.vin, v.reg_number
        FROM job_cards jc JOIN customers c ON c.id = jc.customer_id
        JOIN vehicles v ON v.id = jc.vehicle_id WHERE jc.id = ?
        """, [job_card_id]
    )), "Job card")
    job["job_types"] = fetch_all(conn.execute(
        """
        SELECT jt.id, jt.name FROM job_card_job_types j
        JOIN job_types jt ON jt.id = j.job_type_id WHERE j.job_card_id = ? ORDER BY jt.name
        """, [job_card_id]
    ))
    job["estimates"] = fetch_all(conn.execute(
        "SELECT * FROM estimates WHERE job_card_id = ? ORDER BY version DESC", [job_card_id]
    ))
    job["parts_used"] = fetch_all(conn.execute(
        """
        SELECT pu.*, p.part_name, p.part_number FROM parts_used pu
        JOIN parts p ON p.id = pu.part_id WHERE pu.job_card_id = ? ORDER BY pu.id
        """, [job_card_id]
    ))
    job["invoice"] = fetch_one(conn.execute(
        "SELECT * FROM invoices WHERE job_card_id = ?", [job_card_id]
    ))
    return job

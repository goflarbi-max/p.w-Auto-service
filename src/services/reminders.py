"""Service-reminder scheduling and idempotent SMS processing."""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Any

import duckdb

from src.config import DEFAULT_REMINDER_INTERVAL_MONTHS, REMINDER_MESSAGE_TEMPLATE
from src.services._common import fetch_all, fetch_one, require_record, transaction
from src.services.errors import ValidationError
from src.services.sms import SMSProvider, send_sms_reminder


def _add_months(value: date, months: int) -> date:
    if months <= 0:
        raise ValidationError("Reminder interval must be positive")
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _schedule_reminder(
    conn: duckdb.DuckDBPyConnection, vehicle_id: int, last_service_date: date,
    interval_months: int,
) -> int:
    vehicle = conn.execute("SELECT customer_id FROM vehicles WHERE id = ?", [vehicle_id]).fetchone()
    if vehicle is None:
        raise ValidationError("Vehicle not found")
    next_date = _add_months(last_service_date, interval_months)
    existing = conn.execute(
        """
        SELECT id FROM service_reminders
        WHERE vehicle_id = ? AND status = 'Pending' ORDER BY id DESC LIMIT 1
        """, [vehicle_id]
    ).fetchone()
    if existing:
        conn.execute(
            """
            UPDATE service_reminders SET customer_id = ?, last_service_date = ?,
                next_service_date = ?, reminder_sent = FALSE, reminder_sent_at = NULL,
                status = 'Pending', updated_at = CURRENT_TIMESTAMP WHERE id = ?
            """, [vehicle[0], last_service_date, next_date, existing[0]]
        )
        return existing[0]
    return conn.execute(
        """
        INSERT INTO service_reminders
            (customer_id, vehicle_id, last_service_date, next_service_date)
        VALUES (?, ?, ?, ?) RETURNING id
        """, [vehicle[0], vehicle_id, last_service_date, next_date]
    ).fetchone()[0]


def schedule_reminder(
    conn: duckdb.DuckDBPyConnection, vehicle_id: int, last_service_date: date,
    interval_months: int | None = None, user_id: int | None = None,
) -> dict[str, Any]:
    del user_id
    with transaction(conn):
        reminder_id = _schedule_reminder(
            conn, vehicle_id, last_service_date,
            interval_months or DEFAULT_REMINDER_INTERVAL_MONTHS,
        )
    return require_record(fetch_one(conn.execute(
        "SELECT * FROM service_reminders WHERE id = ?", [reminder_id]
    )), "Reminder")


def _auto_schedule_on_delivery(conn: duckdb.DuckDBPyConnection, job_card_id: int) -> int | None:
    job = conn.execute(
        "SELECT vehicle_id, date_delivered FROM job_cards WHERE id = ? AND status = 'Delivered'",
        [job_card_id],
    ).fetchone()
    if job is None:
        return None
    servicing = conn.execute(
        """
        SELECT 1 FROM job_card_job_types j JOIN job_types jt ON jt.id = j.job_type_id
        WHERE j.job_card_id = ? AND lower(jt.name) = 'servicing'
        """, [job_card_id]
    ).fetchone()
    if servicing is None:
        return None
    return _schedule_reminder(conn, job[0], job[1], DEFAULT_REMINDER_INTERVAL_MONTHS)


def auto_schedule_on_delivery(
    conn: duckdb.DuckDBPyConnection, job_card_id: int,
    user_id: int | None = None,
) -> dict[str, Any] | None:
    del user_id
    with transaction(conn):
        reminder_id = _auto_schedule_on_delivery(conn, job_card_id)
    if reminder_id is None:
        return None
    return fetch_one(conn.execute("SELECT * FROM service_reminders WHERE id = ?", [reminder_id]))


def get_due_reminders(
    conn: duckdb.DuckDBPyConnection, days_ahead: int = 7,
) -> list[dict[str, Any]]:
    if days_ahead < 0:
        raise ValidationError("days_ahead cannot be negative")
    return fetch_all(conn.execute(
        """
        SELECT r.*, c.name AS customer_name, c.phone, v.brand, v.model, v.reg_number
        FROM service_reminders r JOIN customers c ON c.id = r.customer_id
        JOIN vehicles v ON v.id = r.vehicle_id
        WHERE r.status = 'Pending' AND r.reminder_sent = FALSE
          AND r.next_service_date <= ? ORDER BY r.next_service_date, r.id
        """, [date.today() + timedelta(days=days_ahead)]
    ))


def list_reminders(
    conn: duckdb.DuckDBPyConnection, *, status: str | None = None,
    date_from: date | None = None, date_to: date | None = None,
) -> list[dict[str, Any]]:
    """List reminders with optional status and date filters."""
    return fetch_all(conn.execute(
        """
        SELECT r.*, c.name AS customer_name, c.phone, v.brand, v.model, v.reg_number
        FROM service_reminders r JOIN customers c ON c.id = r.customer_id
        JOIN vehicles v ON v.id = r.vehicle_id
        WHERE (? IS NULL OR r.status = ?)
          AND (? IS NULL OR r.next_service_date >= ?)
          AND (? IS NULL OR r.next_service_date <= ?)
        ORDER BY r.next_service_date, r.id
        """, [status, status, date_from, date_from, date_to, date_to]
    ))


def process_due_reminders(
    conn: duckdb.DuckDBPyConnection, days_ahead: int = 7, *,
    provider: SMSProvider | None = None, user_id: int | None = None,
) -> list[dict[str, Any]]:
    del user_id
    results: list[dict[str, Any]] = []
    for reminder in get_due_reminders(conn, days_ahead):
        vehicle = f"{reminder['brand']} {reminder['model']} ({reminder['reg_number']})"
        message = REMINDER_MESSAGE_TEMPLATE.format(
            customer_name=reminder["customer_name"], vehicle=vehicle,
            next_service_date=reminder["next_service_date"].isoformat(),
        )
        outcome = send_sms_reminder(reminder["phone"], message, provider)
        with transaction(conn):
            if outcome.success:
                conn.execute(
                    """
                    UPDATE service_reminders SET reminder_sent = TRUE,
                        reminder_sent_at = CURRENT_TIMESTAMP, status = 'Sent',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND status = 'Pending' AND reminder_sent = FALSE
                    """, [reminder["id"]]
                )
            else:
                conn.execute(
                    """
                    UPDATE service_reminders SET status = 'Failed', updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND status = 'Pending' AND reminder_sent = FALSE
                    """, [reminder["id"]]
                )
        results.append({"reminder_id": reminder["id"], "success": outcome.success,
                        "error": outcome.error})
    return results

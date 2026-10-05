"""Phase 2 service-layer business-rule tests."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import duckdb
import pytest

from scripts.build_database import build_database
from src.services.customers import create_customer, normalize_ghana_phone
from src.services.errors import (
    InsufficientStockError,
    InvalidStatusTransition,
    ValidationError,
)
from src.services.estimates import (
    approve_estimate,
    create_estimate,
    decline_estimate,
    send_estimate,
)
from src.services.invoices import create_invoice, record_payment
from src.services.job_cards import STATUS_FLOW, change_status, open_job_card
from src.services.parts import get_reorder_list, record_part_used, remove_part_used
from src.services.reminders import process_due_reminders, schedule_reminder
from src.services.sms import SMSProvider, SMSResult
from src.services.users import has_permission
from src.services.vehicles import get_vehicle_history


@pytest.fixture()
def conn(tmp_path: Path):
    database = build_database(tmp_path / "services.duckdb")
    connection = duckdb.connect(str(database))
    try:
        yield connection
    finally:
        connection.close()


def _new_job(conn, received: date = date(2027, 1, 2)) -> dict:
    return open_job_card(
        conn, customer_id=1, vehicle_id=2, customer_complaint="Test complaint",
        date_received=received, job_type_ids=[1], user_id=1,
    )


def test_job_numbers_sequence_and_year_reset(conn) -> None:
    first = _new_job(conn, date(2027, 1, 2))
    second = _new_job(conn, date(2027, 2, 3))
    next_year = _new_job(conn, date(2028, 1, 1))
    assert first["job_no"] == "PW-JC-2027-0001"
    assert second["job_no"] == "PW-JC-2027-0002"
    assert next_year["job_no"] == "PW-JC-2028-0001"


def test_every_job_status_transition(conn) -> None:
    statuses = set(STATUS_FLOW)
    for current in statuses:
        for target in statuses:
            conn.execute(
                "UPDATE job_cards SET status = ?, date_delivered = ? WHERE id = 1",
                [current, date.today() if current == "Delivered" else None],
            )
            if target in STATUS_FLOW[current]:
                result = change_status(conn, 1, target, user_id=1)
                assert result["status"] == target
            else:
                with pytest.raises(InvalidStatusTransition):
                    change_status(conn, 1, target, user_id=1)

    conn.execute("INSERT INTO users (name, email, role_id) VALUES ('Tech', 'tech@example.com', 3)")
    conn.execute("UPDATE job_cards SET status = 'Declined', date_delivered = NULL WHERE id = 1")
    with pytest.raises(InvalidStatusTransition):
        change_status(conn, 1, "Received", user_id=2)


def test_estimate_approval_and_decline_workflows(conn) -> None:
    approved_job = _new_job(conn)
    change_status(conn, approved_job["id"], "Diagnosed", user_id=1)
    estimate = create_estimate(conn, approved_job["id"], [
        {"item_type": "Labour", "description": "Test labour", "quantity": Decimal("1"),
         "unit_price": Decimal("500")}
    ])
    sent = send_estimate(conn, estimate["id"], user_id=1)
    approved = approve_estimate(conn, sent["id"], user_id=1)
    assert approved["status"] == "Approved"
    assert conn.execute("SELECT status FROM job_cards WHERE id = ?", [approved_job["id"]]).fetchone()[0] == "In Progress"

    declined_job = _new_job(conn, date(2027, 1, 3))
    change_status(conn, declined_job["id"], "Diagnosed", user_id=1)
    estimate2 = create_estimate(conn, declined_job["id"], [
        {"item_type": "Labour", "description": "Diagnosis", "quantity": Decimal("1"),
         "unit_price": Decimal("100")}
    ])
    send_estimate(conn, estimate2["id"], user_id=1)
    declined = decline_estimate(conn, estimate2["id"], user_id=1)
    assert declined["status"] == "Declined"
    assert conn.execute("SELECT status FROM job_cards WHERE id = ?", [declined_job["id"]]).fetchone()[0] == "Declined"


def test_parts_usage_stock_restore_and_atomic_failure(conn) -> None:
    before = conn.execute("SELECT quantity FROM parts WHERE id = 1").fetchone()[0]
    usage = record_part_used(conn, 1, 1, Decimal("1"), user_id=1)
    assert conn.execute("SELECT quantity FROM parts WHERE id = 1").fetchone()[0] == before - 1
    remove_part_used(conn, usage["id"], user_id=1)
    assert conn.execute("SELECT quantity FROM parts WHERE id = 1").fetchone()[0] == before

    usage_count = conn.execute("SELECT count(*) FROM parts_used WHERE job_card_id = 1").fetchone()[0]
    with pytest.raises(InsufficientStockError):
        record_part_used(conn, 1, 1, before + 1, user_id=1)
    assert conn.execute("SELECT quantity FROM parts WHERE id = 1").fetchone()[0] == before
    assert conn.execute("SELECT count(*) FROM parts_used WHERE job_card_id = 1").fetchone()[0] == usage_count
    assert {row["id"] for row in get_reorder_list(conn)} == {1, 3, 4, 10}


def test_phone_normalization_and_duplicate_customer(conn) -> None:
    assert normalize_ghana_phone("0541837349") == "+233541837349"
    assert normalize_ghana_phone("233541837349") == "+233541837349"
    first = create_customer(conn, "New Customer", "0541837349")
    duplicate = create_customer(conn, "Different Name", "+233541837349")
    assert duplicate["id"] == first["id"]


def test_vehicle_history_by_vin_and_registration(conn) -> None:
    by_vin = get_vehicle_history(conn, vin="wp0aa2a99js100001")
    by_reg = get_vehicle_history(conn, reg_number="gt-911-18")
    assert by_vin["vehicle"]["id"] == by_reg["vehicle"]["id"] == 1
    assert by_vin["job_cards"][0]["job_no"] == "PW-JC-2026-0006"
    assert by_vin["job_cards"][0]["parts_used"]


def test_invoice_idempotency_numbering_and_payments(conn) -> None:
    job = _new_job(conn)
    conn.execute(
        "UPDATE job_cards SET status = 'In Progress', labour_cost = 100, total_cost = 100 WHERE id = ?",
        [job["id"]],
    )
    invoice = create_invoice(conn, job["id"], user_id=1)
    again = create_invoice(conn, job["id"], user_id=1)
    assert invoice["id"] == again["id"]
    assert invoice["invoice_no"] == "PW-INV-2026-0004"

    partial = record_payment(conn, invoice["id"], Decimal("40"), "mobile money", user_id=1)
    assert partial["payment_status"] == "Partial"
    with pytest.raises(ValidationError):
        record_payment(conn, invoice["id"], Decimal("61"), "Cash", user_id=1)
    paid = record_payment(conn, invoice["id"], Decimal("60"), "Cash", user_id=1)
    assert paid["payment_status"] == "Paid"
    assert conn.execute("SELECT count(*) FROM invoice_payments WHERE invoice_id = ?", [invoice["id"]]).fetchone()[0] == 2


class CountingProvider(SMSProvider):
    def __init__(self) -> None:
        self.calls = 0

    def send(self, phone_number: str, message: str) -> SMSResult:
        self.calls += 1
        return SMSResult(success=True, provider_message_id=str(self.calls))


def test_due_reminder_processing_is_idempotent(conn) -> None:
    schedule_reminder(conn, 1, date.today(), interval_months=1, user_id=1)
    conn.execute("UPDATE service_reminders SET next_service_date = CURRENT_DATE WHERE vehicle_id = 1 AND status = 'Pending'")
    provider = CountingProvider()
    first = process_due_reminders(conn, provider=provider, user_id=1)
    second = process_due_reminders(conn, provider=provider, user_id=1)
    assert first and second == []
    assert provider.calls == 1


def test_role_permissions() -> None:
    admin = {"role_name": "Admin", "is_active": True}
    manager = {"role_name": "Manager", "is_active": True}
    technician = {"role_name": "Technician", "is_active": True}
    assert has_permission(admin, "user_management")
    assert has_permission(manager, "invoices")
    assert not has_permission(manager, "user_management")
    assert has_permission(technician, "job_cards")
    assert has_permission(technician, "parts_usage")
    assert not has_permission(technician, "invoices")
    assert not has_permission(technician, "revenue_reports")

"""Integration tests for the P.W Auto Service database foundation."""

from __future__ import annotations

import re
from pathlib import Path

import duckdb
import pytest

from scripts.build_database import build_database
from src.database.connection import ensure_db_exists, next_document_number


@pytest.fixture()
def database_path(tmp_path: Path) -> Path:
    """Build and return an isolated database for each test."""
    return build_database(tmp_path / "test_pw_auto.duckdb")


def test_database_builds_with_required_sample_counts(database_path: Path) -> None:
    """The complete schema and minimum sample dataset are available."""
    connection = duckdb.connect(str(database_path), read_only=True)
    try:
        expected_minimums = {
            "customers": 5,
            "vehicles": 8,
            "appointments": 6,
            "parts": 10,
            "job_cards": 6,
            "roles": 3,
            "users": 1,
        }
        for table, minimum in expected_minimums.items():
            count = connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            assert count >= minimum
        owner = connection.execute(
            """
            SELECT u.name, u.email, r.name
            FROM users u JOIN roles r ON r.id = u.role_id
            """
        ).fetchone()
        assert owner == ("Obed Boatey", "boatey.obed@gmail.com", "Admin")
    finally:
        connection.close()


def test_foreign_keys_are_enforced(database_path: Path) -> None:
    """Stable role/user relationships remain database-enforced."""
    connection = duckdb.connect(str(database_path))
    try:
        with pytest.raises(duckdb.ConstraintException):
            connection.execute(
                """
                INSERT INTO users (name, email, role_id)
                VALUES ('Invalid User', 'invalid@example.com', 99999)
                """
            )
    finally:
        connection.close()


def test_reorder_view_applies_both_rules(database_path: Path) -> None:
    """Low stock and the manual ordering flag both surface in the view."""
    connection = duckdb.connect(str(database_path), read_only=True)
    try:
        rows = connection.execute(
            "SELECT id, reorder_reason FROM v_parts_to_reorder ORDER BY id"
        ).fetchall()
        assert {row[0] for row in rows} == {1, 3, 4, 10}
        assert any("manually flagged" in row[1].lower() for row in rows)
    finally:
        connection.close()


def test_document_numbers_have_required_formats_and_continue(database_path: Path) -> None:
    """Seeded numbers are valid and the yearly counter allocates the next suffix."""
    connection = duckdb.connect(str(database_path))
    try:
        job_numbers = [
            row[0] for row in connection.execute("SELECT job_no FROM job_cards").fetchall()
        ]
        invoice_numbers = [
            row[0] for row in connection.execute("SELECT invoice_no FROM invoices").fetchall()
        ]
        assert all(re.fullmatch(r"PW-JC-2026-\d{4,}", value) for value in job_numbers)
        assert all(re.fullmatch(r"PW-INV-2026-\d{4,}", value) for value in invoice_numbers)

        connection.execute("BEGIN TRANSACTION")
        assert next_document_number(connection, "Job Card", 2026) == "PW-JC-2026-0007"
        assert next_document_number(connection, "Invoice", 2026) == "PW-INV-2026-0004"
        assert next_document_number(connection, "Job Card", 2027) == "PW-JC-2027-0001"
        connection.execute("ROLLBACK")
    finally:
        connection.close()


def test_dashboard_views_use_approved_definitions(database_path: Path) -> None:
    """Ready jobs are in-house and pending excludes terminal statuses."""
    connection = duckdb.connect(str(database_path), read_only=True)
    try:
        statuses = {
            row[0]
            for row in connection.execute("SELECT status FROM v_cars_in_house").fetchall()
        }
        assert "Ready for Delivery" in statuses
        summary = connection.execute(
            "SELECT total_jobs, completed_jobs, pending_jobs FROM v_jobs_yearly_summary WHERE year = 2026"
        ).fetchone()
        assert summary == (6, 1, 5)
        revenue = connection.execute(
            "SELECT invoiced_total, paid_total FROM v_service_revenue_yearly WHERE year = 2026"
        ).fetchone()
        assert revenue[0] == pytest.approx(8140)
        assert revenue[1] == pytest.approx(3540)
    finally:
        connection.close()


def test_primary_key_sequences_continue_after_seed_data(database_path: Path) -> None:
    """A new row receives an ID after the seeded range."""
    connection = duckdb.connect(str(database_path))
    try:
        new_id = connection.execute(
            "INSERT INTO roles (name) VALUES ('Service Advisor') RETURNING id"
        ).fetchone()[0]
        assert new_id == 4
    finally:
        connection.close()


def test_ensure_db_exists_repairs_an_incomplete_database(tmp_path: Path) -> None:
    """Hosted startup recovery rebuilds a file that lacks the required schema."""
    database_path = tmp_path / "incomplete.duckdb"
    connection = duckdb.connect(str(database_path))
    connection.execute("CREATE TABLE stray_table (id INTEGER)")
    connection.close()

    assert ensure_db_exists(database_path) == database_path.resolve()
    repaired = duckdb.connect(str(database_path), read_only=True)
    try:
        version = repaired.execute(
            "SELECT value FROM app_metadata WHERE key = 'schema_version'"
        ).fetchone()[0]
        assert version == "3"
        assert repaired.execute("SELECT count(*) FROM job_cards").fetchone()[0] == 6
    finally:
        repaired.close()

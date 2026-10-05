"""Vehicle operations and service-history queries."""

from __future__ import annotations

from typing import Any

import duckdb

from src.services._common import fetch_all, fetch_one, require_record, transaction
from src.services.customers import get_customer
from src.services.errors import ValidationError


def _clean_identifier(value: str | None) -> str | None:
    return value.strip().upper() if value and value.strip() else None


def get_vehicle(conn: duckdb.DuckDBPyConnection, vehicle_id: int) -> dict[str, Any]:
    """Retrieve one vehicle with its customer summary."""
    return require_record(fetch_one(conn.execute(
        """
        SELECT v.*, c.name AS customer_name, c.phone AS customer_phone
        FROM vehicles v JOIN customers c ON c.id = v.customer_id WHERE v.id = ?
        """, [vehicle_id]
    )), "Vehicle")


def create_vehicle(
    conn: duckdb.DuckDBPyConnection, customer_id: int, brand: str, model: str,
    reg_number: str, *, year: int | None = None, vin: str | None = None,
    user_id: int | None = None,
) -> dict[str, Any]:
    """Create a vehicle for an existing customer."""
    del user_id
    get_customer(conn, customer_id)
    registration, clean_vin = _clean_identifier(reg_number), _clean_identifier(vin)
    if not brand.strip() or not model.strip() or registration is None:
        raise ValidationError("Brand, model, and registration number are required")
    duplicate = conn.execute(
        "SELECT id FROM vehicles WHERE reg_number = ? OR (? IS NOT NULL AND vin = ?)",
        [registration, clean_vin, clean_vin],
    ).fetchone()
    if duplicate:
        raise ValidationError("VIN or registration number already exists")
    with transaction(conn):
        vehicle_id = conn.execute(
            """
            INSERT INTO vehicles (customer_id, brand, model, year, vin, reg_number)
            VALUES (?, ?, ?, ?, ?, ?) RETURNING id
            """, [customer_id, brand.strip(), model.strip(), year, clean_vin, registration]
        ).fetchone()[0]
    return get_vehicle(conn, vehicle_id)


def update_vehicle(
    conn: duckdb.DuckDBPyConnection, vehicle_id: int, *, customer_id: int | None = None,
    brand: str | None = None, model: str | None = None, year: int | None = None,
    vin: str | None = None, reg_number: str | None = None,
    user_id: int | None = None,
) -> dict[str, Any]:
    """Update supplied vehicle fields."""
    del user_id
    current = get_vehicle(conn, vehicle_id)
    owner = customer_id if customer_id is not None else current["customer_id"]
    get_customer(conn, owner)
    clean_vin = _clean_identifier(vin) if vin is not None else current["vin"]
    registration = _clean_identifier(reg_number) if reg_number is not None else current["reg_number"]
    duplicate = conn.execute(
        """
        SELECT id FROM vehicles WHERE id <> ? AND
        (reg_number = ? OR (? IS NOT NULL AND vin = ?))
        """, [vehicle_id, registration, clean_vin, clean_vin]
    ).fetchone()
    if duplicate:
        raise ValidationError("VIN or registration number already exists")
    with transaction(conn):
        conn.execute(
            """
            UPDATE vehicles SET customer_id = ?, brand = ?, model = ?, year = ?, vin = ?,
                reg_number = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?
            """, [owner, brand.strip() if brand is not None else current["brand"],
                    model.strip() if model is not None else current["model"],
                    year if year is not None else current["year"], clean_vin,
                    registration, vehicle_id]
        )
    return get_vehicle(conn, vehicle_id)


def search_vehicles(conn: duckdb.DuckDBPyConnection, query: str) -> list[dict[str, Any]]:
    """Search vehicles by identifiers, brand, or model."""
    pattern = f"%{query.strip()}%"
    return fetch_all(conn.execute(
        """
        SELECT v.*, c.name AS customer_name FROM vehicles v
        JOIN customers c ON c.id = v.customer_id
        WHERE coalesce(v.vin, '') ILIKE ? OR v.reg_number ILIKE ?
           OR v.brand ILIKE ? OR v.model ILIKE ? ORDER BY v.reg_number
        """, [pattern, pattern, pattern, pattern]
    ))


def list_customer_vehicles(
    conn: duckdb.DuckDBPyConnection, customer_id: int,
) -> list[dict[str, Any]]:
    """List all vehicles owned by one customer."""
    get_customer(conn, customer_id)
    return fetch_all(conn.execute(
        "SELECT * FROM vehicles WHERE customer_id = ? ORDER BY brand, model, reg_number",
        [customer_id],
    ))


def get_vehicle_history(
    conn: duckdb.DuckDBPyConnection, *, vehicle_id: int | None = None,
    vin: str | None = None, reg_number: str | None = None,
) -> dict[str, Any]:
    """Return newest-first jobs with parts and invoice summaries."""
    supplied = sum(value is not None for value in (vehicle_id, vin, reg_number))
    if supplied != 1:
        raise ValidationError("Supply exactly one of vehicle_id, vin, or reg_number")
    vehicle = fetch_one(conn.execute(
        """
        SELECT v.*, c.name AS customer_name, c.phone AS customer_phone
        FROM vehicles v JOIN customers c ON c.id = v.customer_id
        WHERE v.id = ? OR (? IS NOT NULL AND upper(v.vin) = upper(?))
           OR (? IS NOT NULL AND upper(v.reg_number) = upper(?))
        """, [vehicle_id, vin, vin, reg_number, reg_number]
    ))
    vehicle = require_record(vehicle, "Vehicle")
    jobs = fetch_all(conn.execute(
        """
        SELECT jc.*, i.id AS invoice_id, i.invoice_no, i.total AS invoice_total,
               i.amount_paid, i.payment_status
        FROM job_cards jc LEFT JOIN invoices i ON i.job_card_id = jc.id
        WHERE jc.vehicle_id = ? ORDER BY jc.date_received DESC, jc.id DESC
        """, [vehicle["id"]]
    ))
    for job in jobs:
        job["parts_used"] = fetch_all(conn.execute(
            """
            SELECT pu.*, p.part_name, p.part_number FROM parts_used pu
            JOIN parts p ON p.id = pu.part_id WHERE pu.job_card_id = ? ORDER BY pu.id
            """, [job["id"]]
        ))
    return {"vehicle": vehicle, "job_cards": jobs}


def get_brand_model_suggestions(conn: duckdb.DuckDBPyConnection) -> dict[str, list[str]]:
    """Return distinct brands and models used in vehicle records."""
    brands = [row[0] for row in conn.execute("SELECT DISTINCT brand FROM vehicles ORDER BY brand").fetchall()]
    models = [row[0] for row in conn.execute("SELECT DISTINCT model FROM vehicles ORDER BY model").fetchall()]
    return {"brands": brands, "models": models}

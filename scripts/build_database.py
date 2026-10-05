"""Create the DuckDB schema and load the bundled sample CSV data."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import DB_PATH  # noqa: E402


LOAD_ORDER: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("roles", "roles.csv", ("id", "name")),
    ("users", "users.csv", ("id", "name", "email", "role_id", "is_active")),
    ("customers", "customers.csv", ("id", "name", "phone", "email", "address")),
    (
        "vehicles",
        "vehicles.csv",
        ("id", "customer_id", "brand", "model", "year", "vin", "reg_number"),
    ),
    (
        "parts",
        "parts.csv",
        (
            "id", "part_name", "part_number", "brand", "type", "quantity",
            "cost_price", "selling_price", "supplier", "reorder_level", "needs_ordering",
        ),
    ),
    ("job_types", "job_types.csv", ("id", "name", "is_active")),
    (
        "appointments",
        "appointments.csv",
        ("id", "source", "appointment_date", "customer_id", "vehicle_id", "notes", "status"),
    ),
    (
        "job_cards",
        "job_cards.csv",
        (
            "id", "job_no", "appointment_id", "customer_id", "vehicle_id", "technician_id",
            "mileage", "customer_complaint", "current_condition", "inspection_notes", "diagnosis",
            "date_received", "expected_delivery", "date_delivered", "status", "labour_cost",
            "parts_total", "tax_rate", "tax_amount", "total_cost",
        ),
    ),
    (
        "job_card_job_types",
        "job_card_job_types.csv",
        ("job_card_id", "job_type_id"),
    ),
    (
        "estimates",
        "estimates.csv",
        ("id", "job_card_id", "version", "status", "created_at", "approved_at"),
    ),
    (
        "estimate_items",
        "estimate_items.csv",
        ("id", "estimate_id", "item_type", "description", "part_id", "quantity", "unit_price"),
    ),
    (
        "parts_used",
        "parts_used.csv",
        ("id", "job_card_id", "part_id", "quantity", "unit_price", "recorded_at"),
    ),
    (
        "parts_orders",
        "parts_orders.csv",
        (
            "id", "part_id", "quantity_ordered", "quantity_received", "unit_cost", "supplier",
            "ordered_date", "expected_date", "received_date", "status", "notes",
        ),
    ),
    (
        "service_reminders",
        "service_reminders.csv",
        (
            "id", "customer_id", "vehicle_id", "last_service_date", "next_service_date",
            "reminder_sent", "reminder_sent_at", "status",
        ),
    ),
    (
        "invoices",
        "invoices.csv",
        (
            "id", "invoice_no", "job_card_id", "issue_date", "labour_total", "parts_total",
            "tax_amount", "total", "payment_status", "amount_paid", "notes",
        ),
    ),
)


def _load_csv(
    connection: duckdb.DuckDBPyConnection,
    table: str,
    csv_path: Path,
    columns: tuple[str, ...],
) -> None:
    """Load one CSV through Pandas using an explicit column contract."""
    frame = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    if tuple(frame.columns) != columns:
        raise ValueError(
            f"{csv_path.name} columns must be {columns}; got {tuple(frame.columns)}"
        )
    frame = frame.replace("", None)
    relation_name = f"load_{table}"
    connection.register(relation_name, frame)
    insert_columns = columns
    if columns[0] == "id":
        expected_ids = [str(number) for number in range(1, len(frame) + 1)]
        if frame["id"].tolist() != expected_ids:
            raise ValueError(f"{csv_path.name} IDs must be sequential from 1")
        insert_columns = columns[1:]
    quoted_columns = ", ".join(f'"{column}"' for column in insert_columns)
    connection.execute(
        f'INSERT INTO "{table}" ({quoted_columns}) SELECT {quoted_columns} FROM "{relation_name}"'
    )
    connection.unregister(relation_name)


def _validate_ownership(connection: duckdb.DuckDBPyConnection) -> None:
    """Reject cross-customer vehicle references that SQL CHECK cannot express."""
    checks = {
        "appointments": """
            SELECT count(*) FROM appointments a JOIN vehicles v ON v.id = a.vehicle_id
            WHERE a.customer_id <> v.customer_id
        """,
        "job_cards": """
            SELECT count(*) FROM job_cards j JOIN vehicles v ON v.id = j.vehicle_id
            WHERE j.customer_id <> v.customer_id
        """,
        "service_reminders": """
            SELECT count(*) FROM service_reminders r JOIN vehicles v ON v.id = r.vehicle_id
            WHERE r.customer_id <> v.customer_id
        """,
    }
    for table, query in checks.items():
        if connection.execute(query).fetchone()[0]:
            raise ValueError(f"{table} contains a vehicle owned by another customer")


def _restore_counters(connection: duckdb.DuckDBPyConnection) -> None:
    """Set yearly counters to the highest imported suffix."""
    patterns = (
        ("Job Card", "job_cards", "job_no", re.compile(r"^PW-JC-(\d{4})-(\d+)$")),
        ("Invoice", "invoices", "invoice_no", re.compile(r"^PW-INV-(\d{4})-(\d+)$")),
    )
    for document_type, table, column, pattern in patterns:
        maxima: dict[int, int] = {}
        for (value,) in connection.execute(f"SELECT {column} FROM {table}").fetchall():
            match = pattern.fullmatch(value)
            if match is None:
                raise ValueError(f"Invalid document number: {value}")
            year, number = int(match.group(1)), int(match.group(2))
            maxima[year] = max(maxima.get(year, 0), number)
        for year, number in maxima.items():
            connection.execute(
                "INSERT INTO document_counters VALUES (?, ?, ?)",
                [document_type, year, number],
            )


def build_database(db_path: Path | str | None = None) -> Path:
    """Drop/recreate the managed schema and atomically load all sample CSV files."""
    destination = Path(db_path or DB_PATH).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    schema_path = PROJECT_ROOT / "src" / "database" / "schema.sql"
    data_dir = PROJECT_ROOT / "data"

    connection = duckdb.connect(str(destination))
    try:
        connection.execute("BEGIN TRANSACTION")
        connection.execute(schema_path.read_text(encoding="utf-8"))
        for table, filename, columns in LOAD_ORDER:
            _load_csv(connection, table, data_dir / filename, columns)
        _validate_ownership(connection)
        _restore_counters(connection)
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()
    return destination


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", type=Path, default=DB_PATH)
    args = parser.parse_args()
    built_path = build_database(args.db_path)
    print(f"Built database: {built_path}")


if __name__ == "__main__":
    main()

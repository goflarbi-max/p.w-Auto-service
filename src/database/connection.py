"""DuckDB connection lifecycle and document-number allocation."""

from __future__ import annotations

import threading
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Iterator, Literal

import duckdb

from src.config import DB_PATH, INVOICE_NUMBER_FORMAT, JOB_NUMBER_FORMAT


SCHEMA_VERSION = "3"
REQUIRED_TABLES = {
    "appointments",
    "customers",
    "estimates",
    "estimate_items",
    "invoices",
    "invoice_payments",
    "job_cards",
    "job_status_history",
    "parts",
    "parts_orders",
    "parts_used",
    "roles",
    "service_reminders",
    "stock_adjustments",
    "users",
    "vehicles",
}
_write_lock = threading.RLock()


def _schema_is_complete(connection: duckdb.DuckDBPyConnection) -> bool:
    """Return whether the configured database contains the expected schema."""
    table_rows = connection.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
    ).fetchall()
    table_names = {row[0] for row in table_rows}
    if not REQUIRED_TABLES.issubset(table_names) or "app_metadata" not in table_names:
        return False
    version = connection.execute(
        "SELECT value FROM app_metadata WHERE key = 'schema_version'"
    ).fetchone()
    return version is not None and version[0] == SCHEMA_VERSION


def ensure_db_exists(db_path: Path | str | None = None) -> Path:
    """Build a missing or structurally incomplete database and return its path."""
    path = Path(db_path or DB_PATH).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    needs_build = not path.exists()
    if not needs_build:
        try:
            check_connection = duckdb.connect(str(path), read_only=True)
            try:
                needs_build = not _schema_is_complete(check_connection)
            finally:
                check_connection.close()
        except duckdb.Error:
            needs_build = True

    if needs_build:
        from scripts.build_database import build_database

        build_database(path)
    return path


@lru_cache(maxsize=4)
def _cached_connection(path_string: str, read_only: bool) -> duckdb.DuckDBPyConnection:
    """Create one reusable connection for each database/mode combination."""
    return duckdb.connect(path_string, read_only=read_only)


def get_connection(
    db_path: Path | str | None = None, *, read_only: bool = False
) -> duckdb.DuckDBPyConnection:
    """Return a cached connection, rebuilding the database first if necessary."""
    path = ensure_db_exists(db_path)
    return _cached_connection(str(path), read_only)


@contextmanager
def write_transaction(
    db_path: Path | str | None = None,
) -> Iterator[duckdb.DuckDBPyConnection]:
    """Serialize a write transaction for rerun-based and threaded callers."""
    with _write_lock:
        connection = get_connection(db_path)
        connection.execute("BEGIN TRANSACTION")
        try:
            yield connection
        except Exception:
            connection.execute("ROLLBACK")
            raise
        else:
            connection.execute("COMMIT")


def next_document_number(
    connection: duckdb.DuckDBPyConnection,
    document_type: Literal["Job Card", "Invoice"],
    year: int,
) -> str:
    """Allocate a yearly job-card or invoice number inside the caller's transaction."""
    if year < 2000:
        raise ValueError("Document year must be 2000 or later")
    connection.execute(
        """
        INSERT INTO document_counters (document_type, year, last_number)
        VALUES (?, ?, 1)
        ON CONFLICT (document_type, year)
        DO UPDATE SET last_number = document_counters.last_number + 1
        """,
        [document_type, year],
    )
    number = connection.execute(
        "SELECT last_number FROM document_counters WHERE document_type = ? AND year = ?",
        [document_type, year],
    ).fetchone()[0]
    template = JOB_NUMBER_FORMAT if document_type == "Job Card" else INVOICE_NUMBER_FORMAT
    return template.format(year=year, number=number)

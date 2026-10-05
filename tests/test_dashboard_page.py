"""Streamlit dashboard AppTest coverage for populated and empty data."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest
from streamlit.testing.v1 import AppTest

from scripts.build_database import build_database


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_PAGE = PROJECT_ROOT / "src" / "ui" / "pages" / "dashboard.py"


def _configure_ui_database(path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import src.config as config
    import src.database.connection as database_connection
    import src.ui.app_context as app_context
    from src.ui.dashboard_cache import clear_dashboard_cache

    try:
        app_context.get_app_connection().close()
    except Exception:
        pass
    database_connection._cached_connection.cache_clear()
    app_context.get_app_connection.clear()
    clear_dashboard_cache()
    monkeypatch.setattr(config, "DB_PATH", path)
    monkeypatch.setattr(database_connection, "DB_PATH", path)


def _remove_operational_data(path: Path) -> None:
    conn = duckdb.connect(str(path))
    try:
        for table in (
            "invoice_payments", "stock_adjustments", "estimate_items", "parts_used",
            "parts_orders", "service_reminders", "invoices", "estimates",
            "job_status_history", "job_card_job_types", "job_cards", "appointments",
            "vehicles", "customers", "parts",
        ):
            conn.execute(f'DELETE FROM "{table}"')
    finally:
        conn.close()


def test_dashboard_loads_with_sample_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = build_database(tmp_path / "dashboard_sample.duckdb")
    _configure_ui_database(path, monkeypatch)
    app = AppTest.from_file(DASHBOARD_PAGE, default_timeout=30).run()
    assert not app.exception
    assert any(title.value == "Dashboard" for title in app.title)


def test_dashboard_loads_with_empty_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = build_database(tmp_path / "dashboard_empty.duckdb")
    _remove_operational_data(path)
    _configure_ui_database(path, monkeypatch)
    app = AppTest.from_file(DASHBOARD_PAGE, default_timeout=30).run()
    assert not app.exception
    assert app.info

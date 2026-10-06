"""Streamlit AppTest smoke coverage for every Phase 3 page."""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from scripts.build_database import build_database


PROJECT_ROOT = Path(__file__).resolve().parents[1]

PAGE_FILES = (
    "app.py",
    "src/ui/pages/home.py",
    "src/ui/pages/job_cards.py",
    "src/ui/pages/customers.py",
    "src/ui/pages/appointments.py",
    "src/ui/pages/parts.py",
    "src/ui/pages/reminders.py",
    "src/ui/pages/settings.py",
    "src/ui/pages/dashboard.py",
)


@pytest.fixture()
def ui_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Point cached UI connections at an isolated sample database."""
    import src.config as config
    import src.database.connection as database_connection
    import src.ui.app_context as app_context

    path = build_database(tmp_path / "ui_test.duckdb")
    database_connection._cached_connection.cache_clear()
    app_context.get_app_connection.clear()
    monkeypatch.setattr(config, "DB_PATH", path)
    monkeypatch.setattr(database_connection, "DB_PATH", path)
    yield path
    try:
        app_context.get_app_connection().close()
    except Exception:
        pass
    database_connection._cached_connection.cache_clear()
    app_context.get_app_connection.clear()


@pytest.mark.parametrize("page_file", PAGE_FILES)
def test_each_page_loads_without_exceptions(ui_database: Path, page_file: str) -> None:
    """Every registered page renders against the bundled sample records."""
    app = AppTest.from_file(PROJECT_ROOT / page_file, default_timeout=30).run()
    assert not app.exception


def test_new_job_card_flow_creates_a_job(ui_database: Path) -> None:
    """The mobile New Job Card flow creates and opens a real job card."""
    import src.ui.app_context as app_context

    conn = app_context.get_app_connection()
    before = conn.execute("SELECT count(*) FROM job_cards").fetchone()[0]

    app = AppTest.from_file(
        PROJECT_ROOT / "src" / "ui" / "pages" / "job_cards.py", default_timeout=30
    ).run()
    app.button(key="new_job_button").click().run()
    vehicle_select = app.selectbox(key="job_vehicle")
    vehicle_select.select(vehicle_select.options[1]).run()
    app.button(key="FormSubmitter:new_job_form-Open Job Card").click().run()

    assert not app.exception
    assert any(title.value.startswith("PW-JC-") for title in app.title)
    after = conn.execute("SELECT count(*) FROM job_cards").fetchone()[0]
    assert after == before + 1


def test_every_seeded_job_card_detail_loads(ui_database: Path) -> None:
    """Every seeded status and its related detail sections render cleanly."""
    import src.ui.app_context as app_context

    conn = app_context.get_app_connection()
    job_ids = [row[0] for row in conn.execute("SELECT id FROM job_cards ORDER BY id").fetchall()]

    for job_id in job_ids:
        app = AppTest.from_file(
            PROJECT_ROOT / "src" / "ui" / "pages" / "job_cards.py",
            default_timeout=45,
        )
        app.session_state["job_page_mode"] = "detail"
        app.session_state["selected_job_card_id"] = job_id
        app.run()
        assert not app.exception, f"Job Card {job_id} failed to render"

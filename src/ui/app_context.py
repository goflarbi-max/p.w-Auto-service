"""Shared Streamlit application state and safe service execution."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

import duckdb
import streamlit as st

from src.database.connection import ensure_db_exists, get_connection
from src.services.errors import ServiceError
from src.services.users import get_user


T = TypeVar("T")


@st.cache_resource
def get_app_connection() -> duckdb.DuckDBPyConnection:
    """Initialize the schema once and return the reusable application connection."""
    ensure_db_exists()
    return get_connection()


def initialize_state() -> None:
    """Create stable navigation and processing keys."""
    defaults: dict[str, Any] = {
        "selected_job_card_id": None,
        "selected_customer_id": None,
        "selected_vehicle_id": None,
        "selected_appointment_id": None,
        "job_page_mode": "list",
        "processing": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
    if "current_user" not in st.session_state:
        st.session_state.current_user = get_user(get_app_connection())


def connection() -> duckdb.DuckDBPyConnection:
    """Return the initialized application connection."""
    return get_app_connection()


def current_user() -> dict[str, Any]:
    """Return the session's current user."""
    initialize_state()
    return st.session_state.current_user


def run_service(
    operation: Callable[..., T], *args: Any, success: str | None = None, **kwargs: Any
) -> T | None:
    """Run a service and convert expected failures into friendly UI messages."""
    try:
        result = operation(*args, **kwargs)
    except ServiceError as exc:
        st.error(str(exc))
        return None
    except Exception:
        st.error("Something went wrong. Please try again or check the application logs.")
        return None
    if success:
        st.toast(success)
    return result


def rerun_after_write(message: str) -> None:
    """Display success, clear the processing guard, and reload current data."""
    from src.ui.dashboard_cache import clear_dashboard_cache

    clear_dashboard_cache()
    st.session_state.processing = False
    st.toast(message)
    st.rerun()

"""Short-lived Streamlit caching around dashboard service reads."""

from __future__ import annotations

import duckdb
import pandas as pd
import streamlit as st

from src.services import dashboard


@st.cache_data(ttl=60)
def cached_reporting_years(_conn: duckdb.DuckDBPyConnection) -> list[int]:
    return dashboard.reporting_years(_conn)


@st.cache_data(ttl=60)
def cached_kpis(_conn: duckdb.DuckDBPyConnection) -> dict[str, object]:
    return dashboard.dashboard_kpis(_conn)


@st.cache_data(ttl=60)
def cached_jobs_by_status(_conn: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return dashboard.jobs_by_status(_conn)


@st.cache_data(ttl=60)
def cached_jobs_summary(
    _conn: duckdb.DuckDBPyConnection, period: str, year: int | None,
) -> pd.DataFrame:
    return dashboard.jobs_completed_pending(_conn, period, year)  # type: ignore[arg-type]


@st.cache_data(ttl=60)
def cached_revenue(
    _conn: duckdb.DuckDBPyConnection, period: str, year: int | None,
) -> pd.DataFrame:
    return dashboard.revenue(_conn, period, year)  # type: ignore[arg-type]


@st.cache_data(ttl=60)
def cached_top_parts(
    _conn: duckdb.DuckDBPyConnection, year: int | None,
) -> pd.DataFrame:
    return dashboard.top_parts_usage(_conn, year)


@st.cache_data(ttl=60)
def cached_orders(
    _conn: duckdb.DuckDBPyConnection, year: int | None,
) -> dict[str, pd.DataFrame]:
    return dashboard.parts_orders_dashboard(_conn, year)


def clear_dashboard_cache() -> None:
    """Clear all dashboard reads after any application write."""
    for cached_function in (
        cached_reporting_years, cached_kpis, cached_jobs_by_status,
        cached_jobs_summary, cached_revenue, cached_top_parts, cached_orders,
    ):
        cached_function.clear()

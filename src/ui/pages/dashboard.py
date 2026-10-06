"""Admin/Manager operational and financial reporting dashboard."""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from src.services.users import has_permission
from src.ui.app_context import connection, current_user
from src.ui.components import empty_state, format_date, money
from src.ui.dashboard_cache import (
    cached_jobs_by_status,
    cached_jobs_summary,
    cached_kpis,
    cached_orders,
    cached_reporting_years,
    cached_revenue,
    cached_top_parts,
)


ACCENT = "#F2B134"


def _labeled_bars(
    data: pd.DataFrame, *, category: str, value: str,
    horizontal: bool = False, color: str = ACCENT,
) -> None:
    """Render a responsive bar chart with always-visible value labels."""
    if data.empty:
        empty_state("No data for this period.")
        return
    base = alt.Chart(data)
    if horizontal:
        bars = base.mark_bar(color=color).encode(
            x=alt.X(f"{value}:Q", title=None),
            y=alt.Y(f"{category}:N", sort="-x", title=None),
        )
        labels = base.mark_text(align="left", dx=4, color="#F4F4F4").encode(
            x=alt.X(f"{value}:Q"), y=alt.Y(f"{category}:N", sort="-x"),
            text=alt.Text(f"{value}:Q", format=",.2f"),
        )
    else:
        bars = base.mark_bar(color=color).encode(
            x=alt.X(f"{category}:N", title=None), y=alt.Y(f"{value}:Q", title=None)
        )
        labels = base.mark_text(dy=-6, color="#F4F4F4").encode(
            x=alt.X(f"{category}:N"), y=alt.Y(f"{value}:Q"),
            text=alt.Text(f"{value}:Q", format=",.0f"),
        )
    st.altair_chart((bars + labels).properties(height=280), width="stretch")


def _table(data: pd.DataFrame) -> None:
    if not data.empty:
        st.dataframe(data, hide_index=True, width="stretch")


def render() -> None:
    """Render the full Phase 4 dashboard."""
    user = current_user()
    if not has_permission(user, "revenue_reports"):
        st.error("Dashboard reports are available to Admin and Manager roles only.")
        return
    conn = connection()
    first_name = str(user.get("name") or "Admin").split()[0]
    st.title(f"Welcome {first_name},")
    st.caption("P.W AUTOMOBILE - GJ-096-6186, Weija SCC")
    years = cached_reporting_years(conn)
    year = st.selectbox("Reporting year", years or [None], format_func=lambda value: str(value) if value else "All years")
    kpis = cached_kpis(conn)
    first, second = st.columns(2)
    first.metric("Cars In-House", kpis["cars_in_house"], border=True)
    second.metric("Awaiting Approval", kpis["awaiting_approval"], border=True)
    third, fourth = st.columns(2)
    third.metric("Parts To Reorder", kpis["parts_to_reorder"], border=True)
    fourth.metric(
        "Unpaid Invoices", f"{kpis['unpaid_invoice_count']} · {money(kpis['outstanding_total'])}",
        border=True,
    )

    st.header("Jobs by Status")
    statuses = cached_jobs_by_status(conn)
    _labeled_bars(statuses, category="status", value="job_count", horizontal=True)
    _table(statuses)

    st.header("Jobs Completed vs Pending")
    jobs_period = st.radio("Jobs period", ["month", "year"], horizontal=True)
    jobs = cached_jobs_summary(conn, jobs_period, year)
    if jobs.empty:
        empty_state("No job data for this period.")
    else:
        category = "period" if jobs_period == "month" else "year"
        long_jobs = jobs[[category, "completed_jobs", "pending_jobs"]].melt(
            id_vars=[category], var_name="series", value_name="jobs"
        )
        chart = alt.Chart(long_jobs).mark_bar().encode(
            x=alt.X(f"{category}:N", title=None), y=alt.Y("jobs:Q", title="Jobs"),
            color=alt.Color("series:N", title=None), xOffset="series:N",
        )
        labels = alt.Chart(long_jobs).mark_text(dy=-5, color="#F4F4F4").encode(
            x=alt.X(f"{category}:N"), y="jobs:Q", xOffset="series:N", text="jobs:Q"
        )
        st.altair_chart((chart + labels).properties(height=280), width="stretch")
        _table(jobs)

    st.header("Service Revenue")
    revenue_period = st.radio("Revenue period", ["month", "year"], horizontal=True)
    revenue = cached_revenue(conn, revenue_period, year)
    if revenue.empty:
        empty_state("No revenue data for this period.")
    else:
        total_billed = revenue["invoiced_total"].sum()
        total_paid = revenue["paid_total"].sum()
        st.write(f"Billed: **{money(total_billed)}** · Collected: **{money(total_paid)}**")
        category = "period" if revenue_period == "month" else "year"
        long_revenue = revenue[[category, "invoiced_total", "paid_total"]].melt(
            id_vars=[category], var_name="series", value_name="amount"
        )
        chart = alt.Chart(long_revenue).mark_bar().encode(
            x=alt.X(f"{category}:N", title=None), y=alt.Y("amount:Q", title="GHS"),
            color=alt.Color("series:N", title=None), xOffset="series:N",
        )
        st.altair_chart(chart.properties(height=300), width="stretch")
        _table(revenue)

    st.header("Top 10 Parts Used")
    usage = cached_top_parts(conn, year)
    _labeled_bars(usage, category="part_name", value="quantity_used", horizontal=True)
    _table(usage)

    st.header("Parts Ordered")
    orders = cached_orders(conn, year)
    _labeled_bars(orders["by_status"], category="status", value="order_count")
    _table(orders["by_status"])
    st.subheader("Recent Orders")
    if orders["recent"].empty:
        empty_state("No parts orders for this period.")
    else:
        for item in orders["recent"].to_dict("records"):
            with st.container(border=True):
                st.markdown(f"**{item['part_name']}**")
                st.write(f"{item['status']} · Ordered {item['quantity_ordered']} · Received {item['quantity_received']}")
                st.caption(format_date(item["ordered_date"]))


render()

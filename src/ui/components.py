"""Reusable mobile-first Streamlit presentation components."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from html import escape
from typing import Any

import streamlit as st


STATUS_COLORS = {
    "Received": "#4C8BF5", "Diagnosed": "#8E7CC3", "Estimate Sent": "#E69138",
    "Approved": "#3D9970", "In Progress": "#00A6A6", "Quality Check": "#7F8C8D",
    "Ready for Delivery": "#2ECC71", "Delivered": "#68737D", "Declined": "#C0392B",
    "Cancelled": "#922B21", "Pending": "#E69138", "Sent": "#3D9970",
    "Failed": "#C0392B", "Unpaid": "#C0392B", "Partial": "#E69138", "Paid": "#3D9970",
}


def money(value: Decimal | int | str | None) -> str:
    """Format a monetary value consistently in Ghana cedis."""
    amount = Decimal(str(value or 0))
    return f"GHS {amount:,.2f}"


def format_date(value: date | datetime | None) -> str:
    """Format dates as DD Mon YYYY."""
    if value is None:
        return "—"
    return value.strftime("%d %b %Y")


def status_badge(status: str) -> None:
    """Render an accessible status label with consistent color."""
    color = STATUS_COLORS.get(status, "#68737D")
    st.markdown(
        f'<span style="display:inline-block;padding:.25rem .65rem;border-radius:999px;'
        f'background:{color};color:white;font-weight:650;font-size:.85rem">{escape(status)}</span>',
        unsafe_allow_html=True,
    )


def job_card_summary_card(job: dict[str, Any], *, key: str) -> bool:
    """Render one compact job summary and return whether Open was tapped."""
    with st.container(border=True):
        st.markdown(f"#### {escape(str(job['job_no']))}")
        st.caption(f"{job.get('reg_number', '—')} · {job.get('brand', '')} {job.get('model', '')}")
        st.write(job.get("customer_name", ""))
        status_badge(str(job["status"]))
        st.caption(f"Expected: {format_date(job.get('expected_delivery'))}")
        return st.button("Open", key=key, use_container_width=True)


def part_row(part: dict[str, Any], *, key: str, action_label: str = "Select") -> bool:
    """Render a compact inventory card and optional action."""
    with st.container(border=True):
        st.markdown(f"**{escape(str(part['part_name']))}**")
        st.caption(str(part.get("part_number") or "No part number"))
        st.write(f"Stock: {part.get('quantity', 0)} · {money(part.get('selling_price'))}")
        if part.get("needs_ordering") or part.get("quantity", 0) < part.get("reorder_level", 0):
            st.warning("Low stock / needs ordering")
        return st.button(action_label, key=key, use_container_width=True)


def confirm_action(label: str, *, key: str, warning: str) -> bool:
    """Require a second explicit tap before a destructive workflow action."""
    confirm_key = f"confirm_{key}"
    if not st.session_state.get(confirm_key, False):
        if st.button(label, key=key, use_container_width=True):
            st.session_state[confirm_key] = True
            st.rerun()
        return False
    st.warning(warning)
    left, right = st.columns(2)
    if left.button("Confirm", key=f"{key}_yes", type="primary", use_container_width=True):
        st.session_state[confirm_key] = False
        return True
    if right.button("Keep", key=f"{key}_no", use_container_width=True):
        st.session_state[confirm_key] = False
        st.rerun()
    return False


def show_error(message: str) -> None:
    """Show a consistent friendly error message."""
    st.error(message)


def empty_state(message: str) -> None:
    """Render a quiet empty-list message."""
    st.info(message)

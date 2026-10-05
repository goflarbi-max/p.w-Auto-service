"""Service-reminder review and mock sending page."""

from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from src.services.reminders import list_reminders, process_due_reminders
from src.ui.app_context import connection, current_user, rerun_after_write, run_service
from src.ui.components import empty_state, format_date, status_badge


def render() -> None:
    st.title("Service Reminders")
    st.warning("SMS TEST MODE — no real messages will be sent.")
    days = st.selectbox("Due within", [0, 7, 14, 30], index=1, format_func=lambda value: f"{value} days")
    status = st.selectbox("Status", ["All", "Pending", "Sent", "Failed", "Cancelled"])
    if st.button("Send Due Reminders Now", type="primary", use_container_width=True):
        result = run_service(
            process_due_reminders, connection(), days_ahead=days,
            user_id=current_user()["id"],
        )
        if result is not None:
            rerun_after_write(f"Processed {len(result)} reminder(s) in test mode")
    reminders = run_service(
        list_reminders, connection(), status=None if status == "All" else status,
        date_to=date.today() + timedelta(days=days),
    ) or []
    if not reminders:
        empty_state("No reminders match this view.")
    for reminder in reminders:
        with st.container(border=True):
            st.markdown(f"**{reminder['customer_name']}**")
            st.write(f"{reminder['brand']} {reminder['model']} · {reminder['reg_number']}")
            st.caption(f"Next service: {format_date(reminder['next_service_date'])}")
            status_badge(reminder["status"])


render()

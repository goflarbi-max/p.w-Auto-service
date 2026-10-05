"""Operational home page without dashboard charts."""

from __future__ import annotations

from datetime import date

import streamlit as st

from src.services.appointments import list_appointments
from src.services.dashboard import cars_in_house, low_stock_count
from src.services.job_cards import list_due_deliveries, list_job_cards
from src.services.reminders import get_due_reminders
from src.ui.app_context import connection, run_service
from src.ui.components import empty_state, format_date, status_badge


def render() -> None:
    """Render the simple operational home screen."""
    st.title("Workshop Home")
    conn = connection()
    in_house = run_service(cars_in_house, conn)
    awaiting = run_service(list_job_cards, conn, status="Estimate Sent") or []
    reorder = run_service(low_stock_count, conn)
    reminders = run_service(get_due_reminders, conn, days_ahead=0) or []

    for label, value in (
        ("Cars In-House", 0 if in_house is None else len(in_house)),
        ("Jobs Awaiting Approval", len(awaiting)),
        ("Parts To Reorder", reorder or 0),
        ("Reminders Due", len(reminders)),
    ):
        with st.container(border=True):
            st.metric(label, value)

    if st.button("New Job Card", key="home_new_job", type="primary", use_container_width=True):
        st.session_state.job_page_mode = "new"
        st.switch_page("src/ui/pages/job_cards.py")
    if st.button("New Appointment", key="home_new_appointment", use_container_width=True):
        st.session_state.appointment_new = True
        st.switch_page("src/ui/pages/appointments.py")
    if st.button("Add Part", key="home_add_part", use_container_width=True):
        st.session_state.part_add = True
        st.switch_page("src/ui/pages/parts.py")

    st.subheader("Today's Appointments")
    appointments = run_service(
        list_appointments, conn, date_from=date.today(), date_to=date.today()
    ) or []
    if not appointments:
        empty_state("No appointments today.")
    for item in appointments:
        with st.container(border=True):
            st.markdown(f"**{item['customer_name']}**")
            st.write(f"{item['brand']} {item['model']} · {item['reg_number']}")
            st.caption(item["source"])
            status_badge(item["status"])

    st.subheader("Due or Overdue Deliveries")
    deliveries = run_service(list_due_deliveries, conn) or []
    if not deliveries:
        empty_state("No deliveries are due or overdue.")
    for job in deliveries:
        with st.container(border=True):
            st.markdown(f"**{job['job_no']}**")
            st.write(f"{job['reg_number']} · {job['brand']} {job['model']}")
            st.caption(f"Expected {format_date(job['expected_delivery'])}")
            status_badge(job["status"])


render()

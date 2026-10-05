"""Appointment scheduling and arrival conversion page."""

from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from src.services.appointments import (
    cancel_appointment,
    convert_to_job_card,
    create_appointment,
    list_appointments,
)
from src.services.customers import search_customers
from src.services.vehicles import list_customer_vehicles
from src.ui.app_context import connection, current_user, rerun_after_write, run_service
from src.ui.components import confirm_action, empty_state, format_date, status_badge


def _new_appointment() -> None:
    st.subheader("New Appointment")
    customers = run_service(search_customers, connection(), "") or []
    if not customers:
        st.warning("Add a customer before creating an appointment.")
        return
    labels = {f"{item['name']} - {item['phone']}": item for item in customers}
    customer = labels[st.selectbox("Customer", list(labels), key="appointment_customer")]
    vehicles = run_service(list_customer_vehicles, connection(), customer["id"]) or []
    if not vehicles:
        st.warning("This customer has no vehicles. Add one on Customers & Vehicles.")
        return
    vehicle_labels = {f"{item['reg_number']} - {item['brand']} {item['model']}": item for item in vehicles}
    vehicle = vehicle_labels[st.selectbox("Vehicle", list(vehicle_labels), key="appointment_vehicle")]
    with st.form("appointment_form"):
        source = st.selectbox("Source", ["Call", "WhatsApp", "Walk-in"])
        appointment_date = st.date_input("Date", value=date.today())
        notes = st.text_area("Notes", value="Workshop appointment")
        submitted = st.form_submit_button("Create Appointment", type="primary", use_container_width=True)
    if submitted:
        result = run_service(
            create_appointment, connection(), source, appointment_date, customer["id"], vehicle["id"],
            notes=notes or None, user_id=current_user()["id"],
        )
        if result:
            st.session_state.appointment_new = False
            rerun_after_write("Appointment created")


def render() -> None:
    st.title("Appointments")
    if st.button("New Appointment", type="primary", use_container_width=True):
        st.session_state.appointment_new = not st.session_state.get("appointment_new", False)
    if st.session_state.get("appointment_new", False):
        _new_appointment()
        st.divider()
    start = st.date_input("From", value=date.today(), key="appointments_from")
    end = st.date_input("To", value=date.today() + timedelta(days=7), key="appointments_to")
    source = st.selectbox("Source", ["All", "Call", "WhatsApp", "Walk-in"])
    status = st.selectbox("Status", ["All", "Booked", "Confirmed", "Arrived", "Completed", "Cancelled", "No Show"])
    appointments = run_service(
        list_appointments, connection(), date_from=start, date_to=end,
        source=None if source == "All" else source, status=None if status == "All" else status,
    ) or []
    if not appointments:
        empty_state("No appointments in this date range.")
    current_day = None
    for item in appointments:
        if item["appointment_date"] != current_day:
            current_day = item["appointment_date"]
            st.subheader(format_date(current_day))
        with st.container(border=True):
            st.markdown(f"**{item['customer_name']}**")
            st.write(f"{item['brand']} {item['model']} · {item['reg_number']}")
            st.caption(f"{item['source']} · {item.get('notes') or 'No notes'}")
            status_badge(item["status"])
            if item["status"] not in {"Completed", "Cancelled", "No Show"}:
                if st.button("Arrived → Open Job Card", key=f"convert_appointment_{item['id']}", use_container_width=True):
                    result = run_service(
                        convert_to_job_card, connection(), item["id"], user_id=current_user()["id"]
                    )
                    if result:
                        st.session_state.selected_job_card_id = result["id"]
                        st.session_state.job_page_mode = "detail"
                        st.switch_page("src/ui/pages/job_cards.py")
                if confirm_action(
                    "Cancel", key=f"cancel_appointment_{item['id']}",
                    warning="Cancel this appointment?",
                ):
                    if run_service(
                        cancel_appointment, connection(), item["id"], user_id=current_user()["id"]
                    ):
                        rerun_after_write("Appointment cancelled")


render()

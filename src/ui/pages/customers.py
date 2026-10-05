"""Customer, vehicle, and service-history page."""

from __future__ import annotations

from datetime import date

import streamlit as st

from src.services.customers import create_customer, get_customer, search_customers, update_customer
from src.services.vehicles import (
    create_vehicle,
    get_brand_model_suggestions,
    get_vehicle,
    get_vehicle_history,
    list_customer_vehicles,
    update_vehicle,
)
from src.ui.app_context import connection, current_user, rerun_after_write, run_service
from src.ui.components import empty_state, format_date, money, status_badge


def _customer_detail(customer_id: int) -> None:
    conn = connection()
    customer = run_service(get_customer, conn, customer_id)
    if customer is None:
        return
    if st.button("Back to Customers", use_container_width=True):
        st.session_state.selected_customer_id = None
        st.session_state.selected_vehicle_id = None
        st.rerun()
    st.title(customer["name"])
    with st.form(f"customer_edit_{customer_id}"):
        name = st.text_input("Name", value=customer["name"])
        phone = st.text_input("Phone", value=customer["phone"])
        email = st.text_input("Email", value=customer["email"] or "")
        address = st.text_area("Address", value=customer["address"] or "")
        if st.form_submit_button("Save Customer", use_container_width=True):
            if run_service(
                update_customer, conn, customer_id, name=name, phone=phone,
                email=email or None, address=address or None, user_id=current_user()["id"],
            ):
                rerun_after_write("Customer updated")

    st.subheader("Vehicles")
    vehicles = run_service(list_customer_vehicles, conn, customer_id) or []
    for vehicle in vehicles:
        with st.container(border=True):
            st.markdown(f"**{vehicle['reg_number']}**")
            st.write(f"{vehicle['brand']} {vehicle['model']} · {vehicle.get('year') or 'Year unknown'}")
            if st.button("Service History", key=f"history_{vehicle['id']}", use_container_width=True):
                st.session_state.selected_vehicle_id = vehicle["id"]
                st.rerun()

    if st.session_state.get("selected_vehicle_id"):
        history = run_service(
            get_vehicle_history, conn, vehicle_id=st.session_state.selected_vehicle_id
        )
        if history:
            st.subheader(f"History · {history['vehicle']['reg_number']}")
            if not history["job_cards"]:
                empty_state("No service history yet.")
            for job in history["job_cards"]:
                with st.container(border=True):
                    st.markdown(f"**{job['job_no']}** · {format_date(job['date_received'])}")
                    status_badge(job["status"])
                    if job.get("invoice_total") is not None:
                        st.caption(f"Invoice: {money(job['invoice_total'])} · {job['payment_status']}")

    with st.expander("Add Vehicle"):
        suggestions = run_service(get_brand_model_suggestions, conn) or {"brands": [], "models": []}
        brand = st.selectbox("Brand", suggestions["brands"], accept_new_options=True)
        model = st.selectbox("Model", suggestions["models"], accept_new_options=True)
        year = st.number_input("Year", 1886, 2100, date.today().year)
        vin = st.text_input("VIN (optional)")
        registration = st.text_input("Registration number")
        if st.button("Add Vehicle", type="primary", use_container_width=True):
            if run_service(
                create_vehicle, conn, customer_id, brand, model, registration,
                year=int(year), vin=vin or None, user_id=current_user()["id"],
            ):
                rerun_after_write("Vehicle added")


def render() -> None:
    st.title("Customers & Vehicles")
    selected = st.session_state.get("selected_customer_id")
    if selected is None and st.session_state.get("selected_vehicle_id"):
        vehicle = run_service(get_vehicle, connection(), st.session_state.selected_vehicle_id)
        if vehicle:
            selected = vehicle["customer_id"]
            st.session_state.selected_customer_id = selected
    if selected:
        _customer_detail(selected)
        return
    query = st.text_input("Search customers", placeholder="Name or phone")
    customers = run_service(search_customers, connection(), query) or []
    if not customers:
        empty_state("No customers found.")
    for customer in customers:
        with st.container(border=True):
            st.markdown(f"**{customer['name']}**")
            st.write(customer["phone"])
            st.caption(customer.get("email") or "No email")
            if st.button("Open", key=f"customer_open_{customer['id']}", use_container_width=True):
                st.session_state.selected_customer_id = customer["id"]
                st.rerun()
    with st.expander("Add New Customer"):
        name = st.text_input("Name", key="customer_add_name")
        phone = st.text_input("Phone", key="customer_add_phone")
        email = st.text_input("Email", key="customer_add_email")
        address = st.text_area("Address", key="customer_add_address")
        if st.button("Create Customer", type="primary", use_container_width=True):
            result = run_service(
                create_customer, connection(), name, phone, email or None, address or None,
                user_id=current_user()["id"],
            )
            if result:
                st.session_state.selected_customer_id = result["id"]
                rerun_after_write("Customer ready")


render()

"""Job-card list, creation, and detail workflows."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd
import streamlit as st

from src.config import PAYMENT_METHODS
from src.documents.invoice_pdf import (
    estimate_filename,
    generate_estimate_pdf,
    generate_invoice_pdf,
    invoice_filename,
)
from src.documents.job_card_pdf import (
    blank_job_card_filename,
    generate_blank_job_card,
    generate_job_card_pdf,
    job_card_filename,
)
from src.services.appointments import convert_to_job_card, list_appointments
from src.services.customers import search_customers
from src.services.estimates import (
    approve_estimate,
    create_estimate,
    decline_estimate,
    get_estimate_full,
    revise_estimate,
    send_estimate,
)
from src.services.invoices import create_invoice, get_invoice_full, record_payment
from src.services.job_cards import (
    change_status,
    get_allowed_status_transitions,
    get_job_card_full,
    get_job_status_history,
    list_job_cards,
    list_job_types,
    open_job_card,
    update_job_card,
)
from src.services.parts import add_part, record_part_used, remove_part_used, search_parts
from src.services.users import has_permission
from src.services.vehicles import get_brand_model_suggestions, list_customer_vehicles
from src.ui.app_context import connection, current_user, initialize_state, rerun_after_write, run_service
from src.ui.components import (
    confirm_action,
    empty_state,
    format_date,
    job_card_summary_card,
    money,
    status_badge,
)


def _open_detail(job_id: int) -> None:
    st.session_state.selected_job_card_id = job_id
    st.session_state.job_page_mode = "detail"
    st.rerun()


def _render_list() -> None:
    st.title("Job Cards")
    if st.button("New Job Card", key="new_job_button", type="primary", use_container_width=True):
        st.session_state.job_page_mode = "new"
        st.rerun()
    blank_pdf = run_service(generate_blank_job_card)
    if blank_pdf:
        st.download_button(
            "Print blank job card", data=blank_pdf, file_name=blank_job_card_filename(),
            mime="application/pdf", use_container_width=True,
        )
    query = st.text_input("Search", placeholder="Job no, registration, VIN or customer")
    status = st.selectbox(
        "Status", ["All", "Received", "Diagnosed", "Estimate Sent", "Approved", "In Progress",
                   "Quality Check", "Ready for Delivery", "Delivered", "Declined", "Cancelled"],
    )
    jobs = run_service(
        list_job_cards, connection(), status=None if status == "All" else status,
        query=query or None,
    ) or []
    if not jobs:
        empty_state("No job cards match these filters.")
    for job in jobs:
        if job_card_summary_card(job, key=f"open_job_{job['id']}"):
            _open_detail(job["id"])


def _render_new() -> None:
    st.title("New Job Card")
    if st.button("Back to Job Cards", use_container_width=True):
        st.session_state.job_page_mode = "list"
        st.rerun()
    conn = connection()

    appointments = run_service(
        list_appointments, conn, date_from=date.today(), status="Arrived"
    ) or []
    if appointments:
        st.subheader("From an arrived appointment")
        appointment_labels = {
            f"{a['appointment_date']} - {a['customer_name']} - {a['reg_number']}": a["id"]
            for a in appointments
        }
        appointment_label = st.selectbox("Appointment", list(appointment_labels), key="job_appointment")
        if st.button("Open Job from Appointment", use_container_width=True):
            result = run_service(
                convert_to_job_card, conn, appointment_labels[appointment_label], user_id=current_user()["id"]
            )
            if result:
                st.session_state.selected_job_card_id = result["id"]
                st.session_state.job_page_mode = "detail"
                rerun_after_write(f"Created {result['job_no']}")

    st.divider()
    customer_mode = st.radio("Customer", ["Existing customer", "New customer"], horizontal=True)
    selected_customer = None
    customer_payload = None
    if customer_mode == "Existing customer":
        customer_query = st.text_input("Find customer", key="job_customer_search")
        customers = run_service(search_customers, conn, customer_query) or []
        if not customers:
            st.info("No customers found. Choose New customer.")
            return
        labels = {f"{c['name']} - {c['phone']}": c for c in customers}
        selected_customer = labels[st.selectbox("Customer record", list(labels), key="job_customer")]
    else:
        customer_payload = {
            "name": st.text_input("Customer name", key="new_customer_name"),
            "phone": st.text_input("Phone", key="new_customer_phone"),
            "email": st.text_input("Email", key="new_customer_email") or None,
            "address": st.text_input("Address", key="new_customer_address") or None,
        }

    vehicle_mode = "New vehicle"
    vehicles = []
    if selected_customer:
        vehicles = run_service(list_customer_vehicles, conn, selected_customer["id"]) or []
        options = ["New vehicle"] + [f"{v['reg_number']} - {v['brand']} {v['model']}" for v in vehicles]
        vehicle_mode = st.selectbox("Vehicle", options, key="job_vehicle")

    vehicle_payload = None
    selected_vehicle = None
    if vehicle_mode == "New vehicle":
        suggestions = run_service(get_brand_model_suggestions, conn) or {"brands": [], "models": []}
        vehicle_payload = {
            "brand": st.selectbox("Brand", suggestions["brands"], accept_new_options=True, key="new_vehicle_brand"),
            "model": st.selectbox("Model", suggestions["models"], accept_new_options=True, key="new_vehicle_model"),
            "year": st.number_input("Year", min_value=1886, max_value=2100, value=date.today().year),
            "vin": st.text_input("VIN (optional)", key="new_vehicle_vin") or None,
            "reg_number": st.text_input("Registration number", key="new_vehicle_reg"),
        }
    else:
        selected_vehicle = vehicles[options.index(vehicle_mode) - 1]

    job_types = run_service(list_job_types, conn) or []
    with st.form("new_job_form"):
        mileage = st.number_input("Mileage", min_value=0, step=1, key="new_job_mileage")
        complaint = st.text_area("Customer complaint", value="Workshop inspection", key="new_job_complaint")
        condition = st.text_area("Current condition", key="new_job_condition")
        inspection = st.text_area("Inspection notes", key="new_job_inspection")
        type_names = st.multiselect("Job types", [item["name"] for item in job_types], key="new_job_types")
        received = st.date_input("Date received", value=date.today(), key="new_job_received")
        expected = st.date_input("Expected delivery", value=date.today(), key="new_job_expected")
        submitted = st.form_submit_button(
            "Open Job Card", type="primary", use_container_width=True,
            disabled=st.session_state.processing,
        )
    if submitted:
        st.session_state.processing = True
        type_ids = [item["id"] for item in job_types if item["name"] in type_names]
        kwargs = dict(
            customer_complaint=complaint, mileage=int(mileage), current_condition=condition or None,
            inspection_notes=inspection or None, job_type_ids=type_ids, date_received=received,
            expected_delivery=expected, user_id=current_user()["id"],
        )
        if selected_customer and selected_vehicle:
            kwargs.update(customer_id=selected_customer["id"], vehicle_id=selected_vehicle["id"])
        else:
            if selected_customer:
                customer_payload = selected_customer
            kwargs.update(customer=customer_payload, vehicle=vehicle_payload)
        result = run_service(open_job_card, conn, **kwargs)
        st.session_state.processing = False
        if result:
            st.session_state.selected_job_card_id = result["id"]
            st.session_state.job_page_mode = "detail"
            rerun_after_write(f"Created {result['job_no']}")


def _render_estimate(job: dict) -> None:
    conn, user = connection(), current_user()
    estimates = job["estimates"]
    latest = get_estimate_full(conn, estimates[0]["id"]) if estimates else None
    if latest:
        status_badge(latest["status"])
        st.write(f"Version {latest['version']} · {money(latest['totals']['total'])}")
        for item in latest["items"]:
            st.write(f"{item['item_type']}: {item['description']} — {item['quantity']} × {money(item['unit_price'])}")
        estimate_pdf = run_service(generate_estimate_pdf, conn, latest["id"])
        if estimate_pdf:
            st.download_button(
                "Download Estimate PDF", data=estimate_pdf,
                file_name=estimate_filename(job["job_no"], latest["version"]),
                mime="application/pdf", use_container_width=True,
            )
    rows = pd.DataFrame([
        {"item_type": "Labour", "description": "Workshop labour", "part_id": None,
         "quantity": 1.0, "unit_price": 0.0}
    ])
    edited = st.data_editor(
        rows, num_rows="dynamic", use_container_width=True, key=f"estimate_editor_{job['id']}",
        column_config={"item_type": st.column_config.SelectboxColumn(options=["Labour", "Part"])},
    )
    items = [
        {"item_type": row["item_type"], "description": row["description"],
         "part_id": None if pd.isna(row["part_id"]) else int(row["part_id"]),
         "quantity": Decimal(str(row["quantity"])), "unit_price": Decimal(str(row["unit_price"]))}
        for _, row in edited.iterrows()
    ]
    if latest is None and st.button("Save Estimate", use_container_width=True):
        if run_service(create_estimate, conn, job["id"], items, user_id=user["id"]):
            rerun_after_write("Estimate saved")
    elif latest and latest["status"] != "Approved" and st.button("Save Revision", use_container_width=True):
        if run_service(revise_estimate, conn, job["id"], items, user_id=user["id"]):
            rerun_after_write("Estimate revision saved")
    if latest and latest["status"] == "Draft" and st.button("Send Estimate", type="primary", use_container_width=True):
        if run_service(send_estimate, conn, latest["id"], user_id=user["id"]):
            rerun_after_write("Estimate sent")
    if latest and latest["status"] == "Sent":
        if st.button("Approve Estimate", type="primary", use_container_width=True):
            if run_service(approve_estimate, conn, latest["id"], user_id=user["id"]):
                rerun_after_write("Estimate approved; job is In Progress")
        if confirm_action("Decline Estimate", key=f"decline_est_{latest['id']}", warning="Close this job as Declined?"):
            if run_service(decline_estimate, conn, latest["id"], user_id=user["id"]):
                rerun_after_write("Estimate declined")
    if len(estimates) > 1:
        with st.expander("Earlier versions"):
            for estimate in estimates[1:]:
                st.write(f"Version {estimate['version']} · {estimate['status']}")


def _render_parts(job: dict) -> None:
    conn = connection()
    for usage in job["parts_used"]:
        with st.container(border=True):
            st.write(f"**{usage['part_name']}**")
            st.caption(f"{usage['quantity']} × {money(usage['unit_price'])}")
            if job["status"] != "Delivered" and st.button("Remove", key=f"remove_usage_{usage['id']}"):
                if run_service(remove_part_used, conn, usage["id"], user_id=current_user()["id"]):
                    rerun_after_write("Part returned to stock")
    query = st.text_input("Find part", key=f"usage_search_{job['id']}")
    parts = run_service(search_parts, conn, query) or []
    if parts:
        labels = {f"{p['part_name']} - stock {p['quantity']}": p for p in parts}
        part = labels[st.selectbox("Part", list(labels), key=f"usage_part_{job['id']}")]
        quantity = st.number_input("Quantity", min_value=0.01, value=1.0, step=0.25)
        price = st.number_input("Unit price", min_value=0.0, value=float(part["selling_price"]), step=1.0)
        if st.button("Record Part Used", type="primary", use_container_width=True):
            result = run_service(
                record_part_used, conn, job["id"], part["id"], Decimal(str(quantity)),
                Decimal(str(price)), user_id=current_user()["id"],
            )
            if result:
                rerun_after_write("Part usage recorded")
    with st.expander("Part not in the list? Add it"):
        name = st.text_input("Part name", key=f"inline_part_name_{job['id']}")
        price = st.number_input("Selling price", min_value=0.0, key=f"inline_part_price_{job['id']}")
        if st.button("Add Part", key=f"inline_add_part_{job['id']}", use_container_width=True):
            if run_service(add_part, conn, name, Decimal(str(price)), user_id=current_user()["id"]):
                rerun_after_write("Part added; search for it above to record usage")


def _render_invoice(job: dict) -> None:
    conn, user = connection(), current_user()
    if not has_permission(user, "invoices"):
        st.info("Invoice access is not available for your role.")
        return
    invoice = job["invoice"]
    if invoice is None:
        if st.button("Create Invoice", type="primary", use_container_width=True):
            if run_service(create_invoice, conn, job["id"], user_id=user["id"]):
                rerun_after_write("Invoice created")
        return
    full = run_service(get_invoice_full, conn, invoice["id"])
    if full is None:
        return
    st.subheader(full["invoice_no"])
    status_badge(full["payment_status"])
    st.write(f"Total: **{money(full['total'])}**")
    st.write(f"Paid: {money(full['amount_paid'])}")
    for payment in full["payments"]:
        st.caption(f"{payment['method']} · {money(payment['amount'])}")
    if full["payment_status"] != "Paid" and has_permission(user, "payments"):
        outstanding = full["total"] - full["amount_paid"]
        amount = st.number_input("Payment amount", min_value=0.01, max_value=float(outstanding), value=float(outstanding))
        method = st.selectbox("Payment method", PAYMENT_METHODS)
        if st.button("Record Payment", type="primary", use_container_width=True):
            if run_service(record_payment, conn, full["id"], Decimal(str(amount)), method, user_id=user["id"]):
                rerun_after_write("Payment recorded")
    invoice_pdf = run_service(generate_invoice_pdf, conn, full["id"])
    if invoice_pdf:
        st.download_button(
            "Download Invoice PDF", data=invoice_pdf,
            file_name=invoice_filename(full["invoice_no"]), mime="application/pdf",
            use_container_width=True,
        )


def _render_detail() -> None:
    job_id = st.session_state.selected_job_card_id
    if job_id is None:
        st.session_state.job_page_mode = "list"
        st.rerun()
    job = run_service(get_job_card_full, connection(), job_id)
    if job is None:
        return
    if st.button("Back to Job Cards", use_container_width=True):
        st.session_state.job_page_mode = "list"
        st.rerun()
    st.title(job["job_no"])
    st.write(f"{job['reg_number']} · {job['brand']} {job['model']} · {job['customer_name']}")
    status_badge(job["status"])
    allowed = run_service(
        get_allowed_status_transitions, connection(), job["id"], current_user()["id"]
    ) or []
    for next_status in allowed:
        if next_status in {"Cancelled", "Declined"}:
            confirmed = confirm_action(
                next_status, key=f"status_{job['id']}_{next_status}",
                warning=f"Change this job to {next_status}?",
            )
            clicked = confirmed
        else:
            clicked = st.button(next_status, key=f"status_{job['id']}_{next_status}", use_container_width=True)
        if clicked and run_service(
            change_status, connection(), job["id"], next_status, current_user()["id"]
        ):
            rerun_after_write(f"Job moved to {next_status}")

    overview, diagnosis, estimate, parts, invoice, history = st.tabs(
        ["Overview", "Diagnosis", "Estimate", "Parts Used", "Invoice", "History"]
    )
    with overview:
        job_pdf = run_service(generate_job_card_pdf, connection(), job["id"])
        if job_pdf:
            st.download_button(
                "Download Job Card PDF", data=job_pdf,
                file_name=job_card_filename(job["job_no"]), mime="application/pdf",
                use_container_width=True,
            )
        with st.form(f"overview_{job['id']}"):
            complaint = st.text_area("Complaint", value=job["customer_complaint"])
            condition = st.text_area("Current condition", value=job["current_condition"] or "")
            mileage = st.number_input("Mileage", min_value=0, value=job["mileage"] or 0)
            expected = st.date_input("Expected delivery", value=job["expected_delivery"] or date.today())
            if st.form_submit_button("Save Overview", use_container_width=True):
                if run_service(
                    update_job_card, connection(), job["id"], customer_complaint=complaint,
                    current_condition=condition, mileage=int(mileage), expected_delivery=expected,
                    user_id=current_user()["id"],
                ):
                    rerun_after_write("Job card updated")
    with diagnosis:
        notes = st.text_area("Inspection notes", value=job["inspection_notes"] or "")
        finding = st.text_area("Diagnosis", value=job["diagnosis"] or "")
        if st.button("Save Diagnosis", use_container_width=True):
            if run_service(
                update_job_card, connection(), job["id"], inspection_notes=notes,
                diagnosis=finding, user_id=current_user()["id"],
            ):
                rerun_after_write("Diagnosis saved")
    with estimate:
        _render_estimate(job)
    with parts:
        _render_parts(job)
    with invoice:
        _render_invoice(job)
    with history:
        timeline = run_service(get_job_status_history, connection(), job["id"]) or []
        if not timeline:
            empty_state("No recorded status changes yet.")
        for entry in timeline:
            status_badge(entry["status"])
            st.caption(f"{entry['changed_at']:%d %b %Y %H:%M} · {entry.get('changed_by_name') or 'System'}")
        if st.button("Open vehicle service history", use_container_width=True):
            st.session_state.selected_customer_id = job["customer_id"]
            st.session_state.selected_vehicle_id = job["vehicle_id"]
            st.switch_page("src/ui/pages/customers.py")


initialize_state()
mode = st.session_state.get("job_page_mode", "list")
if mode == "new":
    _render_new()
elif mode == "detail":
    _render_detail()
else:
    _render_list()

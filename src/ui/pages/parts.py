"""Parts catalogue, stock, reorder, and ordering page."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import streamlit as st

from src.services.parts import (
    add_part,
    adjust_stock,
    create_order,
    flag_needs_ordering,
    get_reorder_list,
    list_orders,
    receive_order,
    search_parts,
    update_part,
)
from src.services.users import has_permission
from src.ui.app_context import connection, current_user, rerun_after_write, run_service
from src.ui.components import empty_state, format_date, money, part_row, status_badge


def _add_part_form() -> None:
    with st.form("add_part_form"):
        name = st.text_input("Part name")
        selling = st.number_input("Selling price", min_value=0.0)
        number = st.text_input("Part number (optional)")
        brand = st.text_input("Brand (optional)")
        part_type = st.selectbox("Type", ["Aftermarket", "Genuine"])
        quantity = st.number_input("Opening quantity", min_value=0.0)
        cost = st.number_input("Cost price", min_value=0.0)
        supplier = st.text_input("Supplier (optional)")
        reorder = st.number_input("Reorder level", min_value=0.0)
        submitted = st.form_submit_button("Add Part", type="primary", use_container_width=True)
    if submitted:
        if run_service(
            add_part, connection(), name, Decimal(str(selling)), part_number=number or None,
            brand=brand or None, part_type=part_type, quantity=Decimal(str(quantity)),
            cost_price=Decimal(str(cost)), supplier=supplier or None,
            reorder_level=Decimal(str(reorder)), user_id=current_user()["id"],
        ):
            st.session_state.part_add = False
            rerun_after_write("Part added")


def _part_detail(part: dict) -> None:
    st.subheader(part["part_name"])
    status_badge("Pending" if part["needs_ordering"] else "Received")
    st.write(f"Stock: {part['quantity']} · Selling: {money(part['selling_price'])}")
    with st.form(f"edit_part_{part['id']}"):
        name = st.text_input("Name", value=part["part_name"])
        selling = st.number_input("Selling price", min_value=0.0, value=float(part["selling_price"]))
        cost = st.number_input("Cost price", min_value=0.0, value=float(part["cost_price"]))
        reorder = st.number_input("Reorder level", min_value=0.0, value=float(part["reorder_level"]))
        if st.form_submit_button("Save Part", use_container_width=True):
            if run_service(
                update_part, connection(), part["id"], part_name=name,
                selling_price=Decimal(str(selling)), cost_price=Decimal(str(cost)),
                reorder_level=Decimal(str(reorder)), user_id=current_user()["id"],
            ):
                rerun_after_write("Part updated")
    delta = st.number_input("Stock adjustment", value=0.0, step=1.0)
    reason = st.text_input("Adjustment reason")
    if st.button("Apply Stock Adjustment", use_container_width=True):
        if run_service(
            adjust_stock, connection(), part["id"], Decimal(str(delta)), reason,
            user_id=current_user()["id"],
        ):
            rerun_after_write("Stock adjusted")
    flag = st.toggle("Needs Ordering", value=part["needs_ordering"])
    if flag != part["needs_ordering"]:
        if run_service(
            flag_needs_ordering, connection(), part["id"], flag,
            user_id=current_user()["id"],
        ):
            rerun_after_write("Ordering flag updated")


def render() -> None:
    st.title("Parts & Inventory")
    user = current_user()
    if not has_permission(user, "inventory"):
        st.warning("Inventory administration is not available for your role.")
        return
    parts_tab, reorder_tab, orders_tab = st.tabs(["Parts", "To Reorder", "Orders"])
    with parts_tab:
        if st.button("Add Part", type="primary", use_container_width=True):
            st.session_state.part_add = not st.session_state.get("part_add", False)
        if st.session_state.get("part_add", False):
            _add_part_form()
        query = st.text_input("Search parts")
        parts = run_service(search_parts, connection(), query) or []
        for part in parts:
            if part_row(part, key=f"part_open_{part['id']}", action_label="Manage"):
                st.session_state.selected_part_id = part["id"]
        selected = st.session_state.get("selected_part_id")
        if selected:
            matching = next((item for item in parts if item["id"] == selected), None)
            if matching:
                _part_detail(matching)
    with reorder_tab:
        items = run_service(get_reorder_list, connection()) or []
        if not items:
            empty_state("No parts need ordering.")
        for part in items:
            with st.container(border=True):
                st.markdown(f"**{part['part_name']}**")
                st.write(f"Stock {part['quantity']} · Reorder {part['reorder_level']}")
                st.warning(part["reorder_reason"])
                quantity = st.number_input(
                    "Order quantity", min_value=0.01, value=float(max(part["shortage_quantity"], 1)),
                    key=f"order_qty_{part['id']}",
                )
                if st.button("Create Order", key=f"create_order_{part['id']}", use_container_width=True):
                    if run_service(
                        create_order, connection(), part["id"], Decimal(str(quantity)),
                        supplier=part.get("supplier"), user_id=user["id"],
                    ):
                        rerun_after_write("Parts order created")
    with orders_tab:
        status = st.selectbox("Order status", ["All", "Ordered", "Partially Received", "Received", "Cancelled"])
        orders = run_service(list_orders, connection(), None if status == "All" else status) or []
        if not orders:
            empty_state("No parts orders match this filter.")
        for order in orders:
            with st.container(border=True):
                st.markdown(f"**{order['part_name']}**")
                st.write(f"Ordered {order['quantity_ordered']} · Received {order['quantity_received']}")
                st.caption(f"Ordered {format_date(order['ordered_date'])}")
                status_badge(order["status"])
                if order["status"] in {"Ordered", "Partially Received"}:
                    outstanding = order["quantity_ordered"] - order["quantity_received"]
                    receive = st.number_input(
                        "Quantity received", min_value=0.01, max_value=float(outstanding),
                        value=float(outstanding), key=f"receive_qty_{order['id']}",
                    )
                    if st.button("Receive Stock", key=f"receive_order_{order['id']}", use_container_width=True):
                        if run_service(
                            receive_order, connection(), order["id"], Decimal(str(receive)),
                            user_id=user["id"],
                        ):
                            rerun_after_write("Order receipt added to stock")


render()

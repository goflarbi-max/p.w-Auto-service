"""Permission-aware navigation and global workshop search."""

from __future__ import annotations

import streamlit as st

from src.services.customers import search_customers
from src.services.users import has_permission
from src.services.vehicles import search_vehicles
from src.ui.app_context import connection, current_user, run_service


def render_sidebar() -> None:
    """Render business identity, current user, and global quick search."""
    user = current_user()
    with st.sidebar:
        st.title("P.W Auto Service")
        st.caption(f"{user['name']} · {user['role_name']}")
        query = st.text_input("Quick search", placeholder="Phone, name, VIN or registration")
        if query.strip():
            customers = run_service(search_customers, connection(), query) or []
            vehicles = run_service(search_vehicles, connection(), query) or []
            for customer in customers[:3]:
                if st.button(
                    f"Customer: {customer['name']}", key=f"global_customer_{customer['id']}",
                    use_container_width=True,
                ):
                    st.session_state.selected_customer_id = customer["id"]
                    st.switch_page("src/ui/pages/customers.py")
            for vehicle in vehicles[:3]:
                if st.button(
                    f"Vehicle: {vehicle['reg_number']}", key=f"global_vehicle_{vehicle['id']}",
                    use_container_width=True,
                ):
                    st.session_state.selected_vehicle_id = vehicle["id"]
                    st.switch_page("src/ui/pages/customers.py")


def build_navigation() -> st.navigation:
    """Create the navigation tree allowed for the current role."""
    user = current_user()
    can_view_reports = has_permission(user, "revenue_reports")
    pages = [
        *(
            [st.Page("src/ui/pages/dashboard.py", title="Dashboard", icon=":material/bar_chart:", default=True)]
            if can_view_reports else []
        ),
        st.Page(
            "src/ui/pages/job_cards.py", title="Job Cards", icon=":material/assignment:",
            default=not can_view_reports,
        ),
        st.Page("src/ui/pages/customers.py", title="Customers & Vehicles", icon=":material/directions_car:"),
        st.Page("src/ui/pages/appointments.py", title="Appointments", icon=":material/calendar_month:"),
        st.Page("src/ui/pages/parts.py", title="Parts & Inventory", icon=":material/inventory_2:"),
        st.Page("src/ui/pages/reminders.py", title="Reminders", icon=":material/notifications:"),
    ]
    if has_permission(user, "user_management"):
        pages.append(st.Page("src/ui/pages/settings.py", title="Settings", icon=":material/settings:"))
    return st.navigation(pages, position="sidebar")

"""Admin-only read-only settings page."""

from __future__ import annotations

import streamlit as st

from src.config import BUSINESS_DETAILS, CURRENCY
from src.services.users import has_permission
from src.ui.app_context import current_user


def render() -> None:
    user = current_user()
    if not has_permission(user, "user_management"):
        st.error("Settings are available to Admin users only.")
        return
    st.title("Settings")
    st.subheader("Business")
    st.write(BUSINESS_DETAILS["name"])
    office = BUSINESS_DETAILS["registered_office"]
    st.write(f"GPS: {office['gps']}")
    st.write(f"{office['area']}, {office['district']}, {office['region']}")
    st.write(f"Telephone: {BUSINESS_DETAILS['telephone']}")
    st.write(f"Currency: {CURRENCY}")
    st.caption(f"Logo path: {BUSINESS_DETAILS['logo_path']}")
    st.subheader("Current User")
    st.write(user["name"])
    st.write(user["email"])
    st.write(f"Role: {user['role_name']}")
    st.info("User and role management are not included in this phase.")


render()

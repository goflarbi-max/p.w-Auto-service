"""P.W Auto Service Streamlit application entry point."""

from __future__ import annotations

from importlib import reload

import streamlit as st

from src.config import BUSINESS_DETAILS
from src.ui.app_context import get_app_connection, initialize_state
from src.ui import navigation as navigation_module


# Streamlit can retain imported dependency modules across hot reruns. Reload the
# small navigation module so removed or reordered pages take effect immediately.
navigation_module = reload(navigation_module)


st.set_page_config(
    page_title="P.W Auto Service",
    page_icon=":material/build:",
    layout="centered",
    initial_sidebar_state="collapsed",
)
st.logo(str(BUSINESS_DETAILS["logo_path"]), size="large")
get_app_connection()
initialize_state()
navigation = navigation_module.build_navigation()
navigation_module.render_sidebar()
navigation.run()

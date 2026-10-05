"""P.W Auto Service Streamlit application entry point."""

from __future__ import annotations

import streamlit as st

from src.config import BUSINESS_DETAILS
from src.ui.app_context import get_app_connection, initialize_state
from src.ui.navigation import build_navigation, render_sidebar


st.set_page_config(
    page_title="P.W Auto Service",
    page_icon=":material/build:",
    layout="centered",
    initial_sidebar_state="collapsed",
)
st.logo(str(BUSINESS_DETAILS["logo_path"]), size="large")
get_app_connection()
initialize_state()
render_sidebar()
build_navigation().run()

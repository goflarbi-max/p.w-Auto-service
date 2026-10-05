"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.getenv("PW_AUTO_DB_PATH", PROJECT_ROOT / "data" / "pw_auto_service.duckdb"))
CURRENCY = "GHS"
DEFAULT_USER_EMAIL = "boatey.obed@gmail.com"
DEFAULT_REMINDER_INTERVAL_MONTHS = 6
REMINDER_MESSAGE_TEMPLATE = (
    "Hello {customer_name}, your {vehicle} service at P.W Auto Service is due "
    "on {next_service_date}. Please call 0541837349 to book."
)
PAYMENT_METHODS = ("Cash", "Mobile Money", "Card", "Bank Transfer")
DOCUMENT_FOOTER = "Thank you for your business"
PAYMENT_DETAILS = ""
DOCUMENT_ACCENT_COLOR = "#2F5D62"
DOCUMENT_FONT_REGULAR = PROJECT_ROOT / "assets" / "fonts" / "DejaVuSans.ttf"
DOCUMENT_FONT_BOLD = PROJECT_ROOT / "assets" / "fonts" / "DejaVuSans-Bold.ttf"
ROLE_PERMISSIONS = {
    "Admin": {"*"},
    "Manager": {
        "job_cards", "estimates", "parts_usage", "inventory", "invoices",
        "payments", "dashboard", "revenue_reports",
    },
    "Technician": {"job_cards", "estimates", "parts_usage"},
}
JOB_NUMBER_FORMAT = "PW-JC-{year}-{number:04d}"
INVOICE_NUMBER_FORMAT = "PW-INV-{year}-{number:04d}"

BUSINESS_DETAILS = {
    "name": "P.W Auto Service",
    "registered_office": {
        "gps": "GJ-096-6186",
        "street_name": "",
        "area": "Weija SCC",
        "district": "Weija Gbawe",
        "region": "Greater Accra",
    },
    "telephone": "0541837349",
    "logo_path": PROJECT_ROOT / "assets" / "logo_placeholder.png",
}

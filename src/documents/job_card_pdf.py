"""Populated and blank workshop job-card PDF generators."""

from __future__ import annotations

import duckdb
from fpdf.fonts import FontFace

from src.documents.common import WorkshopPDF, format_date, format_money
from src.services.estimates import get_estimate_full
from src.services.job_cards import get_job_card_full, list_job_types


def job_card_filename(job_no: str) -> str:
    """Return the required populated job-card filename."""
    return f"{job_no}.pdf"


def blank_job_card_filename() -> str:
    """Return the stable blank job-card filename."""
    return "PW-JC-BLANK.pdf"


def _identity(pdf: WorkshopPDF, data: dict) -> None:
    pdf.section_title("Customer / Vehicle")
    pdf.label_value("Customer", data.get("customer_name"))
    pdf.label_value("Vehicle", f"{data.get('brand', '')} {data.get('model', '')}")
    pdf.ln(5)
    pdf.label_value("Phone", data.get("phone"))
    pdf.label_value("Year", data.get("year"))
    pdf.ln(5)
    pdf.label_value("Email", data.get("email"))
    pdf.label_value("Registration", data.get("reg_number"))
    pdf.ln(5)
    pdf.label_value("Address", data.get("address"))
    pdf.label_value("VIN", data.get("vin"))
    pdf.ln(5)
    pdf.label_value("", "")
    pdf.label_value("Mileage", data.get("mileage"))
    pdf.ln(6)


def _job_types(pdf: WorkshopPDF, all_types: list[str], selected: set[str]) -> None:
    pdf.section_title("Job Types")
    values = [f"{'[x]' if name in selected else '[ ]'} {name}" for name in all_types]
    pdf.set_font(pdf.font_family, "", 9)
    pdf.multi_cell(0, 6, pdf.clean("    ".join(values)))


def _parts(pdf: WorkshopPDF, rows: list[dict], *, blank_rows: int = 0) -> None:
    pdf.section_title("Parts Used")
    headings = FontFace(emphasis="BOLD", fill_color=(235, 238, 238))
    with pdf.table(col_widths=(90, 36, 20, 36), headings_style=headings,
                   line_height=6, padding=1.5) as table:
        header = table.row()
        for value in ("Description", "Part No", "Qty", "Unit Price"):
            header.cell(value)
        for item in rows:
            row = table.row()
            for value in (item.get("part_name", ""), item.get("part_number") or "—",
                          item.get("quantity", ""), format_money(item.get("unit_price"))):
                row.cell(pdf.clean(value))
        for _ in range(blank_rows):
            row = table.row()
            for _column in range(4):
                row.cell(" ")


def _signatures(pdf: WorkshopPDF) -> None:
    pdf.ln(9)
    pdf.set_font(pdf.font_family, "", 9)
    pdf.cell(82, 7, "Customer signature / Date: __________________________")
    pdf.cell(18, 7, "")
    pdf.cell(82, 7, "Technician signature / Date: ______________________")
    pdf.ln(8)


def generate_job_card_pdf(conn: duckdb.DuckDBPyConnection, job_card_id: int) -> bytes:
    """Generate a populated job card as PDF bytes."""
    data = get_job_card_full(conn, job_card_id)
    pdf = WorkshopPDF(title="JOB CARD")
    pdf.add_page()
    pdf.set_font(pdf.font_family, "B", 9)
    pdf.cell(91, 6, pdf.clean(f"Job No: {data['job_no']}"))
    pdf.cell(91, 6, pdf.clean(f"Status: {data['status']}"), align="R")
    pdf.ln(6)
    pdf.cell(91, 6, pdf.clean(f"Received: {format_date(data['date_received'])}"))
    pdf.cell(91, 6, pdf.clean(f"Expected: {format_date(data['expected_delivery'])}"), align="R")
    pdf.ln(7)
    _identity(pdf, data)
    all_types = [item["name"] for item in list_job_types(conn)]
    selected = {item["name"] for item in data["job_types"]}
    _job_types(pdf, all_types, selected)
    pdf.boxed_text("Customer Complaint", data.get("customer_complaint"), minimum_height=18)
    pdf.boxed_text("Current Condition of Car", data.get("current_condition"), minimum_height=18)
    pdf.boxed_text("Inspection Notes", data.get("inspection_notes"), minimum_height=18)
    pdf.boxed_text("Diagnosis", data.get("diagnosis"), minimum_height=18)
    _parts(pdf, data["parts_used"])
    if data["estimates"]:
        latest = get_estimate_full(conn, data["estimates"][0]["id"])
        pdf.section_title("Estimate Summary")
        totals = latest["totals"]
        pdf.multi_cell(
            0, 5, pdf.clean(
                f"Version {latest['version']} · {latest['status']}    "
                f"Labour {format_money(totals['labour'])}    Parts {format_money(totals['parts'])}    "
                f"Tax {format_money(totals['tax'])}    Total {format_money(totals['total'])}"
            )
        )
    _signatures(pdf)
    return pdf.bytes_output()


def generate_blank_job_card(
    job_types: list[str] | None = None,
) -> bytes:
    """Generate a printable empty job-card template."""
    pdf = WorkshopPDF(title="JOB CARD")
    pdf.add_page()
    pdf.set_font(pdf.font_family, "B", 9)
    pdf.cell(91, 6, "Job No: _________________________")
    pdf.cell(91, 6, "Status: _________________________", align="R")
    pdf.ln(6)
    pdf.cell(91, 6, "Received: _______________________")
    pdf.cell(91, 6, "Expected: _______________________", align="R")
    pdf.ln(7)
    _identity(pdf, {})
    _job_types(pdf, job_types or ["Servicing", "Brake", "Engine", "AC", "Electrical"], set())
    pdf.boxed_text("Customer Complaint", "", minimum_height=27)
    pdf.boxed_text("Current Condition of Car", "", minimum_height=24)
    pdf.boxed_text("Inspection Notes", "", minimum_height=27)
    pdf.boxed_text("Diagnosis", "", minimum_height=27)
    _parts(pdf, [], blank_rows=5)
    _signatures(pdf)
    return pdf.bytes_output()

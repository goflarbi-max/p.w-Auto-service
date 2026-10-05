"""Invoice and estimate PDF generators."""

from __future__ import annotations

from decimal import Decimal

import duckdb
from fpdf.fonts import FontFace

from src.config import PAYMENT_DETAILS
from src.documents.common import WorkshopPDF, format_date, format_money
from src.services.estimates import get_estimate_document_full
from src.services.invoices import get_invoice_full


def invoice_filename(invoice_no: str) -> str:
    """Return the required invoice download filename."""
    return f"{invoice_no}.pdf"


def estimate_filename(job_no: str, version: int) -> str:
    """Return the required estimate download filename."""
    return f"{job_no.replace('PW-JC-', 'PW-EST-')}-v{version}.pdf"


def _party_and_vehicle(pdf: WorkshopPDF, data: dict) -> None:
    pdf.section_title("Bill To / Vehicle")
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
    pdf.ln(5)
    types = ", ".join(item["name"] for item in data.get("job_types", [])) or "—"
    pdf.label_value("Job Types", types, 182)
    pdf.ln(6)


def _items_table(pdf: WorkshopPDF, title: str, rows: list[dict]) -> None:
    pdf.section_title(title)
    headings = FontFace(emphasis="BOLD", fill_color=(235, 238, 238))
    with pdf.table(
        col_widths=(76, 30, 16, 30, 30), headings_style=headings,
        text_align=("LEFT", "LEFT", "RIGHT", "RIGHT", "RIGHT"),
        line_height=5, padding=1.5,
    ) as table:
        header = table.row()
        for value in ("Description", "Part No", "Qty", "Unit Price", "Line Total"):
            header.cell(pdf.clean(value))
        for item in rows:
            row = table.row()
            description = item.get("part_name") or item.get("description") or "Part"
            line_total = Decimal(str(item["quantity"])) * Decimal(str(item["unit_price"]))
            for value in (
                description, item.get("part_number") or "—", item.get("quantity"),
                format_money(item.get("unit_price")), format_money(item.get("line_total", line_total)),
            ):
                row.cell(pdf.clean(value))


def _labour_table(pdf: WorkshopPDF, lines: list[dict]) -> None:
    pdf.section_title("Labour")
    headings = FontFace(emphasis="BOLD", fill_color=(235, 238, 238))
    with pdf.table(col_widths=(145, 37), headings_style=headings, line_height=5, padding=1.5) as table:
        header = table.row()
        header.cell("Description")
        header.cell("Amount", align="RIGHT")
        for item in lines:
            row = table.row()
            row.cell(pdf.clean(item.get("description") or "Labour"))
            row.cell(format_money(item.get("line_total", item.get("amount", 0))), align="RIGHT")


def _totals(pdf: WorkshopPDF, *, labour: Decimal, parts: Decimal, tax: Decimal, total: Decimal) -> None:
    pdf.section_title("Totals")
    for label, value in (("Labour subtotal", labour), ("Parts subtotal", parts)):
        pdf.cell(140, 6, label, align="R")
        pdf.cell(42, 6, format_money(value), align="R")
        pdf.ln(6)
    if tax > 0:
        pdf.cell(140, 6, "Tax", align="R")
        pdf.cell(42, 6, format_money(tax), align="R")
        pdf.ln(6)
    pdf.set_font(pdf.font_family, "B", 11)
    pdf.cell(140, 7, "TOTAL", align="R")
    pdf.cell(42, 7, format_money(total), align="R")
    pdf.ln(8)


def generate_invoice_pdf(conn: duckdb.DuckDBPyConnection, invoice_id: int) -> bytes:
    """Generate a complete invoice as PDF bytes."""
    data = get_invoice_full(conn, invoice_id)
    pdf = WorkshopPDF(title="INVOICE", business=data["business"])
    pdf.add_page()
    pdf.set_font(pdf.font_family, "B", 9)
    pdf.cell(91, 6, pdf.clean(f"Invoice No: {data['invoice_no']}"))
    pdf.cell(91, 6, pdf.clean(f"Issue Date: {format_date(data['issue_date'])}"), align="R")
    pdf.ln(6)
    pdf.cell(91, 6, pdf.clean(f"Job Card: {data['job_no']}"))
    if data["payment_status"] == "Paid":
        pdf.set_text_color(30, 110, 60)
        pdf.cell(91, 6, "PAID", align="R")
        pdf.set_text_color(0, 0, 0)
    pdf.ln(7)
    _party_and_vehicle(pdf, data)
    _items_table(pdf, "Parts", data["parts"])
    _labour_table(pdf, data["labour_lines"])
    _totals(pdf, labour=data["labour_total"], parts=data["parts_total"],
            tax=data["tax_amount"], total=data["total"])
    pdf.section_title("Payment")
    balance = data["total"] - data["amount_paid"]
    pdf.multi_cell(
        0, 5, pdf.clean(
            f"Amount paid: {format_money(data['amount_paid'])}    "
            f"Balance due: {format_money(balance)}    Status: {data['payment_status']}"
        )
    )
    if PAYMENT_DETAILS.strip():
        pdf.multi_cell(0, 5, pdf.clean(f"Payment details: {PAYMENT_DETAILS}"))
    if data.get("notes"):
        pdf.boxed_text("Notes", data["notes"], minimum_height=12)
    return pdf.bytes_output()


def generate_estimate_pdf(conn: duckdb.DuckDBPyConnection, estimate_id: int) -> bytes:
    """Generate a selected estimate version as PDF bytes."""
    data = get_estimate_document_full(conn, estimate_id)
    pdf = WorkshopPDF(title="ESTIMATE", business=data["business"])
    pdf.add_page()
    estimate_no = estimate_filename(data["job_no"], data["version"]).removesuffix(".pdf")
    pdf.set_font(pdf.font_family, "B", 9)
    pdf.cell(91, 6, pdf.clean(f"Estimate: {estimate_no}"))
    pdf.cell(91, 6, pdf.clean(f"Created: {format_date(data['created_at'])}"), align="R")
    pdf.ln(6)
    pdf.cell(91, 6, pdf.clean(f"Job Card: {data['job_no']}"))
    pdf.cell(91, 6, pdf.clean(f"Version: {data['version']}"), align="R")
    pdf.ln(7)
    _party_and_vehicle(pdf, data)
    parts = [item for item in data["items"] if item["item_type"] == "Part"]
    labour = [item for item in data["items"] if item["item_type"] == "Labour"]
    _items_table(pdf, "Parts", parts)
    _labour_table(pdf, labour)
    totals = data["totals"]
    _totals(pdf, labour=totals["labour"], parts=totals["parts"],
            tax=totals["tax"], total=totals["total"])
    return pdf.bytes_output()

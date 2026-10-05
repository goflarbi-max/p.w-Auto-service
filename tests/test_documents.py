"""PDF generation tests for invoices, estimates, and job cards."""

from __future__ import annotations

import re
from pathlib import Path

import duckdb
import pytest

from scripts.build_database import build_database
from src.config import BUSINESS_DETAILS
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


@pytest.fixture()
def document_conn(tmp_path: Path):
    path = build_database(tmp_path / "documents.duckdb")
    conn = duckdb.connect(str(path))
    try:
        yield conn
    finally:
        conn.close()


def test_sample_documents_are_valid_pdfs(document_conn) -> None:
    """All populated document variants return PDF bytes."""
    for content in (
        generate_invoice_pdf(document_conn, 3),
        generate_estimate_pdf(document_conn, 6),
        generate_job_card_pdf(document_conn, 6),
    ):
        assert content.startswith(b"%PDF")
        assert len(content) > 1_000


def test_missing_logo_falls_back_without_crashing(
    document_conn, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing configured logo never prevents document generation."""
    monkeypatch.setitem(BUSINESS_DETAILS, "logo_path", tmp_path / "missing-logo.png")
    assert generate_invoice_pdf(document_conn, 3).startswith(b"%PDF")


def test_tax_line_is_conditional(document_conn) -> None:
    """Tax is hidden at zero and rendered when positive."""
    zero_tax = generate_invoice_pdf(document_conn, 2)
    assert b"(Tax)" not in zero_tax
    document_conn.execute(
        "UPDATE invoices SET tax_amount = 100, total = 3950 WHERE id = 2"
    )
    with_tax = generate_invoice_pdf(document_conn, 2)
    assert b"(Tax)" in with_tax


def test_long_invoice_creates_multiple_pages(document_conn) -> None:
    """Thirty-plus part lines split cleanly across pages."""
    for _ in range(32):
        document_conn.execute(
            """
            INSERT INTO parts_used (job_card_id, part_id, quantity, unit_price)
            VALUES (4, 2, 1, 140)
            """
        )
    document_conn.execute(
        "UPDATE invoices SET parts_total = 5180, total = 6030 WHERE id = 1"
    )
    content = generate_invoice_pdf(document_conn, 1)
    assert len(re.findall(rb"/Type /Page\b", content)) >= 2


def test_blank_job_card_generates() -> None:
    assert generate_blank_job_card().startswith(b"%PDF")


def test_document_filenames() -> None:
    assert invoice_filename("PW-INV-2026-0001") == "PW-INV-2026-0001.pdf"
    assert estimate_filename("PW-JC-2026-0001", 2) == "PW-EST-2026-0001-v2.pdf"
    assert job_card_filename("PW-JC-2026-0001") == "PW-JC-2026-0001.pdf"
    assert blank_job_card_filename() == "PW-JC-BLANK.pdf"

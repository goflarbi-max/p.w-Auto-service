"""Shared fpdf2 document layout and formatting helpers."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from fpdf import FPDF

from src.config import (
    BUSINESS_DETAILS,
    DOCUMENT_ACCENT_COLOR,
    DOCUMENT_FONT_BOLD,
    DOCUMENT_FONT_REGULAR,
    DOCUMENT_FOOTER,
)


def format_money(value: Decimal | int | str | None) -> str:
    """Format a monetary amount in Ghana cedis."""
    return f"GHS {Decimal(str(value or 0)):,.2f}"


def format_date(value: date | datetime | None) -> str:
    """Format a document date consistently."""
    return value.strftime("%d %b %Y") if value else ""


def hex_rgb(value: str) -> tuple[int, int, int]:
    """Convert a configured hex color into an RGB tuple."""
    clean = value.lstrip("#")
    return tuple(int(clean[index:index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]


class WorkshopPDF(FPDF):
    """A4 document base with branding, page numbers, and font fallback."""

    def __init__(self, *, title: str, business: dict[str, Any] | None = None) -> None:
        super().__init__(orientation="P", unit="mm", format="A4")
        self.document_title = title
        self.business = business or BUSINESS_DETAILS
        self.accent = hex_rgb(DOCUMENT_ACCENT_COLOR)
        self.set_margins(14, 14, 14)
        self.set_auto_page_break(auto=True, margin=17)
        self.alias_nb_pages()
        self.set_compression(False)
        self.font_family = "Helvetica"
        if Path(DOCUMENT_FONT_REGULAR).is_file() and Path(DOCUMENT_FONT_BOLD).is_file():
            self.add_font("Workshop", style="", fname=str(DOCUMENT_FONT_REGULAR))
            self.add_font("Workshop", style="B", fname=str(DOCUMENT_FONT_BOLD))
            self.font_family = "Workshop"

    def clean(self, value: object | None) -> str:
        """Return printable text, degrading safely when project fonts are absent."""
        text = "" if value is None else str(value)
        if self.font_family == "Helvetica":
            return text.encode("latin-1", errors="replace").decode("latin-1")
        return text

    def header(self) -> None:
        """Render logo-or-text branding and registered office details."""
        logo = Path(self.business.get("logo_path", ""))
        if logo.is_file():
            try:
                self.image(str(logo), x=14, y=10, w=24, h=18, keep_aspect_ratio=True)
                left = 42
            except Exception:
                left = 14
        else:
            left = 14
        self.set_xy(left, 10)
        self.set_font(self.font_family, "B", 13)
        self.cell(100, 6, self.clean(self.business.get("name", "P.W Auto Service")))
        self.set_xy(135, 10)
        self.set_font(self.font_family, "B", 17)
        self.set_text_color(*self.accent)
        self.cell(61, 8, self.clean(self.document_title), align="R")
        self.set_text_color(0, 0, 0)
        office = self.business.get("registered_office", {})
        address_lines = [
            f"GPS: {office.get('gps', '')}",
            office.get("street_name", ""),
            office.get("area", ""),
            office.get("district", ""),
            office.get("region", ""),
            f"Tel: {self.business.get('telephone', '')}",
        ]
        self.set_xy(left, 17)
        self.set_font(self.font_family, "", 8)
        self.multi_cell(90, 4, self.clean(" · ".join(str(item) for item in address_lines if item)))
        self.set_y(31)
        self.set_draw_color(*self.accent)
        self.set_line_width(0.6)
        self.line(14, self.get_y(), 196, self.get_y())
        self.ln(4)

    def footer(self) -> None:
        """Render configurable footer text and Page X of Y."""
        self.set_y(-13)
        self.set_draw_color(160, 160, 160)
        self.set_line_width(0.2)
        self.line(14, self.get_y(), 196, self.get_y())
        self.ln(2)
        self.set_font(self.font_family, "", 8)
        self.cell(130, 5, self.clean(DOCUMENT_FOOTER))
        self.cell(52, 5, f"Page {self.page_no()} of {{nb}}", align="R")

    def section_title(self, title: str) -> None:
        """Render a restrained section heading."""
        self.ln(2)
        self.set_fill_color(235, 238, 238)
        self.set_font(self.font_family, "B", 9)
        self.cell(0, 6, self.clean(title.upper()), fill=True)
        self.ln(7)

    def label_value(self, label: str, value: object | None, width: float = 91) -> None:
        """Render a compact label/value row."""
        self.set_font(self.font_family, "B", 8)
        self.cell(24, 5, self.clean(label))
        self.set_font(self.font_family, "", 8)
        self.cell(width - 24, 5, self.clean(value))

    def boxed_text(self, title: str, value: object | None, *, minimum_height: float = 20) -> None:
        """Render a wrapped bordered narrative section with handwriting space."""
        self.section_title(title)
        start_y = self.get_y()
        self.set_font(self.font_family, "", 9)
        self.multi_cell(0, 5, self.clean(value) or " ", border=1, padding=3)
        used = self.get_y() - start_y
        if used < minimum_height:
            self.rect(14, start_y, 182, minimum_height)
            self.set_y(start_y + minimum_height)

    def bytes_output(self) -> bytes:
        """Finalize and return PDF bytes."""
        return bytes(self.output())

"""DataFrame wrappers around Phase 1 reporting views."""

from __future__ import annotations

from typing import Literal

import duckdb
import pandas as pd

from src.services.errors import ValidationError
from src.services._common import fetch_all


def jobs_by_status(conn: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return conn.execute("SELECT * FROM v_jobs_by_status ORDER BY status").fetchdf()


def cars_in_house(conn: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return conn.execute("SELECT * FROM v_cars_in_house ORDER BY date_received").fetchdf()


def jobs_completed_pending(conn: duckdb.DuckDBPyConnection, period: Literal["month", "year"], year: int | None = None) -> pd.DataFrame:
    if period == "month":
        return conn.execute(
            "SELECT * FROM v_jobs_monthly_summary WHERE (? IS NULL OR year(period) = ?) ORDER BY period",
            [year, year],
        ).fetchdf()
    if period == "year":
        return conn.execute(
            "SELECT * FROM v_jobs_yearly_summary WHERE (? IS NULL OR year = ?) ORDER BY year",
            [year, year],
        ).fetchdf()
    raise ValidationError("period must be 'month' or 'year'")


def revenue(conn: duckdb.DuckDBPyConnection, period: Literal["month", "year"], year: int | None = None) -> pd.DataFrame:
    if period == "month":
        return conn.execute(
            "SELECT * FROM v_service_revenue_monthly WHERE (? IS NULL OR year(period) = ?) ORDER BY period",
            [year, year],
        ).fetchdf()
    if period == "year":
        return conn.execute(
            "SELECT * FROM v_service_revenue_yearly WHERE (? IS NULL OR year = ?) ORDER BY year",
            [year, year],
        ).fetchdf()
    raise ValidationError("period must be 'month' or 'year'")


def parts_usage(conn: duckdb.DuckDBPyConnection, *, year: int | None = None) -> pd.DataFrame:
    return conn.execute(
        "SELECT * FROM v_parts_usage WHERE (? IS NULL OR year(period) = ?) ORDER BY period, part_name",
        [year, year],
    ).fetchdf()


def parts_ordered(conn: duckdb.DuckDBPyConnection, *, year: int | None = None) -> pd.DataFrame:
    return conn.execute(
        "SELECT * FROM v_parts_ordered WHERE (? IS NULL OR year(period) = ?) ORDER BY period, part_name",
        [year, year],
    ).fetchdf()


def low_stock_count(conn: duckdb.DuckDBPyConnection) -> int:
    return conn.execute("SELECT count(*) FROM v_parts_to_reorder").fetchone()[0]


def reporting_years(conn: duckdb.DuckDBPyConnection) -> list[int]:
    """Return every year represented by dashboard source records."""
    rows = conn.execute(
        """
        SELECT DISTINCT report_year FROM (
            SELECT year(date_received) AS report_year FROM job_cards
            UNION ALL SELECT year(issue_date) FROM invoices
            UNION ALL SELECT year(recorded_at) FROM parts_used
            UNION ALL SELECT year(ordered_date) FROM parts_orders
        ) years WHERE report_year IS NOT NULL ORDER BY report_year DESC
        """
    ).fetchall()
    return [row[0] for row in rows]


def dashboard_kpis(conn: duckdb.DuckDBPyConnection) -> dict[str, object]:
    """Return the operational and invoice KPI values used by the dashboard."""
    invoice = conn.execute(
        """
        SELECT count(*), coalesce(sum(total - amount_paid), 0)
        FROM invoices WHERE payment_status IN ('Unpaid', 'Partial')
        """
    ).fetchone()
    return {
        "cars_in_house": conn.execute("SELECT count(*) FROM v_cars_in_house").fetchone()[0],
        "awaiting_approval": conn.execute(
            "SELECT count(*) FROM job_cards WHERE status = 'Estimate Sent'"
        ).fetchone()[0],
        "parts_to_reorder": low_stock_count(conn),
        "unpaid_invoice_count": invoice[0],
        "outstanding_total": invoice[1],
    }


def top_parts_usage(
    conn: duckdb.DuckDBPyConnection, year: int | None = None, limit: int = 10,
) -> pd.DataFrame:
    """Return top parts by quantity and usage value for a selected year."""
    if limit <= 0:
        raise ValidationError("limit must be positive")
    return conn.execute(
        """
        SELECT p.id AS part_id, p.part_name, p.part_number,
               sum(pu.quantity) AS quantity_used,
               sum(pu.quantity * pu.unit_price) AS usage_value
        FROM parts_used pu JOIN parts p ON p.id = pu.part_id
        WHERE (? IS NULL OR year(pu.recorded_at) = ?)
        GROUP BY p.id, p.part_name, p.part_number
        ORDER BY quantity_used DESC, usage_value DESC LIMIT ?
        """, [year, year, limit]
    ).fetchdf()


def parts_orders_dashboard(
    conn: duckdb.DuckDBPyConnection, year: int | None = None,
    recent_limit: int = 10,
) -> dict[str, pd.DataFrame]:
    """Return order status totals and recent order rows for the dashboard."""
    if recent_limit <= 0:
        raise ValidationError("recent_limit must be positive")
    by_status = conn.execute(
        """
        SELECT status, count(*) AS order_count,
               sum(quantity_ordered) AS quantity_ordered,
               sum(quantity_received) AS quantity_received
        FROM parts_orders WHERE (? IS NULL OR year(ordered_date) = ?)
        GROUP BY status ORDER BY status
        """, [year, year]
    ).fetchdf()
    recent = conn.execute(
        """
        SELECT po.id, po.ordered_date, po.status, po.quantity_ordered,
               po.quantity_received, po.supplier, p.part_name, p.part_number
        FROM parts_orders po JOIN parts p ON p.id = po.part_id
        WHERE (? IS NULL OR year(po.ordered_date) = ?)
        ORDER BY po.ordered_date DESC, po.id DESC LIMIT ?
        """, [year, year, recent_limit]
    ).fetchdf()
    return {"by_status": by_status, "recent": recent}

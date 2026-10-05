# P.W Auto Service — Database Foundation

Phase 1 provides the DuckDB schema, realistic sample data, reporting views,
database connection lifecycle, and a provider-neutral mock SMS service. It does
not contain authentication, invoice rendering, or real SMS integration. Phase 3
adds a mobile-first Streamlit workshop UI over the service layer.

## Requirements

- Python 3.10 or newer
- A persistent local path in production

## Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python scripts/build_database.py
python -m pytest
streamlit run app.py
```

The default database is `data/pw_auto_service.duckdb`. Override it without
changing code:

```powershell
$env:PW_AUTO_DB_PATH = "D:\persistent-data\pw_auto_service.duckdb"
python scripts/build_database.py
```

Running the build command drops and recreates the managed schema, then loads all
sample CSV files in one transaction. Do not use it against a production database
unless a full reset is intended.

## Runtime connection behavior

`src.database.connection.ensure_db_exists()` builds the database when its file is
missing or when the expected schema version/tables are incomplete.
`get_connection()` reuses a process-level DuckDB connection, and
`write_transaction()` serializes writes for rerun-based applications. All future
mutations should use the transaction context.

Human-readable numbers are allocated with `next_document_number()` inside the
same transaction that inserts the related job card or invoice. Job and invoice
counters are independent and restart at `0001` each calendar year.

## Inventory transactions

There are deliberately no inventory triggers. A Phase 2 service function should
record part usage as one atomic transaction:

1. Read and lock the intended write path through `write_transaction()`.
2. Confirm that sufficient `parts.quantity` exists.
3. Insert the `parts_used` row.
4. Deduct the used quantity from `parts.quantity`.
5. Recalculate the job card's `parts_total` and `total_cost`.
6. Commit; roll back every step if any validation fails.

Receiving an order should similarly update `parts_orders` and add to stock in one
transaction.

## Reporting views

- `v_parts_to_reorder`
- `v_jobs_by_status`
- `v_cars_in_house`
- `v_jobs_monthly_summary` and `v_jobs_yearly_summary`
- `v_service_revenue_monthly` and `v_service_revenue_yearly`
- `v_parts_usage`
- `v_parts_ordered`

Cars in-house include `Ready for Delivery`. Pending jobs exclude Delivered,
Declined, and Cancelled. Revenue views expose invoiced, paid, and outstanding
amounts.

## Production persistence

Do not keep production data on Streamlit Community Cloud's ephemeral filesystem.
For this single-workshop deployment, use a small VPS or container host with the
DuckDB path on a mounted persistent volume. Point `PW_AUTO_DB_PATH` at that volume
and schedule encrypted backups of the database to cloud object storage. The
custom domain can route to the application hosted on the same VPS.

## Business configuration

Business identity, the Weija office address, telephone number, GHS currency, and
the placeholder path `assets/logo_placeholder.png` are defined in
`src/config.py`. The actual logo can be placed at that path later without a
database migration.

## Service layer

Phase 2 keeps business rules in `src/services/`; a future UI should call these
functions instead of executing SQL. Services accept a DuckDB connection, return
plain dictionaries (or DataFrames for dashboards), use `Decimal` for money, and
wrap multi-table writes in rollback-safe transactions.

```python
from decimal import Decimal

from src.database.connection import get_connection
from src.services.parts import record_part_used

connection = get_connection()
usage = record_part_used(
    connection,
    job_card_id=12,
    part_id=3,
    quantity=Decimal("1.00"),
    user_id=1,
)
```

Expected business failures use exceptions from `src.services.errors`, including
`ValidationError`, `NotFoundError`, `InvalidStatusTransition`, and
`InsufficientStockError`. Payment methods are controlled through
`PAYMENT_METHODS` in `src/config.py`. SMS remains provider-neutral and uses the
console/mock provider unless another provider is supplied.

DuckDB prevents updates to a parent row while foreign-key children reference it,
even when the key itself is unchanged. Relationships to mutable operational
records (customers, vehicles, jobs, estimates, parts, orders, and invoices) are
therefore validated by the service layer inside the same transaction. Stable
role/user relationships retain database foreign keys. Callers must use the
service layer for writes.

## Streamlit pages

- Home: operational counts, quick actions, today's appointments, and deliveries
- Job Cards: creation, workflow, diagnosis, estimates, parts, invoices, and history
- Customers & Vehicles: customer records, vehicles, and service history
- Appointments: scheduling, cancellation, and arrival conversion
- Parts & Inventory: catalogue, stock, reorder flags, orders, and receipts
- Reminders: upcoming reminders and mock SMS processing
- Settings: Admin-only read-only business and user information
- Dashboard: Admin/Manager KPIs, job trends, revenue, parts usage, and orders

No Phase 4 dashboard charts or PDF/print output are included. The Print/PDF
control is deliberately disabled and marked as coming soon.

### Test on a phone over the local network

Connect the computer and phone to the same trusted Wi-Fi network, then run:

```powershell
streamlit run app.py --server.address 0.0.0.0
```

Find the computer's IPv4 address with `ipconfig`, then open
`http://COMPUTER_IP:8501` on the phone. If Windows Firewall prompts, allow access
only on private networks. This local-network mode is for workshop testing; use
HTTPS and the planned hosted deployment for production access.

## PDF documents

The Job Card page provides downloads for invoices, estimate versions, populated
job cards, and a printable blank job card. Generators live in `src/documents/`
and return PDF bytes; UI pages do not construct document layouts or query data.

Sample PDFs are generated under `docs/samples/`. To add the workshop logo,
replace `assets/logo_placeholder.png` with the real PNG. If the file is absent
or invalid, documents safely use the business name as text.

Document settings are in `src/config.py`:

- `DOCUMENT_FOOTER` controls the footer message.
- `PAYMENT_DETAILS` is intentionally blank until real payment instructions are supplied.
- `DOCUMENT_ACCENT_COLOR` controls the single print-safe accent.
- `DOCUMENT_FONT_REGULAR` and `DOCUMENT_FONT_BOLD` identify optional bundled Unicode fonts.

When the configured fonts are absent, PDF generation falls back to a built-in
print-safe font and replaces unsupported characters instead of failing.

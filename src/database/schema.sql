-- P.W Auto Service database schema. DuckDB 1.4 compatible.

DROP VIEW IF EXISTS v_parts_ordered;
DROP VIEW IF EXISTS v_parts_usage;
DROP VIEW IF EXISTS v_service_revenue_yearly;
DROP VIEW IF EXISTS v_service_revenue_monthly;
DROP VIEW IF EXISTS v_jobs_yearly_summary;
DROP VIEW IF EXISTS v_jobs_monthly_summary;
DROP VIEW IF EXISTS v_cars_in_house;
DROP VIEW IF EXISTS v_jobs_by_status;
DROP VIEW IF EXISTS v_parts_to_reorder;

DROP TABLE IF EXISTS job_status_history;
DROP TABLE IF EXISTS invoice_payments;
DROP TABLE IF EXISTS stock_adjustments;
DROP TABLE IF EXISTS estimate_items;
DROP TABLE IF EXISTS parts_used;
DROP TABLE IF EXISTS parts_orders;
DROP TABLE IF EXISTS service_reminders;
DROP TABLE IF EXISTS invoices;
DROP TABLE IF EXISTS estimates;
DROP TABLE IF EXISTS job_card_job_types;
DROP TABLE IF EXISTS job_cards;
DROP TABLE IF EXISTS appointments;
DROP TABLE IF EXISTS job_types;
DROP TABLE IF EXISTS parts;
DROP TABLE IF EXISTS vehicles;
DROP TABLE IF EXISTS customers;
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS roles;
DROP TABLE IF EXISTS document_counters;
DROP TABLE IF EXISTS app_metadata;

DROP SEQUENCE IF EXISTS seq_invoice_id;
DROP SEQUENCE IF EXISTS seq_job_status_history_id;
DROP SEQUENCE IF EXISTS seq_invoice_payment_id;
DROP SEQUENCE IF EXISTS seq_stock_adjustment_id;
DROP SEQUENCE IF EXISTS seq_service_reminder_id;
DROP SEQUENCE IF EXISTS seq_parts_order_id;
DROP SEQUENCE IF EXISTS seq_parts_used_id;
DROP SEQUENCE IF EXISTS seq_part_id;
DROP SEQUENCE IF EXISTS seq_estimate_item_id;
DROP SEQUENCE IF EXISTS seq_estimate_id;
DROP SEQUENCE IF EXISTS seq_job_card_id;
DROP SEQUENCE IF EXISTS seq_job_type_id;
DROP SEQUENCE IF EXISTS seq_appointment_id;
DROP SEQUENCE IF EXISTS seq_vehicle_id;
DROP SEQUENCE IF EXISTS seq_customer_id;
DROP SEQUENCE IF EXISTS seq_user_id;
DROP SEQUENCE IF EXISTS seq_role_id;

CREATE SEQUENCE seq_role_id START 1;
CREATE SEQUENCE seq_user_id START 1;
CREATE SEQUENCE seq_customer_id START 1;
CREATE SEQUENCE seq_vehicle_id START 1;
CREATE SEQUENCE seq_appointment_id START 1;
CREATE SEQUENCE seq_job_type_id START 1;
CREATE SEQUENCE seq_job_card_id START 1;
CREATE SEQUENCE seq_estimate_id START 1;
CREATE SEQUENCE seq_estimate_item_id START 1;
CREATE SEQUENCE seq_part_id START 1;
CREATE SEQUENCE seq_parts_used_id START 1;
CREATE SEQUENCE seq_parts_order_id START 1;
CREATE SEQUENCE seq_service_reminder_id START 1;
CREATE SEQUENCE seq_invoice_id START 1;
CREATE SEQUENCE seq_job_status_history_id START 1;
CREATE SEQUENCE seq_invoice_payment_id START 1;
CREATE SEQUENCE seq_stock_adjustment_id START 1;

CREATE TABLE app_metadata (
    key VARCHAR PRIMARY KEY,
    value VARCHAR NOT NULL
);

CREATE TABLE document_counters (
    document_type VARCHAR NOT NULL CHECK (document_type IN ('Job Card', 'Invoice')),
    year INTEGER NOT NULL CHECK (year >= 2000),
    last_number BIGINT NOT NULL DEFAULT 0 CHECK (last_number >= 0),
    PRIMARY KEY (document_type, year)
);

CREATE TABLE roles (
    id BIGINT PRIMARY KEY DEFAULT nextval('seq_role_id'),
    name VARCHAR NOT NULL UNIQUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE users (
    id BIGINT PRIMARY KEY DEFAULT nextval('seq_user_id'),
    name VARCHAR NOT NULL,
    email VARCHAR NOT NULL UNIQUE,
    role_id BIGINT NOT NULL REFERENCES roles(id),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE customers (
    id BIGINT PRIMARY KEY DEFAULT nextval('seq_customer_id'),
    name VARCHAR NOT NULL,
    phone VARCHAR NOT NULL CHECK (regexp_full_match(phone, '^[+]233[0-9]{9}$')),
    email VARCHAR,
    address VARCHAR,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE vehicles (
    id BIGINT PRIMARY KEY DEFAULT nextval('seq_vehicle_id'),
    customer_id BIGINT NOT NULL,
    brand VARCHAR NOT NULL,
    model VARCHAR NOT NULL,
    year INTEGER CHECK (year BETWEEN 1886 AND 2100),
    vin VARCHAR UNIQUE,
    reg_number VARCHAR NOT NULL UNIQUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE parts (
    id BIGINT PRIMARY KEY DEFAULT nextval('seq_part_id'),
    part_name VARCHAR NOT NULL,
    part_number VARCHAR UNIQUE,
    brand VARCHAR,
    type VARCHAR NOT NULL CHECK (type IN ('Genuine', 'Aftermarket')),
    quantity DECIMAL(12,2) NOT NULL DEFAULT 0 CHECK (quantity >= 0),
    cost_price DECIMAL(12,2) NOT NULL DEFAULT 0 CHECK (cost_price >= 0),
    selling_price DECIMAL(12,2) NOT NULL DEFAULT 0 CHECK (selling_price >= 0),
    supplier VARCHAR,
    reorder_level DECIMAL(12,2) NOT NULL DEFAULT 0 CHECK (reorder_level >= 0),
    needs_ordering BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE job_types (
    id BIGINT PRIMARY KEY DEFAULT nextval('seq_job_type_id'),
    name VARCHAR NOT NULL UNIQUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE appointments (
    id BIGINT PRIMARY KEY DEFAULT nextval('seq_appointment_id'),
    source VARCHAR NOT NULL CHECK (source IN ('Call', 'WhatsApp', 'Walk-in')),
    appointment_date DATE NOT NULL,
    customer_id BIGINT NOT NULL,
    vehicle_id BIGINT NOT NULL,
    notes VARCHAR,
    status VARCHAR NOT NULL DEFAULT 'Booked'
        CHECK (status IN ('Booked', 'Confirmed', 'Arrived', 'Completed', 'Cancelled', 'No Show')),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE job_cards (
    id BIGINT PRIMARY KEY DEFAULT nextval('seq_job_card_id'),
    job_no VARCHAR NOT NULL UNIQUE CHECK (regexp_full_match(job_no, '^PW-JC-[0-9]{4}-[0-9]{4,}$')),
    appointment_id BIGINT UNIQUE,
    customer_id BIGINT NOT NULL,
    vehicle_id BIGINT NOT NULL,
    technician_id BIGINT REFERENCES users(id),
    mileage INTEGER CHECK (mileage >= 0),
    customer_complaint VARCHAR NOT NULL,
    current_condition VARCHAR,
    inspection_notes VARCHAR,
    diagnosis VARCHAR,
    date_received DATE NOT NULL DEFAULT CURRENT_DATE,
    expected_delivery DATE,
    date_delivered DATE,
    status VARCHAR NOT NULL DEFAULT 'Received' CHECK (status IN (
        'Received', 'Diagnosed', 'Estimate Sent', 'Approved', 'In Progress',
        'Quality Check', 'Ready for Delivery', 'Delivered', 'Declined', 'Cancelled'
    )),
    labour_cost DECIMAL(12,2) NOT NULL DEFAULT 0 CHECK (labour_cost >= 0),
    parts_total DECIMAL(12,2) NOT NULL DEFAULT 0 CHECK (parts_total >= 0),
    tax_rate DECIMAL(5,2) NOT NULL DEFAULT 0 CHECK (tax_rate BETWEEN 0 AND 100),
    tax_amount DECIMAL(12,2) NOT NULL DEFAULT 0 CHECK (tax_amount >= 0),
    total_cost DECIMAL(12,2) NOT NULL DEFAULT 0 CHECK (total_cost >= 0),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (expected_delivery IS NULL OR expected_delivery >= date_received),
    CHECK (date_delivered IS NULL OR date_delivered >= date_received),
    CHECK (total_cost = labour_cost + parts_total + tax_amount),
    CHECK ((status = 'Delivered' AND date_delivered IS NOT NULL) OR status <> 'Delivered')
);

CREATE TABLE job_card_job_types (
    job_card_id BIGINT NOT NULL,
    job_type_id BIGINT NOT NULL REFERENCES job_types(id),
    PRIMARY KEY (job_card_id, job_type_id)
);

CREATE TABLE job_status_history (
    id BIGINT PRIMARY KEY DEFAULT nextval('seq_job_status_history_id'),
    job_card_id BIGINT NOT NULL,
    status VARCHAR NOT NULL CHECK (status IN (
        'Received', 'Diagnosed', 'Estimate Sent', 'Approved', 'In Progress',
        'Quality Check', 'Ready for Delivery', 'Delivered', 'Declined', 'Cancelled'
    )),
    changed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by BIGINT REFERENCES users(id)
);

CREATE TABLE estimates (
    id BIGINT PRIMARY KEY DEFAULT nextval('seq_estimate_id'),
    job_card_id BIGINT NOT NULL,
    version INTEGER NOT NULL CHECK (version >= 1),
    status VARCHAR NOT NULL DEFAULT 'Draft'
        CHECK (status IN ('Draft', 'Sent', 'Approved', 'Declined', 'Superseded')),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    approved_at TIMESTAMP,
    UNIQUE (job_card_id, version),
    CHECK ((status = 'Approved' AND approved_at IS NOT NULL) OR
           (status <> 'Approved' AND approved_at IS NULL))
);

CREATE TABLE estimate_items (
    id BIGINT PRIMARY KEY DEFAULT nextval('seq_estimate_item_id'),
    estimate_id BIGINT NOT NULL,
    item_type VARCHAR NOT NULL CHECK (item_type IN ('Labour', 'Part')),
    description VARCHAR NOT NULL,
    part_id BIGINT,
    quantity DECIMAL(12,2) NOT NULL DEFAULT 1 CHECK (quantity > 0),
    unit_price DECIMAL(12,2) NOT NULL CHECK (unit_price >= 0),
    CHECK ((item_type = 'Labour' AND part_id IS NULL) OR item_type = 'Part')
);

CREATE TABLE parts_used (
    id BIGINT PRIMARY KEY DEFAULT nextval('seq_parts_used_id'),
    job_card_id BIGINT NOT NULL,
    part_id BIGINT NOT NULL,
    quantity DECIMAL(12,2) NOT NULL CHECK (quantity > 0),
    unit_price DECIMAL(12,2) NOT NULL CHECK (unit_price >= 0),
    recorded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE parts_orders (
    id BIGINT PRIMARY KEY DEFAULT nextval('seq_parts_order_id'),
    part_id BIGINT NOT NULL,
    quantity_ordered DECIMAL(12,2) NOT NULL CHECK (quantity_ordered > 0),
    quantity_received DECIMAL(12,2) NOT NULL DEFAULT 0
        CHECK (quantity_received >= 0 AND quantity_received <= quantity_ordered),
    unit_cost DECIMAL(12,2) CHECK (unit_cost >= 0),
    supplier VARCHAR,
    ordered_date DATE NOT NULL DEFAULT CURRENT_DATE,
    expected_date DATE,
    received_date DATE,
    status VARCHAR NOT NULL DEFAULT 'Ordered'
        CHECK (status IN ('Ordered', 'Partially Received', 'Received', 'Cancelled')),
    notes VARCHAR,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (expected_date IS NULL OR expected_date >= ordered_date),
    CHECK (received_date IS NULL OR received_date >= ordered_date),
    CHECK ((status = 'Received' AND quantity_received = quantity_ordered AND received_date IS NOT NULL)
        OR status <> 'Received')
);

CREATE TABLE service_reminders (
    id BIGINT PRIMARY KEY DEFAULT nextval('seq_service_reminder_id'),
    customer_id BIGINT NOT NULL,
    vehicle_id BIGINT NOT NULL,
    last_service_date DATE NOT NULL,
    next_service_date DATE NOT NULL,
    reminder_sent BOOLEAN NOT NULL DEFAULT FALSE,
    reminder_sent_at TIMESTAMP,
    status VARCHAR NOT NULL DEFAULT 'Pending'
        CHECK (status IN ('Pending', 'Sent', 'Failed', 'Cancelled')),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (next_service_date >= last_service_date),
    CHECK ((status = 'Sent' AND reminder_sent AND reminder_sent_at IS NOT NULL) OR
           (status <> 'Sent' AND NOT reminder_sent AND reminder_sent_at IS NULL))
);

CREATE TABLE invoices (
    id BIGINT PRIMARY KEY DEFAULT nextval('seq_invoice_id'),
    invoice_no VARCHAR NOT NULL UNIQUE CHECK (regexp_full_match(invoice_no, '^PW-INV-[0-9]{4}-[0-9]{4,}$')),
    job_card_id BIGINT NOT NULL UNIQUE,
    issue_date DATE NOT NULL DEFAULT CURRENT_DATE,
    labour_total DECIMAL(12,2) NOT NULL DEFAULT 0 CHECK (labour_total >= 0),
    parts_total DECIMAL(12,2) NOT NULL DEFAULT 0 CHECK (parts_total >= 0),
    tax_amount DECIMAL(12,2) NOT NULL DEFAULT 0 CHECK (tax_amount >= 0),
    total DECIMAL(12,2) NOT NULL CHECK (total >= 0),
    payment_status VARCHAR NOT NULL DEFAULT 'Unpaid'
        CHECK (payment_status IN ('Unpaid', 'Partial', 'Paid')),
    amount_paid DECIMAL(12,2) NOT NULL DEFAULT 0 CHECK (amount_paid >= 0 AND amount_paid <= total),
    notes VARCHAR,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (total = labour_total + parts_total + tax_amount),
    CHECK ((payment_status = 'Unpaid' AND amount_paid = 0) OR
           (payment_status = 'Partial' AND amount_paid > 0 AND amount_paid < total) OR
           (payment_status = 'Paid' AND amount_paid = total))
);

CREATE TABLE invoice_payments (
    id BIGINT PRIMARY KEY DEFAULT nextval('seq_invoice_payment_id'),
    invoice_id BIGINT NOT NULL,
    amount DECIMAL(12,2) NOT NULL CHECK (amount > 0),
    method VARCHAR NOT NULL,
    recorded_by BIGINT REFERENCES users(id),
    paid_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE stock_adjustments (
    id BIGINT PRIMARY KEY DEFAULT nextval('seq_stock_adjustment_id'),
    part_id BIGINT NOT NULL,
    delta DECIMAL(12,2) NOT NULL CHECK (delta <> 0),
    reason VARCHAR NOT NULL,
    adjustment_type VARCHAR NOT NULL
        CHECK (adjustment_type IN ('Manual', 'Restock', 'Order Receipt')),
    parts_order_id BIGINT,
    recorded_by BIGINT REFERENCES users(id),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_customers_phone ON customers(phone);
CREATE INDEX idx_customers_email ON customers(email);
CREATE INDEX idx_vehicles_customer ON vehicles(customer_id);
CREATE INDEX idx_vehicles_vin ON vehicles(vin);
CREATE INDEX idx_vehicles_reg_number ON vehicles(reg_number);
CREATE INDEX idx_appointments_date_status ON appointments(appointment_date, status);
CREATE INDEX idx_appointments_customer ON appointments(customer_id);
CREATE INDEX idx_appointments_vehicle ON appointments(vehicle_id);
CREATE INDEX idx_job_cards_vehicle_date ON job_cards(vehicle_id, date_received);
CREATE INDEX idx_job_cards_customer_date ON job_cards(customer_id, date_received);
CREATE INDEX idx_job_cards_status ON job_cards(status);
CREATE INDEX idx_job_cards_technician ON job_cards(technician_id);
CREATE INDEX idx_job_card_job_types_type ON job_card_job_types(job_type_id);
CREATE INDEX idx_job_status_history_job_date ON job_status_history(job_card_id, changed_at);
CREATE INDEX idx_estimates_job_version ON estimates(job_card_id, version);
CREATE INDEX idx_estimate_items_estimate ON estimate_items(estimate_id);
CREATE INDEX idx_parts_used_job ON parts_used(job_card_id);
CREATE INDEX idx_parts_used_part ON parts_used(part_id);
CREATE INDEX idx_parts_orders_part_date ON parts_orders(part_id, ordered_date);
CREATE INDEX idx_parts_orders_status ON parts_orders(status);
CREATE INDEX idx_reminders_date_status ON service_reminders(next_service_date, status);
CREATE INDEX idx_reminders_vehicle ON service_reminders(vehicle_id);
CREATE INDEX idx_invoices_issue_date ON invoices(issue_date);
CREATE INDEX idx_invoices_payment_status ON invoices(payment_status);
CREATE INDEX idx_invoice_payments_invoice_date ON invoice_payments(invoice_id, paid_at);
CREATE INDEX idx_stock_adjustments_part_date ON stock_adjustments(part_id, created_at);

CREATE VIEW v_parts_to_reorder AS
SELECT p.*,
       greatest(p.reorder_level - p.quantity, 0) AS shortage_quantity,
       CASE
           WHEN p.quantity < p.reorder_level AND p.needs_ordering THEN 'Low stock and manually flagged'
           WHEN p.quantity < p.reorder_level THEN 'Low stock'
           ELSE 'Manually flagged'
       END AS reorder_reason
FROM parts p
WHERE p.quantity < p.reorder_level OR p.needs_ordering = TRUE;

CREATE VIEW v_jobs_by_status AS
SELECT status, count(*) AS job_count
FROM job_cards
GROUP BY status;

CREATE VIEW v_cars_in_house AS
SELECT jc.id AS job_card_id, jc.job_no, jc.status, jc.date_received,
       jc.expected_delivery, v.id AS vehicle_id, v.reg_number, v.brand, v.model,
       c.id AS customer_id, c.name AS customer_name, c.phone
FROM job_cards jc
JOIN vehicles v ON v.id = jc.vehicle_id
JOIN customers c ON c.id = jc.customer_id
WHERE jc.status IN ('Received', 'Diagnosed', 'Estimate Sent', 'Approved',
                    'In Progress', 'Quality Check', 'Ready for Delivery');

CREATE VIEW v_jobs_monthly_summary AS
SELECT date_trunc('month', date_received)::DATE AS period,
       count(*) AS total_jobs,
       count(*) FILTER (WHERE status = 'Delivered') AS completed_jobs,
       count(*) FILTER (WHERE status NOT IN ('Delivered', 'Declined', 'Cancelled')) AS pending_jobs,
       count(*) FILTER (WHERE status = 'Declined') AS declined_jobs,
       count(*) FILTER (WHERE status = 'Cancelled') AS cancelled_jobs
FROM job_cards
GROUP BY 1;

CREATE VIEW v_jobs_yearly_summary AS
SELECT year(date_received) AS year,
       count(*) AS total_jobs,
       count(*) FILTER (WHERE status = 'Delivered') AS completed_jobs,
       count(*) FILTER (WHERE status NOT IN ('Delivered', 'Declined', 'Cancelled')) AS pending_jobs,
       count(*) FILTER (WHERE status = 'Declined') AS declined_jobs,
       count(*) FILTER (WHERE status = 'Cancelled') AS cancelled_jobs
FROM job_cards
GROUP BY 1;

CREATE VIEW v_service_revenue_monthly AS
SELECT date_trunc('month', issue_date)::DATE AS period,
       sum(labour_total) AS labour_total,
       sum(parts_total) AS parts_total,
       sum(tax_amount) AS tax_total,
       sum(total) AS invoiced_total,
       sum(amount_paid) AS paid_total,
       sum(total - amount_paid) AS balance_due
FROM invoices
GROUP BY 1;

CREATE VIEW v_service_revenue_yearly AS
SELECT year(issue_date) AS year,
       sum(labour_total) AS labour_total,
       sum(parts_total) AS parts_total,
       sum(tax_amount) AS tax_total,
       sum(total) AS invoiced_total,
       sum(amount_paid) AS paid_total,
       sum(total - amount_paid) AS balance_due
FROM invoices
GROUP BY 1;

CREATE VIEW v_parts_usage AS
SELECT date_trunc('month', pu.recorded_at)::DATE AS period,
       p.id AS part_id, p.part_name, p.part_number,
       sum(pu.quantity) AS quantity_used,
       sum(pu.quantity * pu.unit_price) AS usage_revenue,
       count(DISTINCT pu.job_card_id) AS job_count
FROM parts_used pu
JOIN parts p ON p.id = pu.part_id
GROUP BY 1, 2, 3, 4;

CREATE VIEW v_parts_ordered AS
SELECT date_trunc('month', po.ordered_date)::DATE AS period,
       p.id AS part_id, p.part_name, p.part_number,
       sum(po.quantity_ordered) AS quantity_ordered,
       sum(po.quantity_received) AS quantity_received,
       sum(po.quantity_ordered - po.quantity_received) AS quantity_outstanding,
       sum(po.quantity_ordered * coalesce(po.unit_cost, 0)) AS purchase_value
FROM parts_orders po
JOIN parts p ON p.id = po.part_id
GROUP BY 1, 2, 3, 4;

INSERT INTO app_metadata VALUES ('schema_version', '3');

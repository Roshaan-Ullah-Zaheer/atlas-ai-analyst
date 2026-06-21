-- ============================================================
-- Atlas — sample business dataset (PostgreSQL + pgvector)
-- A realistic multi-table e-commerce + operations warehouse:
-- catalog, customers, orders, fulfillment, support, marketing.
-- Structured tables power SQL analytics; documents.embedding
-- powers semantic search via pgvector.
-- ============================================================

CREATE EXTENSION IF NOT EXISTS vector;

-- Reset (demo DB is disposable / re-seedable) ----------------
DROP TABLE IF EXISTS reviews             CASCADE;
DROP TABLE IF EXISTS returns             CASCADE;
DROP TABLE IF EXISTS shipments           CASCADE;
DROP TABLE IF EXISTS payments            CASCADE;
DROP TABLE IF EXISTS order_items         CASCADE;
DROP TABLE IF EXISTS orders              CASCADE;
DROP TABLE IF EXISTS support_tickets     CASCADE;
DROP TABLE IF EXISTS inventory           CASCADE;
DROP TABLE IF EXISTS products            CASCADE;
DROP TABLE IF EXISTS marketing_campaigns CASCADE;
DROP TABLE IF EXISTS customers           CASCADE;
DROP TABLE IF EXISTS employees           CASCADE;
DROP TABLE IF EXISTS warehouses          CASCADE;
DROP TABLE IF EXISTS suppliers           CASCADE;
DROP TABLE IF EXISTS categories          CASCADE;
DROP TABLE IF EXISTS documents           CASCADE;

-- Product taxonomy -------------------------------------------
CREATE TABLE categories (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,                       -- e.g. Audio, Bedding
    department  TEXT NOT NULL,                       -- Electronics, Home, Apparel...
    description TEXT NOT NULL
);

-- Suppliers --------------------------------------------------
CREATE TABLE suppliers (
    id                SERIAL PRIMARY KEY,
    name              TEXT          NOT NULL,
    country           TEXT          NOT NULL,
    region            TEXT          NOT NULL,         -- AMER / EMEA / APAC
    lead_time_days    INTEGER       NOT NULL,
    reliability_score NUMERIC(3,2)  NOT NULL          -- 0.00 - 1.00
);

-- Fulfillment centers ----------------------------------------
CREATE TABLE warehouses (
    id             SERIAL PRIMARY KEY,
    name           TEXT    NOT NULL,
    city           TEXT    NOT NULL,
    country        TEXT    NOT NULL,
    region         TEXT    NOT NULL,
    capacity_units INTEGER NOT NULL
);

-- Staff (sales reps, support agents, managers) ---------------
CREATE TABLE employees (
    id         SERIAL PRIMARY KEY,
    name       TEXT    NOT NULL,
    role       TEXT    NOT NULL,                      -- sales_rep / support_agent / manager
    team       TEXT    NOT NULL,
    region     TEXT    NOT NULL,
    hire_date  DATE    NOT NULL,
    manager_id INTEGER REFERENCES employees(id),
    is_active  BOOLEAN NOT NULL DEFAULT TRUE
);

-- Customers --------------------------------------------------
CREATE TABLE customers (
    id                  SERIAL PRIMARY KEY,
    name                TEXT          NOT NULL,
    email               TEXT          UNIQUE NOT NULL,
    country             TEXT          NOT NULL,
    region              TEXT          NOT NULL,       -- AMER / EMEA / APAC
    segment             TEXT          NOT NULL,       -- Consumer / SMB / Enterprise
    acquisition_channel TEXT          NOT NULL,       -- organic / paid_search / social / referral / email
    signup_date         DATE          NOT NULL,
    is_active           BOOLEAN       NOT NULL DEFAULT TRUE,
    churned             BOOLEAN       NOT NULL DEFAULT FALSE,
    churn_date          DATE,
    lifetime_value      NUMERIC(12,2) NOT NULL DEFAULT 0
);

-- Marketing campaigns ----------------------------------------
CREATE TABLE marketing_campaigns (
    id          SERIAL PRIMARY KEY,
    name        TEXT          NOT NULL,
    channel     TEXT          NOT NULL,               -- paid_search / social / email / display / affiliate
    start_date  DATE          NOT NULL,
    end_date    DATE          NOT NULL,
    budget      NUMERIC(12,2) NOT NULL,
    impressions INTEGER       NOT NULL,
    clicks      INTEGER       NOT NULL,
    conversions INTEGER       NOT NULL
);

-- Products ---------------------------------------------------
CREATE TABLE products (
    id          SERIAL PRIMARY KEY,
    name        TEXT          NOT NULL,
    category_id INTEGER       NOT NULL REFERENCES categories(id),
    supplier_id INTEGER       NOT NULL REFERENCES suppliers(id),
    sku         TEXT          UNIQUE NOT NULL,
    price       NUMERIC(10,2) NOT NULL,
    cost        NUMERIC(10,2) NOT NULL,
    launched_at DATE          NOT NULL,
    is_active   BOOLEAN       NOT NULL DEFAULT TRUE
);

-- Stock on hand per warehouse --------------------------------
CREATE TABLE inventory (
    id               SERIAL PRIMARY KEY,
    product_id       INTEGER NOT NULL REFERENCES products(id),
    warehouse_id     INTEGER NOT NULL REFERENCES warehouses(id),
    quantity_on_hand INTEGER NOT NULL,
    reorder_level    INTEGER NOT NULL,
    updated_at       DATE    NOT NULL
);

-- Orders -----------------------------------------------------
CREATE TABLE orders (
    id           SERIAL PRIMARY KEY,
    customer_id  INTEGER       NOT NULL REFERENCES customers(id),
    employee_id  INTEGER       REFERENCES employees(id),           -- sales rep (NULL = self-serve)
    warehouse_id INTEGER       NOT NULL REFERENCES warehouses(id),
    campaign_id  INTEGER       REFERENCES marketing_campaigns(id), -- attributed campaign (nullable)
    order_date   DATE          NOT NULL,
    status       TEXT          NOT NULL,             -- completed / pending / refunded / cancelled
    channel      TEXT          NOT NULL,             -- web / mobile / partner / in_store
    total_amount NUMERIC(12,2) NOT NULL
);

-- Order line items -------------------------------------------
CREATE TABLE order_items (
    id         SERIAL PRIMARY KEY,
    order_id   INTEGER       NOT NULL REFERENCES orders(id),
    product_id INTEGER       NOT NULL REFERENCES products(id),
    quantity   INTEGER       NOT NULL,
    unit_price NUMERIC(10,2) NOT NULL,
    discount   NUMERIC(10,2) NOT NULL DEFAULT 0
);

-- Payments ---------------------------------------------------
CREATE TABLE payments (
    id       SERIAL PRIMARY KEY,
    order_id INTEGER       NOT NULL REFERENCES orders(id),
    method   TEXT          NOT NULL,                 -- card / paypal / bank_transfer / apple_pay
    amount   NUMERIC(12,2) NOT NULL,
    status   TEXT          NOT NULL,                 -- captured / refunded / failed / pending
    paid_at  TIMESTAMPTZ   NOT NULL
);

-- Shipments --------------------------------------------------
CREATE TABLE shipments (
    id            SERIAL PRIMARY KEY,
    order_id      INTEGER      NOT NULL REFERENCES orders(id),
    warehouse_id  INTEGER      NOT NULL REFERENCES warehouses(id),
    carrier       TEXT         NOT NULL,             -- UPS / FedEx / DHL / USPS / Local
    status        TEXT         NOT NULL,             -- delivered / in_transit / shipped / returned
    shipped_at    DATE         NOT NULL,
    delivered_at  DATE,
    shipping_cost NUMERIC(8,2) NOT NULL
);

-- Returns ----------------------------------------------------
CREATE TABLE returns (
    id            SERIAL PRIMARY KEY,
    order_id      INTEGER       NOT NULL REFERENCES orders(id),
    product_id    INTEGER       NOT NULL REFERENCES products(id),
    reason        TEXT          NOT NULL,            -- defective / wrong_item / not_as_described / changed_mind / damaged
    quantity      INTEGER       NOT NULL,
    refund_amount NUMERIC(10,2) NOT NULL,
    status        TEXT          NOT NULL,            -- approved / pending / rejected / completed
    requested_at  DATE          NOT NULL,
    processed_at  DATE
);

-- Product reviews --------------------------------------------
CREATE TABLE reviews (
    id          SERIAL PRIMARY KEY,
    product_id  INTEGER NOT NULL REFERENCES products(id),
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    rating      INTEGER NOT NULL,                    -- 1 - 5
    title       TEXT    NOT NULL,
    body        TEXT    NOT NULL,
    created_at  DATE    NOT NULL
);

-- Support tickets --------------------------------------------
CREATE TABLE support_tickets (
    id                 SERIAL PRIMARY KEY,
    customer_id        INTEGER     NOT NULL REFERENCES customers(id),
    employee_id        INTEGER     REFERENCES employees(id),  -- assigned agent
    order_id           INTEGER     REFERENCES orders(id),
    created_at         TIMESTAMPTZ NOT NULL,
    subject            TEXT        NOT NULL,
    body               TEXT        NOT NULL,
    category           TEXT        NOT NULL,         -- billing / shipping / product / account
    priority           TEXT        NOT NULL,         -- low / medium / high
    status             TEXT        NOT NULL,         -- open / resolved / escalated
    satisfaction_score INTEGER,                      -- CSAT 1-5 (NULL until resolved)
    resolved_at        TIMESTAMPTZ
);

-- Documents (semantic search via pgvector) -------------------
-- 768-dim to match Gemini embeddings (gemini-embedding-001).
CREATE TABLE documents (
    id         SERIAL PRIMARY KEY,
    title      TEXT        NOT NULL,
    doc_type   TEXT        NOT NULL,                 -- policy / product_doc / faq / release_note
    content    TEXT        NOT NULL,
    embedding  VECTOR(768),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes ----------------------------------------------------
CREATE INDEX idx_products_category  ON products(category_id);
CREATE INDEX idx_products_supplier  ON products(supplier_id);
CREATE INDEX idx_inventory_product  ON inventory(product_id);
CREATE INDEX idx_inventory_wh       ON inventory(warehouse_id);
CREATE INDEX idx_orders_customer    ON orders(customer_id);
CREATE INDEX idx_orders_employee    ON orders(employee_id);
CREATE INDEX idx_orders_campaign    ON orders(campaign_id);
CREATE INDEX idx_orders_date        ON orders(order_date);
CREATE INDEX idx_orders_status      ON orders(status);
CREATE INDEX idx_items_order        ON order_items(order_id);
CREATE INDEX idx_items_product      ON order_items(product_id);
CREATE INDEX idx_payments_order     ON payments(order_id);
CREATE INDEX idx_shipments_order    ON shipments(order_id);
CREATE INDEX idx_returns_order      ON returns(order_id);
CREATE INDEX idx_reviews_product    ON reviews(product_id);
CREATE INDEX idx_tickets_customer   ON support_tickets(customer_id);
CREATE INDEX idx_tickets_agent      ON support_tickets(employee_id);
CREATE INDEX idx_customers_segment  ON customers(segment);
CREATE INDEX idx_customers_region   ON customers(region);
CREATE INDEX idx_documents_embed    ON documents USING hnsw (embedding vector_cosine_ops);

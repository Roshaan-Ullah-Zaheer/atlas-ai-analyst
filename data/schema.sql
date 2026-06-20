-- ============================================================
-- Atlas — sample e-commerce dataset (PostgreSQL + pgvector)
-- Generic business data: sales, customers, support, and documents.
-- Structured tables power SQL analytics; `documents.embedding`
-- powers semantic search via pgvector.
-- ============================================================

CREATE EXTENSION IF NOT EXISTS vector;

-- Reset (demo DB is disposable / re-seedable) ----------------
DROP TABLE IF EXISTS order_items   CASCADE;
DROP TABLE IF EXISTS orders        CASCADE;
DROP TABLE IF EXISTS support_tickets CASCADE;
DROP TABLE IF EXISTS documents     CASCADE;
DROP TABLE IF EXISTS products      CASCADE;
DROP TABLE IF EXISTS customers     CASCADE;

-- Customers --------------------------------------------------
CREATE TABLE customers (
    id          SERIAL PRIMARY KEY,
    name        TEXT        NOT NULL,
    email       TEXT        UNIQUE NOT NULL,
    country     TEXT        NOT NULL,
    region      TEXT        NOT NULL,              -- AMER / EMEA / APAC
    segment     TEXT        NOT NULL,              -- Consumer / SMB / Enterprise
    signup_date DATE        NOT NULL,
    is_active   BOOLEAN     NOT NULL DEFAULT TRUE,
    churned     BOOLEAN     NOT NULL DEFAULT FALSE,
    churn_date  DATE
);

-- Products ---------------------------------------------------
CREATE TABLE products (
    id          SERIAL PRIMARY KEY,
    name        TEXT          NOT NULL,
    category    TEXT          NOT NULL,            -- e.g. Apparel, Electronics
    sku         TEXT          UNIQUE NOT NULL,
    price       NUMERIC(10,2) NOT NULL,
    cost        NUMERIC(10,2) NOT NULL,
    launched_at DATE          NOT NULL
);

-- Orders -----------------------------------------------------
CREATE TABLE orders (
    id           SERIAL PRIMARY KEY,
    customer_id  INTEGER      NOT NULL REFERENCES customers(id),
    order_date   DATE         NOT NULL,
    status       TEXT         NOT NULL,            -- completed / refunded / pending
    channel      TEXT         NOT NULL,            -- web / mobile / partner
    total_amount NUMERIC(12,2) NOT NULL
);

-- Order line items -------------------------------------------
CREATE TABLE order_items (
    id         SERIAL PRIMARY KEY,
    order_id   INTEGER       NOT NULL REFERENCES orders(id),
    product_id INTEGER       NOT NULL REFERENCES products(id),
    quantity   INTEGER       NOT NULL,
    unit_price NUMERIC(10,2) NOT NULL
);

-- Support tickets --------------------------------------------
CREATE TABLE support_tickets (
    id          SERIAL PRIMARY KEY,
    customer_id INTEGER     NOT NULL REFERENCES customers(id),
    created_at  TIMESTAMPTZ NOT NULL,
    subject     TEXT        NOT NULL,
    body        TEXT        NOT NULL,
    category    TEXT        NOT NULL,              -- billing / shipping / product / account
    priority    TEXT        NOT NULL,              -- low / medium / high
    status      TEXT        NOT NULL,              -- open / resolved / escalated
    resolved_at TIMESTAMPTZ
);

-- Documents (semantic search via pgvector) -------------------
-- 768-dim to match Gemini embeddings (text-embedding-004 / gemini-embedding-001).
CREATE TABLE documents (
    id         SERIAL PRIMARY KEY,
    title      TEXT        NOT NULL,
    doc_type   TEXT        NOT NULL,               -- policy / product_doc / faq / release_note
    content    TEXT        NOT NULL,
    embedding  VECTOR(768),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes ----------------------------------------------------
CREATE INDEX idx_orders_customer   ON orders(customer_id);
CREATE INDEX idx_orders_date       ON orders(order_date);
CREATE INDEX idx_items_order       ON order_items(order_id);
CREATE INDEX idx_items_product     ON order_items(product_id);
CREATE INDEX idx_tickets_customer  ON support_tickets(customer_id);
CREATE INDEX idx_customers_segment ON customers(segment);
CREATE INDEX idx_documents_embed   ON documents USING hnsw (embedding vector_cosine_ops);

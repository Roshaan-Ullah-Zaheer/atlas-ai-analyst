"""Seed the Atlas demo database.

Creates the schema (``schema.sql``) and loads a small, clean, deterministic
e-commerce dataset: customers, products, orders + items, support tickets, and
a set of company documents embedded with Gemini for semantic search.

Run from the project root:  python data/seed.py
"""

from __future__ import annotations

import random
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

import psycopg
from pgvector.psycopg import register_vector

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import config, llm  # noqa: E402

random.seed(42)
TODAY = date(2026, 6, 1)

FIRST = ["Ava", "Liam", "Noah", "Emma", "Oliver", "Sophia", "Mia", "Lucas", "Aria", "Ethan",
         "Isla", "Mateo", "Zara", "Omar", "Yuki", "Chen", "Priya", "Diego", "Lena", "Kai",
         "Nadia", "Tomas", "Sara", "Hugo", "Mila", "Arjun", "Freya", "Ivan", "Leah", "Marco"]
LAST = ["Patel", "Smith", "Garcia", "Kim", "Muller", "Rossi", "Khan", "Nguyen", "Silva", "Ahmed",
        "Johnson", "Lopez", "Wang", "Dubois", "Schmidt", "Ivanov", "Costa", "Yamamoto", "Brown", "Haddad"]

# country -> region
COUNTRIES = {
    "United States": "AMER", "Canada": "AMER", "Brazil": "AMER", "Mexico": "AMER",
    "United Kingdom": "EMEA", "Germany": "EMEA", "France": "EMEA", "UAE": "EMEA", "Nigeria": "EMEA",
    "India": "APAC", "Japan": "APAC", "Australia": "APAC", "Singapore": "APAC",
}
SEGMENTS = ["Consumer"] * 6 + ["SMB"] * 3 + ["Enterprise"]

PRODUCTS = [
    ("Aero Wireless Earbuds", "Electronics", 129.00, 54.00),
    ("Pulse Smartwatch 2", "Electronics", 249.00, 110.00),
    ("Lumen 4K Webcam", "Electronics", 89.00, 33.00),
    ("Nimbus Noise-Cancel Headphones", "Electronics", 199.00, 82.00),
    ("Volt Power Bank 20k", "Electronics", 49.00, 18.00),
    ("Terra Hiking Backpack", "Outdoor", 119.00, 47.00),
    ("Summit Insulated Bottle", "Outdoor", 34.00, 11.00),
    ("Drift Camping Tent 2P", "Outdoor", 179.00, 78.00),
    ("Trail Running Jacket", "Apparel", 99.00, 38.00),
    ("Everyday Merino Tee", "Apparel", 45.00, 15.00),
    ("Glide Yoga Mat", "Fitness", 59.00, 21.00),
    ("Forge Adjustable Dumbbells", "Fitness", 299.00, 140.00),
    ("Flow Resistance Band Set", "Fitness", 29.00, 8.00),
    ("Hearth Ceramic Mug Set", "Home", 39.00, 13.00),
    ("Glow Smart Desk Lamp", "Home", 69.00, 26.00),
    ("Calm Linen Duvet", "Home", 149.00, 60.00),
    ("Brew Pour-Over Kit", "Home", 54.00, 19.00),
    ("Pure Vitamin C Serum", "Beauty", 38.00, 11.00),
    ("Silk Hydrating Cream", "Beauty", 44.00, 14.00),
    ("Bloom Gift Box", "Beauty", 79.00, 28.00),
    ("Sprout Indoor Planter", "Home", 32.00, 10.00),
    ("Atlas Travel Cube Set", "Outdoor", 42.00, 14.00),
    ("Echo Bluetooth Speaker", "Electronics", 79.00, 30.00),
    ("Zen Meditation Cushion", "Fitness", 49.00, 16.00),
]

TICKET_TEMPLATES = {
    "shipping": [
        ("Where is my order?", "My order was supposed to arrive last week but the tracking hasn't updated in five days. Can you check the carrier status?"),
        ("Package arrived damaged", "The box was crushed and the {p} inside has a cracked casing. I'd like a replacement shipped."),
        ("Wrong item delivered", "I ordered the {p} but received a completely different product. Please advise on the return."),
    ],
    "billing": [
        ("Double charged for my order", "I was charged twice for the same order on my card. Please refund the duplicate charge."),
        ("Refund not received", "It's been two weeks since my refund was approved for the {p} and I still don't see it on my statement."),
        ("Invoice request", "Could you send a VAT invoice for my recent purchase? I need it for expense reporting."),
    ],
    "product": [
        ("{p} won't turn on", "My {p} stopped powering on after a week. I've tried charging it overnight with no luck."),
        ("Battery drains fast", "The battery on the {p} barely lasts a few hours now. Is this covered under warranty?"),
        ("How do I pair this?", "I can't get the {p} to connect over Bluetooth. The setup guide isn't clear."),
    ],
    "account": [
        ("Can't log in", "I'm locked out of my account and the password reset email never arrives."),
        ("Update billing address", "I moved and need to change the billing address on my account."),
        ("Cancel my subscription", "Please cancel my recurring subscription effective next cycle."),
    ],
}

DOCUMENTS = [
    ("Refund Policy", "policy",
     "Refunds are issued to the original payment method within 5–7 business days of approval. "
     "Items must be returned within 30 days of delivery in original condition. Final-sale and "
     "personal-care items (e.g., serums, creams) are non-refundable for hygiene reasons. "
     "Shipping fees are non-refundable unless the return is due to our error."),
    ("Shipping Policy", "policy",
     "Standard shipping takes 3–5 business days within a region and is free on orders over $75. "
     "Express shipping (1–2 days) is available at checkout. International orders may take 7–14 "
     "business days and can incur customs duties paid by the recipient. Tracking is emailed once "
     "the carrier scans the package."),
    ("Warranty Terms", "policy",
     "Electronics carry a 12-month limited warranty covering manufacturing defects. Fitness "
     "equipment carries a 24-month warranty on the frame. Warranty does not cover accidental "
     "damage, water damage beyond the rated IP level, or normal wear. Approved warranty claims "
     "are repaired or replaced at no cost."),
    ("Returns FAQ", "faq",
     "To start a return, open your order in the account portal and select 'Return item'. Print the "
     "prepaid label and drop the package at any partner location. Refunds are processed after the "
     "warehouse inspects the item, usually within 3 business days of receipt."),
    ("Aero Wireless Earbuds — Product Guide", "product_doc",
     "The Aero Wireless Earbuds offer 6 hours of playback (24 with the case), IPX4 sweat resistance, "
     "and Bluetooth 5.3. To pair, open the case lid near your device and hold the case button for "
     "3 seconds until the light flashes white. A firmware update improves call clarity."),
    ("Pulse Smartwatch 2 — Product Guide", "product_doc",
     "Pulse Smartwatch 2 tracks heart rate, sleep, and 30+ workout types, with a 7-day battery and "
     "5 ATM water resistance. It is not rated for scuba diving. Charge via the magnetic puck; a full "
     "charge takes about 90 minutes."),
    ("Nimbus Headphones — Product Guide", "product_doc",
     "Nimbus Noise-Cancel Headphones deliver up to 30 hours of battery with ANC on. Hold the power "
     "button for 5 seconds to enter pairing mode. Use the companion app to adjust the ANC level and "
     "EQ presets."),
    ("Forge Dumbbells — Safety & Care", "product_doc",
     "Forge Adjustable Dumbbells adjust from 5 to 52.5 lbs per hand. Always set the dial fully into a "
     "weight notch before lifting and store the dumbbells in their cradles. Wipe with a dry cloth; do "
     "not submerge in water."),
    ("Order Cancellation Policy", "policy",
     "Orders can be cancelled for a full refund any time before they enter the 'shipped' status. "
     "Once shipped, treat the order as a return. Subscription orders can be paused or cancelled before "
     "the next billing date with no penalty."),
    ("Damaged or Defective Items", "faq",
     "If an item arrives damaged or defective, report it within 14 days with a photo. We ship a "
     "replacement immediately at no cost and email a prepaid label for the damaged unit. You are not "
     "charged for the replacement."),
    ("Support SLA", "policy",
     "Support targets a first response within 24 hours for standard tickets and within 4 hours for "
     "high-priority issues such as billing errors or safety concerns. Escalated tickets are reviewed "
     "by a senior agent within one business day."),
    ("Loyalty & Discounts", "faq",
     "Members earn 1 point per dollar spent; 100 points equal a $5 reward. New customers get 10% off "
     "their first order. Enterprise accounts receive volume pricing on orders above 50 units."),
    ("Data & Privacy Summary", "policy",
     "We store order history, contact details, and support interactions to fulfill orders and provide "
     "support. We do not sell personal data. Customers may request export or deletion of their data "
     "through the account portal."),
    ("Release Notes — App v4.2", "release_note",
     "App v4.2 adds order tracking notifications, a redesigned returns flow, and faster checkout. It "
     "fixes a bug where refund status could show as pending after completion, and improves Bluetooth "
     "pairing reliability for the Aero Earbuds."),
    ("Price Match Policy", "policy",
     "We match the lower advertised price of an identical, in-stock item from a major retailer within "
     "14 days of purchase. Marketplace and auction listings are excluded. Submit the competitor link "
     "through support to claim the difference as store credit."),
    ("Gift Returns FAQ", "faq",
     "Gift recipients can return items for store credit without notifying the purchaser. Use the gift "
     "receipt number from the packing slip to start the return in the portal."),
]


def _rand_date(start: date, end: date) -> date:
    return start + timedelta(days=random.randint(0, (end - start).days))


def main() -> None:
    missing = config.missing_keys()
    if missing:
        raise SystemExit(f"Missing config: {missing}")

    schema_sql = (Path(__file__).resolve().parent / "schema.sql").read_text(encoding="utf-8")

    print("Connecting to Neon…")
    with psycopg.connect(config.DATABASE_URL, connect_timeout=30) as conn:
        register_vector(conn)
        with conn.cursor() as cur:
            print("Applying schema…")
            cur.execute(schema_sql)

            # --- products ---
            product_ids: list[int] = []
            for i, (name, cat, price, cost) in enumerate(PRODUCTS, start=1):
                sku = f"{cat[:3].upper()}-{i:03d}"
                launched = _rand_date(date(2023, 1, 1), date(2025, 6, 1))
                cur.execute(
                    "INSERT INTO products (name, category, sku, price, cost, launched_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
                    (name, cat, sku, price, cost, launched),
                )
                product_ids.append(cur.fetchone()[0])

            # --- customers ---
            customer_ids: list[int] = []
            used_emails: set[str] = set()
            for _ in range(120):
                fn, ln = random.choice(FIRST), random.choice(LAST)
                base = f"{fn}.{ln}".lower()
                email = f"{base}{random.randint(1, 999)}@example.com"
                while email in used_emails:
                    email = f"{base}{random.randint(1, 9999)}@example.com"
                used_emails.add(email)
                country = random.choice(list(COUNTRIES))
                region = COUNTRIES[country]
                segment = random.choice(SEGMENTS)
                signup = _rand_date(date(2023, 1, 1), date(2026, 3, 1))
                churned = random.random() < 0.18
                churn_dt = _rand_date(signup + timedelta(days=30), TODAY) if churned else None
                cur.execute(
                    "INSERT INTO customers (name, email, country, region, segment, signup_date, "
                    "is_active, churned, churn_date) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                    (f"{fn} {ln}", email, country, region, segment, signup,
                     not churned, churned, churn_dt),
                )
                customer_ids.append(cur.fetchone()[0])

            # --- orders + items ---
            order_count = 0
            item_count = 0
            for cid in customer_ids:
                n_orders = random.choices([0, 1, 2, 3, 5, 8], weights=[1, 3, 4, 3, 2, 1])[0]
                for _ in range(n_orders):
                    odate = _rand_date(date(2024, 6, 1), TODAY)
                    status = random.choices(["completed", "refunded", "pending"], weights=[85, 8, 7])[0]
                    channel = random.choices(["web", "mobile", "partner"], weights=[55, 35, 10])[0]
                    cur.execute(
                        "INSERT INTO orders (customer_id, order_date, status, channel, total_amount) "
                        "VALUES (%s,%s,%s,%s,%s) RETURNING id",
                        (cid, odate, status, channel, 0),
                    )
                    oid = cur.fetchone()[0]
                    order_count += 1
                    total = 0.0
                    for pid in random.sample(product_ids, k=random.randint(1, 4)):
                        idx = product_ids.index(pid)
                        unit = float(PRODUCTS[idx][2])
                        qty = random.randint(1, 3)
                        cur.execute(
                            "INSERT INTO order_items (order_id, product_id, quantity, unit_price) "
                            "VALUES (%s,%s,%s,%s)",
                            (oid, pid, qty, unit),
                        )
                        total += unit * qty
                        item_count += 1
                    cur.execute("UPDATE orders SET total_amount=%s WHERE id=%s", (round(total, 2), oid))

            # --- support tickets ---
            ticket_count = 0
            for _ in range(140):
                cid = random.choice(customer_ids)
                category = random.choice(list(TICKET_TEMPLATES))
                subject, body = random.choice(TICKET_TEMPLATES[category])
                product_name = random.choice(PRODUCTS)[0]
                subject = subject.replace("{p}", product_name)
                body = body.replace("{p}", product_name)
                priority = random.choices(["low", "medium", "high"], weights=[40, 40, 20])[0]
                status = random.choices(["resolved", "open", "escalated"], weights=[65, 25, 10])[0]
                created = datetime.combine(_rand_date(date(2025, 1, 1), TODAY),
                                           time(random.randint(7, 20), random.randint(0, 59)))
                resolved = (created + timedelta(hours=random.randint(2, 96))) if status == "resolved" else None
                cur.execute(
                    "INSERT INTO support_tickets (customer_id, created_at, subject, body, category, "
                    "priority, status, resolved_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (cid, created, subject, body, category, priority, status, resolved),
                )
                ticket_count += 1

            # --- documents (+ embeddings) ---
            print(f"Embedding {len(DOCUMENTS)} documents with Gemini…")
            texts = [f"{title}\n\n{content}" for title, _, content in DOCUMENTS]
            vectors = llm.embed_documents(texts)
            assert len(vectors[0]) == config.EMBED_DIM, f"embedding dim {len(vectors[0])} != {config.EMBED_DIM}"
            for (title, doc_type, content), vec in zip(DOCUMENTS, vectors):
                cur.execute(
                    "INSERT INTO documents (title, doc_type, content, embedding) VALUES (%s,%s,%s,%s)",
                    (title, doc_type, content, vec),
                )

        conn.commit()
        with conn.cursor() as cur:
            counts = {}
            for table in ("customers", "products", "orders", "order_items", "support_tickets", "documents"):
                cur.execute(f"SELECT count(*) FROM {table}")
                counts[table] = cur.fetchone()[0]
    print("Seeded:", ", ".join(f"{k}={v}" for k, v in counts.items()))
    print("Done.")


if __name__ == "__main__":
    main()

"""Seed the Atlas demo database.

Creates the schema (``schema.sql``) and loads a sizable, clean, deterministic
business dataset across 16 related tables — catalog, customers, orders,
fulfillment, support, and marketing — plus company documents embedded with
Gemini for semantic search. Rows are generated in memory with explicit ids so
the whole dataset can be bulk-loaded with COPY (fast, even over the network).

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


# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------
FIRST = ["Ava", "Liam", "Noah", "Emma", "Oliver", "Sophia", "Mia", "Lucas", "Aria", "Ethan",
         "Isla", "Mateo", "Zara", "Omar", "Yuki", "Chen", "Priya", "Diego", "Lena", "Kai",
         "Nadia", "Tomas", "Sara", "Hugo", "Mila", "Arjun", "Freya", "Ivan", "Leah", "Marco",
         "Ines", "Pablo", "Anya", "Theo", "Rhea", "Felix", "Maya", "Cole", "Nina", "Reza"]
LAST = ["Patel", "Smith", "Garcia", "Kim", "Muller", "Rossi", "Khan", "Nguyen", "Silva", "Ahmed",
        "Johnson", "Lopez", "Wang", "Dubois", "Schmidt", "Ivanov", "Costa", "Yamamoto", "Brown", "Haddad",
        "Novak", "Reyes", "Okafor", "Andersen", "Ferrari", "Walsh", "Tanaka", "Mbeki", "Petrov", "Cohen"]

COUNTRIES = {
    "United States": "AMER", "Canada": "AMER", "Brazil": "AMER", "Mexico": "AMER",
    "United Kingdom": "EMEA", "Germany": "EMEA", "France": "EMEA", "UAE": "EMEA", "Nigeria": "EMEA",
    "India": "APAC", "Japan": "APAC", "Australia": "APAC", "Singapore": "APAC",
}
SEGMENTS = ["Consumer"] * 6 + ["SMB"] * 3 + ["Enterprise"]
ACQ_CHANNELS = ["organic", "paid_search", "social", "referral", "email"]

CATEGORY_DEFS = [
    ("Audio", "Electronics"), ("Wearables", "Electronics"),
    ("Computing Accessories", "Electronics"), ("Cameras", "Electronics"),
    ("Kitchen", "Home"), ("Bedding", "Home"), ("Lighting", "Home"), ("Decor", "Home"),
    ("Activewear", "Apparel"), ("Outerwear", "Apparel"),
    ("Strength", "Fitness"), ("Recovery", "Fitness"), ("Cardio", "Fitness"),
    ("Camping", "Outdoor"), ("Travel", "Outdoor"),
    ("Skincare", "Beauty"),
]

NOUNS = {
    "Audio": ["Wireless Earbuds", "Noise-Cancel Headphones", "Bluetooth Speaker", "Studio Monitor", "Soundbar"],
    "Wearables": ["Smartwatch", "Fitness Band", "GPS Watch", "Sleep Ring"],
    "Computing Accessories": ["4K Webcam", "Mechanical Keyboard", "Wireless Mouse", "USB-C Hub", "Laptop Stand"],
    "Cameras": ["Action Camera", "Mirrorless Lens", "Tripod Kit", "Camera Bag"],
    "Kitchen": ["Pour-Over Kit", "Ceramic Mug Set", "Chef Knife", "Cast Iron Pan", "Countertop Blender"],
    "Bedding": ["Linen Duvet", "Memory Pillow", "Cotton Sheet Set", "Weighted Blanket"],
    "Lighting": ["Smart Desk Lamp", "Floor Lamp", "LED Light Strip", "Scented Candle Set"],
    "Decor": ["Indoor Planter", "Wall Art Print", "Woven Throw Rug", "Ceramic Vase Set"],
    "Activewear": ["Merino Tee", "Training Shorts", "Compression Leggings", "Performance Hoodie"],
    "Outerwear": ["Running Jacket", "Rain Shell", "Insulated Vest", "Packable Windbreaker"],
    "Strength": ["Adjustable Dumbbells", "Cast Kettlebell", "Resistance Band Set", "Pull-Up Bar"],
    "Recovery": ["Massage Gun", "Foam Roller", "Meditation Cushion", "Yoga Mat"],
    "Cardio": ["Speed Jump Rope", "Spin Pedals", "Rowing Handle"],
    "Camping": ["Camping Tent 2P", "Sleeping Bag", "Camp Stove", "Hiking Backpack"],
    "Travel": ["Travel Cube Set", "Insulated Bottle", "Carry-On Backpack", "Neck Pillow"],
    "Skincare": ["Vitamin C Serum", "Hydrating Cream", "Cleansing Balm", "Gift Box"],
}

ADJ = ["Aero", "Pulse", "Lumen", "Nimbus", "Volt", "Terra", "Summit", "Drift", "Glide", "Forge",
       "Flow", "Hearth", "Glow", "Calm", "Brew", "Pure", "Silk", "Bloom", "Sprout", "Atlas",
       "Echo", "Zen", "Vertex", "Nova", "Orbit", "Cedar", "Ember", "Frost", "Halo", "Ridge",
       "Slate", "Tide", "Wisp", "Apex", "Cove", "Dune", "Fable", "Grove", "Lyra", "Onyx"]

PRICE_RANGE = {
    "Electronics": (39, 349), "Home": (24, 199), "Apparel": (29, 149),
    "Fitness": (19, 329), "Outdoor": (24, 219), "Beauty": (18, 99),
}

CARRIERS = {  # carrier -> (min_days, max_days) transit time
    "UPS": (2, 5), "FedEx": (2, 4), "DHL": (3, 7), "USPS": (4, 9), "Local": (1, 3),
}

RETURN_REASONS = ["defective", "wrong_item", "not_as_described", "changed_mind", "damaged"]

REVIEW_TITLES = {
    5: ["Absolutely love it", "Exceeded expectations", "Best purchase this year", "Worth every penny"],
    4: ["Really good", "Happy with it", "Solid choice", "Great value"],
    3: ["It's fine", "Does the job", "Okay overall", "Mixed feelings"],
    2: ["Disappointing", "Not great", "Expected more", "Underwhelming"],
    1: ["Would not recommend", "Stopped working", "Very poor", "Returned it"],
}
REVIEW_BODIES = {
    5: "Quality is excellent and it works exactly as described. Shipping was fast and setup was painless.",
    4: "Good product overall with only minor nitpicks. I'd buy from this store again.",
    3: "It's acceptable for the price but nothing special. A few things could be better.",
    2: "It works but the quality feels off and it didn't fully match the description.",
    1: "Had problems out of the box and the experience was frustrating. Not what I hoped for.",
}

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
     "Refunds are issued to the original payment method within 5-7 business days of approval. "
     "Items must be returned within 30 days of delivery in original condition. Final-sale and "
     "personal-care items (e.g., serums, creams) are non-refundable for hygiene reasons. "
     "Shipping fees are non-refundable unless the return is due to our error."),
    ("Shipping Policy", "policy",
     "Standard shipping takes 3-5 business days within a region and is free on orders over $75. "
     "Express shipping (1-2 days) is available at checkout. International orders may take 7-14 "
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
    ("Price Match Policy", "policy",
     "We match the lower advertised price of an identical, in-stock item from a major retailer within "
     "14 days of purchase. Marketplace and auction listings are excluded. Submit the competitor link "
     "through support to claim the difference as store credit."),
    ("Gift Returns FAQ", "faq",
     "Gift recipients can return items for store credit without notifying the purchaser. Use the gift "
     "receipt number from the packing slip to start the return in the portal."),
    ("Shipping Carriers & Delivery Estimates", "policy",
     "We ship via UPS, FedEx, DHL, USPS, and regional Local couriers. UPS and FedEx are fastest at "
     "2-5 business days; DHL handles most international lanes at 3-7 days; USPS is the economy option "
     "at 4-9 days; Local couriers offer same-region delivery in 1-3 days. Carrier is chosen by "
     "destination and service level."),
    ("Free Shipping Threshold", "faq",
     "Orders of $75 or more qualify for free standard shipping within the same region. Express and "
     "international upgrades are charged separately. The threshold is calculated after discounts and "
     "before tax."),
    ("Volume & Enterprise Pricing", "policy",
     "Enterprise customers receive tiered volume discounts: 5% off at 50 units, 10% at 200 units, and "
     "custom pricing above 1,000 units. A dedicated account manager handles quotes and net-30 terms "
     "for approved accounts."),
    ("Subscription & Auto-Replenish", "faq",
     "Auto-replenish lets customers schedule recurring deliveries of consumables (e.g., skincare) at "
     "10% off. Subscriptions can be paused, skipped, or cancelled any time before the next billing "
     "date with no penalty."),
    ("Inventory & Backorder Policy", "policy",
     "When an item is out of stock, customers can place a backorder and are charged only when the item "
     "ships. Reorder levels trigger automatic replenishment from the supplier; lead times vary by "
     "supplier and are shown at checkout for backordered items."),
    ("Aero Wireless Earbuds — Product Guide", "product_doc",
     "The Aero Wireless Earbuds offer 6 hours of playback (24 with the case), IPX4 sweat resistance, "
     "and Bluetooth 5.3. To pair, open the case lid near your device and hold the case button for "
     "3 seconds until the light flashes white. A firmware update improves call clarity."),
    ("Pulse Smartwatch — Product Guide", "product_doc",
     "The Pulse Smartwatch tracks heart rate, sleep, and 30+ workout types, with a 7-day battery and "
     "5 ATM water resistance. It is not rated for scuba diving. Charge via the magnetic puck; a full "
     "charge takes about 90 minutes."),
    ("Nimbus Noise-Cancel Headphones — Product Guide", "product_doc",
     "Nimbus Noise-Cancel Headphones deliver up to 30 hours of battery with ANC on. Hold the power "
     "button for 5 seconds to enter pairing mode. Use the companion app to adjust the ANC level and "
     "EQ presets."),
    ("Forge Adjustable Dumbbells — Safety & Care", "product_doc",
     "Forge Adjustable Dumbbells adjust from 5 to 52.5 lbs per hand. Always set the dial fully into a "
     "weight notch before lifting and store the dumbbells in their cradles. Wipe with a dry cloth; do "
     "not submerge in water."),
    ("Vitamin C Serum — Usage Guide", "product_doc",
     "Apply 3-4 drops of the Vitamin C Serum to clean, dry skin each morning before moisturizer and "
     "sunscreen. Store away from direct sunlight. A slight tingle is normal; discontinue if irritation "
     "persists. Skincare items are final-sale for hygiene reasons."),
    ("Release Notes — App v4.2", "release_note",
     "App v4.2 adds order tracking notifications, a redesigned returns flow, and faster checkout. It "
     "fixes a bug where refund status could show as pending after completion, and improves Bluetooth "
     "pairing reliability for the Aero Earbuds."),
    ("Release Notes — App v4.3", "release_note",
     "App v4.3 introduces saved payment methods, a wishlist, and Apple Pay at checkout. Performance on "
     "the order history screen is significantly faster, and we fixed a rare crash when applying two "
     "discount codes."),
    ("Payment Methods", "faq",
     "We accept major credit and debit cards, PayPal, Apple Pay, and bank transfer for enterprise "
     "accounts. Payments are captured when the order ships. Failed payments are retried once before "
     "the order is held."),
    ("Account Security", "faq",
     "Protect your account with a strong, unique password and enable two-factor authentication in "
     "settings. We never ask for your password by email. Report suspicious activity to support "
     "immediately and we will lock the account pending review."),
    ("Sustainability Commitment", "policy",
     "We use recyclable packaging, consolidate shipments to reduce emissions, and partner with "
     "suppliers that meet our responsible-sourcing standards. Returned items in resalable condition "
     "are restocked rather than discarded."),
    ("Wholesale & Partner Channel", "policy",
     "Approved partners resell our catalog through the partner channel at wholesale pricing with net-30 "
     "terms. Partner orders ship from the nearest regional warehouse and are excluded from consumer "
     "promotions and loyalty points."),
    ("Black Friday & Seasonal Sales", "faq",
     "Seasonal promotions run during Black Friday, end-of-year, and mid-year events. Discounts apply "
     "automatically at checkout and stack with loyalty rewards but not with price-match credit. "
     "Final-sale items remain non-refundable during promotions."),
    ("Damaged in Transit Claims", "faq",
     "If a shipment arrives damaged, keep the packaging and report it within 14 days with photos. We "
     "file the carrier claim on your behalf and ship a replacement immediately; you are never charged "
     "for carrier-caused damage."),
    ("International Orders & Customs", "policy",
     "International orders may be subject to import duties and taxes set by the destination country, "
     "payable by the recipient on delivery. Delivery estimates exclude customs processing time, which "
     "varies by country."),
    ("Workout Recovery Guide", "product_doc",
     "For best results with recovery tools: use the Massage Gun for 1-2 minutes per muscle group, roll "
     "each area on the Foam Roller for 30-60 seconds, and avoid using percussion therapy directly on "
     "bones or joints. Stay hydrated after sessions."),
]


def _rand_date(start: date, end: date) -> date:
    if end <= start:
        return start
    return start + timedelta(days=random.randint(0, (end - start).days))


# ---------------------------------------------------------------------------
# Generate the whole dataset in memory (explicit ids -> bulk COPY)
# ---------------------------------------------------------------------------
def generate() -> dict[str, list[tuple]]:
    cat_index: dict[str, int] = {}
    categories: list[tuple] = []
    dept_of: dict[str, str] = {}
    for i, (name, dept) in enumerate(CATEGORY_DEFS, start=1):
        cat_index[name] = i
        dept_of[name] = dept
        categories.append((i, name, dept, f"{name} products in the {dept} department."))

    # suppliers
    sup_words = ["Apex", "Vertex", "Northwind", "Harbor", "Summit", "Pioneer", "Crestline", "Evergreen",
                 "Meridian", "Keystone", "Brightway", "Cascade", "Ironwood", "Lighthouse", "Trailhead"]
    suppliers: list[tuple] = []
    for i, w in enumerate(sup_words, start=1):
        country = random.choice(list(COUNTRIES))
        suppliers.append((i, f"{w} Supply Co.", country, COUNTRIES[country],
                          random.randint(3, 45), round(random.uniform(0.70, 0.99), 2)))
    supplier_ids = [s[0] for s in suppliers]

    # warehouses
    wh_defs = [
        ("Newark DC", "Newark", "United States", "AMER"),
        ("Dallas DC", "Dallas", "United States", "AMER"),
        ("Rotterdam DC", "Rotterdam", "France", "EMEA"),
        ("Dubai DC", "Dubai", "UAE", "EMEA"),
        ("Singapore DC", "Singapore", "Singapore", "APAC"),
        ("Sydney DC", "Sydney", "Australia", "APAC"),
    ]
    warehouses: list[tuple] = []
    for i, (name, city, country, region) in enumerate(wh_defs, start=1):
        warehouses.append((i, name, city, country, region, random.randint(20000, 90000)))
    wh_by_region: dict[str, list[int]] = {}
    for w in warehouses:
        wh_by_region.setdefault(w[4], []).append(w[0])

    # employees: managers per region, then reps + agents reporting to them
    employees: list[tuple] = []
    eid = 0
    regions = ["AMER", "EMEA", "APAC"]
    region_managers: dict[str, int] = {}
    for region in regions:
        eid += 1
        fn, ln = random.choice(FIRST), random.choice(LAST)
        hire = _rand_date(date(2019, 1, 1), date(2022, 6, 1))
        employees.append((eid, f"{fn} {ln}", "manager", f"{region} Leadership", region, hire, None, True))
        region_managers[region] = eid
    sales_reps_by_region: dict[str, list[int]] = {r: [] for r in regions}
    support_agents: list[int] = []
    for region in regions:
        for _ in range(6):  # 6 sales reps per region
            eid += 1
            fn, ln = random.choice(FIRST), random.choice(LAST)
            hire = _rand_date(date(2021, 1, 1), date(2025, 6, 1))
            employees.append((eid, f"{fn} {ln}", "sales_rep", f"{region} Sales", region, hire,
                              region_managers[region], random.random() > 0.05))
            sales_reps_by_region[region].append(eid)
        for _ in range(5):  # 5 support agents per region
            eid += 1
            fn, ln = random.choice(FIRST), random.choice(LAST)
            hire = _rand_date(date(2021, 1, 1), date(2025, 9, 1))
            employees.append((eid, f"{fn} {ln}", "support_agent", f"{region} Support", region, hire,
                              region_managers[region], random.random() > 0.05))
            support_agents.append(eid)

    # marketing campaigns
    campaigns: list[tuple] = []
    camp_channels = ["paid_search", "social", "email", "display", "affiliate"]
    camp_themes = ["Spring Launch", "Summer Sale", "Back to School", "Black Friday", "Holiday",
                   "New Year", "Flash Deal", "Loyalty Boost", "Win-Back", "Brand Awareness",
                   "Product Spotlight", "Clearance"]
    cid = 0
    for theme in camp_themes:
        for _ in range(2):
            cid += 1
            channel = random.choice(camp_channels)
            start = _rand_date(date(2024, 1, 1), date(2026, 3, 1))
            end = start + timedelta(days=random.randint(14, 60))
            budget = round(random.uniform(2000, 40000), 2)
            impressions = random.randint(50_000, 2_000_000)
            clicks = int(impressions * random.uniform(0.005, 0.05))
            conversions = int(clicks * random.uniform(0.01, 0.08))
            campaigns.append((cid, f"{theme} {channel.replace('_', ' ').title()}", channel,
                              start, end, budget, impressions, clicks, conversions))
    campaign_ids = [c[0] for c in campaigns]

    # products
    products: list[tuple] = []
    pid = 0
    product_price: dict[int, float] = {}
    for cat_name, nouns in NOUNS.items():
        cat_id = cat_index[cat_name]
        dept = dept_of[cat_name]
        adjs = random.sample(ADJ, len(nouns))
        lo, hi = PRICE_RANGE[dept]
        for adj, noun in zip(adjs, nouns):
            pid += 1
            name = f"{adj} {noun}"
            price = round(random.uniform(lo, hi), 2)
            cost = round(price * random.uniform(0.35, 0.55), 2)
            launched = _rand_date(date(2022, 1, 1), date(2025, 9, 1))
            sku = f"{dept[:3].upper()}-{pid:04d}"
            products.append((pid, name, cat_id, random.choice(supplier_ids), sku, price, cost, launched, True))
            product_price[pid] = price
    product_ids = [p[0] for p in products]

    # inventory: each product stocked in 2-4 warehouses
    inventory: list[tuple] = []
    inv_id = 0
    for p in product_ids:
        for w in random.sample([wh[0] for wh in warehouses], k=random.randint(2, 4)):
            inv_id += 1
            inventory.append((inv_id, p, w, random.randint(0, 1500), random.choice([25, 50, 100, 150]),
                              _rand_date(date(2026, 3, 1), TODAY)))

    # customers
    customers: list[tuple] = []
    used_emails: set[str] = set()
    customer_region: dict[int, str] = {}
    cust_id = 0
    for _ in range(600):
        cust_id += 1
        fn, ln = random.choice(FIRST), random.choice(LAST)
        base = f"{fn}.{ln}".lower()
        email = f"{base}{random.randint(1, 999)}@example.com"
        while email in used_emails:
            email = f"{base}{random.randint(1, 99999)}@example.com"
        used_emails.add(email)
        country = random.choice(list(COUNTRIES))
        region = COUNTRIES[country]
        segment = random.choice(SEGMENTS)
        signup = _rand_date(date(2023, 1, 1), date(2026, 3, 1))
        churned = random.random() < 0.17
        churn_dt = _rand_date(signup + timedelta(days=30), TODAY) if churned else None
        customer_region[cust_id] = region
        # lifetime_value filled in after orders are generated
        customers.append([cust_id, f"{fn} {ln}", email, country, region, segment,
                          random.choice(ACQ_CHANNELS), signup, not churned, churned, churn_dt, 0.0])
    customer_ids = [c[0] for c in customers]

    # orders + items + payments + shipments + returns
    orders: list[tuple] = []
    order_items: list[tuple] = []
    payments: list[tuple] = []
    shipments: list[tuple] = []
    returns: list[tuple] = []
    ltv: dict[int, float] = {c: 0.0 for c in customer_ids}

    oid = 0
    item_id = 0
    pay_id = 0
    ship_id = 0
    ret_id = 0
    # weight customers so a minority order a lot (realistic long tail)
    order_target = 2500
    while oid < order_target:
        cid_c = random.choice(customer_ids)
        n_orders = random.choices([1, 2, 3, 5], weights=[5, 3, 2, 1])[0]
        for _ in range(n_orders):
            if oid >= order_target:
                break
            oid += 1
            region = customer_region[cid_c]
            odate = _rand_date(date(2024, 6, 1), TODAY)
            status = random.choices(["completed", "pending", "refunded", "cancelled"],
                                    weights=[76, 9, 9, 6])[0]
            channel = random.choices(["web", "mobile", "partner", "in_store"], weights=[48, 33, 11, 8])[0]
            wh = random.choice(wh_by_region.get(region, [w[0] for w in warehouses]))
            employee = None if random.random() < 0.6 else random.choice(sales_reps_by_region[region])
            campaign = random.choice(campaign_ids) if random.random() < 0.45 else None

            # line items
            total = 0.0
            chosen = random.sample(product_ids, k=random.randint(1, 5))
            order_line_products: list[tuple[int, float, int]] = []
            for p in chosen:
                item_id += 1
                qty = random.randint(1, 4)
                unit = product_price[p]
                discount = round(unit * qty * random.choice([0, 0, 0, 0.1, 0.15, 0.2]), 2)
                order_items.append((item_id, oid, p, qty, unit, discount))
                line = unit * qty - discount
                total += line
                order_line_products.append((p, line, qty))
            total = round(total, 2)
            orders.append((oid, cid_c, employee, wh, campaign, odate, status, channel, total))

            if status == "completed":
                ltv[cid_c] += total

            # payment
            pay_id += 1
            method = random.choices(["card", "paypal", "apple_pay", "bank_transfer"], weights=[58, 22, 14, 6])[0]
            pay_status = {"completed": "captured", "refunded": "refunded",
                          "cancelled": "failed", "pending": "pending"}[status]
            paid_at = datetime.combine(odate, time(random.randint(0, 23), random.randint(0, 59)))
            payments.append((pay_id, oid, method, total, pay_status, paid_at))

            # shipment (only for fulfilled-ish orders)
            if status in ("completed", "refunded"):
                ship_id += 1
                carrier = random.choice(list(CARRIERS))
                lo_d, hi_d = CARRIERS[carrier]
                shipped = odate + timedelta(days=random.randint(0, 2))
                transit = random.randint(lo_d, hi_d)
                delivered = shipped + timedelta(days=transit)
                if status == "refunded":
                    ship_status = "returned"
                elif delivered <= TODAY:
                    ship_status = "delivered"
                else:
                    ship_status = random.choice(["in_transit", "shipped"])
                    delivered = None
                ship_cost = round(0.0 if total >= 75 else random.uniform(4.99, 12.99), 2)
                shipments.append((ship_id, oid, wh, carrier, ship_status, shipped, delivered, ship_cost))

            # return (mostly from refunded orders, occasionally from completed)
            make_return = (status == "refunded") or (status == "completed" and random.random() < 0.04)
            if make_return and order_line_products:
                ret_id += 1
                rp, rline, rqty = random.choice(order_line_products)
                reason = random.choices(RETURN_REASONS, weights=[28, 14, 16, 30, 12])[0]
                ret_status = random.choices(["completed", "approved", "pending", "rejected"],
                                            weights=[55, 22, 15, 8])[0]
                requested = odate + timedelta(days=random.randint(2, 20))
                processed = (requested + timedelta(days=random.randint(1, 10))
                             if ret_status in ("completed", "approved", "rejected") else None)
                refund = round(rline if reason != "changed_mind" else rline * 0.9, 2)
                returns.append((ret_id, oid, rp, reason, max(1, rqty), refund, ret_status, requested, processed))

    # fill in lifetime_value
    for c in customers:
        c[11] = round(ltv[c[0]], 2)
    customers = [tuple(c) for c in customers]

    # reviews
    reviews: list[tuple] = []
    rev_id = 0
    for _ in range(1200):
        rev_id += 1
        p = random.choice(product_ids)
        cust = random.choice(customer_ids)
        rating = random.choices([5, 4, 3, 2, 1], weights=[42, 30, 15, 8, 5])[0]
        title = random.choice(REVIEW_TITLES[rating])
        body = REVIEW_BODIES[rating]
        created = _rand_date(date(2024, 6, 1), TODAY)
        reviews.append((rev_id, p, cust, rating, title, body, created))

    # support tickets
    order_ids = [o[0] for o in orders]
    tickets: list[tuple] = []
    tk_id = 0
    for _ in range(600):
        tk_id += 1
        cust = random.choice(customer_ids)
        agent = random.choice(support_agents) if random.random() > 0.1 else None
        order_ref = random.choice(order_ids) if random.random() < 0.6 else None
        category = random.choice(list(TICKET_TEMPLATES))
        subject, body = random.choice(TICKET_TEMPLATES[category])
        product_name = random.choice(products)[1]
        subject = subject.replace("{p}", product_name)
        body = body.replace("{p}", product_name)
        priority = random.choices(["low", "medium", "high"], weights=[40, 40, 20])[0]
        status = random.choices(["resolved", "open", "escalated"], weights=[64, 26, 10])[0]
        created = datetime.combine(_rand_date(date(2025, 1, 1), TODAY),
                                   time(random.randint(7, 20), random.randint(0, 59)))
        if status == "resolved":
            resolved = created + timedelta(hours=random.randint(2, 96))
            csat = random.choices([5, 4, 3, 2, 1], weights=[40, 30, 15, 9, 6])[0]
        else:
            resolved, csat = None, None
        tickets.append((tk_id, cust, agent, order_ref, created, subject, body,
                        category, priority, status, csat, resolved))

    return {
        "categories": categories, "suppliers": suppliers, "warehouses": warehouses,
        "employees": employees, "marketing_campaigns": campaigns, "products": products,
        "inventory": inventory, "customers": customers, "orders": orders,
        "order_items": order_items, "payments": payments, "shipments": shipments,
        "returns": returns, "reviews": reviews, "support_tickets": tickets,
    }


# column order for each COPY (must match the generated tuples) ---------------
COLUMNS: dict[str, list[str]] = {
    "categories": ["id", "name", "department", "description"],
    "suppliers": ["id", "name", "country", "region", "lead_time_days", "reliability_score"],
    "warehouses": ["id", "name", "city", "country", "region", "capacity_units"],
    "employees": ["id", "name", "role", "team", "region", "hire_date", "manager_id", "is_active"],
    "marketing_campaigns": ["id", "name", "channel", "start_date", "end_date", "budget",
                            "impressions", "clicks", "conversions"],
    "products": ["id", "name", "category_id", "supplier_id", "sku", "price", "cost", "launched_at", "is_active"],
    "inventory": ["id", "product_id", "warehouse_id", "quantity_on_hand", "reorder_level", "updated_at"],
    "customers": ["id", "name", "email", "country", "region", "segment", "acquisition_channel",
                  "signup_date", "is_active", "churned", "churn_date", "lifetime_value"],
    "orders": ["id", "customer_id", "employee_id", "warehouse_id", "campaign_id", "order_date",
               "status", "channel", "total_amount"],
    "order_items": ["id", "order_id", "product_id", "quantity", "unit_price", "discount"],
    "payments": ["id", "order_id", "method", "amount", "status", "paid_at"],
    "shipments": ["id", "order_id", "warehouse_id", "carrier", "status", "shipped_at",
                  "delivered_at", "shipping_cost"],
    "returns": ["id", "order_id", "product_id", "reason", "quantity", "refund_amount", "status",
                "requested_at", "processed_at"],
    "reviews": ["id", "product_id", "customer_id", "rating", "title", "body", "created_at"],
    "support_tickets": ["id", "customer_id", "employee_id", "order_id", "created_at", "subject",
                        "body", "category", "priority", "status", "satisfaction_score", "resolved_at"],
}

# insertion order respects foreign keys --------------------------------------
INSERT_ORDER = ["categories", "suppliers", "warehouses", "employees", "marketing_campaigns",
                "products", "inventory", "customers", "orders", "order_items", "payments",
                "shipments", "returns", "reviews", "support_tickets"]


def _copy(cur, table: str, rows: list[tuple]) -> None:
    cols = ", ".join(COLUMNS[table])
    with cur.copy(f"COPY {table} ({cols}) FROM STDIN") as cp:
        for row in rows:
            cp.write_row(row)


def main() -> None:
    missing = config.missing_keys()
    if missing:
        raise SystemExit(f"Missing config: {missing}")

    schema_sql = (Path(__file__).resolve().parent / "schema.sql").read_text(encoding="utf-8")

    print("Generating dataset…")
    data = generate()

    print("Connecting to Neon…")
    with psycopg.connect(config.DATABASE_URL, connect_timeout=30) as conn:
        register_vector(conn)
        with conn.cursor() as cur:
            print("Applying schema…")
            cur.execute(schema_sql)

            for table in INSERT_ORDER:
                rows = data[table]
                print(f"  COPY {table} ({len(rows)} rows)…")
                _copy(cur, table, rows)

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
            for table in INSERT_ORDER + ["documents"]:
                cur.execute(f"SELECT count(*) FROM {table}")
                counts[table] = cur.fetchone()[0]
    print("Seeded:", ", ".join(f"{k}={v}" for k, v in counts.items()))
    print("Done.")


if __name__ == "__main__":
    main()

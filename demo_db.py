"""
SQLite demo database that mirrors Oracle EBS TCA tables.
Seeds 50 parties, 20 accounts, addresses, contacts, and relationships.
"""

import sqlite3
import os
import random
from datetime import datetime, timedelta

DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "demo.db"))

SEED_PARTIES = [
    # (party_id, party_name, party_type, status, tax_reference, duns_number)
    (1001, "Acme Corporation",          "ORGANIZATION", "A", "US-TAX-001", "100000001"),
    (1002, "Acme Corp",                 "ORGANIZATION", "A", None,         None),       # dup of 1001
    (1003, "Beta Technologies Ltd",     "ORGANIZATION", "A", "UK-TAX-002", "100000002"),
    (1004, "Beta Technologies Limited", "ORGANIZATION", "A", None,         None),       # dup of 1003
    (1005, "Gamma Supplies Inc",        "ORGANIZATION", "A", "US-TAX-003", "100000003"),
    (1006, "Delta Logistics",           "ORGANIZATION", "A", "US-TAX-004", "100000004"),
    (1007, "Epsilon Manufacturing",     "ORGANIZATION", "A", "US-TAX-005", "100000005"),
    (1008, "Zeta Services LLC",         "ORGANIZATION", "A", "US-TAX-006", "100000006"),
    (1009, "Eta Consulting Group",      "ORGANIZATION", "A", "US-TAX-007", "100000007"),
    (1010, "Theta Retail Co",           "ORGANIZATION", "I", "US-TAX-008", "100000008"),  # Inactive
    (1011, "Iota Finance",              "ORGANIZATION", "A", "US-TAX-009", "100000009"),
    (1012, "Kappa Energy",              "ORGANIZATION", "A", "US-TAX-010", "100000010"),
    (1013, "Lambda Healthcare",         "ORGANIZATION", "A", "US-TAX-011", "100000011"),
    (1014, "Mu Pharma",                 "ORGANIZATION", "A", "US-TAX-012", "100000012"),
    (1015, "Nu Transport Ltd",          "ORGANIZATION", "A", "US-TAX-013", "100000013"),
    (2001, "John Smith",                "PERSON",       "A", None,         None),
    (2002, "Jane Doe",                  "PERSON",       "A", None,         None),
    (2003, "Robert Johnson",            "PERSON",       "A", None,         None),
    (2004, "Sarah Williams",            "PERSON",       "A", None,         None),
    (2005, "Michael Brown",             "PERSON",       "A", None,         None),
]

SEED_ACCOUNTS = [
    # (acct_id, party_id, account_number, credit_limit, status, last_order_date, avg_days_to_pay)
    (3001, 1001, "ACC-1001", 50000,  "A", "2026-02-15", 28),
    (3002, 1003, "ACC-1003", 75000,  "A", "2026-01-20", 45),
    (3003, 1005, "ACC-1005", 30000,  "A", "2025-11-01", 62),  # AT-RISK (>60 days)
    (3004, 1006, "ACC-1006", 100000, "A", "2025-07-10", 90),  # DORMANT (>180 days)
    (3005, 1007, "ACC-1007", 25000,  "A", "2026-03-01", 15),
    (3006, 1008, "ACC-1008", 60000,  "A", "2026-02-28", 30),
    (3007, 1009, "ACC-1009", 45000,  "A", "2024-03-01", 120), # DORMANT (>365 days)
    (3008, 1010, "ACC-1010", 0,      "I", "2022-01-01", 0),   # Inactive
    (3009, 1011, "ACC-1011", 80000,  "A", "2026-03-05", 10),
    (3010, 1012, "ACC-1012", 55000,  "A", "2026-02-01", 55),
    (3011, 1013, "ACC-1013", 120000, "A", "2026-03-08", 8),
    (3012, 1014, "ACC-1014", 90000,  "A", "2026-03-10", 22),
    (3013, 1015, "ACC-1015", 35000,  "A", "2025-09-01", 75),  # DORMANT
]

SEED_PARTY_SITES = [
    # (site_id, party_id, address, city, state, postal_code, country, validated)
    (4001, 1001, "100 Main Street",      "New York",    "NY", "10001",     "US", 1),
    (4002, 1003, "50 Oxford Street",     "London",      "",   "W1D 1BS",   "UK", 1),
    (4003, 1005, "200 Oak Avenue",       "Chicago",     "IL", "60601",     "US", 1),
    (4004, 1006, "15 Warehouse Blvd",    "Los Angeles", "CA", "90001",     "US", 1),
    (4005, 1007, "999 Industrial Rd",    "Detroit",     "MI", "48201",     "US", 0),  # unvalidated
    (4006, 1008, "77 Service Lane",      "Houston",     "TX", "77001",     "US", 1),
    (4007, 1009, "321 Consulting Ave",   "Boston",      "MA", "02101",     "US", 1),
    (4008, 1011, "88 Finance Street",    "Chicago",     "IL", "60602",     "US", 1),
    (4009, 1012, "45 Energy Plaza",      "Dallas",      "TX", "75201",     "US", 1),
    (4010, 1013, "12 Medical Center Dr", "Cleveland",   "OH", "44101",     "US", 1),
]

SEED_CONTACT_POINTS = [
    # (cp_id, party_id, type, value, status)
    (5001, 1001, "EMAIL", "billing@acme.com",          "A"),
    (5002, 1001, "PHONE", "+1-212-555-0100",            "A"),
    (5003, 1003, "EMAIL", "accounts@betatech.co.uk",    "A"),
    (5004, 1003, "PHONE", "+44-20-7123-4567",           "A"),
    (5005, 1005, "EMAIL", "BOUNCED-old@gamma.com",      "I"),  # bounced
    (5006, 1005, "PHONE", "+1-312-555-0200",            "A"),
    (5007, 1006, "EMAIL", "logistics@delta.com",        "A"),
    (5008, 1007, "EMAIL", "epsilon@mfg.com",            "A"),
    (5009, 1009, "EMAIL", None,                         "I"),  # no email
    (5010, 1011, "EMAIL", "finance@iota.com",           "A"),
    (5011, 2001, "EMAIL", "john.smith@acme.com",        "A"),
    (5012, 2002, "EMAIL", "jane.doe@betatech.co.uk",   "A"),
]

SEED_RELATIONSHIPS = [
    # (rel_id, subject_id, object_id, rel_type)
    (6001, 1001, 2001, "CUSTOMER_CONTACT"),
    (6002, 1001, 2002, "CUSTOMER_CONTACT"),
    (6003, 1003, 2002, "CUSTOMER_CONTACT"),
    (6004, 1005, 2003, "CUSTOMER_CONTACT"),
    (6005, 1001, 1005, "PARENT_SUBSIDIARY"),  # Gamma is subsidiary of Acme
    (6006, 1003, 1007, "PARTNER"),
    (6007, 1006, 1015, "PARTNER"),
]

SEED_PAYMENT_SCHEDULES = [
    # (ps_id, acct_id, invoice_num, amount_due, amount_remaining, status, due_date)
    (7001, 3001, "INV-10001", 12000, 0,     "CL", "2026-01-15"),
    (7002, 3001, "INV-10002", 8500,  8500,  "OP", "2026-03-01"),
    (7003, 3002, "INV-10003", 25000, 5000,  "OP", "2026-02-28"),
    (7004, 3003, "INV-10004", 15000, 15000, "OP", "2025-12-01"),  # overdue
    (7005, 3009, "INV-10005", 50000, 0,     "CL", "2026-02-15"),
    (7006, 3011, "INV-10006", 30000, 0,     "CL", "2026-03-01"),
    (7007, 3012, "INV-10007", 22000, 22000, "OP", "2026-04-01"),
    (7008, 3010, "INV-10008", 18000, 9000,  "OP", "2026-03-15"),
]

SEED_ORDERS = [
    # (order_id, acct_id, order_date, total_amount, return_flag)
    (8001, 3001, "2026-02-15", 8500,  0),
    (8002, 3001, "2026-01-10", 12000, 0),
    (8003, 3002, "2026-01-20", 25000, 0),
    (8004, 3005, "2026-03-01", 5000,  0),
    (8005, 3006, "2026-02-28", 18000, 0),
    (8006, 3003, "2025-11-01", 15000, 0),  # AT-RISK
    (8007, 3004, "2025-07-10", 30000, 1),  # return
    (8008, 3013, "2025-09-01", 22000, 0),
    (8009, 3009, "2026-03-05", 50000, 0),
    (8010, 3011, "2026-03-08", 30000, 0),
    (8011, 3012, "2026-03-10", 22000, 0),
]

SEED_AUDIT_LOG = []


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    if os.path.exists(DB_PATH):
        return  # already seeded

    conn = get_connection()
    c = conn.cursor()

    c.executescript("""
    CREATE TABLE IF NOT EXISTS hz_parties (
        party_id        INTEGER PRIMARY KEY,
        party_name      TEXT NOT NULL,
        party_type      TEXT NOT NULL,
        status          TEXT DEFAULT 'A',
        tax_reference   TEXT,
        duns_number     TEXT,
        created_at      TEXT DEFAULT (datetime('now')),
        updated_at      TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS hz_cust_accounts (
        cust_account_id  INTEGER PRIMARY KEY,
        party_id         INTEGER NOT NULL,
        account_number   TEXT NOT NULL,
        credit_limit     REAL DEFAULT 0,
        status           TEXT DEFAULT 'A',
        last_order_date  TEXT,
        avg_days_to_pay  REAL DEFAULT 30,
        on_hold          INTEGER DEFAULT 0,
        lifecycle_state  TEXT DEFAULT 'PROSPECT',
        updated_at       TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (party_id) REFERENCES hz_parties(party_id)
    );
    CREATE TABLE IF NOT EXISTS hz_party_sites (
        party_site_id   INTEGER PRIMARY KEY,
        party_id        INTEGER NOT NULL,
        address_line1   TEXT,
        city            TEXT,
        state           TEXT,
        postal_code     TEXT,
        country         TEXT,
        validated       INTEGER DEFAULT 0,
        lat             REAL,
        lon             REAL,
        updated_at      TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (party_id) REFERENCES hz_parties(party_id)
    );
    CREATE TABLE IF NOT EXISTS hz_contact_points (
        contact_point_id INTEGER PRIMARY KEY,
        party_id         INTEGER NOT NULL,
        contact_type     TEXT NOT NULL,
        contact_value    TEXT,
        status           TEXT DEFAULT 'A',
        updated_at       TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (party_id) REFERENCES hz_parties(party_id)
    );
    CREATE TABLE IF NOT EXISTS hz_relationships (
        relationship_id  INTEGER PRIMARY KEY,
        subject_id       INTEGER NOT NULL,
        object_id        INTEGER NOT NULL,
        relationship_type TEXT NOT NULL,
        status           TEXT DEFAULT 'A',
        created_at       TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (subject_id) REFERENCES hz_parties(party_id),
        FOREIGN KEY (object_id)  REFERENCES hz_parties(party_id)
    );
    CREATE TABLE IF NOT EXISTS ar_payment_schedules (
        ps_id            INTEGER PRIMARY KEY,
        cust_account_id  INTEGER NOT NULL,
        invoice_number   TEXT,
        amount_due       REAL DEFAULT 0,
        amount_remaining REAL DEFAULT 0,
        status           TEXT DEFAULT 'OP',
        due_date         TEXT,
        FOREIGN KEY (cust_account_id) REFERENCES hz_cust_accounts(cust_account_id)
    );
    CREATE TABLE IF NOT EXISTS oe_orders (
        order_id         INTEGER PRIMARY KEY,
        cust_account_id  INTEGER NOT NULL,
        order_date       TEXT,
        total_amount     REAL DEFAULT 0,
        is_return        INTEGER DEFAULT 0,
        FOREIGN KEY (cust_account_id) REFERENCES hz_cust_accounts(cust_account_id)
    );
    CREATE TABLE IF NOT EXISTS audit_log (
        log_id           INTEGER PRIMARY KEY AUTOINCREMENT,
        workflow         TEXT,
        entity_type      TEXT,
        entity_id        INTEGER,
        action           TEXT,
        details          TEXT,
        performed_at     TEXT DEFAULT (datetime('now'))
    );
    """)

    c.executemany(
        "INSERT OR IGNORE INTO hz_parties VALUES (?,?,?,?,?,?,datetime('now'),datetime('now'))",
        SEED_PARTIES
    )
    c.executemany(
        "INSERT OR IGNORE INTO hz_cust_accounts(cust_account_id,party_id,account_number,credit_limit,status,last_order_date,avg_days_to_pay) VALUES (?,?,?,?,?,?,?)",
        SEED_ACCOUNTS
    )
    c.executemany(
        "INSERT OR IGNORE INTO hz_party_sites(party_site_id,party_id,address_line1,city,state,postal_code,country,validated) VALUES (?,?,?,?,?,?,?,?)",
        SEED_PARTY_SITES
    )
    c.executemany(
        "INSERT OR IGNORE INTO hz_contact_points(contact_point_id,party_id,contact_type,contact_value,status) VALUES (?,?,?,?,?)",
        SEED_CONTACT_POINTS
    )
    c.executemany(
        "INSERT OR IGNORE INTO hz_relationships(relationship_id,subject_id,object_id,relationship_type) VALUES (?,?,?,?)",
        SEED_RELATIONSHIPS
    )
    c.executemany(
        "INSERT OR IGNORE INTO ar_payment_schedules(ps_id,cust_account_id,invoice_number,amount_due,amount_remaining,status,due_date) VALUES (?,?,?,?,?,?,?)",
        SEED_PAYMENT_SCHEDULES
    )
    c.executemany(
        "INSERT OR IGNORE INTO oe_orders(order_id,cust_account_id,order_date,total_amount,is_return) VALUES (?,?,?,?,?)",
        SEED_ORDERS
    )

    # Compute lifecycle states
    today = datetime.now()
    rows = c.execute("SELECT cust_account_id, last_order_date, status FROM hz_cust_accounts").fetchall()
    for row in rows:
        if row[2] == 'I':
            state = 'INACTIVE'
        elif row[1] is None:
            state = 'PROSPECT'
        else:
            last = datetime.strptime(row[1], "%Y-%m-%d")
            days = (today - last).days
            if days <= 60:
                state = 'ACTIVE'
            elif days <= 180:
                state = 'AT-RISK'
            elif days <= 365:
                state = 'DORMANT'
            else:
                state = 'INACTIVE'
        c.execute("UPDATE hz_cust_accounts SET lifecycle_state=? WHERE cust_account_id=?", (state, row[0]))

    conn.commit()
    conn.close()

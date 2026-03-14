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
    # Extra data for richer credit scoring
    (7009, 3004, "INV-10009", 40000, 40000, "OP", "2025-05-01"),  # very overdue
    (7010, 3004, "INV-10010", 25000, 25000, "OP", "2025-06-15"),  # very overdue
    (7011, 3013, "INV-10011", 12000, 12000, "OP", "2025-08-01"),  # overdue
    (7012, 3005, "INV-10012", 5000,  0,     "CL", "2026-02-20"),
    (7013, 3006, "INV-10013", 18000, 0,     "CL", "2026-03-01"),
    (7014, 3009, "INV-10014", 35000, 35000, "OP", "2026-04-15"),
    (7015, 3011, "INV-10015", 45000, 0,     "CL", "2026-02-25"),
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
    # Extra orders for richer data
    (8012, 3001, "2025-12-05", 15000, 0),
    (8013, 3005, "2026-02-10", 7500,  0),
    (8014, 3005, "2026-01-15", 9200,  0),
    (8015, 3009, "2026-02-20", 42000, 0),
    (8016, 3011, "2026-02-15", 55000, 0),
    (8017, 3003, "2025-10-05", 8000,  1),  # return — hurts credit score
    (8018, 3004, "2025-06-01", 20000, 1),  # return — hurts credit score
    (8019, 3013, "2025-08-15", 15000, 1),  # return
    (8020, 3002, "2025-12-10", 18000, 0),
]

SEED_AUDIT_LOG = [
    # (workflow, entity_type, entity_id, action, details)
    # ── Workflow 1: DEDUPLICATION ──
    ("DEDUPLICATION", "HZ_PARTIES", 1001, "DUPLICATE_SCAN",
     '{"scanned": 14, "duplicate_groups_found": 2, "threshold": 0.88}'),
    ("DEDUPLICATION", "HZ_PARTIES", 1001, "MERGE",
     '{"golden_id": 1001, "merged_id": 1002, "golden_name": "Acme Corporation", '
     '"merged_name": "Acme Corp", "steps": ["Redirected 0 customer accounts", '
     '"Redirected 0 party sites", "Redirected 0 contact points", "Redirected 0 relationships"]}'),
    # ── Workflow 2: ADDRESS_VALIDATION ──
    ("ADDRESS_VALIDATION", "HZ_PARTY_SITES", 4001, "VALIDATED",
     '{"address": "100 Main Street", "city": "New York", "lat": 40.7128, "lon": -74.006}'),
    ("ADDRESS_VALIDATION", "HZ_PARTY_SITES", 4002, "VALIDATED",
     '{"address": "50 Oxford Street", "city": "London", "lat": 51.5074, "lon": -0.1278}'),
    ("ADDRESS_VALIDATION", "HZ_PARTY_SITES", 4005, "VALIDATION_FAILED",
     '{"address": "999 Industrial Rd", "issues": ["Address not verified — missing validated postal data"]}'),
    # ── Workflow 3: CREDIT_ADJUSTMENT ──
    ("CREDIT_ADJUSTMENT", "HZ_CUST_ACCOUNTS", 3005, "INCREASE",
     '{"cust_account_id": 3005, "party_name": "Epsilon Manufacturing", "account_number": "ACC-1007", '
     '"current_limit": 25000, "new_limit": 28750, "score": 3, '
     '"reasons": ["Excellent payment speed (<20 days)", "No overdue invoices"]}'),
    ("CREDIT_ADJUSTMENT", "HZ_CUST_ACCOUNTS", 3009, "INCREASE",
     '{"cust_account_id": 3009, "party_name": "Iota Finance", "account_number": "ACC-1011", '
     '"current_limit": 80000, "new_limit": 92000, "score": 3, '
     '"reasons": ["Excellent payment speed (<20 days)", "No overdue invoices"]}'),
    ("CREDIT_ADJUSTMENT", "HZ_CUST_ACCOUNTS", 3003, "DECREASE",
     '{"cust_account_id": 3003, "party_name": "Gamma Supplies Inc", "account_number": "ACC-1005", '
     '"current_limit": 30000, "new_limit": 22500, "score": -4, '
     '"reasons": ["Very slow payment (>60 days)", "1 overdue invoice(s)", "Elevated return rate: 33%"]}'),
    ("CREDIT_ADJUSTMENT", "HZ_CUST_ACCOUNTS", 3004, "DECREASE",
     '{"cust_account_id": 3004, "party_name": "Delta Logistics", "account_number": "ACC-1006", '
     '"current_limit": 100000, "new_limit": 75000, "score": -5, '
     '"reasons": ["Very slow payment (>60 days)", "2 overdue invoices — high risk", "High return rate: 50%"]}'),
    ("CREDIT_ADJUSTMENT", "HZ_CUST_ACCOUNTS", 3011, "INCREASE",
     '{"cust_account_id": 3011, "party_name": "Lambda Healthcare", "account_number": "ACC-1013", '
     '"current_limit": 120000, "new_limit": 138000, "score": 3, '
     '"reasons": ["Excellent payment speed (<20 days)", "No overdue invoices"]}'),
    # ── Workflow 4: CONTACT_MAINTENANCE ──
    ("CONTACT_MAINTENANCE", "HZ_CONTACT_POINTS", 5005, "MARKED_INVALID",
     '{"reason": "BOUNCED", "value": "BOUNCED-old@gamma.com", "alternates_found": 1}'),
    ("CONTACT_MAINTENANCE", "HZ_CONTACT_POINTS", 5009, "MARKED_INVALID",
     '{"reason": "INVALID", "value": null, "alternates_found": 0}'),
    ("CONTACT_MAINTENANCE", "HZ_CONTACT_POINTS", 5013, "ADDED",
     '{"party_id": 1008, "type": "EMAIL", "value": "support@zeta-services.com"}'),
    # ── Workflow 5: RELATIONSHIP_MGMT ──
    ("RELATIONSHIP_MGMT", "HZ_RELATIONSHIPS", 6005, "VERIFIED",
     '{"subject": "Acme Corporation", "object": "Gamma Supplies Inc", "type": "PARENT_SUBSIDIARY"}'),
    ("RELATIONSHIP_MGMT", "HZ_RELATIONSHIPS", 6008, "ADDED",
     '{"subject_id": 1011, "object_id": 1012, "type": "PARTNER", '
     '"subject_name": "Iota Finance", "object_name": "Kappa Energy"}'),
    # ── Workflow 6: ARCHIVING ──
    ("ARCHIVING", "HZ_CUST_ACCOUNTS", 3007, "SCAN_DORMANT",
     '{"party_name": "Eta Consulting Group", "account_number": "ACC-1009", '
     '"last_order": "2024-03-01", "days_inactive": 744, "can_archive": true, "blockers": []}'),
    ("ARCHIVING", "HZ_CUST_ACCOUNTS", 3008, "ARCHIVED",
     '{"party_name": "Theta Retail Co", "account_number": "ACC-1010", '
     '"last_order": "2022-01-01", "days_inactive": 1534, "status": "INACTIVE"}'),
    ("ARCHIVING", "HZ_CUST_ACCOUNTS", 0, "LIFECYCLE_SYNC",
     '{"status": "UPDATED", "breakdown": {"ACTIVE": 7, "AT-RISK": 1, "DORMANT": 3, "INACTIVE": 2, "PROSPECT": 0}, "total": 13}'),
]


_DB_SCHEMA_VERSION = 2  # bump to force re-seed on next deploy


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    c = conn.cursor()

    # Version check — re-seed when schema version bumps
    c.execute("CREATE TABLE IF NOT EXISTS _meta (key TEXT PRIMARY KEY, value TEXT)")
    row = c.execute("SELECT value FROM _meta WHERE key='schema_version'").fetchone()
    if row and int(row[0]) >= _DB_SCHEMA_VERSION:
        conn.close()
        return  # already up to date

    # Drop all data tables to re-seed cleanly
    for table in [
        "audit_log", "oe_orders", "ar_payment_schedules", "hz_relationships",
        "hz_contact_points", "hz_party_sites", "hz_cust_accounts", "hz_parties",
    ]:
        c.execute(f"DROP TABLE IF EXISTS {table}")

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

    # Seed audit log with representative entries for all 6 workflows
    c.executemany(
        "INSERT INTO audit_log(workflow,entity_type,entity_id,action,details) VALUES (?,?,?,?,?)",
        SEED_AUDIT_LOG
    )

    # Stamp version
    c.execute("INSERT OR REPLACE INTO _meta VALUES ('schema_version', ?)", (str(_DB_SCHEMA_VERSION),))

    conn.commit()
    conn.close()

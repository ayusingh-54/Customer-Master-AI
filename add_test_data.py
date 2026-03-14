"""
Add more test data to the database for testing purposes.
Includes duplicate customers, more accounts, and various edge cases.
"""

import sqlite3
import random
from datetime import datetime, timedelta
from demo_db import DB_PATH, get_connection

# Additional parties (including intentional duplicates for testing deduplication)
ADDITIONAL_PARTIES = [
    # Real duplicates with slight name variations
    (1016, "Acme Corp Inc",                 "ORGANIZATION", "A", "US-TAX-001", None),        # dup of 1001
    (1017, "ACME CORPORATION",              "ORGANIZATION", "A", None, "100000001"),         # dup of 1001
    (1018, "Beta Tech Ltd",                 "ORGANIZATION", "A", "UK-TAX-002", None),        # dup of 1003
    (1019, "Beta Technologies Ltd.",        "ORGANIZATION", "A", None, "100000002"),         # dup of 1003

    # More unique organizations
    (1020, "Omega Distribution",            "ORGANIZATION", "A", "US-TAX-014", "100000014"),
    (1021, "Pi Software Solutions",         "ORGANIZATION", "A", "US-TAX-015", "100000015"),
    (1022, "Rho Electronics",               "ORGANIZATION", "A", "US-TAX-016", "100000016"),
    (1023, "Sigma Industries",              "ORGANIZATION", "A", "US-TAX-017", "100000017"),
    (1024, "Tau Manufacturing",             "ORGANIZATION", "A", "US-TAX-018", "100000018"),
    (1025, "Upsilon Trading Co",            "ORGANIZATION", "A", "US-TAX-019", "100000019"),
    (1026, "Phi Ventures LLC",              "ORGANIZATION", "A", "US-TAX-020", "100000020"),
    (1027, "Chi Consulting",                "ORGANIZATION", "A", "US-TAX-021", "100000021"),
    (1028, "Psi Analytics",                 "ORGANIZATION", "A", "US-TAX-022", "100000022"),
    (1029, "Omega Services",                "ORGANIZATION", "A", "US-TAX-023", "100000023"),

    # More persons
    (2006, "Emily Davis",                   "PERSON",       "A", None, None),
    (2007, "David Miller",                  "PERSON",       "A", None, None),
    (2008, "Lisa Wilson",                   "PERSON",       "A", None, None),
    (2009, "James Moore",                   "PERSON",       "A", None, None),
    (2010, "Patricia Taylor",               "PERSON",       "A", None, None),
]

# Additional accounts
ADDITIONAL_ACCOUNTS = [
    # (acct_id, party_id, account_number, credit_limit, status, last_order_date, avg_days_to_pay)
    (3014, 1016, "ACC-1016", 45000,  "A", "2026-03-09", 25),
    (3015, 1017, "ACC-1017", 55000,  "A", "2026-02-20", 35),
    (3016, 1018, "ACC-1018", 65000,  "A", "2026-03-05", 40),
    (3017, 1019, "ACC-1019", 70000,  "A", "2025-12-15", 85),     # AT-RISK
    (3018, 1020, "ACC-1020", 40000,  "A", "2026-03-08", 20),
    (3019, 1021, "ACC-1021", 95000,  "A", "2026-02-10", 48),
    (3020, 1022, "ACC-1022", 52000,  "A", "2026-01-05", 58),     # AT-RISK
    (3021, 1023, "ACC-1023", 110000, "A", "2026-03-12", 12),
    (3022, 1024, "ACC-1024", 38000,  "A", "2026-02-25", 32),
    (3023, 1025, "ACC-1025", 85000,  "A", "2025-10-01", 95),     # DORMANT
    (3024, 1026, "ACC-1026", 65000,  "A", "2025-08-20", 105),    # DORMANT
    (3025, 1027, "ACC-1027", 48000,  "A", "2026-03-11", 18),
    (3026, 1028, "ACC-1028", 72000,  "A", "2026-02-28", 42),
    (3027, 1029, "ACC-1029", 58000,  "A", "2024-05-01", 150),    # DORMANT (>365 days)
]

# Additional party sites
ADDITIONAL_SITES = [
    # (site_id, party_id, address, city, state, postal_code, country, validated)
    (4011, 1016, "500 Commerce Blvd", "San Francisco", "CA", "94105", "US", 1),
    (4012, 1017, "201 Park Avenue",   "New York",      "NY", "10166", "US", 1),
    (4013, 1018, "30 Gresham Street", "London",        "",   "EC2V 7PE", "UK", 1),
    (4014, 1019, "88 King Street",    "Manchester",    "",   "M2 4WQ", "UK", 0),
    (4015, 1020, "123 Distribution Dr", "Atlanta",     "GA", "30301", "US", 1),
    (4016, 1021, "456 Tech Park",     "Seattle",       "WA", "98101", "US", 1),
    (4017, 1022, "789 Electronics Ave", "Austin",      "TX", "78701", "US", 1),
    (4018, 1023, "321 Industrial Way", "Charlotte",    "NC", "28202", "US", 0),
    (4019, 1024, "654 Factory Road",  "Phoenix",       "AZ", "85001", "US", 1),
    (4020, 1025, "987 Trade Center",  "Miami",         "FL", "33101", "US", 1),
    (4021, 1026, "147 Venture Blvd",  "Denver",        "CO", "80202", "US", 1),
    (4022, 1027, "258 Consulting St", "Portland",      "OR", "97201", "US", 1),
    (4023, 1028, "369 Analytics Drive", "Minneapolis", "MN", "55401", "US", 0),
    (4024, 1029, "741 Service Plaza", "Tampa",         "FL", "33602", "US", 1),
]

# Additional contact points
ADDITIONAL_CONTACT_POINTS = [
    # (cp_id, party_id, type, value, status)
    (5013, 1016, "EMAIL", "contact@acmecorp.com",        "A"),
    (5014, 1016, "PHONE", "+1-415-555-0150",             "A"),
    (5015, 1017, "EMAIL", "info@acmecorp.com",           "A"),
    (5016, 1018, "EMAIL", "support@betatech.co.uk",      "A"),
    (5017, 1019, "EMAIL", "sales@betatech.co.uk",        "A"),
    (5018, 1020, "EMAIL", "contact@omegadist.com",       "A"),
    (5019, 1020, "PHONE", "+1-404-555-0200",             "A"),
    (5020, 1021, "EMAIL", "support@pisoftware.com",      "A"),
    (5021, 1022, "EMAIL", "sales@rhoelectronics.com",    "A"),
    (5022, 1023, "EMAIL", "contact@sigmamfg.com",        "A"),
    (5023, 1024, "EMAIL", "orders@taumfg.com",           "A"),
    (5024, 1025, "EMAIL", "trading@upsilonco.com",       "A"),
    (5025, 1026, "EMAIL", "ventures@phi.com",            "A"),
    (5026, 1027, "EMAIL", "consulting@chi.com",          "A"),
    (5027, 1028, "EMAIL", "analytics@psi.com",           "A"),
    (5028, 1029, "EMAIL", "services@omegasvcs.com",      "A"),
    (5029, 2006, "EMAIL", "emily.davis@company.com",     "A"),
    (5030, 2007, "EMAIL", "david.miller@company.com",    "A"),
    (5031, 2008, "EMAIL", "lisa.wilson@company.com",     "A"),
    (5032, 2009, "EMAIL", "james.moore@company.com",     "A"),
    (5033, 2010, "EMAIL", "patricia.taylor@company.com", "A"),
]

# Additional relationships
ADDITIONAL_RELATIONSHIPS = [
    # (rel_id, subject_id, object_id, rel_type)
    (6008, 1016, 2003, "CUSTOMER_CONTACT"),
    (6009, 1020, 2004, "CUSTOMER_CONTACT"),
    (6010, 1021, 2005, "CUSTOMER_CONTACT"),
    (6011, 1022, 2006, "CUSTOMER_CONTACT"),
    (6012, 1023, 2007, "CUSTOMER_CONTACT"),
    (6013, 1024, 2008, "CUSTOMER_CONTACT"),
    (6014, 1025, 2009, "CUSTOMER_CONTACT"),
    (6015, 1026, 2010, "CUSTOMER_CONTACT"),
    (6016, 1020, 1016, "PARTNER"),
    (6017, 1021, 1022, "PARTNER"),
    (6018, 1023, 1024, "PARENT_SUBSIDIARY"),
]

# Additional orders
ADDITIONAL_ORDERS = [
    # (order_id, acct_id, order_date, total_amount, return_flag)
    (8012, 3014, "2026-03-09", 18500,  0),
    (8013, 3015, "2026-02-20", 22000,  0),
    (8014, 3016, "2026-03-05", 35000,  0),
    (8015, 3017, "2025-12-15", 19000,  0),
    (8016, 3018, "2026-03-08", 12000,  0),
    (8017, 3019, "2026-02-10", 48000,  0),
    (8018, 3020, "2026-01-05", 16000,  1),
    (8019, 3021, "2026-03-12", 55000,  0),
    (8020, 3022, "2026-02-25", 14000,  0),
    (8021, 3023, "2025-10-01", 28000,  0),
    (8022, 3024, "2025-08-20", 21000,  0),
    (8023, 3025, "2026-03-11", 17000,  0),
    (8024, 3026, "2026-02-28", 32000,  0),
    (8025, 3027, "2024-05-01", 25000,  1),
]

# Additional payment schedules
ADDITIONAL_PAYMENT_SCHEDULES = [
    # (ps_id, acct_id, invoice_num, amount_due, amount_remaining, status, due_date)
    (7009, 3014, "INV-10009", 18500, 5000,   "OP", "2026-04-05"),
    (7010, 3015, "INV-10010", 22000, 0,      "CL", "2026-03-20"),
    (7011, 3016, "INV-10011", 35000, 35000,  "OP", "2026-04-05"),
    (7012, 3017, "INV-10012", 19000, 19000,  "OP", "2025-12-01"),  # OVERDUE
    (7013, 3018, "INV-10013", 12000, 0,      "CL", "2026-03-08"),
    (7014, 3019, "INV-10014", 48000, 12000,  "OP", "2026-03-10"),
    (7015, 3020, "INV-10015", 16000, 16000,  "OP", "2025-12-05"),  # OVERDUE
    (7016, 3021, "INV-10016", 55000, 0,      "CL", "2026-03-12"),
    (7017, 3022, "INV-10017", 14000, 14000,  "OP", "2026-03-25"),
    (7018, 3023, "INV-10018", 28000, 28000,  "OP", "2026-01-01"),  # OVERDUE
    (7019, 3024, "INV-10019", 21000, 0,      "CL", "2025-09-20"),
    (7020, 3025, "INV-10020", 17000, 8500,   "OP", "2026-04-11"),
    (7021, 3026, "INV-10021", 32000, 0,      "CL", "2026-02-28"),
    (7022, 3027, "INV-10022", 25000, 25000,  "OP", "2024-06-01"),  # VERY OVERDUE
]


def add_test_data():
    """Add additional test data to the database."""
    conn = get_connection()
    c = conn.cursor()

    print("Adding test data...")

    # Add parties
    try:
        c.executemany(
            "INSERT OR IGNORE INTO hz_parties(party_id, party_name, party_type, status, tax_reference, duns_number, created_at, updated_at) VALUES (?,?,?,?,?,?,datetime('now'),datetime('now'))",
            ADDITIONAL_PARTIES
        )
        print("  [OK] Added {} parties".format(len(ADDITIONAL_PARTIES)))
    except Exception as e:
        print("  [ERROR] Error adding parties: {}".format(e))

    # Add accounts
    try:
        c.executemany(
            "INSERT OR IGNORE INTO hz_cust_accounts(cust_account_id, party_id, account_number, credit_limit, status, last_order_date, avg_days_to_pay) VALUES (?,?,?,?,?,?,?)",
            ADDITIONAL_ACCOUNTS
        )
        print("  [OK] Added {} accounts".format(len(ADDITIONAL_ACCOUNTS)))
    except Exception as e:
        print("  [ERROR] Error adding accounts: {}".format(e))

    # Add sites
    try:
        c.executemany(
            "INSERT OR IGNORE INTO hz_party_sites(party_site_id, party_id, address_line1, city, state, postal_code, country, validated) VALUES (?,?,?,?,?,?,?,?)",
            ADDITIONAL_SITES
        )
        print("  [OK] Added {} party sites".format(len(ADDITIONAL_SITES)))
    except Exception as e:
        print("  [ERROR] Error adding sites: {}".format(e))

    # Add contact points
    try:
        c.executemany(
            "INSERT OR IGNORE INTO hz_contact_points(contact_point_id, party_id, contact_type, contact_value, status) VALUES (?,?,?,?,?)",
            ADDITIONAL_CONTACT_POINTS
        )
        print("  [OK] Added {} contact points".format(len(ADDITIONAL_CONTACT_POINTS)))
    except Exception as e:
        print("  [ERROR] Error adding contact points: {}".format(e))

    # Add relationships
    try:
        c.executemany(
            "INSERT OR IGNORE INTO hz_relationships(relationship_id, subject_id, object_id, relationship_type) VALUES (?,?,?,?)",
            ADDITIONAL_RELATIONSHIPS
        )
        print("  [OK] Added {} relationships".format(len(ADDITIONAL_RELATIONSHIPS)))
    except Exception as e:
        print("  [ERROR] Error adding relationships: {}".format(e))

    # Add orders
    try:
        c.executemany(
            "INSERT OR IGNORE INTO oe_orders(order_id, cust_account_id, order_date, total_amount, is_return) VALUES (?,?,?,?,?)",
            ADDITIONAL_ORDERS
        )
        print("  [OK] Added {} orders".format(len(ADDITIONAL_ORDERS)))
    except Exception as e:
        print("  [ERROR] Error adding orders: {}".format(e))

    # Add payment schedules
    try:
        c.executemany(
            "INSERT OR IGNORE INTO ar_payment_schedules(ps_id, cust_account_id, invoice_number, amount_due, amount_remaining, status, due_date) VALUES (?,?,?,?,?,?,?)",
            ADDITIONAL_PAYMENT_SCHEDULES
        )
        print("  [OK] Added {} payment schedules".format(len(ADDITIONAL_PAYMENT_SCHEDULES)))
    except Exception as e:
        print("  [ERROR] Error adding payment schedules: {}".format(e))

    # Update lifecycle states
    try:
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
        print("  [OK] Updated lifecycle states")
    except Exception as e:
        print("  [ERROR] Error updating lifecycle states: {}".format(e))

    conn.commit()
    conn.close()

    print("\n[SUCCESS] Test data added successfully!")
    print(f"   Total new parties: {len(ADDITIONAL_PARTIES)}")
    print(f"   Total new accounts: {len(ADDITIONAL_ACCOUNTS)}")
    print(f"   Total new sites: {len(ADDITIONAL_SITES)}")
    print(f"   Total new contacts: {len(ADDITIONAL_CONTACT_POINTS)}")
    print(f"   Total new relationships: {len(ADDITIONAL_RELATIONSHIPS)}")
    print(f"   Total new orders: {len(ADDITIONAL_ORDERS)}")
    print(f"   Total new payments: {len(ADDITIONAL_PAYMENT_SCHEDULES)}")


if __name__ == "__main__":
    add_test_data()

# Customer Master Database - Complete Guide

## Overview
This SQLite database mirrors Oracle EBS TCA (Trading Community Architecture) tables and manages customer master data including parties (organizations and persons), accounts, locations, contacts, relationships, orders, and payments.

**Database File:** `demo.db`
**Total Records:** 188
**Total Tables:** 9

---

## Core Tables

### 1. **HZ_PARTIES** (Master Party Data)
The central party table that stores all customers (organizations) and persons.

**Total Records:** 39
- ORGANIZATION (Active): 26
- ORGANIZATION (Inactive): 2
- ORGANIZATION (Merged): 1
- PERSON (Active): 10

| Column | Type | Key | Description |
|--------|------|-----|-------------|
| party_id | INTEGER | PRIMARY KEY | Unique identifier (1001-1029 for orgs, 2001-2010 for persons) |
| party_name | TEXT | - | Customer name |
| party_type | TEXT | - | Either 'ORGANIZATION' or 'PERSON' |
| status | TEXT | - | A=Active, I=Inactive, M=Merged |
| tax_reference | TEXT | - | Tax ID (for duplicate detection) |
| duns_number | TEXT | - | DUNS number (for duplicate detection) |
| created_at | TEXT | - | Auto-timestamp on creation |
| updated_at | TEXT | - | Auto-timestamp on update |

**Key Features:**
- Duplicates identified by fuzzy name matching or exact tax_reference/DUNS match
- 4 intentional duplicates added for testing: Acme variations (1001, 1002, 1016, 1017) and Beta variations (1003, 1004, 1018, 1019)

**Sample Data:**
```
ID: 1001 | Acme Corporation           | Tax: US-TAX-001    | DUNS: 100000001
ID: 1002 | Acme Corp                  | Tax: N/A           | DUNS: N/A  (dup of 1001)
ID: 1020 | Omega Distribution         | Tax: US-TAX-014    | DUNS: 100000014
```

---

### 2. **HZ_CUST_ACCOUNTS** (Customer Accounts)
Represents active accounts for each party, with credit limits and payment patterns.

**Total Records:** 27

| Column | Type | Key | Description |
|--------|------|-----|-------------|
| cust_account_id | INTEGER | PRIMARY KEY | Unique account ID (3001-3027) |
| party_id | INTEGER | FOREIGN KEY | Links to hz_parties(party_id) |
| account_number | TEXT | - | Account code (ACC-XXXX) |
| credit_limit | REAL | - | Credit extended (0-120,000) |
| status | TEXT | - | A=Active, I=Inactive |
| last_order_date | TEXT | - | Date of most recent order (YYYY-MM-DD) |
| avg_days_to_pay | REAL | - | Average payment period (8-150 days) |
| on_hold | INTEGER | - | 0=Normal, 1=On Hold |
| lifecycle_state | TEXT | - | ACTIVE, AT-RISK, DORMANT, INACTIVE, PROSPECT |
| updated_at | TEXT | - | Last update timestamp |

**Lifecycle States:**
- **ACTIVE** (17 accounts): Last order ≤ 60 days ago
- **AT-RISK** (4 accounts): Last order 61-180 days ago
- **DORMANT** (3 accounts): Last order 181-365 days ago
- **INACTIVE** (3 accounts): Last order > 365 days ago or status='I'
- **PROSPECT**: No orders yet

**Total Credit Extended:** $1,681,800

**Sample Data:**
```
ID: 3001 | Party: 1001 (Acme)        | Limit: $50,000  | Credit: 28 days | State: ACTIVE
ID: 3004 | Party: 1006 (Delta)       | Limit: $100,000 | Credit: 90 days | State: DORMANT
ID: 3003 | Party: 1005 (Gamma)       | Limit: $30,000  | Credit: 62 days | State: AT-RISK
```

---

### 3. **HZ_PARTY_SITES** (Customer Locations)
Physical addresses for each party (headquarters, branches, delivery locations).

**Total Records:** 24

| Column | Type | Key | Description |
|--------|------|-----|-------------|
| party_site_id | INTEGER | PRIMARY KEY | Unique site ID (4001-4024) |
| party_id | INTEGER | FOREIGN KEY | Links to hz_parties(party_id) |
| address_line1 | TEXT | - | Street address |
| city | TEXT | - | City name |
| state | TEXT | - | State/Province (US: 2-letter code) |
| postal_code | TEXT | - | ZIP/Postal code |
| country | TEXT | - | Country code (US, UK, etc.) |
| validated | INTEGER | - | 0=Not validated, 1=Address verified |
| lat | REAL | - | Latitude (optional) |
| lon | REAL | - | Longitude (optional) |
| updated_at | TEXT | - | Last update timestamp |

**Validation Status:**
- Validated: 21 sites (87.5%)
- Unvalidated: 3 sites (12.5%)

**Sample Data:**
```
100 Main Street, New York, NY 10001, US [VALID]
50 Oxford Street, London, W1D 1BS, UK [VALID]
999 Industrial Rd, Detroit, MI 48201, US [NOT VALIDATED]
```

---

### 4. **HZ_CONTACT_POINTS** (Contact Information)
Email addresses and phone numbers for parties and persons.

**Total Records:** 33

| Column | Type | Key | Description |
|--------|------|-----|-------------|
| contact_point_id | INTEGER | PRIMARY KEY | Unique contact ID (5001-5033) |
| party_id | INTEGER | FOREIGN KEY | Links to hz_parties(party_id) |
| contact_type | TEXT | - | EMAIL, PHONE, FAX, etc. |
| contact_value | TEXT | - | Actual email or phone number |
| status | TEXT | - | A=Active, I=Inactive (bounced) |
| updated_at | TEXT | - | Last update timestamp |

**Contact Types:**
- EMAIL (Active): 26 records
- EMAIL (Inactive): 2 records (bounced emails)
- PHONE (Active): 5 records

**Sample Data:**
```
ID: 5001 | Party: 1001 | EMAIL | billing@acme.com [ACTIVE]
ID: 5005 | Party: 1005 | EMAIL | BOUNCED-old@gamma.com [INACTIVE]
ID: 5002 | Party: 1001 | PHONE | +1-212-555-0100 [ACTIVE]
```

---

### 5. **HZ_RELATIONSHIPS** (Party Connections)
Business relationships between parties (parent-subsidiary, partnerships, contacts).

**Total Records:** 18

| Column | Type | Key | Description |
|--------|------|-----|-------------|
| relationship_id | INTEGER | PRIMARY KEY | Unique relationship ID (6001-6018) |
| subject_id | INTEGER | FOREIGN KEY | Source party (hz_parties.party_id) |
| object_id | INTEGER | FOREIGN KEY | Target party (hz_parties.party_id) |
| relationship_type | TEXT | - | CUSTOMER_CONTACT, PARTNER, PARENT_SUBSIDIARY, etc. |
| status | TEXT | - | A=Active, default |
| created_at | TEXT | - | Creation timestamp |

**Relationship Types:**
- CUSTOMER_CONTACT (11 links): Person is contact for organization
- PARTNER (5 links): Business partnerships
- PARENT_SUBSIDIARY (2 links): Corporate hierarchy

**Sample Relationships:**
```
1001 (Acme) -> 2001 (John Smith) [CUSTOMER_CONTACT]
1001 (Acme) -> 1005 (Gamma) [PARENT_SUBSIDIARY] (Gamma is subsidiary of Acme)
1003 (Beta Tech) -> 1007 (Epsilon) [PARTNER]
```

---

## Financial Tables

### 6. **AR_PAYMENT_SCHEDULES** (Accounts Receivable)
Invoice tracking and payment status.

**Total Records:** 22

| Column | Type | Key | Description |
|--------|------|-----|-------------|
| ps_id | INTEGER | PRIMARY KEY | Payment schedule ID (7001-7022) |
| cust_account_id | INTEGER | FOREIGN KEY | Links to hz_cust_accounts |
| invoice_number | TEXT | - | Invoice ID (INV-XXXXX) |
| amount_due | REAL | - | Original invoice amount |
| amount_remaining | REAL | - | Still owed |
| status | TEXT | - | CL=Closed, OP=Open |
| due_date | TEXT | - | Payment due date |

**Payment Status:**
| Status | Count | Total Due | Total Remaining |
|--------|-------|-----------|-----------------|
| CL (Closed) | 8 | $234,000 | $0 |
| OP (Open) | 14 | $309,000 | $222,000 |

**OVERDUE INVOICES:** 8 invoices totaling $128,500
- Invoice INV-10004: $15,000 (due 2025-12-01)
- Invoice INV-10012: $19,000 (due 2025-12-01)
- Invoice INV-10018: $28,000 (due 2026-01-01)
- Invoice INV-10022: $25,000 (due 2024-06-01) **VERY OVERDUE**

**Sample Data:**
```
INV-10001 | Acme (Acc 3001) | $12,000 | Status: CLOSED | Due: 2026-01-15
INV-10004 | Gamma (Acc 3003) | $15,000 | Status: OPEN (OVERDUE) | Due: 2025-12-01
INV-10005 | Iota (Acc 3009) | $50,000 | Status: CLOSED | Due: 2026-02-15
```

---

### 7. **OE_ORDERS** (Sales Orders)
Customer order history and transactions.

**Total Records:** 25

| Column | Type | Key | Description |
|--------|------|-----|-------------|
| order_id | INTEGER | PRIMARY KEY | Unique order ID (8001-8025) |
| cust_account_id | INTEGER | FOREIGN KEY | Links to hz_cust_accounts |
| order_date | TEXT | - | Order date (YYYY-MM-DD) |
| total_amount | REAL | - | Order value |
| is_return | INTEGER | - | 0=Normal, 1=Return/RMA |

**Order Statistics:**
- Total Orders: 25
- Total Sales: $600,000
- Average Order: $24,000
- Return Orders: 3
- Return Rate: 12%

**Recent Orders (Last 30 days):**
```
Order 8004 | 2026-03-01 | Acc 3005 | $5,000
Order 8005 | 2026-02-28 | Acc 3006 | $18,000
Order 8020 | 2026-03-12 | Acc 3021 | $55,000
```

---

### 8. **AUDIT_LOG** (System Audit Trail)
Comprehensive audit trail of all system actions.

**Total Records:** 17

| Column | Type | Key | Description |
|--------|------|-----|-------------|
| log_id | INTEGER | PRIMARY KEY | Auto-increment audit ID |
| workflow | TEXT | - | Workflow name |
| entity_type | TEXT | - | Table/entity affected |
| entity_id | INTEGER | - | Record ID |
| action | TEXT | - | Action performed |
| details | TEXT | JSON | Additional details (JSON) |
| performed_at | TEXT | - | Timestamp |

**Audit Workflows:**
| Workflow | Action | Count | Purpose |
|----------|--------|-------|---------|
| ADDRESS_VALIDATION | VALIDATED | 2 | Address verification |
| CREDIT_ADJUSTMENT | INCREASE | 6 | Credit limit changes |
| CREDIT_ADJUSTMENT | DECREASE | 3 | Credit limit reductions |
| DEDUPLICATION | MERGE | 1 | Party merging |
| CONTACT_MAINTENANCE | ADDED/INVALID | 2 | Contact changes |
| RELATIONSHIP_MGMT | ADDED/RESTRUCTURE | 2 | Relationship changes |
| ARCHIVING | ARCHIVED | 1 | Record archival |

---

## Entity Relationship Diagram

```
┌─────────────────────┐
│    HZ_PARTIES       │ (Master)
│  [party_id]PK       │
│  party_name         │
│  party_type         │
│  tax_reference      │
│  duns_number        │
└──────────┬──────────┘
           │
     ┌─────┼─────┬────────────┐
     │     │     │            │
     ▼     ▼     ▼            ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│ HZ_CUST_ACCOUNTS │  │ HZ_PARTY_SITES   │  │ HZ_CONTACT_POINTS│
│  [cust_account_id]  │ [party_site_id]     │[contact_point_id]
│  party_id (FK)   │  │ party_id (FK)    │  │ party_id (FK)    │
│  account_number  │  │ address_line1    │  │ contact_type     │
│  credit_limit    │  │ city, state      │  │ contact_value    │
│  lifecycle_state │  │ postal_code      │  │ status           │
└────────┬─────────┘  └──────────────────┘  └──────────────────┘
         │
     ┌───┴───┐
     ▼       ▼
┌──────────────────┐  ┌──────────────────┐
│ AR_PAYMENT_SCHEDULES│ OE_ORDERS        │
│ [ps_id]          │  │[order_id]        │
│ cust_account_id  │  │cust_account_id   │
│ invoice_number   │  │order_date        │
│ amount_remaining │  │total_amount      │
│ status (CL/OP)   │  │is_return         │
└──────────────────┘  └──────────────────┘

┌──────────────────┐
│ HZ_RELATIONSHIPS │
│ [relationship_id]│
│ subject_id (FK)  │──┐
│ object_id (FK)───┼──┘ (both point to hz_parties)
│ relationship_type│
└──────────────────┘

┌──────────────────┐
│   AUDIT_LOG      │
│  [log_id]        │
│  workflow        │
│  entity_type     │
│  entity_id       │
│  details (JSON)  │
└──────────────────┘
```

---

## Key Data Patterns

### 1. **Duplicate Parties**
4 pairs of duplicates for testing deduplication:
- **Acme (1001):** Acme Corp (1002), Acme Corp Inc (1016), ACME CORPORATION (1017)
- **Beta (1003):** Beta Technologies Limited (1004), Beta Tech Ltd (1018), Beta Technologies Ltd. (1019)

### 2. **Account Lifecycle**
- **ACTIVE (17):** Latest business, avg payment 28 days
- **AT-RISK (4):** Declining engagement, avg payment 75 days
- **DORMANT (3):** No recent activity, avg payment 90 days
- **INACTIVE (3):** Closed or on hold

### 3. **Payment Issues**
- 14 open invoices worth $222,000
- 8 invoices OVERDUE (due < today)
- Largest overdue: INV-10022 for $25,000 (due Jun 2024)

### 4. **Sales Trends**
- 25 orders generating $600K revenue
- 3 returns (12% return rate)
- Avg order value: $24,000
- Most recent activity: March 12, 2026

### 5. **Contact Coverage**
- 26 active email addresses (87%)
- 2 bounced/invalid emails
- 5 phone numbers
- 3 unvalidated addresses

---

## Query Examples

### Find all ACTIVE customers with high credit limits
```sql
SELECT p.party_id, p.party_name, a.account_number, a.credit_limit
FROM hz_parties p
JOIN hz_cust_accounts a ON p.party_id = a.party_id
WHERE a.lifecycle_state = 'ACTIVE' AND a.credit_limit > 70000
ORDER BY a.credit_limit DESC;
```

### Find duplicate parties (similar names)
```sql
SELECT party_id, party_name, tax_reference, duns_number
FROM hz_parties
WHERE party_type = 'ORGANIZATION'
ORDER BY party_name;
```

### Get overdue invoices
```sql
SELECT ps.invoice_number, ps.amount_remaining, ps.due_date, p.party_name
FROM ar_payment_schedules ps
JOIN hz_cust_accounts a ON ps.cust_account_id = a.cust_account_id
JOIN hz_parties p ON a.party_id = p.party_id
WHERE ps.status = 'OP' AND ps.due_date < date('now')
ORDER BY ps.due_date ASC;
```

### Get customer with all related data
```sql
SELECT
    p.party_id, p.party_name, p.party_type,
    COUNT(DISTINCT a.cust_account_id) as num_accounts,
    COUNT(DISTINCT s.party_site_id) as num_sites,
    COUNT(DISTINCT c.contact_point_id) as num_contacts,
    SUM(a.credit_limit) as total_credit
FROM hz_parties p
LEFT JOIN hz_cust_accounts a ON p.party_id = a.party_id
LEFT JOIN hz_party_sites s ON p.party_id = s.party_id
LEFT JOIN hz_contact_points c ON p.party_id = c.party_id
WHERE p.party_id = 1001
GROUP BY p.party_id;
```

---

## Database Size

| Table | Records | Size |
|-------|---------|------|
| hz_parties | 39 | ~3 KB |
| hz_cust_accounts | 27 | ~2 KB |
| hz_party_sites | 24 | ~2 KB |
| hz_contact_points | 33 | ~2 KB |
| hz_relationships | 18 | ~1 KB |
| ar_payment_schedules | 22 | ~2 KB |
| oe_orders | 25 | ~1 KB |
| audit_log | 17 | ~2 KB |
| **TOTAL** | **205** | **~15 KB** |

---

## Testing Data Features

### Ready-to-Test Scenarios:
1. ✅ **Duplicate Detection** - 4 duplicate pairs
2. ✅ **Payment Issues** - 8 overdue invoices
3. ✅ **Lifecycle States** - All 4 lifecycle states represented
4. ✅ **Corporate Hierarchy** - Parent-subsidiary relationships
5. ✅ **Business Partnerships** - Partner relationships
6. ✅ **Contact Management** - Active and inactive contacts
7. ✅ **Address Validation** - Validated and unvalidated sites
8. ✅ **Audit Trail** - 17 audit entries across 7 workflows
9. ✅ **Returns/RMA** - 3 return orders
10. ✅ **Credit Management** - Various credit limits and adjustments

---

## Access Patterns

**Connect to Database:**
```python
from demo_db import get_connection
conn = get_connection()
c = conn.cursor()
```

**Last Updated:** 2026-03-12
**Test Data Generator:** `add_test_data.py`

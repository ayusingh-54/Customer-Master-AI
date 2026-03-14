"""
Workflow 6: Dormant Account Archiving Agent
Nightly scan — identifies and archives accounts with no orders in 365 days.
"""

import json
from datetime import datetime, timedelta
from demo_db import get_connection
from config import ARCHIVE_DAYS, DORMANT_DAYS, AT_RISK_DAYS


def get_lifecycle_state(last_order_date_str: str, account_status: str) -> str:
    """Compute lifecycle state from last order date."""
    if account_status == "I":
        return "INACTIVE"
    if not last_order_date_str:
        return "PROSPECT"
    last = datetime.strptime(last_order_date_str, "%Y-%m-%d")
    days = (datetime.now() - last).days
    if days > ARCHIVE_DAYS:
        return "INACTIVE"
    elif days > DORMANT_DAYS:
        return "DORMANT"
    elif days > AT_RISK_DAYS:
        return "AT-RISK"
    else:
        return "ACTIVE"


def scan_dormant_accounts(dry_run: bool = True) -> dict:
    """
    Identify accounts eligible for archiving (no order in ARCHIVE_DAYS days).
    dry_run=True: report only. dry_run=False: apply changes.
    """
    conn = get_connection()
    c = conn.cursor()

    cutoff = (datetime.now() - timedelta(days=ARCHIVE_DAYS)).strftime("%Y-%m-%d")

    candidates = c.execute("""
        SELECT ca.cust_account_id, ca.account_number, ca.status,
               ca.last_order_date, ca.lifecycle_state,
               hp.party_name, hp.party_id
        FROM hz_cust_accounts ca
        JOIN hz_parties hp ON hp.party_id = ca.party_id
        WHERE ca.status = 'A'
          AND (ca.last_order_date IS NULL OR ca.last_order_date < ?)
    """, (cutoff,)).fetchall()

    results = []
    for acct in candidates:
        # Check blockers
        open_ar = c.execute(
            "SELECT COALESCE(SUM(amount_remaining), 0) FROM ar_payment_schedules "
            "WHERE cust_account_id=? AND status='OP'",
            (acct["cust_account_id"],)
        ).fetchone()[0]

        open_orders = c.execute(
            "SELECT COUNT(*) FROM oe_orders "
            "WHERE cust_account_id=? AND order_date >= ?",
            (acct["cust_account_id"], cutoff)
        ).fetchone()[0]

        can_archive  = (open_ar == 0 and open_orders == 0)
        blockers     = []
        if open_ar > 0:
            blockers.append(f"Open AR balance: ${open_ar:,.2f}")
        if open_orders > 0:
            blockers.append(f"{open_orders} recent orders")

        if can_archive and not dry_run:
            c.execute(
                "UPDATE hz_cust_accounts SET status='I', lifecycle_state='INACTIVE', "
                "updated_at=datetime('now') WHERE cust_account_id=?",
                (acct["cust_account_id"],)
            )
            c.execute(
                "UPDATE hz_parties SET status='I', updated_at=datetime('now') "
                "WHERE party_id=? AND NOT EXISTS ("
                "  SELECT 1 FROM hz_cust_accounts WHERE party_id=? AND status='A'"
                ")",
                (acct["party_id"], acct["party_id"])
            )
            c.execute(
                "INSERT INTO audit_log(workflow,entity_type,entity_id,action,details) VALUES (?,?,?,?,?)",
                ("ARCHIVING", "HZ_CUST_ACCOUNTS", acct["cust_account_id"],
                 "ARCHIVED",
                 json.dumps({"party_name": acct["party_name"],
                             "last_order": acct["last_order_date"]}))
            )

        days_inactive = None
        if acct["last_order_date"]:
            days_inactive = (datetime.now() - datetime.strptime(acct["last_order_date"], "%Y-%m-%d")).days

        results.append({
            "cust_account_id": acct["cust_account_id"],
            "account_number":  acct["account_number"],
            "party_name":      acct["party_name"],
            "last_order_date": acct["last_order_date"],
            "days_inactive":   days_inactive,
            "can_archive":     can_archive,
            "blockers":        blockers,
            "archived":        can_archive and not dry_run,
        })

    if not dry_run:
        conn.commit()
    conn.close()

    return {
        "dry_run":      dry_run,
        "archive_days": ARCHIVE_DAYS,
        "total_found":  len(results),
        "can_archive":  sum(1 for r in results if r["can_archive"]),
        "blocked":      sum(1 for r in results if not r["can_archive"]),
        "archived":     sum(1 for r in results if r.get("archived")),
        "accounts":     results,
    }


def sync_all_lifecycle_states() -> dict:
    """
    Update lifecycle_state for every active account based on last_order_date.
    """
    conn = get_connection()
    c = conn.cursor()

    rows = c.execute(
        "SELECT cust_account_id, last_order_date, status "
        "FROM hz_cust_accounts"
    ).fetchall()

    updates = {"ACTIVE": 0, "AT-RISK": 0, "DORMANT": 0, "INACTIVE": 0, "PROSPECT": 0}
    for row in rows:
        state = get_lifecycle_state(row["last_order_date"], row["status"])
        c.execute(
            "UPDATE hz_cust_accounts SET lifecycle_state=?, updated_at=datetime('now') "
            "WHERE cust_account_id=?",
            (state, row["cust_account_id"])
        )
        updates[state] = updates.get(state, 0) + 1

    conn.commit()
    conn.close()
    return {"status": "UPDATED", "breakdown": updates, "total": len(rows)}

"""
Workflow 3: Credit Limit Auto-Adjustment Agent
Evaluates payment performance and adjusts credit limits.
"""

import json
from datetime import datetime
from demo_db import get_connection
from config import CREDIT_INCREASE_PCT, CREDIT_DECREASE_PCT


def evaluate_credit(cust_account_id: int) -> dict:
    """
    Evaluate a single customer account's payment performance
    and return a credit recommendation.
    """
    conn = get_connection()
    c = conn.cursor()

    acct = c.execute(
        "SELECT ca.*, hp.party_name FROM hz_cust_accounts ca "
        "JOIN hz_parties hp ON hp.party_id = ca.party_id "
        "WHERE ca.cust_account_id=?", (cust_account_id,)
    ).fetchone()
    if not acct:
        conn.close()
        return {"error": f"Account {cust_account_id} not found"}

    # Open AR balance
    open_balance = c.execute(
        "SELECT COALESCE(SUM(amount_remaining), 0) FROM ar_payment_schedules "
        "WHERE cust_account_id=? AND status='OP'", (cust_account_id,)
    ).fetchone()[0]

    # Overdue invoices
    today_str = datetime.now().strftime("%Y-%m-%d")
    overdue_count = c.execute(
        "SELECT COUNT(*) FROM ar_payment_schedules "
        "WHERE cust_account_id=? AND status='OP' AND due_date < ?",
        (cust_account_id, today_str)
    ).fetchone()[0]

    # Order volume (last 6 months)
    six_months_ago = datetime.now().replace(month=max(1, datetime.now().month - 6)).strftime("%Y-%m-%d")
    order_volume = c.execute(
        "SELECT COALESCE(SUM(total_amount), 0) FROM oe_orders "
        "WHERE cust_account_id=? AND order_date >= ?",
        (cust_account_id, six_months_ago)
    ).fetchone()[0]

    # Return rate
    total_orders = c.execute(
        "SELECT COUNT(*) FROM oe_orders WHERE cust_account_id=?", (cust_account_id,)
    ).fetchone()[0]
    return_orders = c.execute(
        "SELECT COUNT(*) FROM oe_orders WHERE cust_account_id=? AND is_return=1",
        (cust_account_id,)
    ).fetchone()[0]
    return_rate = (return_orders / total_orders) if total_orders > 0 else 0

    avg_days = acct["avg_days_to_pay"] or 30
    current_limit = acct["credit_limit"] or 0
    credit_utilisation = (open_balance / current_limit) if current_limit > 0 else 0

    # Scoring model
    score = 0
    reasons = []

    if avg_days <= 20:
        score += 2; reasons.append("Excellent payment speed (<20 days)")
    elif avg_days <= 35:
        score += 1; reasons.append("Good payment speed (≤35 days)")
    elif avg_days <= 60:
        score -= 1; reasons.append("Slow payment speed (36–60 days)")
    else:
        score -= 2; reasons.append("Very slow payment (>60 days)")

    if overdue_count == 0:
        score += 1; reasons.append("No overdue invoices")
    elif overdue_count <= 2:
        score -= 1; reasons.append(f"{overdue_count} overdue invoice(s)")
    else:
        score -= 3; reasons.append(f"{overdue_count} overdue invoices — high risk")

    if return_rate > 0.2:
        score -= 2; reasons.append(f"High return rate: {return_rate:.0%}")
    elif return_rate > 0.1:
        score -= 1; reasons.append(f"Elevated return rate: {return_rate:.0%}")

    if order_volume > 50000:
        score += 1; reasons.append(f"Strong order volume: ${order_volume:,.0f}")

    if credit_utilisation > 0.9:
        score -= 1; reasons.append(f"Near credit limit: {credit_utilisation:.0%} utilised")

    # Decision
    if score >= 2:
        action = "INCREASE"
        pct    = CREDIT_INCREASE_PCT
        new_limit = round(current_limit * (1 + pct), 2)
    elif score <= -2:
        action = "DECREASE"
        pct    = CREDIT_DECREASE_PCT
        new_limit = round(current_limit * (1 - pct), 2)
        if new_limit <= 0:
            action = "HOLD"
            new_limit = 0
    else:
        action    = "NO_CHANGE"
        new_limit = current_limit
        pct       = 0

    conn.close()
    return {
        "cust_account_id": cust_account_id,
        "party_name":      acct["party_name"],
        "account_number":  acct["account_number"],
        "current_limit":   current_limit,
        "open_balance":    open_balance,
        "credit_utilisation": f"{credit_utilisation:.0%}",
        "avg_days_to_pay": avg_days,
        "overdue_invoices": overdue_count,
        "return_rate":     f"{return_rate:.0%}",
        "score":           score,
        "recommendation":  action,
        "new_limit":       new_limit,
        "change_pct":      f"{pct:.0%}",
        "reasons":         reasons,
    }


def apply_credit_adjustment(cust_account_id: int) -> dict:
    """
    Run credit evaluation and apply the recommended change to the database.
    """
    result = evaluate_credit(cust_account_id)
    if "error" in result:
        return result

    if result["recommendation"] == "NO_CHANGE":
        return {**result, "applied": False, "message": "No change required"}

    conn = get_connection()
    c = conn.cursor()

    on_hold = 1 if result["recommendation"] == "HOLD" else 0
    c.execute(
        "UPDATE hz_cust_accounts SET credit_limit=?, on_hold=?, updated_at=datetime('now') "
        "WHERE cust_account_id=?",
        (result["new_limit"], on_hold, cust_account_id)
    )
    c.execute(
        "INSERT INTO audit_log(workflow,entity_type,entity_id,action,details) VALUES (?,?,?,?,?)",
        ("CREDIT_ADJUSTMENT", "HZ_CUST_ACCOUNTS", cust_account_id,
         result["recommendation"],
         json.dumps(result))
    )
    conn.commit()
    conn.close()

    return {**result, "applied": True,
            "message": f"Credit limit changed: ${result['current_limit']:,.0f} → ${result['new_limit']:,.0f}"}


def run_credit_sweep() -> dict:
    """Run credit evaluation for all active accounts."""
    conn = get_connection()
    c = conn.cursor()
    ids = [r[0] for r in c.execute(
        "SELECT cust_account_id FROM hz_cust_accounts WHERE status='A'"
    ).fetchall()]
    conn.close()

    results = []
    for aid in ids:
        res = apply_credit_adjustment(aid)
        results.append(res)

    summary = {
        "total":     len(results),
        "increased": sum(1 for r in results if r.get("recommendation") == "INCREASE"),
        "decreased": sum(1 for r in results if r.get("recommendation") == "DECREASE"),
        "held":      sum(1 for r in results if r.get("recommendation") == "HOLD"),
        "unchanged": sum(1 for r in results if r.get("recommendation") == "NO_CHANGE"),
        "details":   results,
    }
    return summary

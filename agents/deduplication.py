"""
Workflow 1: Customer Deduplication Agent
Finds and merges duplicate parties using fuzzy matching.
"""

import json
from rapidfuzz import fuzz
from demo_db import get_connection


def find_duplicates(party_name: str = None, party_type: str = "ORGANIZATION",
                    threshold: float = 0.88) -> dict:
    """
    Find potential duplicate parties by name similarity (Jaro-Winkler equivalent),
    matching tax_reference, or duns_number.
    """
    conn = get_connection()
    c = conn.cursor()

    if party_name:
        # Find duplicates for a specific party name
        rows = c.execute(
            "SELECT party_id, party_name, party_type, status, tax_reference, duns_number "
            "FROM hz_parties WHERE party_type=? AND status='A'",
            (party_type,)
        ).fetchall()

        matches = []
        for row in rows:
            score = fuzz.token_sort_ratio(party_name.upper(), row["party_name"].upper()) / 100.0
            if score >= threshold:
                matches.append({
                    "party_id":   row["party_id"],
                    "party_name": row["party_name"],
                    "status":     row["status"],
                    "tax_ref":    row["tax_reference"],
                    "duns":       row["duns_number"],
                    "similarity": round(score, 4),
                })
        matches.sort(key=lambda x: x["similarity"], reverse=True)
        conn.close()
        return {"query_name": party_name, "threshold": threshold, "matches": matches}

    else:
        # Full scan — compare all pairs
        rows = c.execute(
            "SELECT party_id, party_name, tax_reference, duns_number "
            "FROM hz_parties WHERE party_type=? AND status='A'",
            (party_type,)
        ).fetchall()
        rows = list(rows)

        duplicate_groups = []
        seen = set()

        for i, r1 in enumerate(rows):
            group = []
            if r1["party_id"] in seen:
                continue
            for j, r2 in enumerate(rows):
                if i == j:
                    continue
                score = fuzz.token_sort_ratio(
                    r1["party_name"].upper(), r2["party_name"].upper()
                ) / 100.0
                # Also check exact tax_reference / duns match
                exact = (
                    (r1["tax_reference"] and r1["tax_reference"] == r2["tax_reference"]) or
                    (r1["duns_number"]   and r1["duns_number"]   == r2["duns_number"])
                )
                if score >= threshold or exact:
                    group.append({
                        "party_id":   r2["party_id"],
                        "party_name": r2["party_name"],
                        "similarity": round(score, 4),
                        "exact_key":  exact,
                    })
                    seen.add(r2["party_id"])

            if group:
                seen.add(r1["party_id"])
                duplicate_groups.append({
                    "golden_candidate": {
                        "party_id":   r1["party_id"],
                        "party_name": r1["party_name"],
                    },
                    "duplicates": group,
                })

        conn.close()
        return {
            "total_duplicate_groups": len(duplicate_groups),
            "threshold": threshold,
            "groups": duplicate_groups,
        }


def merge_parties(golden_id: int, duplicate_id: int) -> dict:
    """
    Merge duplicate_id into golden_id:
    - Redirect accounts, sites, contacts, relationships
    - Mark duplicate as Merged (status='M')
    - Log the merge
    """
    conn = get_connection()
    c = conn.cursor()

    golden   = c.execute("SELECT * FROM hz_parties WHERE party_id=?", (golden_id,)).fetchone()
    duplicate = c.execute("SELECT * FROM hz_parties WHERE party_id=?", (duplicate_id,)).fetchone()

    if not golden:
        conn.close()
        return {"error": f"Golden party {golden_id} not found"}
    if not duplicate:
        conn.close()
        return {"error": f"Duplicate party {duplicate_id} not found"}

    steps = []

    # Re-point customer accounts
    n = c.execute(
        "UPDATE hz_cust_accounts SET party_id=? WHERE party_id=?",
        (golden_id, duplicate_id)
    ).rowcount
    steps.append(f"Redirected {n} customer accounts to golden party")

    # Re-point party sites
    n = c.execute(
        "UPDATE hz_party_sites SET party_id=? WHERE party_id=?",
        (golden_id, duplicate_id)
    ).rowcount
    steps.append(f"Redirected {n} party sites to golden party")

    # Re-point contact points
    n = c.execute(
        "UPDATE hz_contact_points SET party_id=? WHERE party_id=?",
        (golden_id, duplicate_id)
    ).rowcount
    steps.append(f"Redirected {n} contact points to golden party")

    # Re-point relationships (subject and object)
    n1 = c.execute(
        "UPDATE hz_relationships SET subject_id=? WHERE subject_id=?",
        (golden_id, duplicate_id)
    ).rowcount
    n2 = c.execute(
        "UPDATE hz_relationships SET object_id=? WHERE object_id=?",
        (golden_id, duplicate_id)
    ).rowcount
    steps.append(f"Redirected {n1+n2} relationships to golden party")

    # Mark duplicate as merged
    c.execute(
        "UPDATE hz_parties SET status='M', updated_at=datetime('now') WHERE party_id=?",
        (duplicate_id,)
    )

    # Audit log
    c.execute(
        "INSERT INTO audit_log(workflow,entity_type,entity_id,action,details) VALUES (?,?,?,?,?)",
        ("DEDUPLICATION", "HZ_PARTIES", golden_id, "MERGE",
         json.dumps({"golden_id": golden_id, "merged_id": duplicate_id,
                     "golden_name": golden["party_name"],
                     "merged_name": duplicate["party_name"],
                     "steps": steps}))
    )
    conn.commit()
    conn.close()

    return {
        "status":       "SUCCESS",
        "golden_id":    golden_id,
        "duplicate_id": duplicate_id,
        "golden_name":  golden["party_name"],
        "merged_name":  duplicate["party_name"],
        "steps":        steps,
    }

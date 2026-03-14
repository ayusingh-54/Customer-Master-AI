"""
Workflow 4: Contact Point Maintenance Agent
Handles bounced emails, invalid contacts, and contact enrichment.
"""

import json
from demo_db import get_connection


def get_contact_points(party_id: int) -> dict:
    """Return all contact points for a party."""
    conn = get_connection()
    c = conn.cursor()
    hp = c.execute(
        "SELECT party_name FROM hz_parties WHERE party_id=?", (party_id,)
    ).fetchone()
    if not hp:
        conn.close()
        return {"error": f"Party {party_id} not found"}

    rows = c.execute(
        "SELECT * FROM hz_contact_points WHERE party_id=?", (party_id,)
    ).fetchall()
    conn.close()
    return {
        "party_id":   party_id,
        "party_name": hp["party_name"],
        "contacts":   [dict(r) for r in rows],
    }


def mark_contact_invalid(contact_point_id: int, reason: str = "BOUNCED") -> dict:
    """Mark a contact point as invalid (e.g. after email bounce)."""
    conn = get_connection()
    c = conn.cursor()

    cp = c.execute(
        "SELECT * FROM hz_contact_points WHERE contact_point_id=?",
        (contact_point_id,)
    ).fetchone()
    if not cp:
        conn.close()
        return {"error": f"Contact point {contact_point_id} not found"}

    c.execute(
        "UPDATE hz_contact_points SET status='I', updated_at=datetime('now') "
        "WHERE contact_point_id=?", (contact_point_id,)
    )

    # Search for alternate contact at same party
    alternates = c.execute(
        "SELECT * FROM hz_contact_points "
        "WHERE party_id=? AND contact_type=? AND status='A' AND contact_point_id!=?",
        (cp["party_id"], cp["contact_type"], contact_point_id)
    ).fetchall()

    c.execute(
        "INSERT INTO audit_log(workflow,entity_type,entity_id,action,details) VALUES (?,?,?,?,?)",
        ("CONTACT_MAINTENANCE", "HZ_CONTACT_POINTS", contact_point_id,
         "MARKED_INVALID",
         json.dumps({"reason": reason, "value": cp["contact_value"],
                     "alternates_found": len(alternates)}))
    )
    conn.commit()
    conn.close()

    return {
        "contact_point_id":  contact_point_id,
        "party_id":          cp["party_id"],
        "type":              cp["contact_type"],
        "invalidated_value": cp["contact_value"],
        "reason":            reason,
        "alternates_found":  len(alternates),
        "alternates":        [dict(a) for a in alternates],
        "action_needed":     len(alternates) == 0,
    }


def add_contact_point(party_id: int, contact_type: str, contact_value: str) -> dict:
    """Add a new contact point for a party."""
    conn = get_connection()
    c = conn.cursor()

    hp = c.execute("SELECT party_name FROM hz_parties WHERE party_id=?", (party_id,)).fetchone()
    if not hp:
        conn.close()
        return {"error": f"Party {party_id} not found"}

    # Check for duplicate
    existing = c.execute(
        "SELECT contact_point_id FROM hz_contact_points "
        "WHERE party_id=? AND contact_type=? AND contact_value=?",
        (party_id, contact_type.upper(), contact_value)
    ).fetchone()
    if existing:
        conn.close()
        return {"error": "Duplicate contact point", "existing_id": existing[0]}

    c.execute(
        "INSERT INTO hz_contact_points(party_id,contact_type,contact_value,status) "
        "VALUES (?,?,?,?)",
        (party_id, contact_type.upper(), contact_value, "A")
    )
    new_id = c.lastrowid
    c.execute(
        "INSERT INTO audit_log(workflow,entity_type,entity_id,action,details) VALUES (?,?,?,?,?)",
        ("CONTACT_MAINTENANCE", "HZ_CONTACT_POINTS", new_id,
         "ADDED",
         json.dumps({"party_id": party_id, "type": contact_type, "value": contact_value}))
    )
    conn.commit()
    conn.close()

    return {
        "status":           "CREATED",
        "contact_point_id": new_id,
        "party_id":         party_id,
        "party_name":       hp["party_name"],
        "type":             contact_type.upper(),
        "value":            contact_value,
    }


def get_parties_needing_contact() -> dict:
    """Find parties with no active contact points."""
    conn = get_connection()
    c = conn.cursor()
    rows = c.execute("""
        SELECT hp.party_id, hp.party_name, hp.party_type
        FROM hz_parties hp
        LEFT JOIN hz_contact_points cp ON cp.party_id = hp.party_id AND cp.status = 'A'
        WHERE hp.status = 'A'
        GROUP BY hp.party_id
        HAVING COUNT(cp.contact_point_id) = 0
    """).fetchall()
    conn.close()
    return {
        "count":   len(rows),
        "parties": [dict(r) for r in rows],
    }

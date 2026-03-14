"""
Workflow 5: Relationship Graph Maintenance Agent
Manages party-to-party relationships (parent/child, partners, contacts).
"""

import json
from demo_db import get_connection


VALID_REL_TYPES = [
    "CUSTOMER_CONTACT",
    "PARENT_SUBSIDIARY",
    "PARTNER",
    "RESELLER",
    "COMPETITOR",
]


def get_relationships(party_id: int) -> dict:
    """Get all relationships for a party (as subject or object)."""
    conn = get_connection()
    c = conn.cursor()

    hp = c.execute(
        "SELECT party_name, party_type FROM hz_parties WHERE party_id=?", (party_id,)
    ).fetchone()
    if not hp:
        conn.close()
        return {"error": f"Party {party_id} not found"}

    as_subject = c.execute("""
        SELECT r.relationship_id, r.relationship_type, r.status,
               hp.party_id as related_id, hp.party_name as related_name, hp.party_type as related_type
        FROM hz_relationships r
        JOIN hz_parties hp ON hp.party_id = r.object_id
        WHERE r.subject_id = ?
    """, (party_id,)).fetchall()

    as_object = c.execute("""
        SELECT r.relationship_id, r.relationship_type, r.status,
               hp.party_id as related_id, hp.party_name as related_name, hp.party_type as related_type
        FROM hz_relationships r
        JOIN hz_parties hp ON hp.party_id = r.subject_id
        WHERE r.object_id = ?
    """, (party_id,)).fetchall()

    conn.close()
    return {
        "party_id":   party_id,
        "party_name": hp["party_name"],
        "party_type": hp["party_type"],
        "outgoing":   [dict(r) for r in as_subject],
        "incoming":   [dict(r) for r in as_object],
        "total":      len(as_subject) + len(as_object),
    }


def add_relationship(subject_id: int, object_id: int, rel_type: str) -> dict:
    """Add a new relationship between two parties."""
    rel_type = rel_type.upper()
    if rel_type not in VALID_REL_TYPES:
        return {"error": f"Invalid relationship type. Valid: {VALID_REL_TYPES}"}

    conn = get_connection()
    c = conn.cursor()

    # Validate both parties exist
    s = c.execute("SELECT party_name FROM hz_parties WHERE party_id=?", (subject_id,)).fetchone()
    o = c.execute("SELECT party_name FROM hz_parties WHERE party_id=?", (object_id,)).fetchone()
    if not s:
        conn.close()
        return {"error": f"Subject party {subject_id} not found"}
    if not o:
        conn.close()
        return {"error": f"Object party {object_id} not found"}

    # Check for duplicate
    existing = c.execute(
        "SELECT relationship_id FROM hz_relationships "
        "WHERE subject_id=? AND object_id=? AND relationship_type=? AND status='A'",
        (subject_id, object_id, rel_type)
    ).fetchone()
    if existing:
        conn.close()
        return {"error": "Relationship already exists", "relationship_id": existing[0]}

    c.execute(
        "INSERT INTO hz_relationships(subject_id,object_id,relationship_type,status) VALUES (?,?,?,?)",
        (subject_id, object_id, rel_type, "A")
    )
    new_id = c.lastrowid
    c.execute(
        "INSERT INTO audit_log(workflow,entity_type,entity_id,action,details) VALUES (?,?,?,?,?)",
        ("RELATIONSHIP_MGMT", "HZ_RELATIONSHIPS", new_id,
         "ADDED",
         json.dumps({"subject": subject_id, "subject_name": s["party_name"],
                     "object": object_id, "object_name": o["party_name"],
                     "type": rel_type}))
    )
    conn.commit()
    conn.close()

    return {
        "status":          "CREATED",
        "relationship_id": new_id,
        "subject_id":      subject_id,
        "subject_name":    s["party_name"],
        "object_id":       object_id,
        "object_name":     o["party_name"],
        "type":            rel_type,
    }


def update_relationship_for_restructure(old_parent_id: int, new_parent_id: int) -> dict:
    """
    Corporate restructure: transfer all subsidiary/partner relationships
    from old_parent to new_parent.
    """
    conn = get_connection()
    c = conn.cursor()

    old = c.execute("SELECT party_name FROM hz_parties WHERE party_id=?", (old_parent_id,)).fetchone()
    new = c.execute("SELECT party_name FROM hz_parties WHERE party_id=?", (new_parent_id,)).fetchone()
    if not old or not new:
        conn.close()
        return {"error": "One or both parties not found"}

    n = c.execute(
        "UPDATE hz_relationships SET subject_id=? WHERE subject_id=? AND status='A'",
        (new_parent_id, old_parent_id)
    ).rowcount

    c.execute(
        "INSERT INTO audit_log(workflow,entity_type,entity_id,action,details) VALUES (?,?,?,?,?)",
        ("RELATIONSHIP_MGMT", "HZ_PARTIES", old_parent_id,
         "CORPORATE_RESTRUCTURE",
         json.dumps({"old_parent": old_parent_id, "old_name": old["party_name"],
                     "new_parent": new_parent_id, "new_name": new["party_name"],
                     "relationships_transferred": n}))
    )
    conn.commit()
    conn.close()

    return {
        "status":                    "SUCCESS",
        "old_parent_id":             old_parent_id,
        "old_parent_name":           old["party_name"],
        "new_parent_id":             new_parent_id,
        "new_parent_name":           new["party_name"],
        "relationships_transferred": n,
    }


def get_relationship_graph() -> dict:
    """Return full relationship graph summary."""
    conn = get_connection()
    c = conn.cursor()
    total = c.execute("SELECT COUNT(*) FROM hz_relationships WHERE status='A'").fetchone()[0]
    by_type = c.execute(
        "SELECT relationship_type, COUNT(*) as cnt FROM hz_relationships "
        "WHERE status='A' GROUP BY relationship_type"
    ).fetchall()
    conn.close()
    return {
        "total_active_relationships": total,
        "by_type": {r["relationship_type"]: r["cnt"] for r in by_type},
    }

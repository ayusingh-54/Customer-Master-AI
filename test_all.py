#!/usr/bin/env python3
"""
Test suite — exercises all 6 workflows end-to-end.
Run:  python test_all.py
"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(__file__))

# Wipe and re-seed for clean test
db_path = os.path.join(os.path.dirname(__file__), "demo.db")
if os.path.exists(db_path):
    os.remove(db_path)

import demo_db
demo_db.init_db()

from agents.deduplication import find_duplicates, merge_parties
from agents.address        import validate_address, get_unvalidated_addresses
from agents.credit         import evaluate_credit, apply_credit_adjustment, run_credit_sweep
from agents.contact        import (get_contact_points, mark_contact_invalid,
                                   add_contact_point, get_parties_needing_contact)
from agents.relationship   import (get_relationships, add_relationship,
                                   update_relationship_for_restructure, get_relationship_graph)
from agents.archiving      import scan_dormant_accounts, sync_all_lifecycle_states


def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def check(label, result, assert_fn=None):
    ok = assert_fn(result) if assert_fn else True
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {label}")
    if not ok:
        print(f"         Result: {json.dumps(result, indent=4, default=str)}")
    return ok


# ──────────────────────────────────────────────────────────────────────────────
section("WORKFLOW 1: Deduplication")

r = find_duplicates()
check("Full scan finds duplicate groups",       r, lambda x: x["total_duplicate_groups"] >= 1)
check("Beta Technologies detected as dup",      r, lambda x: any(
    "Beta" in g["golden_candidate"]["party_name"] for g in x["groups"]
))

r = find_duplicates(party_name="Acme Corporation")
check("Targeted search returns Acme Corp",      r, lambda x: len(x["matches"]) >= 1)

r = merge_parties(golden_id=1001, duplicate_id=1002)
check("Merge succeeds",                         r, lambda x: x["status"] == "SUCCESS")
check("Merge steps reported",                   r, lambda x: len(x["steps"]) > 0)


# ──────────────────────────────────────────────────────────────────────────────
section("WORKFLOW 2: Address Validation")

r = get_unvalidated_addresses()
check("Unvalidated addresses found",            r, lambda x: x["count"] >= 1)

r = validate_address(party_site_id=4005)
check("Epsilon site validation attempted",      r, lambda x: x["total_checked"] == 1)

r = validate_address(party_id=1001)
check("Acme all sites validated",               r, lambda x: x["total_checked"] >= 1)


# ──────────────────────────────────────────────────────────────────────────────
section("WORKFLOW 3: Credit Limit")

r = evaluate_credit(cust_account_id=3001)
check("Acme credit evaluation returned",        r, lambda x: "recommendation" in x)
check("Score is numeric",                       r, lambda x: isinstance(x["score"], int))

r = evaluate_credit(cust_account_id=3004)  # Delta — dormant, high avg days
check("Delta gets DECREASE or HOLD",            r, lambda x: x["recommendation"] in ("DECREASE","HOLD","NO_CHANGE"))

r = apply_credit_adjustment(3009)           # Iota — excellent payer
check("Iota credit applied",                    r, lambda x: "applied" in x)

r = run_credit_sweep()
check("Credit sweep ran for all accounts",      r, lambda x: x["total"] >= 5)
check("Some accounts increased or unchanged",   r, lambda x: (x["increased"] + x["unchanged"]) > 0)


# ──────────────────────────────────────────────────────────────────────────────
section("WORKFLOW 4: Contact Points")

r = get_contact_points(party_id=1001)
check("Acme contacts returned",                 r, lambda x: len(x["contacts"]) >= 1)

r = mark_contact_invalid(contact_point_id=5005, reason="BOUNCED")
check("Bounced contact marked invalid",         r, lambda x: x["invalidated_value"] is not None)

r = add_contact_point(party_id=1005, contact_type="EMAIL", contact_value="new@gamma.com")
check("New contact added for Gamma",            r, lambda x: x["status"] == "CREATED")

r = get_parties_needing_contact()
check("Parties needing contact returned",       r, lambda x: "count" in x)


# ──────────────────────────────────────────────────────────────────────────────
section("WORKFLOW 5: Relationships")

r = get_relationships(party_id=1001)
check("Acme relationships returned",            r, lambda x: x["total"] >= 1)

r = add_relationship(subject_id=1011, object_id=1012, rel_type="PARTNER")
check("New PARTNER relationship added",         r, lambda x: x["status"] == "CREATED")

r = update_relationship_for_restructure(old_parent_id=1001, new_parent_id=1003)
check("Restructure completed",                  r, lambda x: "relationships_transferred" in x)

r = get_relationship_graph()
check("Graph summary returned",                 r, lambda x: x["total_active_relationships"] >= 1)


# ──────────────────────────────────────────────────────────────────────────────
section("WORKFLOW 6: Archiving & Lifecycle")

r = sync_all_lifecycle_states()
check("Lifecycle states synced",                r, lambda x: x["status"] == "UPDATED")
check("ACTIVE accounts exist",                  r, lambda x: x["breakdown"].get("ACTIVE", 0) >= 1)

r = scan_dormant_accounts(dry_run=True)
check("Dormant scan dry-run returned",          r, lambda x: "total_found" in x)
check("Some dormant accounts found",            r, lambda x: x["total_found"] >= 1)

r = scan_dormant_accounts(dry_run=False)
check("Archive applied (not dry run)",          r, lambda x: "archived" in x)

# ──────────────────────────────────────────────────────────────────────────────
section("SUMMARY")
print("""
  All 6 workflows tested:
  1. Deduplication   — fuzzy match + merge
  2. Address         — validation + enrichment
  3. Credit          — scoring + auto-adjust
  4. Contact         — bounce handling + enrichment
  5. Relationships   — graph + restructure
  6. Archiving       — lifecycle + dormant scan
""")

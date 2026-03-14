#!/usr/bin/env python3
"""
Customer Master Data AI — MCP Server
=====================================
Exposes Oracle EBS TCA customer data management as MCP tools.
Works with Claude Code (claude mcp) and Claude Desktop.

Run:  python server.py
"""

import sys
import os
import json
import asyncio

# Add parent dir so agents can import demo_db / config
sys.path.insert(0, os.path.dirname(__file__))

import demo_db
demo_db.init_db()  # seed SQLite on first run

from mcp.server import Server
from mcp.server.stdio import stdio_server
import mcp.types as types

# ── Import all agents ─────────────────────────────────────────────────────────
from agents.deduplication import find_duplicates, merge_parties
from agents.address        import validate_address, get_unvalidated_addresses
from agents.credit         import evaluate_credit, apply_credit_adjustment, run_credit_sweep
from agents.contact        import (get_contact_points, mark_contact_invalid,
                                   add_contact_point, get_parties_needing_contact)
from agents.relationship   import (get_relationships, add_relationship,
                                   update_relationship_for_restructure, get_relationship_graph)
from agents.archiving      import scan_dormant_accounts, sync_all_lifecycle_states
from agents.excel_export   import (export_customers_master, export_credit_report,
                                   export_duplicates_report, export_audit_log,
                                   export_dormant_report, export_full_dashboard)

app = Server("customer-master-data-ai")


# ═══════════════════════════════════════════════════════════════════════════════
# TOOL REGISTRY
# ═══════════════════════════════════════════════════════════════════════════════

@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [

        # ── Search & Query ────────────────────────────────────────────────────
        types.Tool(
            name="search_parties",
            description=(
                "Search for customer parties by name, party_id, or account_number. "
                "Returns matching parties with their lifecycle state and credit info."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query":      {"type": "string",  "description": "Name or account number to search"},
                    "party_type": {"type": "string",  "description": "ORGANIZATION or PERSON", "default": "ORGANIZATION"},
                    "limit":      {"type": "integer", "description": "Max results (default 20)", "default": 20},
                },
                "required": ["query"],
            },
        ),

        types.Tool(
            name="get_customer_summary",
            description=(
                "Get a full customer summary: party info, account, credit utilisation, "
                "open balance, lifecycle state, contact points, and sites."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "cust_account_id": {"type": "integer", "description": "Customer account ID"},
                    "account_number":  {"type": "string",  "description": "Account number (alternative to ID)"},
                },
            },
        ),

        types.Tool(
            name="get_audit_log",
            description="View the audit log for all AI actions. Filter by workflow or entity.",
            inputSchema={
                "type": "object",
                "properties": {
                    "workflow":  {"type": "string",  "description": "Filter by workflow name"},
                    "limit":     {"type": "integer", "description": "Max entries (default 50)", "default": 50},
                },
            },
        ),

        # ── Workflow 1: Deduplication ─────────────────────────────────────────
        types.Tool(
            name="find_duplicate_parties",
            description=(
                "WORKFLOW 1 — Find potential duplicate parties using fuzzy name matching "
                "(Jaro-Winkler ≥88%) and exact tax_reference / DUNS matching. "
                "Provide a party_name for targeted search or leave blank for full scan."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "party_name": {"type": "string",  "description": "Name to search for duplicates (optional)"},
                    "party_type": {"type": "string",  "description": "ORGANIZATION or PERSON", "default": "ORGANIZATION"},
                    "threshold":  {"type": "number",  "description": "Similarity threshold 0–1 (default 0.88)", "default": 0.88},
                },
            },
        ),

        types.Tool(
            name="merge_duplicate_parties",
            description=(
                "WORKFLOW 1 — Merge a duplicate party into the golden record. "
                "All accounts, sites, contacts, and relationships are redirected. "
                "The duplicate is marked as Merged (status=M)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "golden_id":    {"type": "integer", "description": "Party ID to keep (the golden record)"},
                    "duplicate_id": {"type": "integer", "description": "Party ID to merge and retire"},
                },
                "required": ["golden_id", "duplicate_id"],
            },
        ),

        # ── Workflow 2: Address Validation ────────────────────────────────────
        types.Tool(
            name="validate_address",
            description=(
                "WORKFLOW 2 — Validate and enrich addresses. "
                "Provide party_site_id for one site, party_id for all sites of a party, "
                "or leave blank to process all unvalidated addresses."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "party_site_id": {"type": "integer", "description": "Validate a specific site"},
                    "party_id":      {"type": "integer", "description": "Validate all sites for a party"},
                },
            },
        ),

        types.Tool(
            name="get_unvalidated_addresses",
            description="Return all party sites that have not yet been validated.",
            inputSchema={"type": "object", "properties": {}},
        ),

        # ── Workflow 3: Credit ────────────────────────────────────────────────
        types.Tool(
            name="evaluate_credit",
            description=(
                "WORKFLOW 3 — Evaluate a customer's payment performance and return "
                "a credit limit recommendation (INCREASE / DECREASE / HOLD / NO_CHANGE) "
                "without applying changes."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "cust_account_id": {"type": "integer", "description": "Customer account ID"},
                },
                "required": ["cust_account_id"],
            },
        ),

        types.Tool(
            name="apply_credit_adjustment",
            description=(
                "WORKFLOW 3 — Run credit evaluation AND apply the recommended change to the database. "
                "Puts account ON HOLD if credit drops to zero."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "cust_account_id": {"type": "integer", "description": "Customer account ID"},
                },
                "required": ["cust_account_id"],
            },
        ),

        types.Tool(
            name="run_credit_sweep",
            description=(
                "WORKFLOW 3 — Run credit evaluation and auto-adjust limits for ALL active accounts. "
                "Returns a summary with counts of increases, decreases, holds, and unchanged."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),

        # ── Workflow 4: Contact Points ────────────────────────────────────────
        types.Tool(
            name="get_contact_points",
            description="WORKFLOW 4 — Get all contact points (email, phone, fax) for a party.",
            inputSchema={
                "type": "object",
                "properties": {
                    "party_id": {"type": "integer", "description": "Party ID"},
                },
                "required": ["party_id"],
            },
        ),

        types.Tool(
            name="mark_contact_invalid",
            description=(
                "WORKFLOW 4 — Mark a contact point as invalid (e.g. after email bounce). "
                "Automatically searches for alternate contacts at the same party."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "contact_point_id": {"type": "integer", "description": "Contact point ID"},
                    "reason":           {"type": "string",  "description": "BOUNCED, INVALID, DISCONNECTED", "default": "BOUNCED"},
                },
                "required": ["contact_point_id"],
            },
        ),

        types.Tool(
            name="add_contact_point",
            description="WORKFLOW 4 — Add a new contact point for a party.",
            inputSchema={
                "type": "object",
                "properties": {
                    "party_id":      {"type": "integer", "description": "Party ID"},
                    "contact_type":  {"type": "string",  "description": "EMAIL, PHONE, FAX, WEB"},
                    "contact_value": {"type": "string",  "description": "The email address, phone number, etc."},
                },
                "required": ["party_id", "contact_type", "contact_value"],
            },
        ),

        types.Tool(
            name="get_parties_needing_contact",
            description="WORKFLOW 4 — Find all active parties with no valid contact points.",
            inputSchema={"type": "object", "properties": {}},
        ),

        # ── Workflow 5: Relationships ─────────────────────────────────────────
        types.Tool(
            name="get_relationships",
            description=(
                "WORKFLOW 5 — Get the full relationship graph for a party: "
                "contacts, subsidiaries, partners, resellers."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "party_id": {"type": "integer", "description": "Party ID"},
                },
                "required": ["party_id"],
            },
        ),

        types.Tool(
            name="add_relationship",
            description=(
                "WORKFLOW 5 — Add a relationship between two parties. "
                "Types: CUSTOMER_CONTACT, PARENT_SUBSIDIARY, PARTNER, RESELLER, COMPETITOR."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "subject_id": {"type": "integer", "description": "Subject party ID"},
                    "object_id":  {"type": "integer", "description": "Object party ID"},
                    "rel_type":   {"type": "string",  "description": "Relationship type"},
                },
                "required": ["subject_id", "object_id", "rel_type"],
            },
        ),

        types.Tool(
            name="update_relationships_for_restructure",
            description=(
                "WORKFLOW 5 — Corporate restructure: transfer all relationships "
                "from old_parent_id to new_parent_id."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "old_parent_id": {"type": "integer", "description": "Old parent party ID"},
                    "new_parent_id": {"type": "integer", "description": "New parent party ID"},
                },
                "required": ["old_parent_id", "new_parent_id"],
            },
        ),

        types.Tool(
            name="get_relationship_graph_summary",
            description="WORKFLOW 5 — Summary of all active relationships by type.",
            inputSchema={"type": "object", "properties": {}},
        ),

        # ── Workflow 6: Archiving ─────────────────────────────────────────────
        types.Tool(
            name="scan_dormant_accounts",
            description=(
                "WORKFLOW 6 — Find accounts with no orders in 365+ days. "
                "dry_run=true (default) reports without changes. "
                "dry_run=false archives eligible accounts."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "dry_run": {"type": "boolean", "description": "True=report only, False=archive", "default": True},
                },
            },
        ),

        types.Tool(
            name="sync_lifecycle_states",
            description=(
                "Recalculate and update lifecycle states for all accounts: "
                "PROSPECT → ACTIVE → AT-RISK → DORMANT → INACTIVE."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),

        # ── Excel Exports ─────────────────────────────────────────────────────
        types.Tool(
            name="export_customers_to_excel",
            description=(
                "Create a fully-formatted Excel file with 4 sheets: "
                "Customer Accounts (with credit utilisation + colour-coded lifecycle), "
                "Party Sites (addresses + validation status), "
                "Contact Points, and Lifecycle Summary with bar chart. "
                "File is saved to the Desktop."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "output_dir": {"type": "string", "description": "Save folder (default: Desktop)"},
                },
            },
        ),

        types.Tool(
            name="export_credit_report_to_excel",
            description=(
                "Create an Excel credit risk report with payment scoring, "
                "recommended credit limit changes (INCREASE/DECREASE/HOLD), "
                "colour-coded by risk level. File saved to Desktop."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "output_dir": {"type": "string", "description": "Save folder (default: Desktop)"},
                },
            },
        ),

        types.Tool(
            name="export_duplicates_to_excel",
            description=(
                "Create an Excel report of potential duplicate parties found by fuzzy matching. "
                "Shows similarity scores and AUTO-MERGE vs REVIEW recommendations. "
                "File saved to Desktop."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "threshold":  {"type": "number",  "description": "Similarity threshold (default 0.88)", "default": 0.88},
                    "output_dir": {"type": "string",  "description": "Save folder (default: Desktop)"},
                },
            },
        ),

        types.Tool(
            name="export_audit_log_to_excel",
            description=(
                "Export the AI audit log to a colour-coded Excel file. "
                "Optionally filter by workflow name. File saved to Desktop."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "workflow":   {"type": "string",  "description": "Filter by workflow (optional)"},
                    "output_dir": {"type": "string",  "description": "Save folder (default: Desktop)"},
                },
            },
        ),

        types.Tool(
            name="export_dormant_report_to_excel",
            description=(
                "Create an Excel report of dormant accounts (no orders in 365+ days) "
                "showing which can be archived and which are blocked. "
                "File saved to Desktop."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "output_dir": {"type": "string", "description": "Save folder (default: Desktop)"},
                },
            },
        ),

        types.Tool(
            name="export_full_dashboard_to_excel",
            description=(
                "Create ONE complete Excel dashboard workbook containing ALL reports: "
                "Overview KPIs, Customer Accounts, Credit Analysis, Audit Log. "
                "This is the single file you need for a full management review. "
                "File saved to Desktop."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "output_dir": {"type": "string", "description": "Save folder (default: Desktop)"},
                },
            },
        ),
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# TOOL HANDLERS
# ═══════════════════════════════════════════════════════════════════════════════

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    try:
        result = _dispatch(name, arguments)
    except Exception as e:
        result = {"error": str(e), "tool": name}

    return [types.TextContent(type="text", text=json.dumps(result, indent=2, default=str))]


def _dispatch(name: str, args: dict):

    # Search & Query
    if name == "search_parties":
        return _search_parties(**args)
    if name == "get_customer_summary":
        return _get_customer_summary(**args)
    if name == "get_audit_log":
        return _get_audit_log(**args)

    # Workflow 1
    if name == "find_duplicate_parties":
        return find_duplicates(
            party_name=args.get("party_name"),
            party_type=args.get("party_type", "ORGANIZATION"),
            threshold=args.get("threshold", 0.88),
        )
    if name == "merge_duplicate_parties":
        return merge_parties(args["golden_id"], args["duplicate_id"])

    # Workflow 2
    if name == "validate_address":
        return validate_address(
            party_site_id=args.get("party_site_id"),
            party_id=args.get("party_id"),
        )
    if name == "get_unvalidated_addresses":
        return get_unvalidated_addresses()

    # Workflow 3
    if name == "evaluate_credit":
        return evaluate_credit(args["cust_account_id"])
    if name == "apply_credit_adjustment":
        return apply_credit_adjustment(args["cust_account_id"])
    if name == "run_credit_sweep":
        return run_credit_sweep()

    # Workflow 4
    if name == "get_contact_points":
        return get_contact_points(args["party_id"])
    if name == "mark_contact_invalid":
        return mark_contact_invalid(args["contact_point_id"], args.get("reason", "BOUNCED"))
    if name == "add_contact_point":
        return add_contact_point(args["party_id"], args["contact_type"], args["contact_value"])
    if name == "get_parties_needing_contact":
        return get_parties_needing_contact()

    # Workflow 5
    if name == "get_relationships":
        return get_relationships(args["party_id"])
    if name == "add_relationship":
        return add_relationship(args["subject_id"], args["object_id"], args["rel_type"])
    if name == "update_relationships_for_restructure":
        return update_relationship_for_restructure(args["old_parent_id"], args["new_parent_id"])
    if name == "get_relationship_graph_summary":
        return get_relationship_graph()

    # Workflow 6
    if name == "scan_dormant_accounts":
        return scan_dormant_accounts(args.get("dry_run", True))
    if name == "sync_lifecycle_states":
        return sync_all_lifecycle_states()

    # Excel exports
    if name == "export_customers_to_excel":
        return export_customers_master(output_dir=args.get("output_dir"))
    if name == "export_credit_report_to_excel":
        return export_credit_report(output_dir=args.get("output_dir"))
    if name == "export_duplicates_to_excel":
        return export_duplicates_report(
            threshold=args.get("threshold", 0.88),
            output_dir=args.get("output_dir")
        )
    if name == "export_audit_log_to_excel":
        return export_audit_log(
            workflow=args.get("workflow"),
            output_dir=args.get("output_dir")
        )
    if name == "export_dormant_report_to_excel":
        return export_dormant_report(output_dir=args.get("output_dir"))
    if name == "export_full_dashboard_to_excel":
        return export_full_dashboard(output_dir=args.get("output_dir"))

    return {"error": f"Unknown tool: {name}"}


# ─────────────────────────────────────────────────────────────────────────────
# Helper query functions (not in agent modules)
# ─────────────────────────────────────────────────────────────────────────────

def _search_parties(query: str, party_type: str = "ORGANIZATION", limit: int = 20):
    from demo_db import get_connection
    conn = get_connection()
    c = conn.cursor()
    rows = c.execute("""
        SELECT hp.party_id, hp.party_name, hp.party_type, hp.status,
               hp.tax_reference, hp.duns_number,
               ca.cust_account_id, ca.account_number,
               ca.credit_limit, ca.lifecycle_state, ca.on_hold,
               ca.last_order_date, ca.avg_days_to_pay
        FROM hz_parties hp
        LEFT JOIN hz_cust_accounts ca ON ca.party_id = hp.party_id
        WHERE hp.party_name LIKE ? OR ca.account_number = ?
        LIMIT ?
    """, (f"%{query}%", query, limit)).fetchall()
    conn.close()
    return {"query": query, "count": len(rows), "results": [dict(r) for r in rows]}


def _get_customer_summary(cust_account_id: int = None, account_number: str = None):
    from demo_db import get_connection
    conn = get_connection()
    c = conn.cursor()

    if account_number:
        acct = c.execute(
            "SELECT * FROM hz_cust_accounts WHERE account_number=?", (account_number,)
        ).fetchone()
    else:
        acct = c.execute(
            "SELECT * FROM hz_cust_accounts WHERE cust_account_id=?", (cust_account_id,)
        ).fetchone()

    if not acct:
        conn.close()
        return {"error": "Account not found"}

    aid = acct["cust_account_id"]
    hp  = c.execute(
        "SELECT * FROM hz_parties WHERE party_id=?", (acct["party_id"],)
    ).fetchone()
    sites = c.execute(
        "SELECT * FROM hz_party_sites WHERE party_id=?", (acct["party_id"],)
    ).fetchall()
    contacts = c.execute(
        "SELECT * FROM hz_contact_points WHERE party_id=? AND status='A'", (acct["party_id"],)
    ).fetchall()
    open_bal = c.execute(
        "SELECT COALESCE(SUM(amount_remaining),0) FROM ar_payment_schedules "
        "WHERE cust_account_id=? AND status='OP'", (aid,)
    ).fetchone()[0]
    orders = c.execute(
        "SELECT * FROM oe_orders WHERE cust_account_id=? ORDER BY order_date DESC LIMIT 5",
        (aid,)
    ).fetchall()

    credit_util = (open_bal / acct["credit_limit"]) if acct["credit_limit"] else 0
    conn.close()

    return {
        "party":            dict(hp),
        "account":          dict(acct),
        "open_balance":     open_bal,
        "credit_utilisation": f"{credit_util:.0%}",
        "sites":            [dict(s) for s in sites],
        "contacts":         [dict(c2) for c2 in contacts],
        "recent_orders":    [dict(o) for o in orders],
    }


def _get_audit_log(workflow: str = None, limit: int = 50):
    from demo_db import get_connection
    conn = get_connection()
    c = conn.cursor()
    if workflow:
        rows = c.execute(
            "SELECT * FROM audit_log WHERE workflow=? ORDER BY log_id DESC LIMIT ?",
            (workflow, limit)
        ).fetchall()
    else:
        rows = c.execute(
            "SELECT * FROM audit_log ORDER BY log_id DESC LIMIT ?", (limit,)
        ).fetchall()
    conn.close()
    return {"count": len(rows), "entries": [dict(r) for r in rows]}


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())

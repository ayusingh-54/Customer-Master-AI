"""
Tier-based tool and endpoint permission matrix.
Single source of truth — imported by auth middleware and admin endpoints.

Tiers (from PDF architecture):
  starter       → read-only tools
  professional  → starter + single-record write ops
  enterprise    → all tools including bulk ops + exports
"""

from enum import Enum
from typing import Dict, Set


class Tier(str, Enum):
    STARTER = "starter"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


# ── Tool permission sets per tier ────────────────────────────────────────────

TIER_TOOLS: Dict[Tier, Set[str]] = {

    # Starter: read-only tools (10)
    Tier.STARTER: {
        "search_parties",
        "get_customer_summary",
        "get_audit_log",
        "find_duplicate_parties",
        "get_unvalidated_addresses",
        "evaluate_credit",
        "get_contact_points",
        "get_parties_needing_contact",
        "get_relationships",
        "get_relationship_graph_summary",
    },

    # Professional: starter + single-record writes (18)
    Tier.PROFESSIONAL: {
        # Read-only (inherited from starter)
        "search_parties",
        "get_customer_summary",
        "get_audit_log",
        "find_duplicate_parties",
        "get_unvalidated_addresses",
        "evaluate_credit",
        "get_contact_points",
        "get_parties_needing_contact",
        "get_relationships",
        "get_relationship_graph_summary",
        # Write operations (single-record)
        "merge_duplicate_parties",
        "validate_address",
        "apply_credit_adjustment",
        "mark_contact_invalid",
        "add_contact_point",
        "add_relationship",
        "update_relationships_for_restructure",
        "scan_dormant_accounts",
    },

    # Enterprise: all tools including bulk ops + exports (22+)
    Tier.ENTERPRISE: {
        # Read-only
        "search_parties",
        "get_customer_summary",
        "get_audit_log",
        "find_duplicate_parties",
        "get_unvalidated_addresses",
        "evaluate_credit",
        "get_contact_points",
        "get_parties_needing_contact",
        "get_relationships",
        "get_relationship_graph_summary",
        # Single-record writes
        "merge_duplicate_parties",
        "validate_address",
        "apply_credit_adjustment",
        "mark_contact_invalid",
        "add_contact_point",
        "add_relationship",
        "update_relationships_for_restructure",
        "scan_dormant_accounts",
        # Bulk operations (enterprise-only)
        "run_credit_sweep",
        "sync_lifecycle_states",
        # Exports (enterprise-only)
        "export_customers",
        "export_credit_report",
        "export_duplicates",
        "export_audit_log",
        "export_dormant",
        "export_dashboard",
    },
}


# ── REST endpoint → tool name mapping ────────────────────────────────────────

ENDPOINT_TO_TOOL: Dict[str, str] = {
    "/api/v1/parties/search":                   "search_parties",
    "/api/v1/parties/summary":                  "get_customer_summary",
    "/api/v1/audit-log":                        "get_audit_log",
    "/api/v1/deduplication/find-duplicates":     "find_duplicate_parties",
    "/api/v1/deduplication/merge":               "merge_duplicate_parties",
    "/api/v1/address/validate":                  "validate_address",
    "/api/v1/address/unvalidated":               "get_unvalidated_addresses",
    "/api/v1/credit/evaluate":                   "evaluate_credit",
    "/api/v1/credit/apply":                      "apply_credit_adjustment",
    "/api/v1/credit/sweep":                      "run_credit_sweep",
    "/api/v1/contacts/needs-contact":            "get_parties_needing_contact",
    "/api/v1/contacts/mark-invalid":             "mark_contact_invalid",
    "/api/v1/contacts/add":                      "add_contact_point",
    "/api/v1/relationships/add":                 "add_relationship",
    "/api/v1/relationships/restructure":         "update_relationships_for_restructure",
    "/api/v1/relationships/graph/summary":       "get_relationship_graph_summary",
    "/api/v1/archiving/scan-dormant":            "scan_dormant_accounts",
    "/api/v1/archiving/sync-lifecycle":          "sync_lifecycle_states",
    # Export endpoints — enterprise only
    "/api/v1/export/customers":                  "export_customers",
    "/api/v1/export/credit-report":              "export_credit_report",
    "/api/v1/export/duplicates":                 "export_duplicates",
    "/api/v1/export/audit-log":                  "export_audit_log",
    "/api/v1/export/dormant":                    "export_dormant",
    "/api/v1/export/dashboard":                  "export_dashboard",
}


# ── Default quota limits (calls per 24-hour rolling window) ──────────────────

DEFAULT_QUOTAS: Dict[Tier, int] = {
    Tier.STARTER:       500,
    Tier.PROFESSIONAL:  2000,
    Tier.ENTERPRISE:    10000,
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def is_tool_allowed(tier: str, tool_name: str) -> bool:
    """Check if a tool is allowed for the given tier."""
    try:
        tier_enum = Tier(tier)
    except ValueError:
        return False
    return tool_name in TIER_TOOLS.get(tier_enum, set())

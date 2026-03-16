#!/usr/bin/env python3
"""
Customer Master AI — Production API Server
==========================================
FastAPI REST API + MCP HTTP/SSE endpoint for Render deployment.

Endpoints:
  GET  /                        API info
  GET  /health                  Health check
  GET  /docs                    Swagger UI (interactive)
  GET  /redoc                   ReDoc UI
  POST /api/v1/parties/search   Search parties
  POST /api/v1/parties/summary  Customer summary
  POST /api/v1/audit-log        Audit log query
  POST /api/v1/deduplication/*  Workflow 1 tools
  POST /api/v1/address/*        Workflow 2 tools
  POST /api/v1/credit/*         Workflow 3 tools
  GET/POST /api/v1/contacts/*   Workflow 4 tools
  GET/POST /api/v1/relationships/* Workflow 5 tools
  POST /api/v1/archiving/*      Workflow 6 tools
  GET  /api/v1/export/*         Excel file downloads
  GET  /mcp/sse                 MCP SSE stream (Claude Desktop)
  POST /mcp/messages/           MCP messages endpoint

Auth: X-API-Key header (set API_SECRET_KEY env var; omit for open dev mode)
"""

import os
import sys
import json
import hashlib
import logging
import shutil
import tempfile
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

# ── Path setup (ensure project root importable) ───────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import config  # noqa: E402 — must be first so env vars are loaded

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("customer-master-ai")

# ── Web framework imports ─────────────────────────────────────────────────────
from fastapi import FastAPI, HTTPException, Security, Request, Response, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# ── MCP ───────────────────────────────────────────────────────────────────────
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

# ── Tier permissions & middleware ─────────────────────────────────────────────
from tier_permissions import is_tool_allowed
from middleware import resolve_tool_name, TelemetryMiddleware
from api.admin import router as admin_router

# ── Agent imports (aliased to avoid name clashes with MCP tool functions) ─────
import demo_db

from agents.deduplication import (
    find_duplicates        as _find_duplicates,
    merge_parties          as _merge_parties,
)
from agents.address import (
    validate_address       as _validate_address,
    get_unvalidated_addresses as _get_unvalidated_addresses,
)
from agents.credit import (
    evaluate_credit        as _eval_credit,
    apply_credit_adjustment as _apply_credit,
    run_credit_sweep       as _run_credit_sweep,
)
from agents.contact import (
    get_contact_points     as _get_contacts,
    mark_contact_invalid   as _mark_contact_invalid,
    add_contact_point      as _add_contact_point,
    get_parties_needing_contact as _get_parties_needing_contact,
)
from agents.relationship import (
    get_relationships      as _get_relationships,
    add_relationship       as _add_relationship,
    update_relationship_for_restructure as _update_restructure,
    get_relationship_graph as _get_rel_graph,
)
from agents.archiving import (
    scan_dormant_accounts  as _scan_dormant,
    sync_all_lifecycle_states as _sync_lifecycle,
)
from agents.excel_export import (
    export_customers_master  as _export_customers,
    export_credit_report     as _export_credit,
    export_duplicates_report as _export_duplicates,
    export_audit_log         as _export_audit,
    export_dormant_report    as _export_dormant,
    export_full_dashboard    as _export_dashboard,
)


# ═══════════════════════════════════════════════════════════════════════════════
# AUTH — Tier-based API key gateway
# ═══════════════════════════════════════════════════════════════════════════════

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


@dataclass
class APIKeyMetadata:
    key_id: int = 0
    customer_name: str = ""
    tier: str = "enterprise"
    quota_limit: int = 10000
    quota_used: int = 0
    is_dev: bool = False


async def verify_api_key(
    request: Request,
    api_key: Optional[str] = Security(_api_key_header),
) -> APIKeyMetadata:
    """
    Multi-step API key validation:
    1. Dev mode bypass (API_SECRET_KEY == 'dev-secret-key')
    2. Accept both X-API-Key and Authorization: Bearer headers
    3. SHA-256 lookup in api_keys table
    4. Fallback: master key (API_SECRET_KEY) → enterprise tier
    5. Check is_active, expires_at, quota
    """
    secret = config.API_SECRET_KEY

    # 1. Dev mode — open auth for local development
    if not secret or secret == "dev-secret-key":
        meta = APIKeyMetadata(is_dev=True)
        request.state.key_meta = meta
        return meta

    # 2. Accept Authorization: Bearer header as alternative
    if not api_key:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            api_key = auth_header[7:]

    # 3. Accept ?apiKey= query parameter (required for MCP SSE clients)
    if not api_key:
        api_key = request.query_params.get("apiKey")

    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Provide X-API-Key header, Authorization: Bearer, or ?apiKey= param.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # 3. Look up hashed key in api_keys table
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    conn = demo_db.get_connection()
    row = conn.execute(
        "SELECT key_id, customer_name, tier, quota_limit, quota_used, "
        "quota_reset_at, is_active, expires_at FROM api_keys WHERE api_key_hash=?",
        (key_hash,),
    ).fetchone()

    # 4. Fallback: if key matches API_SECRET_KEY directly → enterprise master key
    if not row:
        conn.close()
        if api_key == secret:
            meta = APIKeyMetadata(key_id=0, customer_name="master", tier="enterprise")
            request.state.key_meta = meta
            return meta
        raise HTTPException(
            status_code=401,
            detail="Invalid API key.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # 5. Validate key state
    if not row["is_active"]:
        conn.close()
        raise HTTPException(status_code=403, detail="API key has been revoked.")

    if row["expires_at"]:
        try:
            exp = datetime.fromisoformat(row["expires_at"])
            if datetime.utcnow() > exp:
                conn.close()
                raise HTTPException(status_code=403, detail="API key has expired.")
        except ValueError:
            pass

    # 6. Quota check (lazy reset)
    quota_used = row["quota_used"]
    quota_limit = row["quota_limit"]
    reset_at = row["quota_reset_at"]

    try:
        reset_dt = datetime.fromisoformat(reset_at)
        if datetime.utcnow() > reset_dt:
            # Reset quota window
            quota_used = 0
            new_reset = (datetime.utcnow() + timedelta(hours=24)).isoformat()
            conn.execute(
                "UPDATE api_keys SET quota_used=0, quota_reset_at=? WHERE key_id=?",
                (new_reset, row["key_id"]),
            )
    except (ValueError, TypeError):
        pass

    if quota_used >= quota_limit:
        conn.close()
        raise HTTPException(
            status_code=429,
            detail=f"Quota exceeded ({quota_limit} calls/day). Resets at {reset_at}.",
        )

    # 7. Increment usage counter
    conn.execute(
        "UPDATE api_keys SET quota_used=quota_used+1 WHERE key_id=?",
        (row["key_id"],),
    )
    conn.commit()
    conn.close()

    meta = APIKeyMetadata(
        key_id=row["key_id"],
        customer_name=row["customer_name"],
        tier=row["tier"],
        quota_limit=quota_limit,
        quota_used=quota_used + 1,
    )
    request.state.key_meta = meta
    return meta


async def enforce_tier(
    request: Request,
    key_meta: APIKeyMetadata = Depends(verify_api_key),
) -> APIKeyMetadata:
    """Check if the current key's tier allows access to the requested endpoint."""
    if key_meta.is_dev:
        return key_meta

    path = request.url.path
    tool_name = resolve_tool_name(path)

    if tool_name and not is_tool_allowed(key_meta.tier, tool_name):
        raise HTTPException(
            status_code=403,
            detail=f"Tool '{tool_name}' is not available on your '{key_meta.tier}' tier. "
                   f"Upgrade to access this feature.",
        )
    return key_meta


# ═══════════════════════════════════════════════════════════════════════════════
# REQUEST / RESPONSE MODELS
# ═══════════════════════════════════════════════════════════════════════════════

class SearchRequest(BaseModel):
    query: str
    party_type: str = "ORGANIZATION"
    limit: int = 20

class CustomerSummaryRequest(BaseModel):
    cust_account_id: Optional[int] = None
    account_number: Optional[str] = None

class AuditLogRequest(BaseModel):
    workflow: Optional[str] = None
    limit: int = 50

class FindDuplicatesRequest(BaseModel):
    party_name: Optional[str] = None
    party_type: str = "ORGANIZATION"
    threshold: float = 0.88

class MergeRequest(BaseModel):
    golden_id: int
    duplicate_id: int

class ValidateAddressRequest(BaseModel):
    party_site_id: Optional[int] = None
    party_id: Optional[int] = None

class AccountIdRequest(BaseModel):
    cust_account_id: int

class MarkContactInvalidRequest(BaseModel):
    contact_point_id: int
    reason: str = "BOUNCED"

class AddContactRequest(BaseModel):
    party_id: int
    contact_type: str
    contact_value: str

class AddRelationshipRequest(BaseModel):
    subject_id: int
    object_id: int
    rel_type: str

class RestructureRequest(BaseModel):
    old_parent_id: int
    new_parent_id: int

class ScanDormantRequest(BaseModel):
    dry_run: bool = True


# ═══════════════════════════════════════════════════════════════════════════════
# DB HELPER FUNCTIONS  (duplicated from server.py to avoid stdio side-effects)
# ═══════════════════════════════════════════════════════════════════════════════

def _search_parties(query: str, party_type: str = "ORGANIZATION", limit: int = 20) -> dict:
    conn = demo_db.get_connection()
    c = conn.cursor()
    rows = c.execute(
        """
        SELECT hp.party_id, hp.party_name, hp.party_type, hp.status,
               hp.tax_reference, hp.duns_number,
               ca.cust_account_id, ca.account_number,
               ca.credit_limit, ca.lifecycle_state, ca.on_hold,
               ca.last_order_date, ca.avg_days_to_pay
        FROM hz_parties hp
        LEFT JOIN hz_cust_accounts ca ON ca.party_id = hp.party_id
        WHERE hp.party_name LIKE ? OR ca.account_number = ?
        LIMIT ?
        """,
        (f"%{query}%", query, limit),
    ).fetchall()
    conn.close()
    return {"query": query, "count": len(rows), "results": [dict(r) for r in rows]}


def _get_customer_summary(
    cust_account_id: Optional[int] = None,
    account_number: Optional[str] = None,
) -> dict:
    conn = demo_db.get_connection()
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
    hp       = c.execute("SELECT * FROM hz_parties WHERE party_id=?", (acct["party_id"],)).fetchone()
    sites    = c.execute("SELECT * FROM hz_party_sites WHERE party_id=?", (acct["party_id"],)).fetchall()
    contacts = c.execute(
        "SELECT * FROM hz_contact_points WHERE party_id=? AND status='A'", (acct["party_id"],)
    ).fetchall()
    open_bal = c.execute(
        "SELECT COALESCE(SUM(amount_remaining),0) FROM ar_payment_schedules "
        "WHERE cust_account_id=? AND status='OP'",
        (aid,),
    ).fetchone()[0]
    orders = c.execute(
        "SELECT * FROM oe_orders WHERE cust_account_id=? ORDER BY order_date DESC LIMIT 5",
        (aid,),
    ).fetchall()
    conn.close()

    credit_util = (open_bal / acct["credit_limit"]) if acct["credit_limit"] else 0
    return {
        "party":              dict(hp),
        "account":            dict(acct),
        "open_balance":       open_bal,
        "credit_utilisation": f"{credit_util:.0%}",
        "sites":              [dict(s) for s in sites],
        "contacts":           [dict(c2) for c2 in contacts],
        "recent_orders":      [dict(o) for o in orders],
    }


def _get_audit_log(workflow: Optional[str] = None, limit: int = 50) -> dict:
    conn = demo_db.get_connection()
    c = conn.cursor()
    if workflow:
        rows = c.execute(
            "SELECT * FROM audit_log WHERE workflow=? ORDER BY log_id DESC LIMIT ?",
            (workflow, limit),
        ).fetchall()
    else:
        rows = c.execute(
            "SELECT * FROM audit_log ORDER BY log_id DESC LIMIT ?", (limit,)
        ).fetchall()
    conn.close()
    return {"count": len(rows), "entries": [dict(r) for r in rows]}


# ═══════════════════════════════════════════════════════════════════════════════
# DB INITIALISATION
# ═══════════════════════════════════════════════════════════════════════════════

def _init_database() -> None:
    db_path = config.DB_PATH
    db_dir  = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
        logger.info("Created data directory: %s", db_dir)
    demo_db.init_db()
    logger.info("Database ready at: %s", db_path)


# ═══════════════════════════════════════════════════════════════════════════════
# FASTAPI APPLICATION
# ═══════════════════════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(application: FastAPI):
    logger.info("Starting Customer Master AI (env=%s)", config.ENVIRONMENT)
    _init_database()
    # Keep lifecycle states fresh on every boot
    try:
        result = _sync_lifecycle()
        logger.info("Lifecycle sync: %s", result.get("breakdown", {}))
    except Exception:
        logger.exception("Lifecycle sync failed (non-fatal)")
    logger.info("All systems ready.")
    yield
    logger.info("Customer Master AI shut down.")


app = FastAPI(
    title="Customer Master AI",
    description=(
        "AI-powered customer master data management for Oracle EBS TCA. "
        "Six intelligent workflows: deduplication, address validation, "
        "credit management, contact maintenance, relationship management, "
        "and dormant account archiving.\n\n"
        "**Auth:** Pass `X-API-Key: <your-key>` header (obtain from your admin).\n"
        "**MCP (Claude Desktop):** connect to `GET /mcp/sse`."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
# Allow all origins (CORS fully open). Host validation not needed since endpoints
# require either API key auth or are read-only (health, docs, MCP SSE).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Telemetry middleware ──────────────────────────────────────────────────────
app.add_middleware(TelemetryMiddleware)

# ── Rate limiter ──────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── Admin router (key management + usage analytics) ──────────────────────────
app.include_router(admin_router)


# ─────────────────────────────────────────────────────────────────────────────
# SYSTEM ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@app.api_route("/", methods=["GET", "HEAD"], tags=["System"], summary="API info")
async def root():
    return {
        "service":    "Customer Master AI",
        "version":    "1.0.0",
        "docs":       "/docs",
        "health":     "/health",
        "mcp_sse":    "/mcp/sse",
        "workflows":  6,
        "tools":      22,
    }


@app.get("/health", tags=["System"], summary="Health check")
async def health():
    return {
        "status":      "healthy",
        "service":     "customer-master-ai",
        "version":     "1.0.0",
        "db_mode":     config.DB_MODE,
        "db_path":     config.DB_PATH,
        "environment": config.ENVIRONMENT,
    }


# ─────────────────────────────────────────────────────────────────────────────
# QUERY ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/api/v1/parties/search", tags=["Query"], summary="Search parties by name / account number")
@limiter.limit("60/minute")
async def search_parties_endpoint(
    request: Request,
    body: SearchRequest,
    key_meta: APIKeyMetadata = Depends(enforce_tier),
):
    try:
        return _search_parties(body.query, body.party_type, body.limit)
    except Exception as exc:
        logger.exception("search_parties error")
        raise HTTPException(500, detail=str(exc))


@app.post("/api/v1/parties/summary", tags=["Query"], summary="Full customer profile")
@limiter.limit("60/minute")
async def customer_summary_endpoint(
    request: Request,
    body: CustomerSummaryRequest,
    key_meta: APIKeyMetadata = Depends(enforce_tier),
):
    try:
        return _get_customer_summary(body.cust_account_id, body.account_number)
    except Exception as exc:
        raise HTTPException(500, detail=str(exc))


@app.post("/api/v1/audit-log", tags=["Query"], summary="AI action audit log")
@limiter.limit("30/minute")
async def audit_log_endpoint(
    request: Request,
    body: AuditLogRequest,
    key_meta: APIKeyMetadata = Depends(enforce_tier),
):
    try:
        return _get_audit_log(body.workflow, body.limit)
    except Exception as exc:
        raise HTTPException(500, detail=str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# WORKFLOW 1: DEDUPLICATION
# ─────────────────────────────────────────────────────────────────────────────

@app.post(
    "/api/v1/deduplication/find-duplicates",
    tags=["Workflow 1: Deduplication"],
    summary="Find duplicate parties via fuzzy name matching",
)
@limiter.limit("20/minute")
async def find_duplicates_endpoint(
    request: Request,
    body: FindDuplicatesRequest,
    key_meta: APIKeyMetadata = Depends(enforce_tier),
):
    try:
        return _find_duplicates(body.party_name, body.party_type, body.threshold)
    except Exception as exc:
        raise HTTPException(500, detail=str(exc))


@app.post(
    "/api/v1/deduplication/merge",
    tags=["Workflow 1: Deduplication"],
    summary="Merge duplicate into golden record",
)
@limiter.limit("10/minute")
async def merge_parties_endpoint(
    request: Request,
    body: MergeRequest,
    key_meta: APIKeyMetadata = Depends(enforce_tier),
):
    try:
        return _merge_parties(body.golden_id, body.duplicate_id)
    except Exception as exc:
        raise HTTPException(500, detail=str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# WORKFLOW 2: ADDRESS VALIDATION
# ─────────────────────────────────────────────────────────────────────────────

@app.post(
    "/api/v1/address/validate",
    tags=["Workflow 2: Address"],
    summary="Validate and enrich addresses",
)
@limiter.limit("30/minute")
async def validate_address_endpoint(
    request: Request,
    body: ValidateAddressRequest,
    key_meta: APIKeyMetadata = Depends(enforce_tier),
):
    try:
        return _validate_address(body.party_site_id, body.party_id)
    except Exception as exc:
        raise HTTPException(500, detail=str(exc))


@app.get(
    "/api/v1/address/unvalidated",
    tags=["Workflow 2: Address"],
    summary="List all unvalidated party sites",
)
@limiter.limit("30/minute")
async def unvalidated_addresses_endpoint(
    request: Request,
    key_meta: APIKeyMetadata = Depends(enforce_tier),
):
    try:
        return _get_unvalidated_addresses()
    except Exception as exc:
        raise HTTPException(500, detail=str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# WORKFLOW 3: CREDIT MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────────

@app.post(
    "/api/v1/credit/evaluate",
    tags=["Workflow 3: Credit"],
    summary="Score payment performance (read-only)",
)
@limiter.limit("30/minute")
async def evaluate_credit_endpoint(
    request: Request,
    body: AccountIdRequest,
    key_meta: APIKeyMetadata = Depends(enforce_tier),
):
    try:
        return _eval_credit(body.cust_account_id)
    except Exception as exc:
        raise HTTPException(500, detail=str(exc))


@app.post(
    "/api/v1/credit/apply",
    tags=["Workflow 3: Credit"],
    summary="Evaluate and apply credit limit change",
)
@limiter.limit("20/minute")
async def apply_credit_endpoint(
    request: Request,
    body: AccountIdRequest,
    key_meta: APIKeyMetadata = Depends(enforce_tier),
):
    try:
        return _apply_credit(body.cust_account_id)
    except Exception as exc:
        raise HTTPException(500, detail=str(exc))


@app.post(
    "/api/v1/credit/sweep",
    tags=["Workflow 3: Credit"],
    summary="Bulk credit sweep for ALL active accounts",
)
@limiter.limit("5/minute")
async def credit_sweep_endpoint(
    request: Request,
    key_meta: APIKeyMetadata = Depends(enforce_tier),
):
    try:
        return _run_credit_sweep()
    except Exception as exc:
        raise HTTPException(500, detail=str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# WORKFLOW 4: CONTACT POINTS
# Note: /contacts/needs-contact must come BEFORE /contacts/{party_id}
# ─────────────────────────────────────────────────────────────────────────────

@app.get(
    "/api/v1/contacts/needs-contact",
    tags=["Workflow 4: Contacts"],
    summary="Active parties with no valid contact points",
)
@limiter.limit("30/minute")
async def parties_needing_contact_endpoint(
    request: Request,
    key_meta: APIKeyMetadata = Depends(enforce_tier),
):
    try:
        return _get_parties_needing_contact()
    except Exception as exc:
        raise HTTPException(500, detail=str(exc))


@app.get(
    "/api/v1/contacts/{party_id}",
    tags=["Workflow 4: Contacts"],
    summary="Get all contact points for a party",
)
@limiter.limit("60/minute")
async def get_contacts_endpoint(
    request: Request,
    party_id: int,
    key_meta: APIKeyMetadata = Depends(enforce_tier),
):
    try:
        return _get_contacts(party_id)
    except Exception as exc:
        raise HTTPException(500, detail=str(exc))


@app.post(
    "/api/v1/contacts/mark-invalid",
    tags=["Workflow 4: Contacts"],
    summary="Mark a contact as invalid (bounced email etc.)",
)
@limiter.limit("20/minute")
async def mark_contact_invalid_endpoint(
    request: Request,
    body: MarkContactInvalidRequest,
    key_meta: APIKeyMetadata = Depends(enforce_tier),
):
    try:
        return _mark_contact_invalid(body.contact_point_id, body.reason)
    except Exception as exc:
        raise HTTPException(500, detail=str(exc))


@app.post(
    "/api/v1/contacts/add",
    tags=["Workflow 4: Contacts"],
    summary="Add new contact point (EMAIL / PHONE / FAX / WEB)",
)
@limiter.limit("30/minute")
async def add_contact_endpoint(
    request: Request,
    body: AddContactRequest,
    key_meta: APIKeyMetadata = Depends(enforce_tier),
):
    try:
        return _add_contact_point(body.party_id, body.contact_type, body.contact_value)
    except Exception as exc:
        raise HTTPException(500, detail=str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# WORKFLOW 5: RELATIONSHIPS
# Note: /relationships/graph/summary must come BEFORE /relationships/{party_id}
# ─────────────────────────────────────────────────────────────────────────────

@app.get(
    "/api/v1/relationships/graph/summary",
    tags=["Workflow 5: Relationships"],
    summary="Summary of all active relationships by type",
)
@limiter.limit("30/minute")
async def relationship_graph_endpoint(
    request: Request,
    key_meta: APIKeyMetadata = Depends(enforce_tier),
):
    try:
        return _get_rel_graph()
    except Exception as exc:
        raise HTTPException(500, detail=str(exc))


@app.get(
    "/api/v1/relationships/{party_id}",
    tags=["Workflow 5: Relationships"],
    summary="Relationship graph for a party",
)
@limiter.limit("60/minute")
async def get_relationships_endpoint(
    request: Request,
    party_id: int,
    key_meta: APIKeyMetadata = Depends(enforce_tier),
):
    try:
        return _get_relationships(party_id)
    except Exception as exc:
        raise HTTPException(500, detail=str(exc))


@app.post(
    "/api/v1/relationships/add",
    tags=["Workflow 5: Relationships"],
    summary="Add a relationship between two parties",
)
@limiter.limit("20/minute")
async def add_relationship_endpoint(
    request: Request,
    body: AddRelationshipRequest,
    key_meta: APIKeyMetadata = Depends(enforce_tier),
):
    try:
        return _add_relationship(body.subject_id, body.object_id, body.rel_type)
    except Exception as exc:
        raise HTTPException(500, detail=str(exc))


@app.post(
    "/api/v1/relationships/restructure",
    tags=["Workflow 5: Relationships"],
    summary="Corporate restructure — transfer relationships to new parent",
)
@limiter.limit("10/minute")
async def restructure_endpoint(
    request: Request,
    body: RestructureRequest,
    key_meta: APIKeyMetadata = Depends(enforce_tier),
):
    try:
        return _update_restructure(body.old_parent_id, body.new_parent_id)
    except Exception as exc:
        raise HTTPException(500, detail=str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# WORKFLOW 6: ARCHIVING
# ─────────────────────────────────────────────────────────────────────────────

@app.post(
    "/api/v1/archiving/scan-dormant",
    tags=["Workflow 6: Archiving"],
    summary="Find accounts with no orders in 365+ days",
)
@limiter.limit("10/minute")
async def scan_dormant_endpoint(
    request: Request,
    body: ScanDormantRequest,
    key_meta: APIKeyMetadata = Depends(enforce_tier),
):
    try:
        return _scan_dormant(body.dry_run)
    except Exception as exc:
        raise HTTPException(500, detail=str(exc))


@app.post(
    "/api/v1/archiving/sync-lifecycle",
    tags=["Workflow 6: Archiving"],
    summary="Recalculate lifecycle states for all accounts",
)
@limiter.limit("5/minute")
async def sync_lifecycle_endpoint(
    request: Request,
    key_meta: APIKeyMetadata = Depends(enforce_tier),
):
    try:
        return _sync_lifecycle()
    except Exception as exc:
        raise HTTPException(500, detail=str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# EXCEL EXPORTS — stream file directly to client
# ─────────────────────────────────────────────────────────────────────────────

EXCEL_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _stream_excel(export_fn, **kwargs) -> Response:
    """
    Runs an excel export function in a temp directory, reads the file into
    memory, streams it to the HTTP client, then cleans up.
    """
    tmpdir = tempfile.mkdtemp(prefix="cm_export_")
    try:
        result = export_fn(output_dir=tmpdir, **kwargs)
        filepath = result.get("file")
        if not filepath or not os.path.exists(filepath):
            return JSONResponse(
                {"error": "Export produced no file", "detail": result},
                status_code=500,
            )
        with open(filepath, "rb") as fh:
            content = fh.read()
        filename = os.path.basename(filepath)
        return Response(
            content=content,
            media_type=EXCEL_MIME,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


@app.get("/api/v1/export/customers", tags=["Exports"], summary="Customer master report (4 sheets)")
@limiter.limit("5/minute")
async def export_customers_endpoint(request: Request, _: str = Depends(verify_api_key)):
    try:
        return _stream_excel(_export_customers)
    except Exception as exc:
        raise HTTPException(500, detail=str(exc))


@app.get("/api/v1/export/credit-report", tags=["Exports"], summary="Credit risk report")
@limiter.limit("5/minute")
async def export_credit_endpoint(request: Request, _: str = Depends(verify_api_key)):
    try:
        return _stream_excel(_export_credit)
    except Exception as exc:
        raise HTTPException(500, detail=str(exc))


@app.get("/api/v1/export/duplicates", tags=["Exports"], summary="Duplicate detection report")
@limiter.limit("5/minute")
async def export_duplicates_endpoint(
    request: Request,
    threshold: float = 0.88,
    key_meta: APIKeyMetadata = Depends(enforce_tier),
):
    try:
        return _stream_excel(_export_duplicates, threshold=threshold)
    except Exception as exc:
        raise HTTPException(500, detail=str(exc))


@app.get("/api/v1/export/audit-log", tags=["Exports"], summary="AI audit log report")
@limiter.limit("5/minute")
async def export_audit_endpoint(
    request: Request,
    workflow: Optional[str] = None,
    key_meta: APIKeyMetadata = Depends(enforce_tier),
):
    try:
        return _stream_excel(_export_audit, workflow=workflow)
    except Exception as exc:
        raise HTTPException(500, detail=str(exc))


@app.get("/api/v1/export/dormant", tags=["Exports"], summary="Dormant account report")
@limiter.limit("5/minute")
async def export_dormant_endpoint(request: Request, _: str = Depends(verify_api_key)):
    try:
        return _stream_excel(_export_dormant)
    except Exception as exc:
        raise HTTPException(500, detail=str(exc))


@app.get(
    "/api/v1/export/dashboard",
    tags=["Exports"],
    summary="Complete management dashboard (all reports in one file)",
)
@limiter.limit("5/minute")
async def export_dashboard_endpoint(request: Request, _: str = Depends(verify_api_key)):
    try:
        return _stream_excel(_export_dashboard)
    except Exception as exc:
        raise HTTPException(500, detail=str(exc))


# ═══════════════════════════════════════════════════════════════════════════════
# MCP SERVER — HTTP / SSE transport (Claude Desktop connects here)
# ═══════════════════════════════════════════════════════════════════════════════

_RENDER_HOST = "customer-master-ai.onrender.com"

mcp = FastMCP(
    "customer-master-ai",
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[
            "127.0.0.1:*",
            "localhost:*",
            "[::1]:*",
            _RENDER_HOST,
            f"{_RENDER_HOST}:*",
        ],
        allowed_origins=[
            "http://127.0.0.1:*",
            "http://localhost:*",
            "http://[::1]:*",
            f"https://{_RENDER_HOST}",
            f"https://{_RENDER_HOST}:*",
        ],
    ),
)


# ── Search & Query ─────────────────────────────────────────────────────────────

@mcp.tool()
def search_parties(query: str, party_type: str = "ORGANIZATION", limit: int = 20) -> dict:
    """Search customer parties by name or account number."""
    return _search_parties(query, party_type, limit)


@mcp.tool()
def get_customer_summary(cust_account_id: int = None, account_number: str = None) -> dict:
    """Full customer profile: party info, credit, contacts, sites, recent orders."""
    return _get_customer_summary(cust_account_id, account_number)


@mcp.tool()
def get_audit_log(workflow: str = None, limit: int = 50) -> dict:
    """AI action audit log. Optionally filter by workflow name."""
    return _get_audit_log(workflow, limit)


# ── Workflow 1: Deduplication ─────────────────────────────────────────────────

@mcp.tool()
def find_duplicate_parties(
    party_name: str = None,
    party_type: str = "ORGANIZATION",
    threshold: float = 0.88,
) -> dict:
    """
    WORKFLOW 1 — Find duplicate parties using fuzzy name matching
    (Jaro-Winkler ≥88%) and exact tax_reference / DUNS matching.
    Leave party_name blank for a full database scan.
    """
    return _find_duplicates(party_name, party_type, threshold)


@mcp.tool()
def merge_duplicate_parties(golden_id: int, duplicate_id: int) -> dict:
    """
    WORKFLOW 1 — Merge a duplicate party into the golden record.
    All accounts, sites, contacts, and relationships are redirected.
    The duplicate is marked as Merged (status=M).
    """
    return _merge_parties(golden_id, duplicate_id)


# ── Workflow 2: Address Validation ────────────────────────────────────────────

@mcp.tool()
def validate_address(party_site_id: int = None, party_id: int = None) -> dict:
    """
    WORKFLOW 2 — Validate and enrich addresses.
    Pass party_site_id for one site, party_id for all sites of a party,
    or omit both to process all unvalidated addresses.
    """
    return _validate_address(party_site_id, party_id)


@mcp.tool()
def get_unvalidated_addresses() -> dict:
    """WORKFLOW 2 — Return all party sites that have not yet been validated."""
    return _get_unvalidated_addresses()


# ── Workflow 3: Credit Management ────────────────────────────────────────────

@mcp.tool()
def evaluate_credit(cust_account_id: int) -> dict:
    """
    WORKFLOW 3 — Score a customer's payment performance and return a
    credit limit recommendation (INCREASE / DECREASE / HOLD / NO_CHANGE)
    without applying any changes.
    """
    return _eval_credit(cust_account_id)


@mcp.tool()
def apply_credit_adjustment(cust_account_id: int) -> dict:
    """
    WORKFLOW 3 — Evaluate and apply the recommended credit limit change.
    Puts account ON HOLD if credit drops to zero.
    """
    return _apply_credit(cust_account_id)


@mcp.tool()
def run_credit_sweep() -> dict:
    """
    WORKFLOW 3 — Evaluate and auto-adjust credit limits for ALL active accounts.
    Returns counts of increases, decreases, holds, and unchanged.
    """
    return _run_credit_sweep()


# ── Workflow 4: Contact Points ────────────────────────────────────────────────

@mcp.tool()
def get_contact_points(party_id: int) -> dict:
    """WORKFLOW 4 — Get all contact points (email, phone, fax) for a party."""
    return _get_contacts(party_id)


@mcp.tool()
def mark_contact_invalid(contact_point_id: int, reason: str = "BOUNCED") -> dict:
    """
    WORKFLOW 4 — Mark a contact point as invalid (e.g. after email bounce).
    reason: BOUNCED | INVALID | DISCONNECTED
    Automatically searches for alternate contacts at the same party.
    """
    return _mark_contact_invalid(contact_point_id, reason)


@mcp.tool()
def add_contact_point(party_id: int, contact_type: str, contact_value: str) -> dict:
    """
    WORKFLOW 4 — Add a new contact point for a party.
    contact_type: EMAIL | PHONE | FAX | WEB
    """
    return _add_contact_point(party_id, contact_type, contact_value)


@mcp.tool()
def get_parties_needing_contact() -> dict:
    """WORKFLOW 4 — Find all active parties with no valid contact points."""
    return _get_parties_needing_contact()


# ── Workflow 5: Relationships ─────────────────────────────────────────────────

@mcp.tool()
def get_relationships(party_id: int) -> dict:
    """
    WORKFLOW 5 — Get the full relationship graph for a party:
    contacts, subsidiaries, partners, resellers.
    """
    return _get_relationships(party_id)


@mcp.tool()
def add_relationship(subject_id: int, object_id: int, rel_type: str) -> dict:
    """
    WORKFLOW 5 — Add a relationship between two parties.
    rel_type: CUSTOMER_CONTACT | PARENT_SUBSIDIARY | PARTNER | RESELLER | COMPETITOR
    """
    return _add_relationship(subject_id, object_id, rel_type)


@mcp.tool()
def update_relationships_for_restructure(old_parent_id: int, new_parent_id: int) -> dict:
    """
    WORKFLOW 5 — Corporate restructure: transfer all relationships
    from old_parent_id to new_parent_id.
    """
    return _update_restructure(old_parent_id, new_parent_id)


@mcp.tool()
def get_relationship_graph_summary() -> dict:
    """WORKFLOW 5 — Summary of all active relationships by type."""
    return _get_rel_graph()


# ── Workflow 6: Archiving ─────────────────────────────────────────────────────

@mcp.tool()
def scan_dormant_accounts(dry_run: bool = True) -> dict:
    """
    WORKFLOW 6 — Find accounts with no orders in 365+ days.
    dry_run=True  → report only (default, safe).
    dry_run=False → archive eligible accounts.
    """
    return _scan_dormant(dry_run)


@mcp.tool()
def sync_lifecycle_states() -> dict:
    """
    WORKFLOW 6 — Recalculate lifecycle states for all accounts:
    PROSPECT → ACTIVE → AT-RISK → DORMANT → INACTIVE.
    """
    return _sync_lifecycle()


# ── Mount MCP SSE at /mcp ─────────────────────────────────────────────────────
# Claude Code/Desktop connects via:  GET https://<host>/mcp/sse?apiKey=<key>
# MCP messages endpoint:             POST https://<host>/mcp/messages/
app.mount("/mcp", mcp.sse_app())

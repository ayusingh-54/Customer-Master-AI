"""
Admin endpoints for API key management and usage analytics.
Protected by X-Admin-Key header (checked against ADMIN_API_KEY env var).
"""

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Security, Request, Depends
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

import config
import demo_db
from tier_permissions import Tier, DEFAULT_QUOTAS

router = APIRouter(prefix="/api/admin", tags=["Admin"])

_admin_key_header = APIKeyHeader(name="X-Admin-Key", auto_error=False)


async def verify_admin_key(admin_key: Optional[str] = Security(_admin_key_header)) -> str:
    """Validate admin key from X-Admin-Key header."""
    expected = config.ADMIN_API_KEY
    if not expected:
        raise HTTPException(500, detail="ADMIN_API_KEY not configured on server")
    if admin_key != expected:
        raise HTTPException(401, detail="Invalid or missing X-Admin-Key header")
    return admin_key


# ── Request models ───────────────────────────────────────────────────────────

class CreateKeyRequest(BaseModel):
    customer_name: str
    tier: str = "starter"
    quota_limit: Optional[int] = None
    expires_days: Optional[int] = None


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/keys", summary="Create a new API key")
async def create_key(
    body: CreateKeyRequest,
    _: str = Depends(verify_admin_key),
):
    """
    Generate a new API key for a customer. Returns the plaintext key ONCE.
    Store it securely — the server only keeps the SHA-256 hash.
    """
    # Validate tier
    try:
        tier_enum = Tier(body.tier)
    except ValueError:
        raise HTTPException(400, detail=f"Invalid tier: {body.tier}. Must be starter/professional/enterprise")

    # Generate secure random key
    plaintext_key = f"cm_sk_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(plaintext_key.encode()).hexdigest()
    key_prefix = plaintext_key[:8]

    # Quota
    quota = body.quota_limit or DEFAULT_QUOTAS[tier_enum]

    # Expiry
    expires_at = None
    if body.expires_days:
        expires_at = (datetime.utcnow() + timedelta(days=body.expires_days)).isoformat()

    conn = demo_db.get_connection()
    try:
        conn.execute(
            "INSERT INTO api_keys(api_key_hash, api_key_prefix, customer_name, tier, quota_limit, expires_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (key_hash, key_prefix, body.customer_name, body.tier, quota, expires_at),
        )
        conn.commit()
        key_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    finally:
        conn.close()

    return {
        "key_id": key_id,
        "api_key": plaintext_key,
        "customer_name": body.customer_name,
        "tier": body.tier,
        "quota_limit": quota,
        "expires_at": expires_at,
        "note": "Save this key now — it will NOT be shown again.",
    }


@router.get("/keys", summary="List all API keys")
async def list_keys(_: str = Depends(verify_admin_key)):
    """List all API keys (prefix only — never returns hash or plaintext)."""
    conn = demo_db.get_connection()
    rows = conn.execute(
        "SELECT key_id, api_key_prefix, customer_name, tier, "
        "quota_limit, quota_used, quota_reset_at, is_active, created_at, expires_at "
        "FROM api_keys ORDER BY key_id"
    ).fetchall()
    conn.close()
    return {"count": len(rows), "keys": [dict(r) for r in rows]}


@router.delete("/keys/{key_id}", summary="Revoke an API key")
async def revoke_key(key_id: int, _: str = Depends(verify_admin_key)):
    """Revoke an API key. Immediately blocks all future requests using this key."""
    conn = demo_db.get_connection()
    row = conn.execute("SELECT key_id, customer_name FROM api_keys WHERE key_id=?", (key_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, detail=f"Key ID {key_id} not found")
    conn.execute("UPDATE api_keys SET is_active=0 WHERE key_id=?", (key_id,))
    conn.commit()
    conn.close()
    return {"status": "revoked", "key_id": key_id, "customer_name": row["customer_name"]}


@router.get("/keys/{key_id}/usage", summary="Usage statistics for a key")
async def key_usage(key_id: int, days: int = 7, _: str = Depends(verify_admin_key)):
    """Per-key usage statistics: total calls, calls by tool, calls by day, avg response time."""
    conn = demo_db.get_connection()

    # Verify key exists
    key_row = conn.execute(
        "SELECT key_id, customer_name, tier FROM api_keys WHERE key_id=?", (key_id,)
    ).fetchone()
    if not key_row:
        conn.close()
        raise HTTPException(404, detail=f"Key ID {key_id} not found")

    since = (datetime.utcnow() - timedelta(days=days)).isoformat()

    total = conn.execute(
        "SELECT COUNT(*) FROM usage_log WHERE api_key_id=? AND request_timestamp>=?",
        (key_id, since),
    ).fetchone()[0]

    by_tool = conn.execute(
        "SELECT tool_name, COUNT(*) as cnt FROM usage_log "
        "WHERE api_key_id=? AND request_timestamp>=? GROUP BY tool_name ORDER BY cnt DESC",
        (key_id, since),
    ).fetchall()

    by_day = conn.execute(
        "SELECT DATE(request_timestamp) as day, COUNT(*) as cnt FROM usage_log "
        "WHERE api_key_id=? AND request_timestamp>=? GROUP BY day ORDER BY day",
        (key_id, since),
    ).fetchall()

    avg_ms = conn.execute(
        "SELECT AVG(response_time_ms) FROM usage_log "
        "WHERE api_key_id=? AND request_timestamp>=?",
        (key_id, since),
    ).fetchone()[0]

    conn.close()

    return {
        "key_id": key_id,
        "customer_name": key_row["customer_name"],
        "tier": key_row["tier"],
        "period_days": days,
        "total_calls": total,
        "calls_by_tool": {r["tool_name"]: r["cnt"] for r in by_tool},
        "calls_by_day": [{"date": r["day"], "count": r["cnt"]} for r in by_day],
        "avg_response_ms": round(avg_ms, 1) if avg_ms else 0,
    }


@router.get("/usage/summary", summary="Global usage summary")
async def usage_summary(_: str = Depends(verify_admin_key)):
    """Global telemetry: total keys, active keys, 24h call count, top tools, top customers."""
    conn = demo_db.get_connection()

    total_keys = conn.execute("SELECT COUNT(*) FROM api_keys").fetchone()[0]
    active_keys = conn.execute("SELECT COUNT(*) FROM api_keys WHERE is_active=1").fetchone()[0]

    since_24h = (datetime.utcnow() - timedelta(hours=24)).isoformat()

    calls_24h = conn.execute(
        "SELECT COUNT(*) FROM usage_log WHERE request_timestamp>=?", (since_24h,)
    ).fetchone()[0]

    top_tools = conn.execute(
        "SELECT tool_name, COUNT(*) as cnt FROM usage_log "
        "WHERE request_timestamp>=? GROUP BY tool_name ORDER BY cnt DESC LIMIT 10",
        (since_24h,),
    ).fetchall()

    top_customers = conn.execute(
        "SELECT ak.customer_name, COUNT(*) as cnt FROM usage_log ul "
        "JOIN api_keys ak ON ak.key_id = ul.api_key_id "
        "WHERE ul.request_timestamp>=? GROUP BY ak.customer_name ORDER BY cnt DESC LIMIT 10",
        (since_24h,),
    ).fetchall()

    conn.close()

    return {
        "total_keys": total_keys,
        "active_keys": active_keys,
        "total_calls_24h": calls_24h,
        "top_tools": [{"tool": r["tool_name"], "calls": r["cnt"]} for r in top_tools],
        "top_customers": [{"customer": r["customer_name"], "calls": r["cnt"]} for r in top_customers],
    }

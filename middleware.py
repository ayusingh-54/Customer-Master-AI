"""
Telemetry middleware — logs every API/MCP call to usage_log table.
Fire-and-forget: telemetry must never crash a request.
"""

import time
import logging
import re

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from tier_permissions import ENDPOINT_TO_TOOL

logger = logging.getLogger("customer-master-ai.telemetry")

# Dynamic path patterns for routes like /contacts/{party_id}
_DYNAMIC_ROUTES = [
    (re.compile(r"^/api/v1/contacts/\d+$"),       "get_contact_points"),
    (re.compile(r"^/api/v1/relationships/\d+$"),   "get_relationships"),
]


def resolve_tool_name(path: str) -> str | None:
    """Map a request path to its corresponding tool name."""
    tool = ENDPOINT_TO_TOOL.get(path)
    if tool:
        return tool
    for pattern, tool_name in _DYNAMIC_ROUTES:
        if pattern.match(path):
            return tool_name
    return None


class TelemetryMiddleware(BaseHTTPMiddleware):
    """Logs response time and tool usage for every /api/v1/ and /mcp/ request."""

    async def dispatch(self, request: Request, call_next):
        start = time.time()
        response = await call_next(request)
        elapsed_ms = int((time.time() - start) * 1000)

        path = request.url.path
        if path.startswith("/api/v1/") or path.startswith("/mcp/"):
            key_meta = getattr(request.state, "key_meta", None)
            if key_meta and not key_meta.is_dev:
                _log_usage(
                    api_key_id=key_meta.key_id,
                    tool_name=resolve_tool_name(path),
                    endpoint=path,
                    response_time_ms=elapsed_ms,
                    status_code=response.status_code,
                )

        return response


def _log_usage(api_key_id, tool_name, endpoint, response_time_ms, status_code):
    """Insert a row into usage_log. Fire-and-forget (non-blocking)."""
    try:
        import demo_db
        conn = demo_db.get_connection()
        conn.execute(
            "INSERT INTO usage_log(api_key_id, tool_name, endpoint, response_time_ms, status_code) "
            "VALUES (?, ?, ?, ?, ?)",
            (api_key_id, tool_name, endpoint, response_time_ms, status_code),
        )
        conn.commit()
        conn.close()
    except Exception:
        logger.debug("Telemetry log failed (non-fatal)", exc_info=True)

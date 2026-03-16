# Customer Master AI — Complete Setup & Deployment Guide

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Deploy on Render](#2-deploy-on-render)
3. [How API Keys Work on Render](#3-how-api-keys-work-on-render)
4. [Creating Customer API Keys](#4-creating-customer-api-keys)
5. [Tier System & Tool Permissions](#5-tier-system--tool-permissions)
6. [Delivering to Customers — The Thin Client Package](#6-delivering-to-customers--the-thin-client-package)
7. [Customer Setup Instructions](#7-customer-setup-instructions)
8. [Monitoring & Telemetry](#8-monitoring--telemetry)
9. [Testing Checklist](#9-testing-checklist)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. Architecture Overview

Customer Master AI uses a **hosted MCP thin-client architecture** that protects
your intellectual property while delivering full value to customers.

```
CUSTOMER MACHINE (thin client)          YOUR SERVER (Render)
┌─────────────────────────┐             ┌─────────────────────────────────┐
│  CLAUDE.md              │             │  Auth Gateway                   │
│  .mcp.json ─────────────┼── API ──────>  key → tier → quota            │
│  .env (API key)         │   call +    │  Tier Enforcement               │
│  scripts/prep_data.py   │   Bearer    │  22 MCP Tools                   │
│                         │   token     │  Business Logic (6 workflows)   │
│  NO business logic      │             │  SQLite / Oracle Database       │
│  NO proprietary prompts │             │  Telemetry Logging              │
└─────────────────────────┘             └─────────────────────────────────┘
```

**What stays server-side (never shipped):**
- Credit scoring algorithms and thresholds
- Fuzzy matching deduplication logic
- Address validation rules
- Lifecycle state calculation
- Oracle ERP query patterns
- All database access

**What ships to customer:**
- `CLAUDE.md` — workflow instructions only (what tools to call, not how they work)
- `.mcp.json` — MCP server URL pointer
- `.env.example` — API key placeholder
- `scripts/prep_data.py` — thin CSV-to-JSON file helper

---

## 2. Deploy on Render

### Prerequisites
- A GitHub account with the repo: `github.com/ayusingh-54/Customer-Master-AI`
- A Render account at https://render.com (free to create)

### Step-by-Step Deployment

**Step 1: Log in to Render**
- Go to https://dashboard.render.com
- Sign in with GitHub

**Step 2: Create a Blueprint**
- Click **New** in the top navigation
- Select **Blueprint**
- Connect your GitHub repository: `ayusingh-54/Customer-Master-AI`
- Render auto-detects the `render.yaml` file

**Step 3: Apply the Blueprint**
- Review the service configuration:
  - Service: `customer-master-ai` (Docker, Starter plan $7/mo)
  - Persistent Disk: 1 GB at `/data`
  - Auto-generated keys: `API_SECRET_KEY`, `ADMIN_API_KEY`
- Click **Apply**

**Step 4: Wait for Build**
- Render builds the Docker image (~3-5 minutes first time)
- Health check: `GET /health` is polled automatically
- Once green, your service is live

**Step 5: Set ANTHROPIC_API_KEY**
- Go to your service → **Environment** tab
- Find `ANTHROPIC_API_KEY` (marked as needing manual input)
- Click **Edit** and paste your Anthropic API key
- Click **Save Changes** → service restarts automatically

**Step 6: Copy Your Auto-Generated Keys**
- In the **Environment** tab, find:
  - `API_SECRET_KEY` — your master API key (full access to all endpoints)
  - `ADMIN_API_KEY` — your admin key (for managing customer API keys)
- Click the eye icon to reveal each key
- **Save both keys securely** — you need them for API access and key management

### Your Live Endpoints

| Endpoint | URL |
|----------|-----|
| API Docs (Swagger) | `https://customer-master-ai.onrender.com/docs` |
| Health Check | `https://customer-master-ai.onrender.com/health` |
| MCP SSE (Claude) | `https://customer-master-ai.onrender.com/mcp/sse` |
| REST API | `https://customer-master-ai.onrender.com/api/v1/...` |
| Admin API | `https://customer-master-ai.onrender.com/api/admin/...` |

---

## 3. How API Keys Work on Render

Render has a special feature called `generateValue: true` in the `render.yaml`:

```yaml
- key: API_SECRET_KEY
  generateValue: true     # Render creates a random cryptographic key

- key: ADMIN_API_KEY
  generateValue: true     # Same — unique random value
```

**What this means:**
- On first deploy, Render generates a unique, cryptographically secure random string for each key
- These keys persist across deploys (they don't change unless you manually edit them)
- You find them in your service's **Environment** tab on the Render dashboard
- Click the eye icon next to a variable to reveal its value

**Key hierarchy:**
| Key | Header | Purpose | Access |
|-----|--------|---------|--------|
| `API_SECRET_KEY` | `X-API-Key` | Master key — full enterprise access to all tools | You only |
| `ADMIN_API_KEY` | `X-Admin-Key` | Admin key — create/revoke customer keys, view usage | You only |
| Customer keys | `X-API-Key` | Per-customer keys — tier-scoped, quota-limited | Customer |

---

## 4. Creating Customer API Keys

Use the admin endpoints to create per-customer API keys with tier-based permissions.

### Create a Key

```bash
curl -X POST https://customer-master-ai.onrender.com/api/admin/keys \
  -H "X-Admin-Key: YOUR_ADMIN_KEY_HERE" \
  -H "Content-Type: application/json" \
  -d '{
    "customer_name": "Acme Corp",
    "tier": "professional",
    "quota_limit": 2000,
    "expires_days": 365
  }'
```

**Response:**
```json
{
  "key_id": 4,
  "api_key": "cm_sk_aBcDeFgHiJkLmNoPqRsTuVwXyZ123456789012",
  "customer_name": "Acme Corp",
  "tier": "professional",
  "quota_limit": 2000,
  "expires_at": "2027-03-16T00:00:00",
  "note": "Save this key now — it will NOT be shown again."
}
```

**IMPORTANT**: The `api_key` value is shown **only once**. The server stores only the SHA-256 hash. Save it immediately and share it with the customer securely.

### List All Keys

```bash
curl https://customer-master-ai.onrender.com/api/admin/keys \
  -H "X-Admin-Key: YOUR_ADMIN_KEY_HERE"
```

### Revoke a Key

```bash
curl -X DELETE https://customer-master-ai.onrender.com/api/admin/keys/4 \
  -H "X-Admin-Key: YOUR_ADMIN_KEY_HERE"
```

### View Key Usage

```bash
curl https://customer-master-ai.onrender.com/api/admin/keys/4/usage?days=7 \
  -H "X-Admin-Key: YOUR_ADMIN_KEY_HERE"
```

---

## 5. Tier System & Tool Permissions

Each customer API key is assigned a tier. The tier determines which tools are accessible.

### Starter Tier (10 tools) — Read-Only Access

| Tool | Description |
|------|-------------|
| `search_parties` | Search by name or account number |
| `get_customer_summary` | Full customer profile |
| `get_audit_log` | View AI action history |
| `find_duplicate_parties` | Scan for duplicates (view only) |
| `get_unvalidated_addresses` | List unvalidated addresses |
| `evaluate_credit` | Score payment performance (read-only) |
| `get_contact_points` | View party contacts |
| `get_parties_needing_contact` | Find parties missing contacts |
| `get_relationships` | View relationship graph |
| `get_relationship_graph_summary` | Relationship overview |

**Locked**: All write operations, bulk sweeps, exports.

### Professional Tier (18 tools) — Single-Record Writes

Everything in Starter, plus:

| Tool | Description |
|------|-------------|
| `merge_duplicate_parties` | Merge duplicates |
| `validate_address` | Validate and enrich addresses |
| `apply_credit_adjustment` | Apply credit limit changes |
| `mark_contact_invalid` | Mark bounced contacts |
| `add_contact_point` | Add new contacts |
| `add_relationship` | Create relationship links |
| `update_relationships_for_restructure` | Corporate restructure |
| `scan_dormant_accounts` | Scan for dormant accounts |

**Locked**: Bulk credit sweep, lifecycle sync, all exports.

### Enterprise Tier (22+ tools) — Full Access

Everything in Professional, plus:

| Tool | Description |
|------|-------------|
| `run_credit_sweep` | Bulk credit evaluation for ALL accounts |
| `sync_lifecycle_states` | Recalculate all lifecycle states |
| All 6 Excel export endpoints | Download formatted reports |

**Quota defaults**: Starter=500/day, Professional=2000/day, Enterprise=10000/day.

---

## 6. Delivering to Customers — The Thin Client Package

The `thin-client/` folder in your repository is what you deliver to customers.

### What's in the Package

```
thin-client/
├── CLAUDE.md           # Workflow instructions (NO business logic)
├── .mcp.json           # Points to your Render server
├── .env.example        # API key placeholder
└── scripts/
    └── prep_data.py    # CSV → JSON file helper (no logic)
```

### How to Deliver

1. **Create the customer's API key** using the admin endpoint (see Section 4)
2. **Copy the `thin-client/` folder** — this is the deliverable
3. **Share the API key** with the customer securely (email, password manager, etc.)
4. **Send setup instructions** (see Section 7)

### Zip for Distribution

```bash
cd customer-master-ai
zip -r customer-master-ai-client.zip thin-client/
```

---

## 7. Customer Setup Instructions

Share these instructions with your customers:

### For Claude Code (CLI)

1. **Unzip** the package to any folder on your machine
2. **Copy** `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
3. **Edit** `.env` and paste your API key:
   ```
   CUSTOMER_MASTER_API_KEY=cm_sk_your_actual_key_here
   ```
4. **Open** Claude Code in the folder:
   ```bash
   cd thin-client
   claude
   ```
5. Claude reads `CLAUDE.md` and `.mcp.json` automatically — start using workflows!

### For Claude Desktop

1. Open Claude Desktop settings
2. Go to **MCP Servers** configuration
3. Add a new server with:
   - **URL**: `https://customer-master-ai.onrender.com/mcp/sse`
   - **Header**: `X-API-Key: cm_sk_your_actual_key_here`
4. Save and reconnect

### Testing the Connection

Ask Claude: "Search for Acme Corporation"

If connected, Claude will call `search_parties` and return customer data.

---

## 8. Monitoring & Telemetry

Every API call is logged with the tool name, response time, and status code.

### Global Usage Summary

```bash
curl https://customer-master-ai.onrender.com/api/admin/usage/summary \
  -H "X-Admin-Key: YOUR_ADMIN_KEY_HERE"
```

**Response:**
```json
{
  "total_keys": 5,
  "active_keys": 4,
  "total_calls_24h": 142,
  "top_tools": [
    {"tool": "search_parties", "calls": 45},
    {"tool": "get_customer_summary", "calls": 32}
  ],
  "top_customers": [
    {"customer": "Acme Corp", "calls": 89},
    {"customer": "Beta Inc", "calls": 53}
  ]
}
```

### Per-Customer Usage

```bash
curl https://customer-master-ai.onrender.com/api/admin/keys/4/usage?days=30 \
  -H "X-Admin-Key: YOUR_ADMIN_KEY_HERE"
```

Shows: total calls, calls by tool, calls by day, average response time.

### What You Can Learn from Telemetry

- **Most-used features** — prioritize roadmap based on actual usage
- **Unusual patterns** — spot potential resale or abuse
- **Per-customer analytics** — prepare data for QBR conversations
- **Performance trends** — identify slow endpoints

---

## 9. Testing Checklist

After deployment, verify everything works:

### Server Health
- [ ] `GET /health` returns `{"status": "healthy"}`
- [ ] `GET /docs` shows Swagger UI with all 22+ endpoints
- [ ] `GET /` shows API info JSON

### Auth — Dev Mode (local only)
- [ ] With `API_SECRET_KEY=dev-secret-key`, all endpoints work without any key

### Auth — Production Keys
- [ ] Master key (`API_SECRET_KEY`) gives full access to all tools
- [ ] Demo starter key (`cm_sk_starter_demo_key_2026`) can call `search_parties`
- [ ] Demo starter key gets 403 on `run_credit_sweep` (enterprise-only)
- [ ] Demo enterprise key (`cm_sk_enterprise_demo_key_2026`) can call all tools

### Admin Endpoints
- [ ] `POST /api/admin/keys` creates a new key (requires `X-Admin-Key`)
- [ ] `GET /api/admin/keys` lists all keys (prefix only, no hashes)
- [ ] `DELETE /api/admin/keys/{id}` revokes a key
- [ ] Revoked key gets 403 on next API call

### Tier Enforcement
- [ ] Starter key: `evaluate_credit` works (read-only, allowed)
- [ ] Starter key: `apply_credit_adjustment` returns 403 (write, not allowed)
- [ ] Professional key: `apply_credit_adjustment` works
- [ ] Professional key: `run_credit_sweep` returns 403 (bulk, not allowed)
- [ ] Enterprise key: all tools work

### MCP Connection
- [ ] Claude Desktop connects via `GET /mcp/sse`
- [ ] MCP tools are listed and callable
- [ ] Tool results stream back correctly

### Telemetry
- [ ] After making API calls, `GET /api/admin/usage/summary` shows counts
- [ ] Per-key usage endpoint shows breakdown by tool

---

## 10. Troubleshooting

### 401 — "Missing or invalid API key"
- Check that you're sending `X-API-Key` header (or `Authorization: Bearer` header)
- Verify the key is correct — keys are case-sensitive
- If using the master key, check `API_SECRET_KEY` in Render Environment tab

### 403 — "Tool not available on your tier"
- The customer's key tier doesn't allow this tool
- Check tier with: `GET /api/admin/keys` (find the key by prefix)
- Upgrade: Create a new key with a higher tier and share with customer

### 403 — "API key has been revoked"
- The key was deleted via `DELETE /api/admin/keys/{id}`
- Create a new key for the customer

### 429 — "Quota exceeded"
- The customer hit their daily call limit
- Quota resets automatically 24 hours after the first call of the window
- To increase: create a new key with higher `quota_limit`

### MCP SSE Connection Fails
- Verify the URL: `https://customer-master-ai.onrender.com/mcp/sse`
- Check that the service is running (visit `/health`)
- Render free-tier services sleep after 15 minutes — first request may take ~30s

### Database Reset on Deploy
- Schema version bumps trigger a full reseed (demo data restored)
- Customer API keys created via admin endpoints will be lost
- For production: back up api_keys table before schema-changing deploys

### Render Build Fails
- Check build logs in Render dashboard
- Common issue: Python package version conflicts in requirements.txt
- Ensure Dockerfile uses `python:3.11-slim` (tested and working)

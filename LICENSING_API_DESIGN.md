# Licensing API Design
## What You Host (SaaS Backend)

**Purpose:** Validate licenses, track usage, manage subscriptions
**Deployment:** Simple FastAPI on GCP Cloud Run ($10-20/month)
**Scale:** Support 100+ customers with minimal infrastructure

---

## Architecture

```
┌────────────────────────────────────────────────────────┐
│           YOUR LICENSING API SERVER                    │
│         (What You Host - 10 endpoints)                 │
├────────────────────────────────────────────────────────┤
│                                                        │
│  Database:                                             │
│  └─ PostgreSQL ($35/month)                             │
│     ├─ licenses (who has what)                         │
│     ├─ usage_logs (API calls made)                     │
│     ├─ billing (invoice records)                       │
│     └─ customers (OWC, etc.)                           │
│                                                        │
│  REST API Endpoints:                                   │
│  ├─ POST /validate-license                             │
│  ├─ POST /track-usage                                  │
│  ├─ GET /usage-analytics                               │
│  ├─ POST /subscription/create                          │
│  ├─ POST /subscription/update                          │
│  ├─ POST /subscription/cancel                          │
│  ├─ GET /admin/customers                               │
│  ├─ GET /admin/revenue                                 │
│  └─ POST /admin/license-key (generate)                 │
│                                                        │
│  External Services:                                    │
│  ├─ Stripe (billing) - 2.9% transaction fee            │
│  ├─ Slack notifications (free)                         │
│  └─ Email (SendGrid - free tier)                       │
│                                                        │
└────────────────────────────────────────────────────────┘
         ↑
         │ (API calls with license key)
         │
    Customer (OWC) environments
```

---

## Database Schema

### Table 1: Customers
```sql
CREATE TABLE customers (
    id UUID PRIMARY KEY,
    name VARCHAR(255) NOT NULL,  -- "Organization Web Client"
    email VARCHAR(255) NOT NULL,
    contact_person VARCHAR(255),
    created_at TIMESTAMP,
    status ENUM ('active', 'inactive', 'trial'),
    industry VARCHAR(100),
    country VARCHAR(100),
    notes TEXT
);

Example:
├─ id: 550e8400-e29b-41d4-a716-446655440001
├─ name: Organization Web Client
├─ email: contact@owc.com
├─ created_at: 2024-03-13
└─ status: active
```

### Table 2: Licenses
```sql
CREATE TABLE licenses (
    id UUID PRIMARY KEY,
    customer_id UUID REFERENCES customers(id),
    api_key VARCHAR(64) UNIQUE,  -- lic-owc-abc123...
    agent_name VARCHAR(100),     -- "deduplication", "collections", etc.
    license_type ENUM ('per-agent', 'all-agents', 'trial'),
    subscription_id VARCHAR(100),-- Stripe subscription ID

    -- Validity
    start_date DATE,
    end_date DATE,
    is_active BOOLEAN DEFAULT true,

    -- Limits
    max_calls_per_day INTEGER,
    max_tokens_per_month INTEGER,

    -- Tracking
    created_at TIMESTAMP,
    last_validated_at TIMESTAMP,
    usage_checked_at TIMESTAMP
);

Examples:
License 1:
├─ customer: OWC
├─ agent: deduplication
├─ api_key: lic-owc-dedup-xyz789
├─ max_calls_per_day: 1000
└─ end_date: 2025-03-13 (12 months from now)

License 2:
├─ customer: OWC
├─ agent: collections
├─ api_key: lic-owc-collect-xyz789
└─ end_date: 2025-03-13
```

### Table 3: Usage Logs
```sql
CREATE TABLE usage_logs (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    license_id UUID REFERENCES licenses(id),
    customer_id UUID REFERENCES customers(id),
    agent_name VARCHAR(100),
    api_endpoint VARCHAR(255),
    api_method VARCHAR(10),     -- POST, GET, etc.
    status_code INTEGER,        -- 200, 401, 500, etc.
    response_time_ms INTEGER,
    tokens_used INTEGER,        -- Claude tokens consumed
    error_message TEXT,
    logged_at TIMESTAMP,

    -- For billing (if usage-based)
    billable_units DECIMAL(10,2)
);

Example:
├─ license: lic-owc-dedup-xyz789
├─ agent: deduplication
├─ endpoint: /api/v1/deduplicate-customers
├─ status: 200
├─ tokens_used: 2500
├─ logged_at: 2024-03-13 10:15:23
```

### Table 4: Subscriptions
```sql
CREATE TABLE subscriptions (
    id UUID PRIMARY KEY,
    customer_id UUID REFERENCES customers(id),
    stripe_subscription_id VARCHAR(100),
    plan VARCHAR(100),          -- "all-agents", "per-agent", etc.
    price_per_month DECIMAL(10,2),

    billing_cycle_start DATE,
    billing_cycle_end DATE,
    next_billing_date DATE,

    status ENUM ('active', 'past_due', 'cancelled'),
    cancellation_date DATE,

    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

Example for OWC:
├─ plan: all-agents
├─ price: $1,250/month
├─ billing_cycle: 2024-03-13 to 2024-04-13
├─ next_billing: 2024-04-13
└─ status: active
```

### Table 5: Billing
```sql
CREATE TABLE billing_invoices (
    id UUID PRIMARY KEY,
    customer_id UUID REFERENCES customers(id),
    subscription_id UUID REFERENCES subscriptions(id),
    invoice_number VARCHAR(50) UNIQUE,  -- INV-2024-001

    amount_due DECIMAL(10,2),
    amount_paid DECIMAL(10,2),

    status ENUM ('draft', 'sent', 'paid', 'failed'),
    sent_at TIMESTAMP,
    due_date DATE,
    paid_at TIMESTAMP,

    stripe_invoice_id VARCHAR(100),
    pdf_url VARCHAR(500),

    created_at TIMESTAMP
);
```

---

## API Endpoints Design

### Endpoint 1: Validate License (CRITICAL)
```
POST /api/v1/validate-license

Called by: Agent code when it starts or periodically
Usage: Happens 1-5 times per day per customer

Request:
{
    "api_key": "lic-owc-dedup-xyz789",
    "agent_name": "deduplication",
    "timestamp": "2024-03-13T10:15:23Z"
}

Response (Valid):
{
    "valid": true,
    "customer_name": "Organization Web Client",
    "agent": "deduplication",
    "expires_at": "2025-03-13",
    "limits": {
        "calls_per_day": 1000,
        "tokens_per_month": 5000000
    },
    "current_usage": {
        "calls_today": 245,
        "tokens_this_month": 1250000,
        "percentage_used": 25
    },
    "warning": null,  // OR "approaching_limit" / "limit_exceeded"
    "cache_until": "2024-03-14T10:15:23Z"  // Cache response for 24 hours
}

Response (Invalid):
{
    "valid": false,
    "reason": "license_expired",  // or "invalid_key", "deactivated"
    "expired_at": "2024-01-13"
}

Code implementation (OWC's agent code):
from licensing import validate_license

result = validate_license("lic-owc-dedup-xyz789")
if not result["valid"]:
    raise RuntimeError(f"Invalid license: {result['reason']}")
```

### Endpoint 2: Track Usage
```
POST /api/v1/track-usage

Called by: Agent after each API call
Usage: 1,000+ times per day for active customers

Request:
{
    "api_key": "lic-owc-dedup-xyz789",
    "agent_name": "deduplication",
    "endpoint": "/api/v1/deduplicate-customers",
    "status_code": 200,
    "response_time_ms": 1250,
    "tokens_used": 2500,
    "timestamp": "2024-03-13T10:15:23Z"
}

Response:
{
    "logged": true,
    "usage_so_far_today": 245,
    "usage_limit_daily": 1000,
    "warning": null
}

What you do with this:
├─ Store in usage_logs table
├─ Update customer dashboard
├─ Check if approaching limits
├─ Aggregate for billing
└─ Alert if suspicious activity
```

### Endpoint 3: Get Usage Analytics
```
GET /api/v1/usage-analytics?api_key=xxx&period=month

Called by: Dashboard, customer requests
Usage: 10-50 times per month

Response:
{
    "period": "2024-03",
    "api_calls": {
        "total": 12450,
        "by_agent": {
            "deduplication": 5000,
            "collections": 3500,
            "risk_assessment": 2450,
            "compliance": 1200,
            "strategy": 300
        },
        "by_day": [
            {"date": "2024-03-01", "calls": 400},
            {"date": "2024-03-02", "calls": 380},
            // ...
            {"date": "2024-03-13", "calls": 420}
        ]
    },
    "tokens_used": {
        "total": 3125000,
        "input_tokens": 1875000,
        "output_tokens": 1250000,
        "estimated_cost": $3.13
    },
    "performance": {
        "avg_response_time_ms": 1230,
        "p95_response_time_ms": 3400,
        "p99_response_time_ms": 5200,
        "error_rate": 0.05  // 0.05%
    },
    "cost_estimate": {
        "your_api_calls": "$0 (fixed license)",
        "claude_tokens": "$3.13",
        "infrastructure": "$1.06"  // Their share of licensing server
    }
}
```

### Endpoint 4: Subscription Management
```
POST /api/v1/subscription/create

Called by: Admin panel when customer signs up
Usage: 1 time when customer joins, then on renewal

Request:
{
    "customer_id": "550e8400-e29b-41d4-a716-446655440001",
    "plan": "all-agents",  // or "per-agent"
    "price_per_month": 1250,
    "stripe_payment_method_id": "pm_xxx"
}

Response:
{
    "subscription_id": "sub-owc-123456",
    "stripe_subscription_id": "sub_stripe_123",
    "status": "active",
    "next_billing_date": "2024-04-13",
    "licenses_created": [
        "lic-owc-dedup-xyz789",
        "lic-owc-collect-xyz789",
        "lic-owc-risk-xyz789",
        "lic-owc-compliance-xyz789",
        "lic-owc-strategy-xyz789"
    ]
}
```

### Endpoint 5: Generate License Key
```
POST /api/v1/admin/license-key

Called by: You, in admin panel
Usage: 1 time per customer per agent

Request:
{
    "customer_id": "550e8400-e29b-41d4-a716-446655440001",
    "agent_name": "deduplication",
    "subscription_id": "sub-owc-123456",
    "valid_until": "2025-03-13"
}

Response:
{
    "api_key": "lic-owc-dedup-abc123xyz789abc123xyz789abc",
    "customer": "Organization Web Client",
    "agent": "deduplication",
    "valid_from": "2024-03-13",
    "valid_until": "2025-03-13",
    "curl_test": "curl -X POST https://licensing.yourcompany.com/api/v1/validate-license -d '{\"api_key\": \"...\"}'"
}

You send to OWC:
├─ Provide the API key
├─ Show them how to set it in .env
├─ Include curl test command
└─ They paste into their config and test
```

### Endpoint 6: Admin Dashboard (GET endpoints)
```
GET /api/admin/customers
- List all customers
- Show active vs inactive
- Payment status

GET /api/admin/revenue
- Monthly recurring revenue (MRR)
- Churn rate
- Expansion revenue
- Customer lifetime value

GET /api/admin/alerts
- Failed payments
- Approaching license expiration
- Suspicious usage patterns
- Error spikes
```

---

## Simple Implementation (FastAPI)

```python
# licensing_api.py
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from datetime import datetime, timedelta
import uuid
import hashlib
import os
from sqlalchemy import create_engine, Column, String, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

app = FastAPI(title="Agent Licensing API")

DATABASE_URL = os.getenv("DATABASE_URL")  # PostgreSQL connection
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

# ============================================================================
# DATABASE MODELS
# ============================================================================

class License(Base):
    __tablename__ = "licenses"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    customer_name = Column(String)
    api_key = Column(String, unique=True, index=True)
    agent_name = Column(String)
    end_date = Column(DateTime)
    is_active = Column(Boolean, default=True)

# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class ValidateLicenseRequest(BaseModel):
    api_key: str
    agent_name: str
    timestamp: str = None

class ValidateLicenseResponse(BaseModel):
    valid: bool
    customer_name: str = None
    expires_at: str = None
    reason: str = None  # If invalid

class TrackUsageRequest(BaseModel):
    api_key: str
    agent_name: str
    endpoint: str
    status_code: int
    response_time_ms: int
    tokens_used: int = 0

# ============================================================================
# ENDPOINTS
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check"""
    return {"status": "ok"}

@app.post("/api/v1/validate-license")
async def validate_license(request: ValidateLicenseRequest):
    """
    Validate customer's license key
    Called by agent code before running
    """
    db = SessionLocal()
    try:
        # Find license by API key
        license_record = db.query(License).filter(
            License.api_key == request.api_key,
            License.agent_name == request.agent_name
        ).first()

        if not license_record:
            return {
                "valid": False,
                "reason": "invalid_key"
            }

        if not license_record.is_active:
            return {
                "valid": False,
                "reason": "deactivated"
            }

        if license_record.end_date < datetime.now():
            return {
                "valid": False,
                "reason": "license_expired",
                "expired_at": license_record.end_date.isoformat()
            }

        # License is valid!
        return {
            "valid": True,
            "customer_name": license_record.customer_name,
            "agent": license_record.agent_name,
            "expires_at": license_record.end_date.isoformat(),
            "limits": {
                "calls_per_day": 10000,
                "tokens_per_month": 10000000
            }
        }
    finally:
        db.close()

@app.post("/api/v1/track-usage")
async def track_usage(request: TrackUsageRequest):
    """
    Track API usage for billing
    Called after each agent API call
    """
    db = SessionLocal()
    try:
        # Validate API key exists
        license_record = db.query(License).filter(
            License.api_key == request.api_key
        ).first()

        if not license_record:
            raise HTTPException(status_code=401, detail="Invalid API key")

        # TODO: Log to usage_logs table
        # For now, just acknowledge

        return {
            "logged": True,
            "warning": None
        }
    finally:
        db.close()

@app.post("/api/v1/admin/license-key")
async def create_license_key(
    customer_name: str,
    agent_name: str,
    valid_until_days: int = 365,
    admin_key: str = Header(None)
):
    """
    Generate new license key
    Admin-only endpoint (requires admin_key)
    """
    # Verify admin key
    if admin_key != os.getenv("ADMIN_KEY"):
        raise HTTPException(status_code=403, detail="Unauthorized")

    db = SessionLocal()
    try:
        # Generate random API key
        api_key = f"lic-{customer_name.lower()}-{str(uuid.uuid4())[:20]}"

        # Create license record
        license_record = License(
            customer_name=customer_name,
            api_key=api_key,
            agent_name=agent_name,
            end_date=datetime.now() + timedelta(days=valid_until_days),
            is_active=True
        )

        db.add(license_record)
        db.commit()

        return {
            "api_key": api_key,
            "customer": customer_name,
            "agent": agent_name,
            "valid_until": license_record.end_date.isoformat()
        }
    finally:
        db.close()

# ============================================================================
# RUN
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

---

## Deployment (Minimal)

### Infrastructure Cost
```
Monthly:
├─ Cloud Run: $0.10 per GB-second * usage ≈ $10-20/month
├─ PostgreSQL (managed): $35/month
├─ Storage: $2/month
├─ SSL certs: $0 (free)
└─ Total: $47-57/month

Annual: ~$600/year
```

### Deployment Steps
```bash
# 1. Create PostgreSQL database
gcloud sql instances create licensing-db \
    --database-version=POSTGRES_15 \
    --tier=db-f1-micro

# 2. Deploy API
gcloud run deploy licensing-api \
    --source . \
    --region=us-central1 \
    --set-env-vars="DATABASE_URL=..."

# 3. Test
curl https://licensing-api-xxx.run.app/health
```

---

## Security Considerations

### API Key Security
```
✅ Generate random 32+ character keys
✅ Hash in database (don't store plain)
✅ Use HTTPS only (TLS 1.3+)
✅ Rate limit validation calls (10,000/minute)
✅ Rotate keys annually
❌ Don't send in URL query params
❌ Don't log full API keys
```

### Database Security
```
✅ Encrypt at rest (GCP default)
✅ Encrypt in transit (TLS)
✅ Daily backups
✅ IP whitelisting (restrict to your Cloud Run)
✅ Principle of least privilege (read-only user)
❌ Don't expose database directly
```

### Customer Data Isolation
```
Each customer sees only:
├─ Their own usage data
├─ Their own licenses
├─ Their own invoices
└─ NOT other customers' data

Implement row-level security:
├─ Always filter by customer_id
├─ Never cross-contaminate data
├─ Audit access logs
```

---

## Monitoring & Alerts

### What to Monitor
```
Real-time:
├─ API response time (target: <500ms)
├─ Error rate (target: <0.1%)
├─ License validation success rate (target: 99.9%)

Daily:
├─ Failed payment attempts
├─ Licenses expiring soon (30 days)
├─ Suspicious usage patterns

Monthly:
├─ Revenue collected
├─ Customer churn
├─ Cost per customer
```

### Alerting Rules
```
└─ API response time > 2 seconds
   └─ Scale up (add more Cloud Run instances)

└─ Error rate > 1%
   └─ Check logs, fix bugs, notify customers

└─ License validation failure
   └─ Page on-call engineer immediately

└─ Failed payment
   └─ Notify customer, retry in 3 days
   └─ Disable agent access if >30 days unpaid
```

---

## Summary

**What you build:** Simple FastAPI server with 6-8 endpoints
**What it does:** Validates licenses, tracks usage, manages billing
**Cost to you:** $50-60/month
**Revenue per 10 customers:** $12,500-15,000/month
**Profit margin:** 95%+

This is the CORE of your B2B SaaS business! 🚀


# Enterprise Deployment Guide: Customer Master AI
## Claude + GCP + Oracle Database Integration

**Author:** Senior DevOps & AI/ML Engineering Team
**Date:** March 2026
**Environment:** Production
**Target:** Google Cloud Platform (GCP)

---

## Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [Prerequisites](#prerequisites)
3. [Phase 1: GCP Setup](#phase-1-gcp-setup)
4. [Phase 2: Oracle Database Setup](#phase-2-oracle-database-setup)
5. [Phase 3: API Layer Development](#phase-3-api-layer-development)
6. [Phase 4: Claude Integration](#phase-4-claude-integration)
7. [Phase 5: Security & Authentication](#phase-5-security--authentication)
8. [Phase 6: Deployment](#phase-6-deployment)
9. [Phase 7: Monitoring & Logging](#phase-7-monitoring--logging)
10. [Troubleshooting](#troubleshooting)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLAUDE (Frontend)                       │
│                    Claude Code + AI Agent                       │
└────────────────────────────┬────────────────────────────────────┘
                             │ API Calls (REST/gRPC)
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    GCP Cloud Run (Compute)                      │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  FastAPI/Django Application Layer                       │  │
│  │  - Tool handlers (find_duplicates, merge_parties, etc.) │  │
│  │  - Request validation                                   │  │
│  │  - Response formatting                                  │  │
│  │  - Rate limiting & caching                              │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────────────────────┬────────────────────────────────────┘
                             │ Oracle Client (TCP/IP)
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│              Oracle Database (Cloud SQL / On-Prem)              │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  hz_parties                                              │  │
│  │  hz_cust_accounts                                        │  │
│  │  hz_party_sites                                          │  │
│  │  hz_contact_points                                       │  │
│  │  hz_relationships                                        │  │
│  │  ar_payment_schedules                                    │  │
│  │  oe_orders                                               │  │
│  │  audit_log                                               │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
       ▲
       │ Backup/Monitoring
       ▼
┌─────────────────────────────────────────────────────────────────┐
│         GCP Storage, Logging, and Monitoring                    │
│  ├─ Cloud Storage (Backups)                                     │
│  ├─ Cloud Logging (Application logs)                            │
│  ├─ Cloud Monitoring (Metrics, alerts)                          │
│  └─ Cloud IAM (Access control)                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Prerequisites

### Required Knowledge
- ✅ Python (FastAPI/Django)
- ✅ SQL & Oracle Database
- ✅ GCP Console & gcloud CLI
- ✅ Docker & Containerization
- ✅ REST API design
- ✅ Claude API integration
- ✅ CI/CD pipelines

### Required Tools
```bash
# Install these on your local machine
gcloud --version          # Google Cloud SDK
python --version          # Python 3.9+
docker --version          # Docker
git --version            # Version control
sqlplus --version        # Oracle client (optional, for testing)
```

### GCP Requirements
- Active GCP project with billing enabled
- Owner or Editor role
- APIs enabled:
  - Cloud Run API
  - Cloud SQL Admin API
  - Cloud Logging API
  - Cloud Monitoring API
  - Artifact Registry API

### Oracle Database
- Oracle 19c or 21c (Cloud SQL or on-premises)
- Network connectivity to GCP
- Read/Write permissions

---

## Phase 1: GCP Setup

### Step 1.1: Create GCP Project

```bash
# Set your project ID
export PROJECT_ID="customer-master-ai"
export REGION="us-central1"
export ZONE="us-central1-a"

# Create project
gcloud projects create ${PROJECT_ID} \
    --name="Customer Master AI Platform"

# Set as default
gcloud config set project ${PROJECT_ID}

# Enable billing (requires manual setup in console)
# Go to: https://console.cloud.google.com/billing
```

### Step 1.2: Enable Required APIs

```bash
# Enable all necessary APIs
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  cloudsql.googleapis.com \
  logging.googleapis.com \
  monitoring.googleapis.com \
  compute.googleapis.com \
  servicenetworking.googleapis.com \
  cloudresourcemanager.googleapis.com \
  iam.googleapis.com
```

### Step 1.3: Create Service Account for Application

```bash
# Create service account
gcloud iam service-accounts create customer-master-api \
    --display-name="Customer Master API Service Account"

# Store service account email
export SERVICE_ACCOUNT="customer-master-api@${PROJECT_ID}.iam.gserviceaccount.com"

# Grant Cloud Run access
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/run.invoker"

# Grant Cloud SQL Client access (for database connection)
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/cloudsql.client"

# Grant Logging write access
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/logging.logWriter"

# Grant Monitoring metric write access
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/monitoring.metricWriter"

# Create and download key
gcloud iam service-accounts keys create \
    ~/keys/${PROJECT_ID}-sa-key.json \
    --iam-account=${SERVICE_ACCOUNT}

# Set key in environment
export GOOGLE_APPLICATION_CREDENTIALS=~/keys/${PROJECT_ID}-sa-key.json
```

### Step 1.4: Create Artifact Registry Repository

```bash
# Create Docker repository
gcloud artifacts repositories create customer-master-repo \
    --repository-format=docker \
    --location=${REGION} \
    --description="Customer Master AI Docker images"

# Configure Docker authentication
gcloud auth configure-docker ${REGION}-docker.pkg.dev

# Set repository URL
export REPOSITORY_URL="${REGION}-docker.pkg.dev/${PROJECT_ID}/customer-master-repo"
```

### Step 1.5: Create VPC and Networking (for Security)

```bash
# Create VPC
gcloud compute networks create customer-master-vpc \
    --subnet-mode=custom \
    --bgp-routing-mode=regional

# Create subnet
gcloud compute networks subnets create customer-master-subnet \
    --network=customer-master-vpc \
    --region=${REGION} \
    --range=10.0.0.0/20 \
    --enable-flow-logs

# Create Cloud NAT for outbound access
gcloud compute routers create customer-master-router \
    --network=customer-master-vpc \
    --region=${REGION}

gcloud compute routers nats create customer-master-nat \
    --router=customer-master-router \
    --region=${REGION} \
    --nat-all-subnet-ip-ranges \
    --auto-allocate-nat-external-ips
```

---

## Phase 2: Oracle Database Setup

### Step 2.1: Option A - Cloud SQL for Oracle (Recommended)

```bash
# Create Cloud SQL Oracle instance
gcloud sql instances create customer-master-oracle \
    --database-version=ORACLE_19 \
    --tier=db-custom-4-16384 \
    --region=${REGION} \
    --network=customer-master-vpc \
    --backup-start-time=02:00 \
    --maintenance-window-day=SUN \
    --maintenance-window-hour=03 \
    --maintenance-window-duration=4 \
    --enable-bin-log \
    --enable-point-in-time-recovery

# Set root password
gcloud sql users set-password root \
    --instance=customer-master-oracle \
    --password=[GENERATE_SECURE_PASSWORD]

# Create application database user
gcloud sql users create customer-master-user \
    --instance=customer-master-oracle \
    --type=BUILT_IN \
    --password=[GENERATE_SECURE_PASSWORD]

# Get instance IP
export CLOUDSQL_IP=$(gcloud sql instances describe customer-master-oracle \
    --format='value(ipAddresses[0].ipAddress)')

# Create Cloud SQL Proxy for local testing
cloud_sql_proxy -instances=${PROJECT_ID}:${REGION}:customer-master-oracle=tcp:1521 &
```

### Step 2.2: Create Database Schema

```bash
# Create connection string
export ORACLE_CONNECT_STRING="customer-master-user@${CLOUDSQL_IP}:1521/ORCL"

# Run SQL scripts to create tables
sqlplus -s ${ORACLE_CONNECT_STRING} << 'EOSQL'
-- Create Tables (copy schema from demo_db.py)
CREATE TABLE hz_parties (
    party_id        NUMBER PRIMARY KEY,
    party_name      VARCHAR2(255) NOT NULL,
    party_type      VARCHAR2(30) NOT NULL,
    status          VARCHAR2(1) DEFAULT 'A',
    tax_reference   VARCHAR2(50),
    duns_number     VARCHAR2(20),
    created_at      TIMESTAMP DEFAULT SYSTIMESTAMP,
    updated_at      TIMESTAMP DEFAULT SYSTIMESTAMP
);

CREATE TABLE hz_cust_accounts (
    cust_account_id NUMBER PRIMARY KEY,
    party_id        NUMBER NOT NULL REFERENCES hz_parties(party_id),
    account_number  VARCHAR2(30) NOT NULL,
    credit_limit    NUMBER DEFAULT 0,
    status          VARCHAR2(1) DEFAULT 'A',
    last_order_date DATE,
    avg_days_to_pay NUMBER DEFAULT 30,
    on_hold         NUMBER DEFAULT 0,
    lifecycle_state VARCHAR2(20) DEFAULT 'PROSPECT',
    updated_at      TIMESTAMP DEFAULT SYSTIMESTAMP
);

-- [Continue with all other tables...]

-- Create indexes for performance
CREATE INDEX idx_parties_name ON hz_parties(party_name);
CREATE INDEX idx_accounts_party ON hz_cust_accounts(party_id);
CREATE INDEX idx_accounts_lifecycle ON hz_cust_accounts(lifecycle_state);
CREATE INDEX idx_payments_status ON ar_payment_schedules(status);

-- Grant permissions
GRANT SELECT, INSERT, UPDATE, DELETE ON hz_parties TO customer-master-user;
GRANT SELECT, INSERT, UPDATE, DELETE ON hz_cust_accounts TO customer-master-user;
-- [Grant all tables...]

COMMIT;
EXIT;
EOSQL
```

### Step 2.3: Load Initial Data

```bash
# Export from SQLite to CSV
sqlite3 demo.db << 'EOF'
.headers on
.mode csv
.output parties.csv
SELECT * FROM hz_parties;
.output accounts.csv
SELECT * FROM hz_cust_accounts;
-- [Export all tables...]
EOF

# Load data into Oracle (use SQLPlus or Data Pump)
sqlldr ${ORACLE_CONNECT_STRING} control=load_data.ctl
```

### Step 2.4: Enable Network Access

```bash
# Get GCP project network address
export GCP_NETWORK_CIDR="10.0.0.0/20"

# Create Cloud SQL firewall rule
gcloud sql instances patch customer-master-oracle \
    --require-ssl

# If on-premises Oracle, configure VPN/Private Service Connection
gcloud services vpc-peerings connect \
    --service=servicenetworking.googleapis.com \
    --ranges=google-managed-services-customer-master-vpc \
    --network=customer-master-vpc
```

---

## Phase 3: API Layer Development

### Step 3.1: Create FastAPI Application

Create: `app.py`

```python
"""
Customer Master AI - FastAPI Application Layer
Connects Claude to Oracle Database
"""

from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import oracledb
import logging
import json
from datetime import datetime
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI
app = FastAPI(
    title="Customer Master API",
    description="Oracle Database API for Customer Master AI",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict to Claude domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database Configuration
ORACLE_CONFIG = {
    'user': os.getenv('ORACLE_USER', 'customer-master-user'),
    'password': os.getenv('ORACLE_PASSWORD'),
    'dsn': oracledb.makedsn(
        host=os.getenv('ORACLE_HOST'),
        port=int(os.getenv('ORACLE_PORT', 1521)),
        service_name=os.getenv('ORACLE_SERVICE_NAME', 'ORCL')
    )
}

# Connection Pool
pool = None

def init_db_pool():
    """Initialize connection pool"""
    global pool
    try:
        pool = oracledb.create_pool(
            user=ORACLE_CONFIG['user'],
            password=ORACLE_CONFIG['password'],
            dsn=ORACLE_CONFIG['dsn'],
            min=2,
            max=10,
            increment=1
        )
        logger.info("Database pool initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database pool: {e}")
        raise

def get_db_connection():
    """Get database connection from pool"""
    try:
        return pool.acquire()
    except Exception as e:
        logger.error(f"Failed to acquire database connection: {e}")
        raise HTTPException(status_code=500, detail="Database connection failed")

# ============================================================================
# PYDANTIC MODELS (Request/Response schemas)
# ============================================================================

class FindDuplicatesRequest(BaseModel):
    party_name: Optional[str] = None
    party_type: str = "ORGANIZATION"
    threshold: float = 0.88

class FindDuplicatesResponse(BaseModel):
    query_name: Optional[str]
    threshold: float
    matches: List[dict]

class MergePartiesRequest(BaseModel):
    golden_id: int
    duplicate_id: int

class MergePartiesResponse(BaseModel):
    status: str
    golden_id: int
    duplicate_id: int
    steps: List[str]

# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    init_db_pool()
    logger.info("Application started")

@app.on_event("shutdown")
async def shutdown_event():
    """Close database pool on shutdown"""
    if pool:
        pool.close()
    logger.info("Application shutdown")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM DUAL")
        conn.close()
        return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Database unavailable")

@app.post("/api/v1/duplicates/find")
async def find_duplicate_parties(request: FindDuplicatesRequest):
    """
    Find potential duplicate parties using fuzzy matching

    Args:
        party_name: Optional party name to search for
        party_type: ORGANIZATION or PERSON
        threshold: Similarity threshold (0-1)

    Returns:
        List of potential duplicates grouped by similarity
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Fetch active parties
        cursor.execute("""
            SELECT party_id, party_name, tax_reference, duns_number
            FROM hz_parties
            WHERE party_type = :party_type AND status = 'A'
        """, {'party_type': request.party_type})

        rows = cursor.fetchall()
        matches = []

        if request.party_name:
            # Targeted search
            from rapidfuzz import fuzz

            for row in rows:
                score = fuzz.token_sort_ratio(
                    request.party_name.upper(),
                    row[1].upper()
                ) / 100.0

                if score >= request.threshold:
                    matches.append({
                        'party_id': row[0],
                        'party_name': row[1],
                        'tax_reference': row[2],
                        'duns_number': row[3],
                        'similarity': round(score, 4)
                    })

            matches.sort(key=lambda x: x['similarity'], reverse=True)
        else:
            # Full scan
            from rapidfuzz import fuzz

            duplicate_groups = []
            seen = set()

            for i, r1 in enumerate(rows):
                group = []
                if r1[0] in seen:
                    continue

                for j, r2 in enumerate(rows):
                    if i == j:
                        continue

                    score = fuzz.token_sort_ratio(
                        r1[1].upper(), r2[1].upper()
                    ) / 100.0

                    # Check exact matches
                    exact = (
                        (r1[2] and r1[2] == r2[2]) or
                        (r1[3] and r1[3] == r2[3])
                    )

                    if score >= request.threshold or exact:
                        group.append({
                            'party_id': r2[0],
                            'party_name': r2[1],
                            'similarity': round(score, 4),
                            'exact_match': exact
                        })
                        seen.add(r2[0])

                if group:
                    seen.add(r1[0])
                    duplicate_groups.append({
                        'golden_candidate': {
                            'party_id': r1[0],
                            'party_name': r1[1]
                        },
                        'duplicates': group
                    })

            matches = duplicate_groups

        conn.close()

        return {
            'query_name': request.party_name,
            'threshold': request.threshold,
            'matches': matches,
            'count': len(matches)
        }

    except Exception as e:
        logger.error(f"Error finding duplicates: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/duplicates/merge")
async def merge_duplicate_parties(request: MergePartiesRequest):
    """
    Merge duplicate party into golden record

    Args:
        golden_id: Master party ID to keep
        duplicate_id: Duplicate party ID to merge

    Returns:
        Merge result with steps taken
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Fetch parties
        cursor.execute("SELECT party_id, party_name FROM hz_parties WHERE party_id = :id",
                      {'id': request.golden_id})
        golden = cursor.fetchone()

        cursor.execute("SELECT party_id, party_name FROM hz_parties WHERE party_id = :id",
                      {'id': request.duplicate_id})
        duplicate = cursor.fetchone()

        if not golden:
            raise ValueError(f"Golden party {request.golden_id} not found")
        if not duplicate:
            raise ValueError(f"Duplicate party {request.duplicate_id} not found")

        steps = []

        # Re-point customer accounts
        cursor.execute("""
            UPDATE hz_cust_accounts SET party_id = :golden WHERE party_id = :dup
        """, {'golden': request.golden_id, 'dup': request.duplicate_id})
        rows = cursor.rowcount
        steps.append(f"Redirected {rows} customer accounts")

        # Re-point party sites
        cursor.execute("""
            UPDATE hz_party_sites SET party_id = :golden WHERE party_id = :dup
        """, {'golden': request.golden_id, 'dup': request.duplicate_id})
        rows = cursor.rowcount
        steps.append(f"Redirected {rows} party sites")

        # Re-point contact points
        cursor.execute("""
            UPDATE hz_contact_points SET party_id = :golden WHERE party_id = :dup
        """, {'golden': request.golden_id, 'dup': request.duplicate_id})
        rows = cursor.rowcount
        steps.append(f"Redirected {rows} contact points")

        # Re-point relationships
        cursor.execute("""
            UPDATE hz_relationships SET subject_id = :golden WHERE subject_id = :dup
        """, {'golden': request.golden_id, 'dup': request.duplicate_id})
        rows1 = cursor.rowcount

        cursor.execute("""
            UPDATE hz_relationships SET object_id = :golden WHERE object_id = :dup
        """, {'golden': request.golden_id, 'dup': request.duplicate_id})
        rows2 = cursor.rowcount
        steps.append(f"Redirected {rows1 + rows2} relationships")

        # Mark duplicate as merged
        cursor.execute("""
            UPDATE hz_parties SET status = 'M', updated_at = SYSTIMESTAMP
            WHERE party_id = :dup
        """, {'dup': request.duplicate_id})

        # Audit log
        cursor.execute("""
            INSERT INTO audit_log(workflow, entity_type, entity_id, action, details)
            VALUES(:workflow, :entity_type, :entity_id, :action, :details)
        """, {
            'workflow': 'DEDUPLICATION',
            'entity_type': 'HZ_PARTIES',
            'entity_id': request.golden_id,
            'action': 'MERGE',
            'details': json.dumps({
                'golden_id': request.golden_id,
                'merged_id': request.duplicate_id,
                'golden_name': golden[1],
                'merged_name': duplicate[1],
                'steps': steps
            })
        })

        conn.commit()
        conn.close()

        logger.info(f"Merged party {request.duplicate_id} into {request.golden_id}")

        return {
            'status': 'SUCCESS',
            'golden_id': request.golden_id,
            'duplicate_id': request.duplicate_id,
            'golden_name': golden[1],
            'merged_name': duplicate[1],
            'steps': steps
        }

    except Exception as e:
        logger.error(f"Error merging parties: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/customers/active")
async def get_active_customers():
    """Get all active customers"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT p.party_id, p.party_name, a.cust_account_id,
                   a.credit_limit, a.lifecycle_state, a.avg_days_to_pay
            FROM hz_parties p
            JOIN hz_cust_accounts a ON p.party_id = a.party_id
            WHERE a.lifecycle_state = 'ACTIVE'
            ORDER BY a.credit_limit DESC
        """)

        columns = [desc[0] for desc in cursor.description]
        customers = [dict(zip(columns, row)) for row in cursor.fetchall()]

        conn.close()

        return {
            'count': len(customers),
            'customers': customers
        }

    except Exception as e:
        logger.error(f"Error fetching active customers: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/invoices/overdue")
async def get_overdue_invoices():
    """Get overdue invoices"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT ps.ps_id, ps.invoice_number, ps.amount_remaining,
                   ps.due_date, p.party_name, a.account_number
            FROM ar_payment_schedules ps
            JOIN hz_cust_accounts a ON ps.cust_account_id = a.cust_account_id
            JOIN hz_parties p ON a.party_id = p.party_id
            WHERE ps.status = 'OP' AND ps.due_date < TRUNC(SYSDATE)
            ORDER BY ps.due_date ASC
        """)

        columns = [desc[0] for desc in cursor.description]
        invoices = [dict(zip(columns, row)) for row in cursor.fetchall()]

        conn.close()

        return {
            'count': len(invoices),
            'total_amount': sum(inv['amount_remaining'] for inv in invoices),
            'invoices': invoices
        }

    except Exception as e:
        logger.error(f"Error fetching overdue invoices: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/audit-log")
async def get_audit_log(limit: int = 100):
    """Get audit log entries"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT log_id, workflow, entity_type, entity_id, action,
                   details, performed_at
            FROM audit_log
            ORDER BY performed_at DESC
            FETCH FIRST :limit ROWS ONLY
        """, {'limit': limit})

        columns = [desc[0] for desc in cursor.description]
        logs = [dict(zip(columns, row)) for row in cursor.fetchall()]

        conn.close()

        return {
            'count': len(logs),
            'logs': logs
        }

    except Exception as e:
        logger.error(f"Error fetching audit log: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
```

### Step 3.2: Create Requirements File

Create: `requirements.txt`

```
fastapi==0.104.1
uvicorn==0.24.0
pydantic==2.5.0
oracledb==1.3.0
rapidfuzz==3.5.2
google-cloud-logging==3.8.0
google-cloud-monitoring==2.16.0
python-dotenv==1.0.0
```

### Step 3.3: Create Dockerfile

Create: `Dockerfile`

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app.py .
COPY config.py .

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"

# Run application
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
```

---

## Phase 4: Claude Integration

### Step 4.1: Create Claude Integration Module

Create: `claude_integration.py`

```python
"""
Claude Integration Module
Handles communication between Claude and the API
"""

from anthropic import Anthropic
import requests
import json
import logging

logger = logging.getLogger(__name__)

class ClaudeCustomerMasterAgent:
    def __init__(self, api_base_url: str, api_key: str = None):
        """
        Initialize Claude agent for Customer Master

        Args:
            api_base_url: Base URL of the FastAPI application
            api_key: Optional API key for authentication
        """
        self.client = Anthropic()
        self.api_base_url = api_base_url
        self.api_key = api_key
        self.tools = self._define_tools()

    def _define_tools(self):
        """Define tools available to Claude"""
        return [
            {
                "name": "find_duplicate_parties",
                "description": "Find potential duplicate customers using fuzzy matching. Can search for a specific party name or scan all parties.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "party_name": {
                            "type": "string",
                            "description": "Optional party name to search for duplicates"
                        },
                        "party_type": {
                            "type": "string",
                            "enum": ["ORGANIZATION", "PERSON"],
                            "description": "Type of party to search for",
                            "default": "ORGANIZATION"
                        },
                        "threshold": {
                            "type": "number",
                            "description": "Similarity threshold (0-1)",
                            "default": 0.88
                        }
                    },
                    "required": []
                }
            },
            {
                "name": "merge_duplicate_parties",
                "description": "Merge a duplicate party into the golden (master) record. All related data (accounts, sites, contacts, relationships) will be redirected.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "golden_id": {
                            "type": "integer",
                            "description": "Party ID of the master record to keep"
                        },
                        "duplicate_id": {
                            "type": "integer",
                            "description": "Party ID of the duplicate to merge"
                        }
                    },
                    "required": ["golden_id", "duplicate_id"]
                }
            },
            {
                "name": "get_active_customers",
                "description": "Get list of all active customers with credit limits and lifecycle status",
                "input_schema": {
                    "type": "object",
                    "properties": {}
                }
            },
            {
                "name": "get_overdue_invoices",
                "description": "Get list of all overdue invoices that need collection action",
                "input_schema": {
                    "type": "object",
                    "properties": {}
                }
            },
            {
                "name": "get_audit_log",
                "description": "Get recent audit log entries for compliance and tracking",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "Number of entries to retrieve",
                            "default": 100
                        }
                    }
                }
            }
        ]

    def _call_api(self, tool_name: str, tool_input: dict):
        """
        Call the FastAPI backend

        Args:
            tool_name: Name of the tool to call
            tool_input: Input parameters

        Returns:
            API response
        """
        try:
            if tool_name == "find_duplicate_parties":
                endpoint = f"{self.api_base_url}/api/v1/duplicates/find"
                response = requests.post(endpoint, json=tool_input)

            elif tool_name == "merge_duplicate_parties":
                endpoint = f"{self.api_base_url}/api/v1/duplicates/merge"
                response = requests.post(endpoint, json=tool_input)

            elif tool_name == "get_active_customers":
                endpoint = f"{self.api_base_url}/api/v1/customers/active"
                response = requests.get(endpoint)

            elif tool_name == "get_overdue_invoices":
                endpoint = f"{self.api_base_url}/api/v1/invoices/overdue"
                response = requests.get(endpoint)

            elif tool_name == "get_audit_log":
                endpoint = f"{self.api_base_url}/api/v1/audit-log"
                limit = tool_input.get('limit', 100)
                response = requests.get(endpoint, params={'limit': limit})

            else:
                raise ValueError(f"Unknown tool: {tool_name}")

            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"API call failed: {e}")
            return {"error": str(e)}

    def process_user_request(self, user_message: str, system_prompt: str = None) -> str:
        """
        Process user request through Claude with tool calling

        Args:
            user_message: The user's request
            system_prompt: Optional custom system prompt

        Returns:
            Claude's response
        """
        if not system_prompt:
            system_prompt = """You are a Senior Customer Master Data Management Agent.
You help manage customer data, identify and merge duplicates, track collections,
and maintain data quality.

You have access to tools that interact with the Oracle database through a REST API.
Always provide clear explanations of actions taken and their business impact.

When finding duplicates, explain the similarity scores and recommend which record
should be the golden (master) record based on data quality and completeness.

When merging duplicates, explain all the cascading changes made to related records."""

        messages = [{"role": "user", "content": user_message}]

        # Agentic loop - keep processing until Claude doesn't call tools
        while True:
            response = self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=4096,
                system=system_prompt,
                tools=self.tools,
                messages=messages
            )

            logger.info(f"Claude response - Stop reason: {response.stop_reason}")

            # Check if Claude wants to call tools
            if response.stop_reason == "tool_use":
                # Process tool calls
                tool_results = []

                for content_block in response.content:
                    if content_block.type == "tool_use":
                        tool_name = content_block.name
                        tool_input = content_block.input
                        tool_use_id = content_block.id

                        logger.info(f"Calling tool: {tool_name}")

                        # Call the tool
                        result = self._call_api(tool_name, tool_input)

                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "content": json.dumps(result)
                        })

                # Add assistant response and tool results to messages
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})

            else:
                # Claude finished without more tool calls
                # Extract the final text response
                for content_block in response.content:
                    if hasattr(content_block, 'text'):
                        return content_block.text

                return "No response generated"


# Example usage
if __name__ == "__main__":
    # Initialize agent
    agent = ClaudeCustomerMasterAgent(
        api_base_url="http://localhost:8080"
    )

    # Process user request
    user_request = "Find all duplicate customers in our system and show me the results"

    response = agent.process_user_request(user_request)
    print("Claude Response:")
    print(response)
```

---

## Phase 5: Security & Authentication

### Step 5.1: Create Environment Configuration

Create: `config.py`

```python
"""
Configuration management for deployment
"""

import os
from dotenv import load_dotenv

load_dotenv()

# GCP Configuration
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")
GCP_REGION = os.getenv("GCP_REGION", "us-central1")

# Oracle Configuration
ORACLE_USER = os.getenv("ORACLE_USER")
ORACLE_PASSWORD = os.getenv("ORACLE_PASSWORD")
ORACLE_HOST = os.getenv("ORACLE_HOST")
ORACLE_PORT = int(os.getenv("ORACLE_PORT", 1521))
ORACLE_SERVICE_NAME = os.getenv("ORACLE_SERVICE_NAME", "ORCL")

# API Configuration
API_PORT = int(os.getenv("PORT", 8080))
API_HOST = os.getenv("API_HOST", "0.0.0.0")
DEBUG = os.getenv("DEBUG", "False") == "True"

# Claude Configuration
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20241022")

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Database Pool
DB_POOL_MIN = int(os.getenv("DB_POOL_MIN", 2))
DB_POOL_MAX = int(os.getenv("DB_POOL_MAX", 10))

print(f"Configuration loaded - Project: {GCP_PROJECT_ID}, Region: {GCP_REGION}")
```

### Step 5.2: Create Secrets Manager Configuration

```bash
# Create secrets in GCP Secret Manager
gcloud secrets create oracle-user --replication-policy="automatic" \
    --data-file=-<<< "customer-master-user"

gcloud secrets create oracle-password --replication-policy="automatic" \
    --data-file=-<<< "[SECURE_PASSWORD]"

gcloud secrets create oracle-host --replication-policy="automatic" \
    --data-file=-<<< "[ORACLE_IP_ADDRESS]"

gcloud secrets create claude-api-key --replication-policy="automatic" \
    --data-file=-<<< "[CLAUDE_API_KEY]"

# Grant service account access to secrets
gcloud secrets add-iam-policy-binding oracle-user \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/secretmanager.secretAccessor"

gcloud secrets add-iam-policy-binding oracle-password \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/secretmanager.secretAccessor"

# And for other secrets...
```

### Step 5.3: Create .env.example

Create: `.env.example`

```bash
# GCP Configuration
GCP_PROJECT_ID=customer-master-ai
GCP_REGION=us-central1

# Oracle Database
ORACLE_USER=customer-master-user
ORACLE_PASSWORD=YOUR_SECURE_PASSWORD
ORACLE_HOST=cloudsql-ip-address
ORACLE_PORT=1521
ORACLE_SERVICE_NAME=ORCL

# API Configuration
PORT=8080
API_HOST=0.0.0.0
DEBUG=False

# Claude Configuration
CLAUDE_API_KEY=sk-ant-xxxxxxxxxxxx

# Logging
LOG_LEVEL=INFO

# Database Pool
DB_POOL_MIN=2
DB_POOL_MAX=10
```

---

## Phase 6: Deployment

### Step 6.1: Build Docker Image

```bash
# Build image
docker build -t ${REPOSITORY_URL}/customer-master-api:latest .

# Test locally
docker run -it \
  -p 8080:8080 \
  -e ORACLE_HOST=localhost \
  -e ORACLE_USER=customer-master-user \
  -e ORACLE_PASSWORD=password \
  ${REPOSITORY_URL}/customer-master-api:latest

# Test health endpoint
curl http://localhost:8080/health
```

### Step 6.2: Push Image to Artifact Registry

```bash
# Push to registry
docker push ${REPOSITORY_URL}/customer-master-api:latest

# Verify
gcloud artifacts docker images list ${REGION}-docker.pkg.dev/${PROJECT_ID}/customer-master-repo
```

### Step 6.3: Deploy to Cloud Run

```bash
# Deploy service
gcloud run deploy customer-master-api \
    --image=${REPOSITORY_URL}/customer-master-api:latest \
    --platform=managed \
    --region=${REGION} \
    --memory=2Gi \
    --cpu=2 \
    --timeout=300 \
    --max-instances=10 \
    --service-account=${SERVICE_ACCOUNT} \
    --vpc-connector=customer-master-vpc-connector \
    --set-env-vars="GCP_PROJECT_ID=${PROJECT_ID}" \
    --set-env-vars="ORACLE_HOST=$(gcloud sql instances describe customer-master-oracle --format='value(ipAddresses[0].ipAddress)')" \
    --set-cloudsql-instances=${PROJECT_ID}:${REGION}:customer-master-oracle \
    --no-allow-unauthenticated

# Get service URL
export CLOUD_RUN_URL=$(gcloud run services describe customer-master-api \
    --platform=managed \
    --region=${REGION} \
    --format='value(status.url)')

echo "Service deployed at: ${CLOUD_RUN_URL}"
```

### Step 6.4: Configure Cloud SQL Auth Proxy

```bash
# Create Cloud Run to Cloud SQL connector
gcloud compute networks vpc-peerings connect \
    --service=servicenetworking.googleapis.com \
    --ranges=google-managed-services-${GCP_REGION} \
    --network=customer-master-vpc

# Update Cloud Run service with Cloud SQL connection
gcloud run services update customer-master-api \
    --set-cloudsql-instances=${PROJECT_ID}:${REGION}:customer-master-oracle \
    --region=${REGION}
```

### Step 6.5: Set Up Environment Variables in Cloud Run

```bash
# Update service with secrets from Secret Manager
gcloud run services update customer-master-api \
    --set-env-vars="ORACLE_USER=customer-master-user" \
    --set-env-vars="ORACLE_SERVICE_NAME=ORCL" \
    --update-secrets="ORACLE_PASSWORD=oracle-password:latest" \
    --update-secrets="ORACLE_HOST=oracle-host:latest" \
    --update-secrets="CLAUDE_API_KEY=claude-api-key:latest" \
    --region=${REGION}
```

---

## Phase 7: Monitoring & Logging

### Step 7.1: Configure Cloud Logging

```bash
# Create log sink for application logs
gcloud logging sinks create customer-master-logs \
    logging.googleapis.com/projects/${PROJECT_ID}/logs/customer-master-api \
    --log-filter='resource.type="cloud_run_revision" AND resource.labels.service_name="customer-master-api"'

# View logs
gcloud logging read \
    'resource.type=cloud_run_revision AND resource.labels.service_name=customer-master-api' \
    --limit=50 \
    --format=json
```

### Step 7.2: Set Up Monitoring Dashboards

```bash
# Create dashboard
gcloud monitoring dashboards create --config-from-file=- << 'EOF'
{
  "displayName": "Customer Master API Dashboard",
  "mosaicLayout": {
    "columns": 12,
    "tiles": [
      {
        "width": 6,
        "height": 4,
        "widget": {
          "title": "Request Rate",
          "xyChart": {
            "dataSets": [{
              "timeSeriesQuery": {
                "timeSeriesFilter": {
                  "filter": 'resource.type="cloud_run_revision" AND metric.type="run.googleapis.com/request_count"'
                }
              }
            }]
          }
        }
      },
      {
        "xPos": 6,
        "width": 6,
        "height": 4,
        "widget": {
          "title": "Error Rate",
          "xyChart": {
            "dataSets": [{
              "timeSeriesQuery": {
                "timeSeriesFilter": {
                  "filter": 'resource.type="cloud_run_revision" AND metric.type="run.googleapis.com/request_latencies" AND metric.response_code_class="5xx"'
                }
              }
            }]
          }
        }
      }
    ]
  }
}
EOF
```

### Step 7.3: Create Alerts

```bash
# Alert for high error rate
gcloud alpha monitoring policies create \
    --notification-channels=[CHANNEL_ID] \
    --display-name="Customer Master API - High Error Rate" \
    --condition-display-name="Error Rate > 5%" \
    --condition-threshold-value=0.05 \
    --condition-threshold-duration=300s
```

---

## Phase 8: Integration with Claude Code CLI

### Step 8.1: Create MCP Server (Optional)

```python
# mcp_server.py
"""
Model Context Protocol (MCP) Server for Customer Master
Allows Claude Code to directly access database through MCP"""

from mcp.server import Server
import mcp.types as types
from typing import Any
import oracledb

server = Server("customer-master-mcp")

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> Any:
    """Handle tool calls from Claude"""
    if name == "find_duplicate_parties":
        # Implementation
        pass
    elif name == "merge_duplicate_parties":
        # Implementation
        pass
    # ... etc

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(server, host="0.0.0.0", port=3000)
```

### Step 8.2: Configure Claude Code Settings

Create: `claude_settings.json`

```json
{
  "apiUrl": "https://customer-master-api-xxxxx.run.app",
  "apiKey": "YOUR_API_KEY",
  "database": {
    "type": "oracle",
    "host": "cloudsql-ip",
    "port": 1521,
    "database": "ORCL"
  },
  "tools": [
    {
      "name": "find_duplicate_parties",
      "enabled": true
    },
    {
      "name": "merge_duplicate_parties",
      "enabled": true
    },
    {
      "name": "get_active_customers",
      "enabled": true
    },
    {
      "name": "get_overdue_invoices",
      "enabled": true
    }
  ]
}
```

---

## Troubleshooting

### Issue 1: Oracle Connection Failed

```bash
# Check Cloud SQL instance
gcloud sql instances describe customer-master-oracle

# Verify network connectivity
gcloud compute ssh test-instance --zone ${ZONE} -- \
    nc -zv ${CLOUDSQL_IP} 1521

# Check service account permissions
gcloud projects get-iam-policy ${PROJECT_ID} \
    --flatten="bindings[].members" \
    --filter="bindings.members:${SERVICE_ACCOUNT}"
```

### Issue 2: Cloud Run Service Timeout

```bash
# Increase timeout
gcloud run services update customer-master-api \
    --timeout=600 \
    --region=${REGION}

# Check logs for slow queries
gcloud logging read \
    'severity=WARNING AND resource.type=cloud_run_revision' \
    --limit=20
```

### Issue 3: Authentication Failures

```bash
# Verify service account key
gcloud auth application-default print-access-token

# Re-authorize
gcloud auth application-default login

# Test API access
curl -H "Authorization: Bearer $(gcloud auth print-access-token)" \
    ${CLOUD_RUN_URL}/health
```

---

## Summary Checklist

- [ ] GCP Project created and configured
- [ ] Service account with proper permissions
- [ ] Artifact Registry repository created
- [ ] Oracle database provisioned (Cloud SQL or on-premises)
- [ ] Database schema created and data loaded
- [ ] FastAPI application developed and tested
- [ ] Docker image built and pushed
- [ ] Cloud Run service deployed
- [ ] Secret Manager configured
- [ ] Monitoring and logging set up
- [ ] Claude integration tested
- [ ] Load testing completed
- [ ] Documentation finalized

---

## Production Deployment Checklist

**Security:**
- [ ] Enable VPC Service Controls
- [ ] Configure Cloud Armor (DDoS protection)
- [ ] Enable Cloud SQL SSL/TLS
- [ ] Implement API authentication (OAuth 2.0 / mTLS)
- [ ] Enable audit logging
- [ ] Regular security scanning

**Reliability:**
- [ ] Set up automated backups (daily)
- [ ] Configure disaster recovery
- [ ] Load testing (5000+ requests/sec)
- [ ] Failover testing
- [ ] Incident response plan

**Operations:**
- [ ] Runbook documentation
- [ ] On-call rotation setup
- [ ] Alert escalation paths
- [ ] Performance baseline
- [ ] Cost optimization

---

## Cost Estimation (Monthly)

| Service | Usage | Cost |
|---------|-------|------|
| Cloud Run | 1M requests | $6 |
| Cloud SQL | 4-core, 16GB | $150-200 |
| Cloud Storage | 100GB backup | $2 |
| Cloud Logging | 50GB logs | $10 |
| **Total** | | **$170-220** |

---

## Contact & Support

For deployment issues:
- Check GCP Status Page: status.cloud.google.com
- Review Cloud Run Logs: Cloud Console > Cloud Run > Logs
- Contact GCP Support: support.google.com/cloud

For Claude integration:
- Claude API Documentation: https://docs.anthropic.com
- Claude Code Guide: https://claude.com/claude-code

---

**Document Version:** 1.0
**Last Updated:** March 2026
**Next Review:** June 2026

# Deployment Quick Start - 7 Easy Steps

## Complete Implementation in 2-3 Hours

---

## STEP 1: Set Up GCP Project (15 minutes)

### 1.1 Create Project
```bash
export PROJECT_ID="customer-master-ai"
export REGION="us-central1"

# Create project
gcloud projects create ${PROJECT_ID} --name="Customer Master AI"
gcloud config set project ${PROJECT_ID}

# Enable billing (manual in console: https://console.cloud.google.com/billing)
```

### 1.2 Enable APIs
```bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  cloudsql.googleapis.com \
  logging.googleapis.com \
  monitoring.googleapis.com
```

### 1.3 Create Service Account
```bash
# Create account
gcloud iam service-accounts create customer-master-api \
    --display-name="Customer Master API"

export SERVICE_ACCOUNT="customer-master-api@${PROJECT_ID}.iam.gserviceaccount.com"

# Grant roles
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/run.invoker"

gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/cloudsql.client"

# Download key
mkdir -p ~/keys
gcloud iam service-accounts keys create ~/keys/sa-key.json \
    --iam-account=${SERVICE_ACCOUNT}

export GOOGLE_APPLICATION_CREDENTIALS=~/keys/sa-key.json
```

### 1.4 Create Artifact Registry
```bash
gcloud artifacts repositories create customer-master-repo \
    --repository-format=docker \
    --location=${REGION}

gcloud auth configure-docker ${REGION}-docker.pkg.dev

export REPOSITORY_URL="${REGION}-docker.pkg.dev/${PROJECT_ID}/customer-master-repo"
```

---

## STEP 2: Set Up Oracle Database (20 minutes)

### 2.1 Create Cloud SQL Instance
```bash
gcloud sql instances create customer-master-oracle \
    --database-version=ORACLE_19 \
    --tier=db-custom-4-16384 \
    --region=${REGION} \
    --backup-start-time=02:00

# Get IP
export CLOUDSQL_IP=$(gcloud sql instances describe customer-master-oracle \
    --format='value(ipAddresses[0].ipAddress)')

echo "Oracle IP: ${CLOUDSQL_IP}"
```

### 2.2 Set Database Passwords
```bash
# Set root password
gcloud sql users set-password root \
    --instance=customer-master-oracle \
    --password=RootPassword123!

# Create app user
gcloud sql users create customer-master-user \
    --instance=customer-master-oracle \
    --type=BUILT_IN \
    --password=AppPassword123!
```

### 2.3 Create Tables (Using SQLPlus or SQL*Plus)
```bash
# Download and run the SQL script from demo_db.py
# Or use Cloud SQL Admin Console to execute SQL

# Key tables:
# - hz_parties
# - hz_cust_accounts
# - hz_party_sites
# - hz_contact_points
# - hz_relationships
# - ar_payment_schedules
# - oe_orders
# - audit_log

# Create indexes for performance
CREATE INDEX idx_parties_name ON hz_parties(party_name);
CREATE INDEX idx_accounts_party ON hz_cust_accounts(party_id);
CREATE INDEX idx_payments_status ON ar_payment_schedules(status);
```

### 2.4 Test Connection
```bash
# Create Cloud SQL Proxy locally
cloud_sql_proxy -instances=${PROJECT_ID}:${REGION}:customer-master-oracle=tcp:1521 &

# Test connection
sqlplus customer-master-user@localhost:1521/ORCL
# Enter password: AppPassword123!
# Run: SELECT COUNT(*) FROM hz_parties;
```

---

## STEP 3: Create API Application (30 minutes)

### 3.1 Create app.py
Copy the FastAPI application from `DEPLOYMENT_GUIDE_COMPLETE.md` (Step 3.1)

### 3.2 Create requirements.txt
```
fastapi==0.104.1
uvicorn==0.24.0
pydantic==2.5.0
oracledb==1.3.0
rapidfuzz==3.5.2
google-cloud-logging==3.8.0
python-dotenv==1.0.0
```

### 3.3 Create Dockerfile
```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y gcc libssl-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

ENV PYTHONUNBUFFERED=1
ENV PORT=8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
```

### 3.4 Create .env file
```bash
ORACLE_USER=customer-master-user
ORACLE_PASSWORD=AppPassword123!
ORACLE_HOST=${CLOUDSQL_IP}
ORACLE_PORT=1521
ORACLE_SERVICE_NAME=ORCL
DEBUG=True
```

### 3.5 Test Locally
```bash
# Install dependencies
pip install -r requirements.txt

# Start application
python app.py

# In another terminal, test health check
curl http://localhost:8080/health

# Test API
curl -X POST http://localhost:8080/api/v1/duplicates/find \
  -H "Content-Type: application/json" \
  -d '{"party_type": "ORGANIZATION", "threshold": 0.88}'
```

---

## STEP 4: Build & Push Docker Image (10 minutes)

### 4.1 Build Image
```bash
docker build -t ${REPOSITORY_URL}/customer-master-api:latest .
```

### 4.2 Push to Registry
```bash
docker push ${REPOSITORY_URL}/customer-master-api:latest

# Verify
gcloud artifacts docker images list ${REGION}-docker.pkg.dev/${PROJECT_ID}/customer-master-repo
```

---

## STEP 5: Deploy to Cloud Run (15 minutes)

### 5.1 Deploy Service
```bash
gcloud run deploy customer-master-api \
    --image=${REPOSITORY_URL}/customer-master-api:latest \
    --platform=managed \
    --region=${REGION} \
    --memory=2Gi \
    --cpu=2 \
    --timeout=300 \
    --max-instances=10 \
    --service-account=${SERVICE_ACCOUNT} \
    --set-env-vars="ORACLE_HOST=${CLOUDSQL_IP}" \
    --set-env-vars="ORACLE_USER=customer-master-user" \
    --set-env-vars="ORACLE_PORT=1521" \
    --set-env-vars="ORACLE_SERVICE_NAME=ORCL" \
    --set-env-vars="ORACLE_PASSWORD=AppPassword123!" \
    --no-allow-unauthenticated
```

### 5.2 Get Service URL
```bash
export CLOUD_RUN_URL=$(gcloud run services describe customer-master-api \
    --platform=managed \
    --region=${REGION} \
    --format='value(status.url)')

echo "API deployed at: ${CLOUD_RUN_URL}"
```

### 5.3 Test Deployment
```bash
# Get access token
export TOKEN=$(gcloud auth application-default print-access-token)

# Test health check
curl -H "Authorization: Bearer ${TOKEN}" \
    ${CLOUD_RUN_URL}/health

# Test API endpoint
curl -H "Authorization: Bearer ${TOKEN}" \
    -X POST ${CLOUD_RUN_URL}/api/v1/duplicates/find \
    -H "Content-Type: application/json" \
    -d '{"party_type": "ORGANIZATION"}'
```

---

## STEP 6: Integrate with Claude (20 minutes)

### 6.1 Create Claude Integration Module

Create `claude_integration.py` from `DEPLOYMENT_GUIDE_COMPLETE.md` (Step 4.1)

### 6.2 Set Up Environment
```bash
# Get Claude API Key from https://console.anthropic.com
export CLAUDE_API_KEY="sk-ant-xxxxxxxxxxxxxxx"

# Create .env for Claude integration
cat > claude_env.txt << EOF
CLAUDE_API_KEY=${CLAUDE_API_KEY}
API_BASE_URL=${CLOUD_RUN_URL}
EOF
```

### 6.3 Test Claude Integration
```python
from claude_integration import ClaudeCustomerMasterAgent

# Initialize agent
agent = ClaudeCustomerMasterAgent(
    api_base_url="${CLOUD_RUN_URL}"
)

# Test request
response = agent.process_user_request(
    "Find all duplicate customers in our system"
)

print(response)
```

### 6.4 Set Up Anthropic SDK (Optional)
```bash
pip install anthropic

# Test Claude API directly
python << 'EOF'
import anthropic
import os

client = anthropic.Anthropic(api_key=os.getenv("CLAUDE_API_KEY"))

message = client.messages.create(
    model="claude-3-5-sonnet-20241022",
    max_tokens=1024,
    messages=[
        {"role": "user", "content": "Say hello"}
    ]
)

print(message.content[0].text)
EOF
```

---

## STEP 7: Set Up Monitoring & Go Live (10 minutes)

### 7.1 Enable Logging
```bash
# View logs
gcloud logging read \
    'resource.type="cloud_run_revision" AND resource.labels.service_name="customer-master-api"' \
    --limit=50

# Tail logs in real-time
gcloud logging read --tail \
    'resource.type="cloud_run_revision" AND resource.labels.service_name="customer-master-api"'
```

### 7.2 Create Uptime Check
```bash
gcloud monitoring uptime-checks create customer-master-api \
    --resource-type=uptime-url \
    --monitored-resource=uptime_url:https://${CLOUD_RUN_URL}/health \
    --http-check=request_body=,use_ssl=true
```

### 7.3 Create Alert Policy
```bash
# Alert if service is down
gcloud alpha monitoring policies create \
    --display-name="Customer Master API Down" \
    --condition-display-name="Service Unavailable" \
    --condition-threshold-value=1 \
    --condition-threshold-duration=300s
```

### 7.4 Document Endpoints
```bash
cat > API_ENDPOINTS.txt << EOF
=== Customer Master API Endpoints ===

Base URL: ${CLOUD_RUN_URL}

Authentication: Bearer token via gcloud auth

Endpoints:

1. GET /health
   Health check - returns 200 if system is operational

2. POST /api/v1/duplicates/find
   Find duplicate parties
   Body: {"party_name": optional, "party_type": "ORGANIZATION", "threshold": 0.88}

3. POST /api/v1/duplicates/merge
   Merge duplicate into golden record
   Body: {"golden_id": 1001, "duplicate_id": 1002}

4. GET /api/v1/customers/active
   Get all active customers

5. GET /api/v1/invoices/overdue
   Get overdue invoices

6. GET /api/v1/audit-log?limit=100
   Get audit log entries

EOF

cat API_ENDPOINTS.txt
```

---

## Summary: What You Just Did

✅ **Step 1:** Created GCP project with service accounts (15 min)
✅ **Step 2:** Provisioned Oracle database in Cloud SQL (20 min)
✅ **Step 3:** Built FastAPI application layer (30 min)
✅ **Step 4:** Created and pushed Docker image (10 min)
✅ **Step 5:** Deployed to Cloud Run with auto-scaling (15 min)
✅ **Step 6:** Integrated with Claude AI agent (20 min)
✅ **Step 7:** Set up monitoring and alerts (10 min)

**Total Time:** ~2.5 hours

**Result:** Production-grade API running on GCP, connected to Oracle, ready for Claude integration

---

## Testing the Full Stack

### Test 1: API Direct Call
```bash
curl -H "Authorization: Bearer $(gcloud auth application-default print-access-token)" \
    -X POST ${CLOUD_RUN_URL}/api/v1/duplicates/find \
    -H "Content-Type: application/json" \
    -d '{"party_type": "ORGANIZATION"}'
```

### Test 2: Claude Integration
```python
from claude_integration import ClaudeCustomerMasterAgent

agent = ClaudeCustomerMasterAgent(
    api_base_url="${CLOUD_RUN_URL}"
)

# Test each capability
requests = [
    "Find all duplicate customers",
    "Get all active customers with credit limits",
    "Show me overdue invoices",
    "Merge party 1002 into party 1001",
    "What's in the audit log?"
]

for request in requests:
    print(f"\nRequest: {request}")
    response = agent.process_user_request(request)
    print(f"Response: {response}")
```

### Test 3: Load Testing
```bash
# Install wrk
brew install wrk  # macOS
# or apt-get install wrk  # Linux

# Run load test
wrk -t12 -c400 -d30s -H "Authorization: Bearer ${TOKEN}" \
    ${CLOUD_RUN_URL}/api/v1/customers/active
```

---

## Troubleshooting Common Issues

### Issue: "Cloud SQL connection refused"
```bash
# Check if instance is running
gcloud sql instances describe customer-master-oracle

# Check IP is correct
echo "Oracle IP: ${CLOUDSQL_IP}"

# Verify firewall rules
gcloud sql instances describe customer-master-oracle --format='value(settings.ipConfiguration)'
```

### Issue: "Service unavailable"
```bash
# Check Cloud Run logs
gcloud logging read \
    'resource.type="cloud_run_revision" AND severity="ERROR"' \
    --limit=20

# Check if service has enough memory
gcloud run services describe customer-master-api --region=${REGION}

# Increase memory if needed
gcloud run services update customer-master-api \
    --memory=4Gi \
    --region=${REGION}
```

### Issue: "Authentication failed"
```bash
# Re-authenticate
gcloud auth application-default login

# Get new token
gcloud auth application-default print-access-token

# Verify service account permissions
gcloud projects get-iam-policy ${PROJECT_ID} \
    --flatten="bindings[].members" \
    --filter="bindings.members:${SERVICE_ACCOUNT}"
```

---

## Next Steps

1. **Load Initial Data**
   - Export from demo.db to CSV
   - Import into Oracle Cloud SQL

2. **Set Up CI/CD Pipeline**
   - Create Cloud Build trigger for git repo
   - Automatic deployment on push

3. **Implement Additional Features**
   - Add more endpoints
   - Implement caching layer (Redis)
   - Add rate limiting

4. **Optimize Performance**
   - Add database indexes
   - Enable query caching
   - Use connection pooling

5. **Production Hardening**
   - Enable VPC Service Controls
   - Implement API authentication
   - Set up DDoS protection
   - Configure SSL/TLS

---

## Cost Per Month

- Cloud Run: $5-10 (1M requests)
- Cloud SQL: $150-200 (4-core instance)
- Cloud Logging: $5-10
- **Total: ~$160-220/month**

---

## Support Commands

```bash
# View all deployed services
gcloud run services list --region=${REGION}

# View recent deployments
gcloud run services describe customer-master-api --region=${REGION}

# View resource usage
gcloud monitoring time-series list \
    --filter='resource.type="cloud_run_revision"'

# View costs
gcloud billing accounts list
gcloud billing budgets list --billing-account=[ACCOUNT_ID]
```

---

**Deployment Complete!** 🎉

Your Customer Master AI is now running on GCP with:
- ✅ Oracle database in Cloud SQL
- ✅ FastAPI application on Cloud Run
- ✅ Claude AI integration ready
- ✅ Monitoring and logging enabled
- ✅ Auto-scaling configured

You can now use Claude to interact with your customer database!

import os
from dotenv import load_dotenv

load_dotenv()

# Database mode: "demo" (SQLite) or "oracle"
DB_MODE = os.getenv("DB_MODE", "demo")

# Oracle EBS connection (only needed if DB_MODE=oracle)
ORACLE_HOST = os.getenv("ORACLE_HOST", "161.118.185.249")
ORACLE_PORT = int(os.getenv("ORACLE_PORT", "1521"))
ORACLE_SID  = os.getenv("ORACLE_SID", "EBSDB")
ORACLE_USER = os.getenv("ORACLE_USER", "apps")
ORACLE_PASS = os.getenv("ORACLE_PASS", "")

# Anthropic API key (for sub-agent AI calls)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# Business rules
DEDUP_NAME_THRESHOLD    = float(os.getenv("DEDUP_NAME_THRESHOLD", "0.88"))
DEDUP_ADDRESS_THRESHOLD = float(os.getenv("DEDUP_ADDRESS_THRESHOLD", "0.90"))
CREDIT_INCREASE_PCT     = float(os.getenv("CREDIT_INCREASE_PCT", "0.15"))   # 15%
CREDIT_DECREASE_PCT     = float(os.getenv("CREDIT_DECREASE_PCT", "0.25"))   # 25%
AT_RISK_DAYS            = int(os.getenv("AT_RISK_DAYS", "60"))
DORMANT_DAYS            = int(os.getenv("DORMANT_DAYS", "180"))
ARCHIVE_DAYS            = int(os.getenv("ARCHIVE_DAYS", "365"))

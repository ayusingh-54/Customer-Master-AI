# ─────────────────────────────────────────────────────────────────────────────
# Customer Master AI — Production Docker Image
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim

# Prevents .pyc files and enables real-time logging
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# ── System dependencies ───────────────────────────────────────────────────────
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc curl \
    && rm -rf /var/lib/apt/lists/*

# ── Python dependencies (separate layer for better caching) ──────────────────
COPY requirements.txt .
RUN pip install -r requirements.txt

# ── Application code ──────────────────────────────────────────────────────────
COPY . .

# ── Non-root user + persistent data directory ────────────────────────────────
RUN adduser --disabled-password --gecos '' appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /app /data

USER appuser

# ── Expose port ───────────────────────────────────────────────────────────────
EXPOSE 10000

# ── Health check ──────────────────────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:10000/health || exit 1

# ── Start command ─────────────────────────────────────────────────────────────
# gunicorn.conf.py handles workers, timeout, log format
CMD ["gunicorn", "api.main:app", \
     "--config", "gunicorn.conf.py"]

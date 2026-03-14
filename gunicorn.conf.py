"""
Gunicorn configuration for production deployment on Render.
"""

import os
import multiprocessing

# Binding
bind = f"0.0.0.0:{os.getenv('PORT', '10000')}"

# Workers — 1 for SQLite (no concurrent writes), 2 for read-heavy
workers = int(os.getenv("WORKERS", "1"))
worker_class = "uvicorn.workers.UvicornWorker"

# Timeouts — generous for AI workloads
timeout = 120
graceful_timeout = 30
keepalive = 5

# Logging
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("LOG_LEVEL", "info").lower()
access_log_format = '%(h)s "%(r)s" %(s)s %(b)s %(D)sμs'

# Process naming
proc_name = "customer-master-ai"

# Lifecycle hooks
def on_starting(server):
    server.log.info("Customer Master AI starting up…")

def on_exit(server):
    server.log.info("Customer Master AI shut down.")

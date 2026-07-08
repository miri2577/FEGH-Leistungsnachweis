import os

bind = "0.0.0.0:8000"
workers = int(os.environ.get("GUNICORN_WORKERS", "3"))   # ~2*CPU+1; für 7–9 Nutzer reichlich
timeout = 60
graceful_timeout = 30
keepalive = 5
accesslog = "/app/logs/gunicorn-access.log"
errorlog = "/app/logs/gunicorn-error.log"
# Least-Trust (ISO A.8.20): nur das interne Docker-Netz (Caddy) darf X-Forwarded-*
# setzen – nicht "*". Docker-Bridge-Netze liegen in 172.16.0.0/12; per Env anpassbar.
forwarded_allow_ips = os.environ.get("GUNICORN_FORWARDED_ALLOW", "172.16.0.0/12")
# Worker-Recycling gegen Memory-Leaks + Request-Limits (DoS-Härtung).
max_requests = 1000
max_requests_jitter = 100
limit_request_line = 8190
limit_request_fields = 100

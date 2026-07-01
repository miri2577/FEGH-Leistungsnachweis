bind = "0.0.0.0:8000"
workers = 3                 # ~2*CPU+1; für 7–9 Nutzer reichlich
timeout = 60
accesslog = "/app/logs/gunicorn-access.log"
errorlog = "/app/logs/gunicorn-error.log"
forwarded_allow_ips = "*"   # nur Caddy im internen Docker-Netz spricht mit gunicorn

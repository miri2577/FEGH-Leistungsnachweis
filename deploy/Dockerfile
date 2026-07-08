FROM python:3.12.13-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# Least-Privilege: unprivilegierter Laufzeit-User; App-Verzeichnisse ihm übereignen.
RUN mkdir -p /app/logs /app/media /app/staticfiles \
    && chmod +x /app/deploy/entrypoint.sh \
    && useradd -u 10001 -r -s /usr/sbin/nologin app \
    && chown -R app:app /app
USER app

ENTRYPOINT ["/app/deploy/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "-c", "deploy/gunicorn.conf.py"]

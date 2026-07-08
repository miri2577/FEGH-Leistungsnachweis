#!/bin/sh
# Migrationen + statische Dateien bei jedem Containerstart
set -e
python manage.py migrate --noinput
python manage.py collectstatic --noinput
python manage.py createcachetable   # idempotent; legt die DB-Cache-Tabelle an (Prod: DatabaseCache)
exec "$@"

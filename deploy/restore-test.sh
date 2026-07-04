#!/bin/bash
# Restore-Test in eine Wegwerf-Postgres-Instanz (vierteljährlich ausführen).
# Ein Backup ohne getesteten Restore ist kein Backup.
# Aufruf:  ./restore-test.sh backups/fegh_2026-07-01_0230.sql.age
set -euo pipefail
FILE="${1:?Backup-Datei angeben}"
NAME=fegh_restore_test

cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; }
trap cleanup EXIT          # Wegwerf-DB IMMER entfernen (auch bei Abbruch/Fehler)
cleanup                    # evtl. Reste eines früheren Laufs vorab beseitigen

docker run -d --name "$NAME" -e POSTGRES_PASSWORD=testpw postgres:16 >/dev/null
sleep 5
# Prod-Rolle 'fegh' anlegen, damit die OWNER-/GRANT-Zeilen des Dumps nicht als Fehler auflaufen
docker exec "$NAME" psql -U postgres -c "CREATE ROLE fegh;" >/dev/null 2>&1 || true
age -d -i ~/age-key.txt "$FILE" | docker exec -i "$NAME" psql -U postgres >/dev/null
echo "Restore OK – Tabellen:"
docker exec "$NAME" psql -U postgres -c '\dt' | head -40
echo "Restore-Test erfolgreich. Wegwerf-DB wird entfernt. Ergebnis mit Datum dokumentieren."

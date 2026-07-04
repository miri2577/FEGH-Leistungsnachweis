#!/bin/bash
# Restore-Test in eine Wegwerf-Postgres-Instanz (vierteljährlich ausführen).
# Ein Backup ohne getesteten Restore ist kein Backup.
# Aufruf:  ./restore-test.sh backups/fegh_2026-07-01_0230.sql.age
set -euo pipefail
FILE="${1:?Backup-Datei angeben}"

docker run -d --name fegh_restore_test -e POSTGRES_PASSWORD=testpw postgres:16 >/dev/null
sleep 5
age -d -i ~/age-key.txt "$FILE" | docker exec -i fegh_restore_test psql -U postgres >/dev/null
echo "Restore OK – Tabellen:"
docker exec fegh_restore_test psql -U postgres -c '\dt' | head -40
docker rm -f fegh_restore_test >/dev/null
echo "Wegwerf-DB entfernt. Ergebnis mit Datum dokumentieren."

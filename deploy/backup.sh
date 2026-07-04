#!/bin/bash
# Verschlüsseltes PostgreSQL-Backup + Rotation. Als 'deploy'-User per Cron.
# Voraussetzung: 'age' installiert, dein age-PUBLIC-Key eingetragen.
# Der PRIVATE Key liegt NICHT auf dem Server – nur du kannst entschlüsseln.
set -euo pipefail
cd "$(dirname "$0")"

STAMP=$(date +%F_%H%M)
OUT="$(pwd)/backups"
# age-Recipient (ÖFFENTLICHER Schlüssel) aus Env ODER deploy/age-recipient.txt (nicht im Git).
AGE_RECIPIENT="${AGE_RECIPIENT:-$(cat "$(dirname "$0")/age-recipient.txt" 2>/dev/null || true)}"
if [ -z "${AGE_RECIPIENT:-}" ] || [ "$AGE_RECIPIENT" = "age1DEIN_PUBLIC_KEY" ]; then
  echo "FEHLER: age-Recipient fehlt. Lege deploy/age-recipient.txt mit deinem age-PUBLIC-Key an (age1…)." >&2
  exit 1
fi
mkdir -p "$OUT"

docker compose exec -T db pg_dump -U fegh fegh \
  | age -r "$AGE_RECIPIENT" > "$OUT/fegh_$STAMP.sql.age"

# Rotation: tägliche Backups 7 Tage behalten (wöchentlich/monatlich per separatem Cron/Copy)
find "$OUT" -name 'fegh_*.sql.age' -mtime +7 -delete

# Offsite-Spiegel (verschlüsselte Datei ist auch extern sicher), z. B.:
# rclone copy "$OUT/fegh_$STAMP.sql.age" hidrive:fegh-backups/
echo "Backup ok: fegh_$STAMP.sql.age"

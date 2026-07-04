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

# Offsite-Spiegel (3-2-1-Regel): die verschlüsselte Datei zusätzlich extern ablegen,
# damit Serververlust/Ransomware nicht Datenbank UND Backups gleichzeitig vernichtet.
# RCLONE_REMOTE z. B. "hidrive:fegh-backups/" (einmalig 'rclone config' einrichten).
# Schlägt der Upload fehl, bricht das Skript (set -e) VOR dem Erfolg-Ping ab -> Alarm.
if [ -n "${RCLONE_REMOTE:-}" ]; then
  rclone copy "$OUT/fegh_$STAMP.sql.age" "$RCLONE_REMOTE"
  echo "Offsite-Kopie nach $RCLONE_REMOTE ok."
else
  echo "WARNUNG: RCLONE_REMOTE nicht gesetzt – Backup liegt NUR lokal (kein Schutz gegen Serververlust)." >&2
fi

# Dead-Man's-Switch: nur bei ERFOLG pingen. Bleibt der Ping aus (Backup-Fehler oder
# Server tot), alarmiert der Monitor (z. B. healthchecks.io) automatisch.
if [ -n "${HEALTHCHECK_URL:-}" ]; then
  curl -fsS -m 10 --retry 3 "$HEALTHCHECK_URL" >/dev/null || true
fi
echo "Backup ok: fegh_$STAMP.sql.age"

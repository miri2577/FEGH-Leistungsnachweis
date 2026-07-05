#!/bin/bash
# Verschlüsseltes PostgreSQL-Backup + Rotation. Als 'deploy'-User per Cron.
# Voraussetzung: 'age' installiert, dein age-PUBLIC-Key eingetragen.
# Der PRIVATE Key liegt NICHT auf dem Server – nur du kannst entschlüsseln.
set -euo pipefail
cd "$(dirname "$0")"

STAMP=$(date +%F_%H%M)
OUT="$(pwd)/backups"
HERE="$(dirname "$0")"

# age-Recipients (ÖFFENTLICHE Schlüssel) – MEHRERE möglich (Bus-Faktor: ein zweiter
# Schlüssel z. B. beim Träger, damit Backups auch ohne die Einzelperson lesbar sind).
# Quelle in dieser Reihenfolge:
#   1) AGE_RECIPIENTS        (Env, mehrere durch Leerzeichen/Zeilenumbruch getrennt)
#   2) deploy/age-recipients.txt  (eine Zeile je Key, '#'-Kommentare erlaubt)
#   3) AGE_RECIPIENT / deploy/age-recipient.txt  (Einzelschlüssel, abwärtskompatibel)
RECIP_RAW="${AGE_RECIPIENTS:-}"
[ -z "$RECIP_RAW" ] && [ -f "$HERE/age-recipients.txt" ] && RECIP_RAW="$(cat "$HERE/age-recipients.txt")"
[ -z "$RECIP_RAW" ] && RECIP_RAW="${AGE_RECIPIENT:-$(cat "$HERE/age-recipient.txt" 2>/dev/null || true)}"

AGE_ARGS=()
while IFS= read -r line; do
  key="${line%%#*}"                       # Kommentar ab '#' abschneiden
  key="$(printf '%s' "$key" | tr -d '[:space:]')"
  [ -z "$key" ] && continue
  [ "$key" = "age1DEIN_PUBLIC_KEY" ] && continue   # Platzhalter zählt nicht
  AGE_ARGS+=(-r "$key")
done <<< "$RECIP_RAW"

if [ "${#AGE_ARGS[@]}" -eq 0 ]; then
  echo "FEHLER: kein gültiger age-Recipient. Lege deploy/age-recipients.txt (age1…) an." >&2
  exit 1
fi
echo "Verschlüsselt an $(( ${#AGE_ARGS[@]} / 2 )) Empfänger."
mkdir -p "$OUT"

docker compose exec -T db pg_dump -U fegh fegh \
  | age "${AGE_ARGS[@]}" > "$OUT/fegh_$STAMP.sql.age"

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

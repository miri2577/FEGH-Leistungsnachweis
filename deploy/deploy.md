# Deployment-Runbook · FEGH-Leistungsnachweis

Produktivbetrieb auf einem **Strato V-Server (Root/VPS, Linux)** mit **Docker Compose + Caddy + PostgreSQL**.
Netz: Internet → Caddy (80/443) → gunicorn (web:8000, intern) → PostgreSQL (db:5432, intern).

> ⚠️ **Vor dem ersten echten (Art.-9-DSGVO-)Datensatz** müssen die organisatorischen Punkte (AVV, VVT, DSFA, TOM, Löschkonzept) erledigt sein – „technisch deployt" ≠ „betriebsbereit für echte Daten". Siehe Abschnitt 7.

## 1. Voraussetzungen
- Strato V-Server (Ubuntu/Debian), root-SSH-Zugang für die Ersteinrichtung.
- Domain/Subdomain, z. B. `nachweis.deine-domain.de`, **A-Record (und AAAA bei IPv6) auf die VPS-IP**.
  Erst wenn `dig nachweis.deine-domain.de` die VPS-IP liefert, Caddy starten (sonst scheitert die Let's-Encrypt-Challenge).
- Lokal ein SSH-Key (`ssh-keygen -t ed25519 -C "fegh-deploy"`) und ein **age**-Schlüsselpaar für Backups.

## 2. Server-Härtung (als root)
```bash
apt update && apt full-upgrade -y
timedatectl set-timezone Europe/Berlin
# Non-root Deploy-User + SSH-Key
adduser --disabled-password deploy && usermod -aG sudo deploy
install -d -m 700 /home/deploy/.ssh
nano /home/deploy/.ssh/authorized_keys        # deinen ed25519-Public-Key einfügen
chown -R deploy:deploy /home/deploy/.ssh && chmod 600 /home/deploy/.ssh/authorized_keys
# SSH härten: /etc/ssh/sshd_config.d/hardening.conf
#   PermitRootLogin no / PasswordAuthentication no / PubkeyAuthentication yes / AllowUsers deploy
#   -> in ZWEITER Session als deploy testen, dann: systemctl restart ssh
# Firewall
ufw default deny incoming && ufw default allow outgoing
ufw allow 22/tcp && ufw allow 80/tcp && ufw allow 443/tcp && ufw enable
# fail2ban + automatische Sicherheitsupdates
apt install -y fail2ban unattended-upgrades
dpkg-reconfigure -plow unattended-upgrades
# Docker (offizielles Skript)
curl -fsSL https://get.docker.com | sh
usermod -aG docker deploy && systemctl enable --now docker
```

## 3. App ausrollen (als deploy)
```bash
sudo install -d -o deploy -g deploy /srv/fegh
git clone https://github.com/miri2577/FEGH-Leistungsnachweis /srv/fegh
cd /srv/fegh/deploy
cp .env.prod.example .env.prod && chmod 600 .env.prod
nano .env.prod          # SECRET_KEY, ALLOWED_HOSTS, CSRF, DB-Passwort setzen
nano Caddyfile          # Domain eintragen
docker compose up -d --build
docker compose exec web python manage.py createsuperuser   # Break-Glass-Admin
```
Migrationen + `collectstatic` laufen automatisch im `entrypoint.sh`.

## 4. Smoke-Test
- `https://nachweis.deine-domain.de` erreichbar (gültiges TLS-Zertifikat).
- Login, 2FA-Einrichtung, eine Erfassung testen.
- `docker compose exec web python manage.py check --deploy` → keine relevanten Warnungen.
- HSTS zuerst kurz (`DJANGO_HSTS_SECONDS=300`) testen, dann auf `31536000` (1 Jahr) hochsetzen.

## 5. 2FA & Härtung scharf schalten
- In `.env.prod`: `DJANGO_OTP_REQUIRED=1` (2FA für alle verpflichtend). Break-Glass-Superuser (ohne Mitarbeiter-Profil) bleibt ausgenommen.
- Optional `django-auditlog` + `django-axes` aktivieren (in `requirements.txt` einkommentieren, in `INSTALLED_APPS`/Middleware aufnehmen, `migrate`).

## 6. Backups
- `deploy/backup.sh`: `pg_dump` → mit **age** gegen deinen Public-Key verschlüsselt. Cron als `deploy`:
  `30 2 * * * /srv/fegh/deploy/backup.sh >> /srv/fegh/deploy/logs/backup.log 2>&1`
- **Offsite-Spiegel** (z. B. Strato HiDrive) – die verschlüsselte Datei ist auch extern sicher.
- **Restore-Test** vierteljährlich: `deploy/restore-test.sh backups/<datei>.sql.age`; Ergebnis mit Datum dokumentieren.
- Privaten age-Key **niemals** auf den Server legen.

## 7. DSGVO-/Art.-9-Abschluss (organisatorisch – vor Echtbetrieb)
- [ ] **AV-Vertrag (Art. 28)** mit Strato abschließen und ablegen.
- [ ] **VVT (Art. 30)**: Verarbeitungstätigkeit + Rechenzentrums-Standort (DE) dokumentieren.
- [ ] **DSFA (Art. 35)** mit Datenschutzbeauftragter/Träger klären (Art.-9-Daten).
- [ ] **TOM** schriftlich: Rollen-Zugriffskontrolle (User/Leitung/Admin), TLS, 2FA, Backups, Protokollierung.
- [ ] **Löschkonzept**: Aufbewahrungsfristen je Datenart (Abrechnung typ. 6–10 Jahre) mit Träger klären; Lösch-Command + Protokoll.

## 8. Betrieb
- **Update:** `git pull && docker compose up -d --build` (Migrationen laufen im entrypoint).
- **Container-Updates** (nicht von unattended-upgrades erfasst): regelmäßig `docker compose pull` + Rebuild (python-slim, postgres, caddy).
- **Rollback:** vorheriges Image bzw. DB-Restore aus Backup.

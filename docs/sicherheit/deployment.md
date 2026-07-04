# Deployment (Produktivbetrieb)

Vollständiges, nachbaubares Runbook für den Produktivbetrieb der FEGH-Leistungsnachweis-App
(Django 5, Team TBEW, Berliner Eingliederungshilfe). Ziel-Umgebung: **Strato V-Server
(Debian 13)** mit **Docker Compose + Caddy + PostgreSQL**, erreichbar unter
`leistungsnachweis.eingliederungshilfe.cloud`.

!!! danger "Art.-9-DSGVO-Daten"
    Diese App verarbeitet besondere Kategorien personenbezogener Daten (Gesundheits-/
    Sozialdaten von Klient\*innen). „Technisch deployt" ist **nicht** dasselbe wie
    „betriebsbereit für Echtdaten". Vor dem ersten echten Datensatz müssen die
    organisatorischen Punkte (AVV, VVT, DSFA, TOM, Löschkonzept) abgeschlossen sein.
    Siehe [Härtung](haertung.md) und das Deploy-Runbook im Repo (`deploy/deploy.md`, Abschnitt 7).

---

## 1. Architektur

Der gesamte externe Zugriff läuft über einen einzigen TLS-Endpunkt. Nur Caddy ist von
außen erreichbar; `web` (gunicorn) und `db` (PostgreSQL) liegen im internen Docker-Netz
und haben **keine** veröffentlichten Ports.

```text
Internet
   │  :80  (HTTP -> Redirect auf HTTPS)
   │  :443 (HTTPS, Auto-TLS via Let's Encrypt)
   ▼
┌──────────────┐   reverse_proxy web:8000    ┌──────────────────────┐   :5432   ┌──────────────┐
│   Caddy 2    │ ──────────────────────────▶ │  gunicorn (non-root) │ ────────▶ │ PostgreSQL 16│
│ 80/443 auto- │                             │  web:8000, USER app  │  intern   │  db:5432     │
│    HTTPS     │ ◀── staticfiles:/srv/static │  config.wsgi         │           │  (intern)    │
└──────────────┘        (ro-Volume)          └──────────────────────┘           └──────────────┘
```

| Schicht | Container | Port | Von außen? | Aufgabe |
|---------|-----------|------|------------|---------|
| Reverse Proxy | `caddy` (`caddy:2`) | 80, 443 | **ja** | Auto-HTTPS (Let's Encrypt), HTTP→HTTPS-Redirect, gzip/zstd, Access-Log |
| App | `web` (Build aus `deploy/Dockerfile`) | 8000 (intern) | nein | gunicorn + Django, läuft als non-root-User `app` (UID 10001) |
| Datenbank | `db` (`postgres:16`) | 5432 (intern) | nein | PostgreSQL, RLS aktiv (siehe [rls.md](rls.md)) |

!!! note "TLS-Terminierung"
    Caddy terminiert TLS und setzt `X-Forwarded-Proto`. Django vertraut diesem Header
    (`SECURE_PROXY_SSL_HEADER`) und erzwingt intern `SECURE_SSL_REDIRECT`. Der
    Healthcheck von `web` prüft deshalb bewusst per **reinem TCP-Connect** auf
    `127.0.0.1:8000` – ein HTTP-Request würde am SSL-Redirect bzw. der Host-Prüfung
    scheitern.

---

## 2. Deploy-Artefakte (`deploy/`)

Alle Bausteine liegen im Verzeichnis `deploy/` des Repos.

### 2.1 `Dockerfile`

Basis `python:3.12-slim`, unprivilegierter Laufzeit-User, ausführbares Entrypoint.

```dockerfile
FROM python:3.12-slim
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
```

!!! tip "Windows-Falle: fehlendes +x-Bit"
    Wird das Repo unter Windows committet, fehlt dem `entrypoint.sh` oft das
    Ausführungs-Bit. Das `chmod +x /app/deploy/entrypoint.sh` im Dockerfile setzt es beim
    Build wieder – deshalb startet der Container auch nach Windows-Commits zuverlässig.

### 2.2 `docker-compose.yml`

Drei Services (`db`, `web`, `caddy`), benannte Volumes für persistente Daten. Zentrale
Punkte:

- `web`-Healthcheck: TCP-Connect auf `127.0.0.1:8000` (umgeht SSL-Redirect/Host-Prüfung).
- `caddy` startet erst, wenn `web` **healthy** ist (`depends_on: condition: service_healthy`).
- `web` startet erst, wenn `db` **healthy** ist (`pg_isready`).
- Persistente benannte Volumes: `pgdata`, `staticfiles`, `media`, `applog`, `caddy_data`,
  `caddy_config`.

```yaml
services:
  db:
    image: postgres:16
    restart: unless-stopped
    env_file: .env.prod
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER}"]
      interval: 10s
      timeout: 5s
      retries: 5

  web:
    build:
      context: ..
      dockerfile: deploy/Dockerfile
    restart: unless-stopped
    env_file: .env.prod
    depends_on:
      db:
        condition: service_healthy
    volumes:
      - staticfiles:/app/staticfiles
      - media:/app/media
      - applog:/app/logs         # benanntes Volume (vom non-root-User beschreibbar)
    healthcheck:
      # reiner TCP-Check auf gunicorn:8000 (umgeht SSL-Redirect/Host-Prüfung)
      test: ["CMD", "python", "-c", "import socket; socket.create_connection(('127.0.0.1',8000),3).close()"]
      interval: 15s
      timeout: 5s
      retries: 5
      start_period: 40s

  caddy:
    image: caddy:2
    restart: unless-stopped
    ports: ["80:80", "443:443"]
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - staticfiles:/srv/static:ro
      - caddy_data:/data
      - caddy_config:/config
    depends_on:
      web:
        condition: service_healthy   # erst proxyen, wenn gunicorn wirklich bereit ist

volumes:
  pgdata: {}
  staticfiles: {}
  media: {}
  applog: {}
  caddy_data: {}
  caddy_config: {}
```

!!! note "`applog` als benanntes Volume"
    Weil `web` als non-root-User `app` läuft, muss das Log-Verzeichnis für ihn beschreibbar
    sein. Ein benanntes Volume (`applog:/app/logs`) statt eines Host-Bind-Mounts umgeht
    Owner-/Permission-Probleme.

### 2.3 `Caddyfile`

Auto-HTTPS über Let's Encrypt; nur die Domain anpassen.

```caddy
# Domain anpassen. Caddy holt & erneuert das TLS-Zertifikat automatisch (Let's Encrypt).
leistungsnachweis.eingliederungshilfe.cloud {
    encode zstd gzip
    log {
        output file /data/access.log
    }
    reverse_proxy web:8000
}
```

!!! warning "DNS zuerst"
    Der A-Record (und AAAA bei IPv6) muss **vor** dem ersten Caddy-Start auf die
    Server-IP zeigen, sonst scheitert die ACME-/Let's-Encrypt-Challenge. Prüfen mit
    `dig leistungsnachweis.eingliederungshilfe.cloud +short`.

### 2.4 `entrypoint.sh`

Läuft bei **jedem** Containerstart: Migrationen + statische Dateien, dann Start des
CMD (gunicorn).

```sh
#!/bin/sh
# Migrationen + statische Dateien bei jedem Containerstart
set -e
python manage.py migrate --noinput
python manage.py collectstatic --noinput
exec "$@"
```

Damit laufen Datenbank-Migrationen bei jedem `up`/Rebuild automatisch – ein separater
Migrations-Schritt beim Update entfällt.

### 2.5 `.env.prod.example`

Vorlage für die Secrets-Datei. **Nicht** ins Git; als `deploy/.env.prod` mit `chmod 600`
anlegen.

```bash
# Kopie als deploy/.env.prod anlegen (NICHT ins Git; chmod 600, chown deploy).
# Secret-Key erzeugen: python -c "import secrets;print(secrets.token_urlsafe(64))"
DJANGO_SECRET_KEY=bitte-frischen-64-zeichen-zufallswert-einsetzen
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=leistungsnachweis.eingliederungshilfe.cloud
DJANGO_CSRF_TRUSTED_ORIGINS=https://leistungsnachweis.eingliederungshilfe.cloud
DJANGO_OTP_REQUIRED=1
DJANGO_HSTS_SECONDS=300

# PostgreSQL
POSTGRES_DB=fegh
POSTGRES_USER=fegh
POSTGRES_PASSWORD=langes-zufallspasswort-einsetzen
DATABASE_URL=postgres://fegh:langes-zufallspasswort-einsetzen@db:5432/fegh
```

---

## 3. Umgebungsvariablen

Konfiguriert in `deploy/.env.prod` (ausgewertet in `config/settings.py`).

| Variable | Beispiel / Default | Zweck |
|----------|--------------------|-------|
| `DJANGO_SECRET_KEY` | 64-Zeichen-Zufall | Signaturschlüssel. In Prod (`DEBUG=0`) **Pflicht** – ohne startet die App nicht. |
| `DJANGO_DEBUG` | `0` | `0` = Produktion. Fail-closed: sobald `DATABASE_URL` **oder** `DJANGO_ALLOWED_HOSTS` gesetzt ist, wird DEBUG auf `False` erzwungen. |
| `DJANGO_ALLOWED_HOSTS` | `leistungsnachweis.eingliederungshilfe.cloud` | Komma-Liste erlaubter Hosts. In Prod leer = keine Requests akzeptiert. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://leistungsnachweis.eingliederungshilfe.cloud` | Komma-Liste der HTTPS-Origins (Django 4+ nötig für POST/CSRF). |
| `DJANGO_OTP_REQUIRED` | `1` | 2FA-Pflicht für alle (außer Break-Glass-Superuser `root`). |
| `DJANGO_HSTS_SECONDS` | `300` → `31536000` | HSTS-Dauer. Erst kurz (300 s) testen, dann 1 Jahr. |
| `DJANGO_IDLE_TIMEOUT_MIN` | `15` | Leerlauf-Timeout der Session in Minuten (`SESSION_IDLE_TIMEOUT`). |
| `POSTGRES_DB` | `fegh` | DB-Name (von `db`- und `web`-Container genutzt). |
| `POSTGRES_USER` | `fegh` | DB-User. |
| `POSTGRES_PASSWORD` | Zufall | DB-Passwort (muss mit `DATABASE_URL` übereinstimmen). |
| `DATABASE_URL` | `postgres://fegh:...@db:5432/fegh` | Verbindungs-URL; nur wenn gesetzt, nutzt Django PostgreSQL (sonst lokal SQLite). |
| `DJANGO_SEED_ROOT_PASSWORD` | – (optional) | Passwort für Break-Glass `root` im `seed`-Command. Ohne diese + `DEBUG=0` wird **kein** Seed-Superuser erzeugt. |
| `DJANGO_AXES_FAILURE_LIMIT` | `5` (optional) | Fehlversuche bis Sperre (django-axes). |
| `DJANGO_AXES_COOLOFF_HOURS` | `1` (optional) | Stunden bis Auto-Entsperrung (django-axes). |

!!! note "Weitere fixe Prod-Härtung"
    Bei `DEBUG=False` setzt `config/settings.py` u. a. automatisch: WhiteNoise +
    `CompressedManifestStaticFilesStorage`, `SECURE_SSL_REDIRECT`, HSTS mit
    `INCLUDE_SUBDOMAINS`/`PRELOAD`, `SESSION_COOKIE_SECURE`/`CSRF_COOKIE_SECURE`,
    `SESSION_COOKIE_HTTPONLY`, `SameSite=Lax`, `X_FRAME_OPTIONS=DENY`,
    `SESSION_COOKIE_AGE=8h`, `SESSION_EXPIRE_AT_BROWSER_CLOSE`, Argon2 als Passwort-Hash
    und rotierendes File-Logging. Details siehe [Härtung](haertung.md).

---

## 4. Erst-Deploy (Server als root)

!!! tip "Server-Härtung zuerst"
    Vor dem App-Deploy den Server härten (non-root Deploy-User, SSH-Key-only, UFW,
    fail2ban, unattended-upgrades, Docker). Der vollständige Ablauf steht im Repo unter
    `deploy/deploy.md` (Abschnitt 2). Das folgende Runbook zeigt den App-Teil.

```bash
# 1) Repo holen
git clone https://github.com/miri2577/FEGH-Leistungsnachweis /srv/fegh
cd /srv/fegh/deploy

# 2) Secrets-Datei anlegen
cp .env.prod.example .env.prod
chmod 600 .env.prod

# 3) Secrets erzeugen und eintragen (SECRET_KEY + DB-Passwort)
openssl rand -hex 64            # -> DJANGO_SECRET_KEY
openssl rand -hex 24            # -> POSTGRES_PASSWORD (auch in DATABASE_URL eintragen)
nano .env.prod                  # SECRET_KEY, ALLOWED_HOSTS, CSRF, DB-Passwort setzen

# 4) Domain in den Caddyfile eintragen
sed -i 's/nachweis.deine-domain.de/leistungsnachweis.eingliederungshilfe.cloud/' Caddyfile

# 5) Bauen und starten
docker compose up -d --build

# 6) Break-Glass-Admin anlegen
docker compose exec web python manage.py createsuperuser
```

Migrationen und `collectstatic` laufen automatisch im `entrypoint.sh` – kein separater
Schritt nötig.

!!! warning "Erststart: staticfiles/media-Volume ggf. einmalig löschen"
    Da `web` als non-root-User `app` läuft, kann ein aus einem früheren (root-)Build
    stammendes Volume falsche Owner haben und `collectstatic` scheitern lassen. Falls der
    Erststart daran hängt, **einmalig** die App-Volumes zurücksetzen (das Daten-Volume
    `pgdata` **bleibt** unangetastet):

    ```bash
    docker compose down
    docker volume rm deploy_staticfiles deploy_media
    docker compose up -d --build
    ```

### 4.1 Smoke-Test

```bash
# TLS/Erreichbarkeit
curl -I https://leistungsnachweis.eingliederungshilfe.cloud

# Django-Prod-Checks
docker compose exec web python manage.py check --deploy
```

- Login + 2FA-Einrichtung durchspielen, eine Erfassung testen.
- Kein unerwarteter Warn-Output bei `check --deploy`.

---

## 5. Nach dem Deploy: root-Passwort setzen

Der Break-Glass-Superuser `root` (ohne Mitarbeiter-Profil, kein Klientenzugriff) sollte
ein starkes, separat verwahrtes Passwort erhalten:

```bash
docker compose exec web python manage.py changepassword root
```

!!! note "HSTS stufenweise scharf schalten"
    Beim ersten Rollout `DJANGO_HSTS_SECONDS=300` (5 min) – so lässt sich ein Fehlkonfig
    schnell korrigieren, ohne Browser für ein Jahr auf HTTPS zu nageln. Läuft alles,
    in `.env.prod` auf `31536000` (1 Jahr) setzen und `web` neu starten:

    ```bash
    nano .env.prod                       # DJANGO_HSTS_SECONDS=31536000
    docker compose up -d                 # web übernimmt neuen Wert
    ```

---

## 6. Update-Deploy

```bash
cd /srv/fegh
git pull
cd deploy
docker compose up -d --build
```

Migrationen laufen automatisch im `entrypoint.sh`. Für Base-Image-Updates (nicht von
unattended-upgrades erfasst) regelmäßig:

```bash
docker compose pull        # postgres:16, caddy:2 aktualisieren
docker compose up -d --build
```

**Rollback:** vorheriges Image bzw. DB-Restore aus Backup – siehe
[Backup & Restore](backup-restore.md).

---

## 7. Fallen & Troubleshooting

| Symptom | Ursache | Lösung |
|---------|---------|--------|
| `entrypoint.sh: permission denied` | Windows-Commit ohne +x-Bit | Im Dockerfile per `chmod +x` bereits gelöst – ggf. Rebuild (`--build`). |
| `collectstatic`/Static-Errors beim Erststart | Volume mit falschen Ownern (root vs. UID 10001) | Einmalig `docker volume rm deploy_staticfiles deploy_media`, dann Rebuild. `pgdata` bleibt. |
| Caddy: TLS-Cert-Fehler | DNS zeigt nicht auf Server | `dig … +short`, A/AAAA-Record korrigieren, Caddy neu starten. |
| `web` bleibt `unhealthy` | gunicorn nicht bereit / DB fehlt | `docker compose logs web`; `db`-Healthcheck prüfen. |
| CSRF-Fehler bei POST | `DJANGO_CSRF_TRUSTED_ORIGINS` fehlt/falsch | HTTPS-Origin exakt (mit `https://`) eintragen, `web` neu starten. |
| App startet nicht (`SECRET_KEY`) | `DJANGO_SECRET_KEY` in Prod nicht gesetzt | In `.env.prod` setzen. |

Logs ansehen:

```bash
docker compose logs -f web
docker compose logs -f caddy
docker compose exec web tail -f /app/logs/django.log
```

---

## 8. Weiterführend

- [Härtung](haertung.md) – Security-Einstellungen, 2FA, django-axes, DSGVO-Checkliste.
- [Row-Level Security (RLS)](rls.md) – Mandanten-/Zeilenschutz in PostgreSQL.
- [Backup & Restore](backup-restore.md) – `pg_dump` + age-Verschlüsselung, Restore-Test.

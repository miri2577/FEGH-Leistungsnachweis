# Sicherheitshärtung

Diese Seite dokumentiert die Sicherheits- und Datenschutz-Härtung der FEGH-Leistungsnachweis-Webapp. Die App verarbeitet besondere Kategorien personenbezogener Daten (Art.-9-DSGVO: Gesundheits- und Sozialdaten von Klient*innen der Eingliederungshilfe). Die Härtung folgt zwei Leitgedanken:

- **Datentrennung nach Team (Need-to-know):** Jede*r sieht nur die Klient*innen des eigenen bzw. geleiteten Teams.
- **Fail-closed:** Konfigurationsfehler führen zu weniger Zugriff, nie zu mehr.

!!! danger "DSGVO-Kern"
    Der Admin (Systemadministration) hat **keinen** Klientenzugriff. Diese Trennung ist an mehreren Stellen redundant abgesichert (Rollenlogik, keine Django-Admin-Rechte, Regressionstests) und darf nicht aufgeweicht werden.

---

## (a) Rollenmodell

Die gesamte Sichtbarkeits- und Zugriffslogik ist zentral in `nachweis/services.py` (Zeilen ~20–110) gebündelt. Views fragen ausschließlich diese Funktionen ab – es gibt kein verstreutes, ad-hoc gebautes Scoping.

### Rollen im Überblick

| Rolle | Klientenzugriff | Sichtbarer Umfang | Kasse |
|-------|-----------------|-------------------|-------|
| **User** (Betreuer*in) | ja | Klient*innen des **eigenen** Teams (Vertretung: alle im Team) | eigenes/geleitetes Team |
| **Leitung** | ja | Klient*innen der **geleiteten** Team(s) + eigenes Team | eigenes/geleitetes Team |
| **Verwaltung** | **nein** | keine Klient*innen; dafür **alle Kassen** (Finanz-Hub) | alle |
| **Admin** | **nein** | keine Klient*innen; verwaltet Teams & Mitarbeiter | keine |
| **Break-Glass-Superuser `root`** | alle | Notzugang, ohne Mitarbeiter-Profil | alle |

### Zentrale Funktionen (`services.py`)

| Funktion | Zweck |
|----------|-------|
| `mitarbeiter_fuer(user)` | Liefert das `Mitarbeiter`-Profil zum Login (oder `None`). |
| `ist_admin(user)` | App-Rolle Admin – **kein** Klientenzugriff, auch nicht als Superuser. |
| `ist_leitung(user)` | Leitung (für Team-Auswertung & Genehmigungen); Break-Glass zählt ebenfalls als Leitung. |
| `ist_verwaltung(user)` | Team Verwaltung – keine Klientenarbeit, aber Kasse. |
| `ohne_klientenarbeit(user)` | `True` für Admin **oder** Verwaltung. |
| `teams_fuer(user)` | Teams, deren Klient*innen sichtbar sind. Admin → `none()`; Leitung → geleitete + eigenes; User → eigenes; Break-Glass → alle. |
| `klienten_fuer(user)` | Klient*innen im Zugriff (`Klient`-QuerySet). Admin/Verwaltung → `none()`; Break-Glass → alle; sonst `team__in=teams_fuer(user)`. |
| `_superuser_ohne_profil(user)` | Erkennt den technischen Break-Glass-Superuser **ohne** Mitarbeiter-Profil (Notzugang). |

!!! note "Warum ein Superuser *ohne* Profil?"
    Der Break-Glass-Zugang wird bewusst am Fehlen eines `Mitarbeiter`-Profils erkannt (`_superuser_ohne_profil`). Ein regulärer Login (mit Profil) wird dadurch niemals „versehentlich" zum Allzugriff – Superuser-Rechte allein reichen nicht, es muss auch das Profil fehlen.

!!! warning "Admin ist nicht gleich Superuser"
    Die App-Rolle **Admin** (`Rolle.ADMIN`) ist eine reine Verwaltungsrolle für Teams/Mitarbeiter und hat **keinen** Klientenzugriff. `ist_admin()` liefert selbst dann `False` für den Klientenzugriff-Pfad, wenn zusätzlich Superuser-Rechte gesetzt wären. Der technische Notzugang ist ausschließlich der profillose `root`.

---

## (b) Keine App-Rolle bekommt `is_staff` → Django-Admin nur für Break-Glass

Beim Anlegen/Aktualisieren eines Kontos setzt `konto_rechte_setzen(user, rolle)` in `nachweis/accounts.py` **immer**:

```python
user.is_staff = False
user.is_superuser = False
```

Damit erhält **keine** App-Rolle (auch nicht Admin oder Leitung) Zugang zum Django-Admin unter `/admin/`.

!!! danger "Begründung: Der Django-Admin umgeht das Team-Scoping"
    Der Django-Admin arbeitet direkt auf den Modell-Tabellen und ruft **nicht** `klienten_fuer()` / `teams_fuer()` auf. Ohne diese Härtung könnte:

    - eine **Leitung** dort teamübergreifend **alle** Klient*innen sehen und ändern,
    - ein **Admin** sich über das `rolle`-Feld selbst zur Leitung machen (**Rechte-Eskalation**).

    Team-, Mitarbeiter- und Klienten-Pflege läuft deshalb ausschließlich über die app-nativen, rollen- und team-gescopten Seiten. Der Django-Admin bleibt dem technischen Break-Glass-Superuser vorbehalten.

Die Django-Rechte-Gruppen (`Administration`, `Leitung`) werden aus dokumentarischen Gründen weiterhin zugeordnet (`ensure_gruppen()`), sind aber **ohne `is_staff` im Admin wirkungslos**.

!!! tip "2FA gilt auch im Admin"
    Die `OTPErzwingenMiddleware` nimmt nur `/admin/login/` aus, **nicht** den gesamten `/admin/`-Bereich – so ist die 2FA-Pflicht auf der sensibelsten Oberfläche nicht umgehbar.

---

## (c) Seed: kein `admin/admin` mehr, `root` nur mit Passwort

Der Demodaten-Seed (`nachweis/management/commands/seed.py`) wurde gehärtet:

- **Kein statischer `admin/admin`-Superuser mehr.** Alt-Konten aus früheren Seeds werden aktiv entfernt:

  ```python
  get_user_model().objects.filter(username="admin", is_superuser=True).delete()
  ```

- **Demo-Mitarbeiter** werden ohne Admin-Rechte angelegt (`is_staff = False`, `is_superuser = False`).

- **Break-Glass `root`** wird nur angelegt, wenn ein Passwort verfügbar ist:

  ```python
  root_pw = os.environ.get("DJANGO_SEED_ROOT_PASSWORD") or ("root12345" if settings.DEBUG else "")
  ```

  Das heißt: In Produktion (`DEBUG=0`) ohne gesetzte `DJANGO_SEED_ROOT_PASSWORD` wird **gar kein** Seed-Superuser erzeugt – stattdessen dann bewusst `python manage.py createsuperuser`.

!!! note "Produktivstart ohne Demodaten"
    `python manage.py seed --leer` legt keine Fiktivdaten an, sondern nur die Rechte-Gruppen und den Jahresparameter, und gibt eine Schritt-für-Schritt-Anleitung für den echten Produktivstart aus (Superuser → Teams → Mitarbeiter → Klient*innen).

---

## (d) django-axes: Login-Lockout (Brute-Force-Schutz)

`django-axes` sperrt fehlschlagende Logins. Konfiguration in `config/settings.py`:

```python
AXES_FAILURE_LIMIT = int(os.environ.get("DJANGO_AXES_FAILURE_LIMIT", "5"))
AXES_COOLOFF_TIME  = int(os.environ.get("DJANGO_AXES_COOLOFF_HOURS", "1"))  # Stunden
AXES_RESET_ON_SUCCESS   = True                            # erfolgreicher Login setzt Zähler zurück
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]    # sperrt Kombination, nicht ganze NATs
AXES_ENABLE_ADMIN = True
AXES_VERBOSE = True
```

- **Default:** 5 Fehlversuche → Sperre, 1 Stunde Cooloff (danach automatische Entsperrung).
- **Lockout-Schlüssel** ist die Kombination `username` + `ip_address` – dadurch werden nicht ganze NAT-/Firmen-IPs mit vielen Nutzer*innen kollektiv ausgesperrt.
- Bei Sperre antwortet der Login mit **HTTP 429 (Too Many Requests)**.

Damit axes die Fehlversuche zählt, muss sein Auth-Backend **vor** dem Standard-Backend stehen, und die `AxesMiddleware` läuft als **letzte** Middleware:

```python
AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesStandaloneBackend',
    'django.contrib.auth.backends.ModelBackend',
]

MIDDLEWARE = [
    # ...
    'axes.middleware.AxesMiddleware',   # MUSS als letzte Middleware laufen
]
```

!!! tip "Manuelles Entsperren"
    Sperren lassen sich vor Ablauf des Cooloff aufheben mit:

    ```bash
    python manage.py axes_reset            # alle Sperren
    python manage.py axes_reset_username <name>
    ```

---

## (e) django-auditlog: revisionssichere Änderungsprotokollierung

`django-auditlog` protokolliert, **wer wann welchen** sensiblen Datensatz angelegt, geändert oder gelöscht hat. Die getrackten Modelle stehen in `config/settings.py`:

```python
AUDITLOG_INCLUDE_TRACKING_MODELS = (
    # Art-9-Freitexte werden NICHT im Auditlog gespeichert (Datenminimierung, ISO A.8.11):
    {"model": "nachweis.Leistung", "exclude_fields": ["dokumentation", "notiz"]},
    {"model": "nachweis.Klient", "exclude_fields": ["kommentar"]},
    {"model": "nachweis.Termin", "exclude_fields": ["notiz"]},
    {"model": "nachweis.Abwesenheit", "exclude_fields": ["kommentar"]},
    "nachweis.Gruppe",
    "nachweis.Arbeitszeit",
    "nachweis.Kassenbuchung",
    "nachweis.Zaehlprotokoll",
    "nachweis.Mitarbeiter",
)
```

Die `auditlog.middleware.AuditlogMiddleware` hängt an jeden Log-Eintrag den **Actor** (`request.user`), sodass Änderungen einer konkreten Person zugeordnet werden können. Sie ist in `MIDDLEWARE` eingetragen.

!!! note "Datenminimierung: Verlaufstexte bleiben aus dem Auditlog"
    Die besonders sensiblen Freitextfelder (`Leistung.dokumentation`/`notiz`, `Klient.kommentar`,
    `Termin.notiz`, `Abwesenheit.kommentar`) sind per `exclude_fields` vom Tracking ausgenommen –
    der **Wer/Wann/Was-Nachweis bleibt** erhalten, der Art-9-Inhalt landet aber **nicht zusätzlich**
    im Log. Die Timeline-Wiederherstellung lässt diese Felder dadurch unangetastet (sie werden nicht
    mit Log-Werten überschrieben).

---

## (f) Auto-Logout bei Inaktivität

Nach einer konfigurierbaren Leerlaufzeit werden angemeldete Nutzer*innen automatisch abgemeldet – **serverseitig erzwungen**, also auch ohne JavaScript wirksam.

- **Middleware** `InaktivitaetsAbmeldung` in `nachweis/middleware.py`: Jede Anfrage gilt als Aktivität und setzt den Timer zurück (gleitendes Fenster über `request.session["last_activity"]`). Bei Überschreitung: `logout()` und Redirect auf `…/login?timeout=1`.
- **Setting** `SESSION_IDLE_TIMEOUT` (in Sekunden), abgeleitet aus Minuten:

  ```python
  SESSION_IDLE_TIMEOUT = int(os.environ.get("DJANGO_IDLE_TIMEOUT_MIN", "15")) * 60
  ```

  Default: **15 Minuten**.
- **Clientseitig** ergänzen ein Timer plus Keepalive über den Endpunkt `/api/ping/` das serverseitige Fenster (Warnung/Verlängerung im Browser).

!!! note "Zwei Ebenen"
    Der serverseitige Timeout ist die verbindliche Grenze. Der Client-Timer und `/api/ping/` dienen der Benutzerführung (z. B. Vorwarnung), können die Server-Regel aber nicht aushebeln.

---

## (g) DEBUG fail-closed & SECRET_KEY-Pflicht

In `config/settings.py` ist der Debug-Modus so abgesichert, dass ein Deploy-Konfigfehler **keine** offene Debug-Instanz erzeugen kann:

```python
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"

# Fail-closed: Produktions-Indikatoren erzwingen DEBUG=False – auch wenn
# DJANGO_DEBUG versehentlich fehlt/vertippt ist.
if DEBUG and (os.environ.get("DATABASE_URL") or os.environ.get("DJANGO_ALLOWED_HOSTS")):
    DEBUG = False

# In Produktion (DEBUG=0) NIEMALS mit dem unsicheren Dev-Key laufen.
if not DEBUG and not os.environ.get("DJANGO_SECRET_KEY"):
    from django.core.exceptions import ImproperlyConfigured
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY muss in Produktion (DEBUG=0) gesetzt sein.")
```

- Sobald **echte DB** (`DATABASE_URL`) **oder** `DJANGO_ALLOWED_HOSTS` gesetzt sind, läuft die Instanz garantiert **nicht** im Debug-Modus – selbst wenn `DJANGO_DEBUG` fehlt oder vertippt ist.
- Läuft die Instanz produktiv (`DEBUG=0`), ist ein **explizit gesetzter `DJANGO_SECRET_KEY` Pflicht** – der eingebaute Dev-Key (`django-insecure-…`) wird verweigert (`ImproperlyConfigured`).
- `ALLOWED_HOSTS` ist im Debug offen (`["*"]`), in Produktion **leer**, sofern nicht explizit gesetzt.

!!! warning "Zusätzliche Produktions-Schalter (`if not DEBUG`)"
    Nur bei `DEBUG=False` greifen u. a. `SECURE_SSL_REDIRECT`, HSTS (`SECURE_HSTS_SECONDS`), `SESSION_COOKIE_SECURE` / `CSRF_COOKIE_SECURE`, `SESSION_COOKIE_HTTPONLY`, `X_FRAME_OPTIONS = "DENY"`, `SECURE_PROXY_SSL_HEADER` (Caddy terminiert TLS) sowie WhiteNoise für statische Dateien. Sessions sind an den Arbeitstag gekoppelt (`SESSION_COOKIE_AGE = 8h`, `SESSION_EXPIRE_AT_BROWSER_CLOSE = True`).

### Content-Security-Policy (CSP)

`nachweis.middleware.CSPMiddleware` setzt eine Content-Security-Policy als **zweite XSS-Verteidigungslinie** (hinter Djangos Auto-Escaping): `default-src 'self'`, `object-src 'none'` und `frame-ancestors 'none'` blocken externe Skripte, Datenabfluss an fremde Hosts und das Einbetten in fremde Seiten.

- **`script-src` ist Nonce-basiert – ohne `'unsafe-inline'`.** Die Middleware würfelt pro Request ein `secrets`-Nonce, legt es _vor_ dem Rendern an `request.csp_nonce` und hängt es als `'nonce-…'` an `script-src`. Nur die eigenen Inline-`<script>` tragen dieses Nonce (`nonce="{{ request.csp_nonce }}"`); **eingeschleustes** Inline-JS führt der Browser nicht mehr aus. Damit die Policy ohne `'unsafe-inline'` auskommt, wurden **alle 61 Inline-Event-Handler** (`onclick`/`onsubmit`/`onchange`) in die zentrale, per Event-Delegation gebundene `nachweis/static/nachweis/js/aktionen.js` ausgelagert – deklarativ über `data-`Attribute (`data-confirm`, `data-autosubmit`, `data-print`, `data-copy-from`, `data-set-value`, `data-nav-select`, `data-select-on-click`).
- **`style-src` behält `'unsafe-inline'` bewusst.** Die Templates nutzen 858 Inline-`style`-Attribute; diese zu eliminieren wäre unverhältnismäßig, und CSS-Injection ist ein weit geringeres Risiko als Script-Injection.
- **Standard: Report-Only** (`Content-Security-Policy-Report-Only`) – meldet Verstöße, blockiert nichts. So lässt sich die Policy gefahrlos beobachten.
- **Scharf schalten** mit `DJANGO_CSP_ENFORCE=1` (Header wird zu `Content-Security-Policy`); in Produktion (`DEBUG=False`) ist das **fail-closed an**.
- Optional `DJANGO_CSP_REPORT_URI=…` für einen Melde-Endpunkt.

---

## (h) Passwort-Hashing mit Argon2

Bevorzugter Hash-Algorithmus ist **Argon2** (`argon2-cffi`), konfiguriert in `config/settings.py`:

```python
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
```

Neue und bei Login geänderte Passwörter werden mit Argon2 gehasht; PBKDF2 bleibt nur als Fallback für Altbestände. Aktivierungs-/Reset-Links nutzen Djangos zustandslosen `PasswordResetTokenGenerator` (einmalig gültig, zeitlich begrenzt über `PASSWORD_RESET_TIMEOUT = 7 Tage`).

---

## (i) Isolations-Regressionstests

Die Team-/Datentrennung ist der DSGVO-Kern und dauerhaft durch Tests in `nachweis/tests.py` abgesichert. Bei einem Scoping-Fehler schlagen sie fehl.

**Ausführung:**

```bash
python manage.py test nachweis
```

Der Test `TeamIsolationTests` baut zwei Fach-Teams (A, B), ein Verwaltungsteam sowie User, Leitung und Admin auf und prüft:

| Test | Prüft |
|------|-------|
| `test_klienten_fuer_team_scoped` | User A sieht nur Klient A, nicht Klient B (und umgekehrt) – **Team-Scoping**. |
| `test_admin_hat_keinen_klientenzugriff` | `klienten_fuer(admin).count() == 0` – **Admin ohne Klienten**. |
| `test_leitung_sieht_nur_geleitetes_team` | Leitung von Team A sieht Klient A, nicht Klient B. |
| `test_suche_kein_fremdteam_klient` | Die **Suche** (`/api/suche/`) findet keinen Fremdteam-Klienten. |
| `test_suche_admin_ohne_klienten` | Die Suche liefert dem Admin gar keine Kategorie „klienten". |
| `test_druck_fremdklient_404` | Direkter Aufruf `/druck/?klient=<fremd>` → **HTTP 404** (IDOR-Schutz). |
| `test_termin_fremd_nicht_loeschbar` | Löschversuch auf fremden Termin bleibt wirkungslos (**IDOR** auf Objektebene). |
| `test_kalender_nur_eigenes_team` | Der **Kalender** zeigt nur Mitarbeiter des eigenen Teams. |

!!! tip "Bei jeder Änderung am Scoping ausführen"
    Diese Tests sind das Sicherheitsnetz für die Datentrennung. Nach Änderungen an `services.py`, an Views mit Klientenbezug oder am Rollenmodell müssen sie grün bleiben.

---

## (j) ISO-27001-Audit (Juli 2026): umgesetzte Fixes

Ein mehrstufiger Sicherheitsaudit (White-Box-Codeprüfung + Deployment-Review, jede Erkenntnis
adversarial gegengeprüft) bewertete die App nach **ISO/IEC 27001:2022** und OWASP. Ergebnis: keine
aus dem Internet ohne Zugangsdaten ausnutzbare Lücke. Die bestätigten Befunde wurden umgesetzt:

| Fix | ISO-Control | Kurzbeschreibung |
|-----|-------------|------------------|
| **Selbst-Eskalation** unterbunden | A.5.3 Aufgabentrennung | Ein Admin kann die **eigene** Rolle/Team/Teamleitung nicht mehr ändern (kein Selbst-Upgrade zur Leitung → kein Klientenzugriff). Fremde Konten bleiben verwaltbar. |
| **Offboarding-Schutz** | A.8.3 Zugriffsbeschränkung | Ein bewusst deaktiviertes Konto (`Mitarbeiter.aktiv=False`) lässt sich **nicht** per (noch gültigem) Aktivierungslink reaktivieren. |
| **`.dockerignore`** | A.8.12 Data-Leakage | `db.sqlite3`, `.git`, Logs, `.env*`, `*.age` landen nicht mehr in den (unverschlüsselten) Image-Layern. |
| **Suche per POST** | A.8.15 Protokollierung | Der Suchbegriff (Klientenname/Aktenzeichen) steht nicht mehr im Query-String und damit nicht im Reverse-Proxy-/Access-Log. |
| **Passwort-Mindestlänge 12** | A.5.17 Authentisierungsinfo | `MinimumLengthValidator` mit `min_length=12` (statt Django-Default 8). |
| **CSV-Injection neutralisiert** | A.8.28 Sichere Codierung | Formel-Präfixe (`= + - @`) in Rechnungs-/eAbrechnungs-CSV bekommen ein Apostroph vorangestellt (`_csv_safe`). |
| **Auditlog-Maskierung** | A.8.11 Datenmaskierung | Art-9-Freitexte via `exclude_fields` nicht mehr im Auditlog (siehe Abschnitt e). |
| **OTP fail-closed** | A.8.5 Sichere Authentisierung | 2FA in Produktion **standardmäßig Pflicht** (siehe unten). |
| **`/admin/` hinter VPN** | A.8.20 Netzwerksicherheit | Django-Admin nur aus dem zugelassenen Netz (Caddy `ADMIN_ALLOW_CIDR`) – siehe [VPN-Zugang & Admin-Schutz](vpn.md). |
| **PDF-Dateiname bereinigt** | A.8.28 Sichere Codierung | Nachname im `Content-Disposition`-Header auf `[A-Za-z0-9._-]` reduziert. |
| **gunicorn gehärtet** | A.8.20 / A.8.9 | `forwarded_allow_ips` auf das Docker-Netz beschränkt (statt `*`), Worker-Recycling + Request-Limits. |
| **Abhängigkeiten exakt gepinnt** | A.8.8 Schwachstellen-Mgmt | `requirements.txt` vollständig `==`-gepinnt (reproduzierbare Builds); Docker-Images per **Digest** gepinnt (`postgres`/`caddy`), Python-Basis auf Patch-Version. |
| **Permissions-Policy-Header** | A.8.9 Konfigurationsmgmt | Caddy setzt `Permissions-Policy` und entfernt den `Server`-Header. |
| **CSP fail-closed** | A.8.9 Konfigurationsmgmt | Content-Security-Policy wird in Produktion **erzwungen** (statt nur Report-Only); Override per `DJANGO_CSP_ENFORCE`. |
| **Rate-Limiting** | A.5.17 Authentisierungsinfo | IP-Limit (15/h) am öffentlichen Aktivierungs-Endpunkt gegen Token-Bruteforce/DoS – über geteilten DB-Cache. |
| **2FA-Step-up** | A.8.5 Sichere Authentisierung | Deaktivieren der Zwei-Faktor-Authentifizierung erfordert die erneute Passwort-Eingabe (Schutz gegen Session-Übernahme). |

!!! tip "OTP-Zwang & CSP sind jetzt fail-closed"
    In Produktion (`DEBUG=False`) sind **2FA-Pflicht** (`OTP_REQUIRED`) und **CSP-Enforce**
    standardmäßig **an**; nur ein explizites `DJANGO_OTP_REQUIRED=0` bzw. `DJANGO_CSP_ENFORCE=0`
    schaltet sie ab. Lokal (`DEBUG=True`) bleiben beide aus (Report-Only bzw. optional).

!!! note "Geteilter Cache & Rate-Limiting"
    In Produktion nutzt die App einen **DB-Cache** (PostgreSQL, prozessübergreifend über alle
    gunicorn-Worker – kein zusätzlicher Dienst). Die Tabelle legt der `entrypoint.sh` per
    `createcachetable` an (idempotent). Darauf setzt das IP-Rate-Limit des Aktivierungs-Endpunkts auf.

!!! note "Bewusst offen / organisatorisch"
    Verbliebene niedrigpriore Härtungen: **DB-TLS** im internen
    Docker-Netz (geringer Nutzen, da nicht exponiert) und Migrationen aus dem Container-Start
    entkoppeln (bei **einem** Web-Container unkritisch – der aktuelle Weg ist korrekt). Der
    **wichtigste** verbleibende Schritt ist organisatorisch: die Datenschutz-Dokumente
    (VVT, DSFA, AVV Träger↔Betreiber) **vor** dem ersten echten Klientendatensatz.

---

## Relevante Umgebungsvariablen

| Env-Variable | Default | Wirkung |
|--------------|---------|---------|
| `DJANGO_SECRET_KEY` | Dev-Key | **Pflicht** in Produktion (`DEBUG=0`), sonst `ImproperlyConfigured`. |
| `DJANGO_DEBUG` | `1` | Debug-Modus; wird bei Prod-Indikatoren **fail-closed** auf `False` erzwungen. |
| `DATABASE_URL` | – | PostgreSQL (sonst SQLite). Gesetzt ⇒ erzwingt `DEBUG=False`. |
| `DJANGO_ALLOWED_HOSTS` | leer | Erlaubte Hosts (kommasepariert). Gesetzt ⇒ erzwingt `DEBUG=False`. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | leer | HTTPS-Origins für CSRF (Django 4+). |
| `DJANGO_AXES_FAILURE_LIMIT` | `5` | Fehlversuche bis Login-Lockout. |
| `DJANGO_AXES_COOLOFF_HOURS` | `1` | Stunden bis zur automatischen Entsperrung. |
| `DJANGO_IDLE_TIMEOUT_MIN` | `15` | Inaktivitäts-Timeout in Minuten (→ `SESSION_IDLE_TIMEOUT`). |
| `DJANGO_OTP_REQUIRED` | `1` in Prod, `0` lokal | 2FA-Pflicht für **alle** (inkl. Break-Glass); in Produktion (`DEBUG=0`) **fail-closed an**, nur `0` schaltet ab. |
| `CADDY_DOMAIN` | – | Domain für Caddy/TLS (Platzhalter `{$CADDY_DOMAIN}` in der Caddyfile). |
| `ADMIN_ALLOW_CIDR` | `127.0.0.1/32` | Netz, aus dem `/admin/` erreichbar ist (VPN); Default = nur localhost. Siehe [VPN](vpn.md). |
| `DJANGO_SEED_ROOT_PASSWORD` | – | Passwort für Break-Glass `root` im Seed; ohne dies + `DEBUG=0` kein Seed-Superuser. |
| `DJANGO_HSTS_SECONDS` | `31536000` | HSTS-Dauer (nur bei `DEBUG=0`). |
| `DJANGO_CSP_ENFORCE` | `1` in Prod, `0` lokal | CSP erzwingen statt Report-Only; in Produktion (`DEBUG=0`) **fail-closed an**, nur `0` schaltet ab. |
| `DJANGO_CSP_REPORT_URI` | – | optionaler Melde-Endpunkt für CSP-Verstöße. |
| `DJANGO_LOG_FILE` | `logs/django.log` | Rotierendes Security-/Request-Log (nur bei `DEBUG=0`). |

!!! note "Dateiüberblick"
    - `config/settings.py` – zentrale Härtungs-Settings (DEBUG fail-closed, axes, auditlog, Argon2, Prod-Schalter).
    - `nachweis/services.py` – Rollen-/Scoping-Logik.
    - `nachweis/accounts.py` – `konto_rechte_setzen` (kein `is_staff`).
    - `nachweis/middleware.py` – `InaktivitaetsAbmeldung`, `OTPErzwingenMiddleware`, `RLSKontext`.
    - `nachweis/management/commands/seed.py` – gehärteter Seed (kein `admin/admin`, `root` nur mit Passwort).
    - `nachweis/tests.py` – Isolations-Regressionstests.

# Was wurde umgesetzt (Juli 2026)

Diese Seite fasst chronologisch und thematisch zusammen, was in der Ausbaustufe
**Juli 2026** des FEGH-Leistungsnachweises umgesetzt wurde. Sie dient als
Projektstand und Changelog: kurze Absätze mit dem *Warum*, konkrete Belege aus dem
Code (`config/settings.py`, `nachweis/models.py`, `nachweis/views.py`) und Links
auf die jeweiligen Detailseiten.

!!! note "Kontext"
    Der Leistungsnachweis verarbeitet **Art.-9-DSGVO-Daten** (Gesundheits-/Sozialdaten
    von Klient\*innen im Team TBEW, Berliner Eingliederungshilfe). Deshalb liegt der
    Schwerpunkt dieser Ausbaustufe auf **Datenschutz, Zugriffstrennung und
    Nachvollziehbarkeit** – ergänzt um Fach-Features und einen produktionsreifen Betrieb.

---

## 1 · Sicherheit & DSGVO

Der größte Block dieser Ausbaustufe. Ziel: Die App ist auch bei Fehlbedienung,
Angriffsversuchen und Konfigurationsfehlern **fail-closed** und hält die
DSGVO-Rollentrennung technisch durch (nicht nur organisatorisch).

### Keine `is_staff`-Rechte für App-Rollen – Django-Admin nur als Break-Glass

Die Anwendungsrollen (`User`, `Leitung`, `Admin`, `Verwaltung`) bekommen **keinen
Zugang zum Django-Admin** mehr. Der Django-Admin bleibt ausschließlich dem
Break-Glass-Superuser `root` vorbehalten (ein technischer Login **ohne**
`Mitarbeiter`-Profil und damit ohne Klientenbezug). So kann keine App-Rolle über den
Admin an der Rechte- und Datentrennung vorbei arbeiten.

!!! danger "DSGVO-Trennung"
    Die Rolle `Admin` verwaltet Teams und Mitarbeiter\*innen, hat aber **keinen
    Klientenzugriff** (siehe `Rolle` in `nachweis/models.py`). Diese Trennung wäre
    wertlos, wenn Admins über den Django-Admin doch an die `Klient`-Tabelle kämen –
    darum ist `is_staff` für App-Rollen ausgeschlossen.

### Seed-Standardlogin `admin/admin` entfernt

Aus dem Seed-Kommando wurde das bequeme, aber gefährliche Demo-Konto `admin/admin`
entfernt. Ein produktiver Start ohne bekannte Standard-Zugangsdaten ist Pflicht.

### XSS-Fix in der Erfassung

In der Live-Erfassung (`erfassung` / `api_leistung_save` in `nachweis/views.py`)
werden Freitextfelder (Tätigkeit, Notiz, Dokumentation) konsequent escaped, sodass
eingegebenes Markup **nicht** als HTML/JS im Browser ausgeführt wird.

### Suche team-gescopt

Die globale Suche liefert nur Treffer aus dem **eigenen Sichtbarkeitsbereich**. In
`_suche_kategorien` / `api_suche` (`nachweis/views.py`) wird die Query pro Rolle
gefiltert: User sieht die eigenen Klient\*innen, Leitung die geleiteten Teams, Admin
gar keine Klientendaten. Kein Datenleck über die Suchleiste.

### django-axes – Brute-Force-Lockout

`axes` ist als App und Middleware eingebunden (`config/settings.py`). Nach zu vielen
Fehlversuchen wird die Kombination **Benutzername + IP** gesperrt.

| Einstellung | Wert (Default) | Env-Variable |
| --- | --- | --- |
| Fehlversuche bis Sperre | `5` | `DJANGO_AXES_FAILURE_LIMIT` |
| Cool-off bis Auto-Entsperrung | `1` Stunde | `DJANGO_AXES_COOLOFF_HOURS` |
| Reset bei Erfolg | `True` | – |
| Sperr-Parameter | `username + ip_address` | – |

```python
AXES_FAILURE_LIMIT = int(os.environ.get("DJANGO_AXES_FAILURE_LIMIT", "5"))
AXES_COOLOFF_TIME = int(os.environ.get("DJANGO_AXES_COOLOFF_HOURS", "1"))
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
```

### django-auditlog – Änderungsprotokoll

Revisionssicheres Protokoll, **wer wann welchen sensiblen Datensatz** angelegt,
geändert oder gelöscht hat. Die `AuditlogMiddleware` hängt den handelnden
`request.user` an jeden Eintrag. Erfasst werden u. a. `Klient`, `Leistung`,
`Gruppe`, `Arbeitszeit`, `Abwesenheit`, `Kassenbuchung`, `Zaehlprotokoll`,
`Mitarbeiter`, `Termin` (siehe `AUDITLOG_INCLUDE_TRACKING_MODELS`).

### Auto-Logout bei Inaktivität

Serverseitig erzwungen über die Middleware `nachweis.middleware.InaktivitaetsAbmeldung`
plus ein clientseitiger Timer. Standard **15 Minuten**, konfigurierbar:

```python
SESSION_IDLE_TIMEOUT = int(os.environ.get("DJANGO_IDLE_TIMEOUT_MIN", "15")) * 60
```

### DEBUG fail-closed

Ein Deploy-Konfigfehler darf **nie** eine offene Debug-Instanz mit Dev-Key erzeugen.
Sobald Produktions-Indikatoren gesetzt sind (`DATABASE_URL` oder
`DJANGO_ALLOWED_HOSTS`), erzwingt `config/settings.py` `DEBUG = False`; und ohne
gesetzten `DJANGO_SECRET_KEY` startet die Instanz in Produktion gar nicht erst.

```python
if DEBUG and (os.environ.get("DATABASE_URL") or os.environ.get("DJANGO_ALLOWED_HOSTS")):
    DEBUG = False

if not DEBUG and not os.environ.get("DJANGO_SECRET_KEY"):
    raise ImproperlyConfigured("DJANGO_SECRET_KEY muss in Produktion (DEBUG=0) gesetzt sein.")
```

Im Produktionszweig (`if not DEBUG:`) greifen zusätzlich HSTS, `SECURE_SSL_REDIRECT`,
sichere/HttpOnly-Cookies, `X_FRAME_OPTIONS = "DENY"`, Content-Type-Nosniff sowie
Argon2 als Passwort-Hash.

### Isolations-Regressionstests

Automatisierte Tests stellen sicher, dass die Team-Isolation **nicht versehentlich
zurückgebaut** wird: Ein User sieht keine fremden Klient\*innen, Admin keine
Klientendaten, die Suche bleibt gescopt. Diese Tests laufen bei jeder Änderung.

### PostgreSQL Row-Level-Security (opt-in)

Als zusätzliche Tiefenverteidigung kann die Team-Isolation direkt in der Datenbank
erzwungen werden (RLS). Die Middleware `nachweis.middleware.RLSKontext` setzt den
Sitzungskontext pro Request. Standardmäßig **opt-in**, damit lokal (SQLite) alles
unverändert bleibt.

!!! tip "Detailseiten"
    Vertiefung: [Datenschutz](sicherheit/datenschutz.md) ·
    [Row-Level-Security](sicherheit/rls.md) ·
    [Backup & Restore](sicherheit/backup-restore.md) ·
    [Deployment](sicherheit/deployment.md)

---

## 2 · Features

Fachliche Erweiterungen für den Arbeitsalltag im Team.

### Globale Spotlight-Suche

Ein Overlay (Tastatur-Kurzbefehl) mit Live-Ergebnissen über `api_suche`
(`nachweis/views.py`). Durchsucht Klient\*innen, Leistungen, Gruppen u. a. – **immer
rollen-gescopt** (siehe Abschnitt Sicherheit).

### Wochen-Auslastung AL / kLE / FLS + Balkendiagramm

Das Dashboard zeigt die Wochenauslastung je Leistungsart. Grundlage sind die
FLS-Kennzahlen aus `nachweis/models.py`: `Klient.al` (bewilligte FLS/Monat),
`Klient.kle` (davon kalkulatorische Leistungseinheit) und `fls_gesamt = AL + kLE`.
Als Fachleistungsstunden zählen die Arten `FS`, `WFS`, `BAO` (`FLS_ARTEN`). Berechnet
in `services.wochenauslastung`, angezeigt in `mein_ueberblick` / `dashboard` inkl.
Balkendiagramm.

### Druck-Center „Druck-Nachweise“

Sammelseite `druck_center` (`nachweis/views.py`), die alle druckbaren Nachweise
bündelt: **Klient**-Monatsnachweis, **Arbeitszeit**nachweis, **Kassen**blatt und
**Gruppen**nachweis. Leitung kann Nachweise des ganzen Teams drucken, User nur die
eigenen (`_druck_mitarbeiter`).

### Kasse: Kassenbuch + Zählprotokoll

Vollständige Bargeldkasse je Team (`Kasse` → `Kassenmonat` → `Kassenbuchung`, plus
`Zaehlprotokoll`). Der Kassenmonat rechnet `endbestand = vortrag + einnahmen −
ausgaben`; das Zählprotokoll stellt den **physischen Bargeldbestand** (Stückelung
100 € … 1 Cent, `GELDSTUECKELUNG`) dem Buchbestand gegenüber und weist die
`differenz` aus. Die Rolle **Verwaltung** ist Finanz-Hub und sieht/pflegt alle Kassen.

### Wochenkalender (Tag/Woche/Monat, Vollbild, Filter)

Terminkalender je Mitarbeiter\*in (`Termin`, `kalender` in `nachweis/views.py`) mit
Ansichten **Tag / Woche / Monat**, Vollbildmodus und Filtern. Termine werden zur
besseren Unterscheidung mit einer **stabilen Pastellfarbe** und dem Kürzel der/des
Klient\*in versehen (`Klient.farbe`, `kuerzel_anzeige`, `FARBPALETTE`).

### Dokumentation je Leistung + letzte 10 auf dem Dashboard

Jede `Leistung` hat ein Freitextfeld `dokumentation` (ausführlicher Verlaufstext). Das
Dashboard zeigt die **letzten 10** Dokumentationen. Zusätzlich gibt es einen
druckbaren Doku-Verlauf je Klient\*in (`doku_druck`).

### Wiederherstellungs-Timeline

Eine Timeline macht Änderungen an sensiblen Datensätzen sichtbar und
nachvollziehbar (auf Basis des Audit-Logs) und unterstützt die Wiederherstellung.

!!! tip "Detailseiten"
    [Wochenkalender](anleitung/kalender.md) ·
    [Druck-Nachweise](anleitung/druck-nachweis.md) ·
    [Mein Überblick](anleitung/mein-ueberblick.md) ·
    [Leistungsnachweis](anleitung/leistungsnachweis.md) ·
    [Gruppen](anleitung/gruppen.md)

---

## 3 · Betrieb

Produktionsreife für die Strato-Instanz (Debian 13, Docker + Caddy + PostgreSQL,
`leistungsnachweis.eingliederungshilfe.cloud`).

### Docker non-root + Healthcheck

Der Container läuft als **non-root-Benutzer** und hat einen **Healthcheck**, sodass
Docker/Compose einen kranken Container erkennt und neu startet. Statische Dateien
werden in Produktion über WhiteNoise ausgeliefert
(`CompressedManifestStaticFilesStorage`).

### Verschlüsseltes Backup (age) + Cron + Restore-Test

Automatische, mit **age** verschlüsselte Datenbank-Backups, per **Cron** geplant,
inklusive regelmäßigem **Restore-Test** (ein Backup ist nur so gut wie seine
nachgewiesene Wiederherstellbarkeit).

### DB-Indizes

Für schnelle, oft genutzte Abfragen sind Indizes gesetzt, u. a. in
`nachweis/models.py`:

- `Klient`: `Index(fields=["team", "status"])`
- `Leistung`: `["klient", "datum"]`, `["betreuer", "datum"]`
- `Termin`: `["mitarbeiter", "datum"]`, `["datum"]`
- `Arbeitszeit`: `["mitarbeiter", "datum"]`

### Leerstart (`seed --leer`)

Für einen sauberen Produktivstart erzeugt das Seed-Kommando mit `--leer` **nur die
Grundstruktur ohne Fiktivdaten** – ideal, um mit echten Daten zu beginnen, ohne
Demo-Klient\*innen aufräumen zu müssen.

!!! tip "Detailseiten"
    [Backup & Restore](sicherheit/backup-restore.md) ·
    [Deployment](sicherheit/deployment.md) ·
    [Backups & Löschkonzept](sicherheit/backups-loeschkonzept.md) ·
    [Lokale Entwicklung](technik/entwicklung-lokal.md)

---

## Weiterführende Seiten

- Sicherheit: [Datenschutz](sicherheit/datenschutz.md) ·
  [Row-Level-Security](sicherheit/rls.md) ·
  [Backup & Restore](sicherheit/backup-restore.md) ·
  [Deployment](sicherheit/deployment.md)
- Anleitungen: [Wochenkalender](anleitung/kalender.md) ·
  [Druck-Nachweise](anleitung/druck-nachweis.md) ·
  [Zwei-Faktor](anleitung/zwei-faktor.md) ·
  [Arbeitszeit & Stempeluhr](anleitung/arbeitszeit-stempeluhr.md)
- Fachliches: [FLS & kLE](fachliches/fls-kle.md) ·
  [Rollen & Teams](fachliches/rollen-teams.md)
- Technik: [Datenmodell](technik/datenmodell.md) ·
  [Projektstruktur](technik/projektstruktur.md)

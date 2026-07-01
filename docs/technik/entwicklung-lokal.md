# Lokale Entwicklung: einrichten, starten, testen

Diese Seite führt Schritt für Schritt durch das lokale Aufsetzen der App – von der virtuellen Umgebung über die Datenbank und die Demodaten bis zum laufenden Entwicklungsserver. Sie richtet sich an Entwickler*innen, die das Projekt zum ersten Mal auf ihrem Rechner starten.

!!! info "Voraussetzungen"
    - **Python 3.12** (nativ unter Windows; kein WSL nötig)
    - **Git**
    - Ein Terminal (unter Windows: PowerShell)

## 1. Repository holen

```bash
git clone https://github.com/miri2577/FEGH-Leistungsnachweis.git
cd FEGH-Leistungsnachweis
```

## 2. Virtuelle Umgebung (venv) anlegen und aktivieren

Eine **virtuelle Umgebung** kapselt die Python-Pakete des Projekts, damit sie sich nicht mit anderen Projekten oder dem System-Python ins Gehege kommen.

=== "Windows (PowerShell)"

    ```powershell
    py -3.12 -m venv .venv
    .\.venv\Scripts\Activate.ps1
    ```

=== "macOS / Linux"

    ```bash
    python3.12 -m venv .venv
    source .venv/bin/activate
    ```

Nach dem Aktivieren steht `(.venv)` vorne in der Eingabezeile.

!!! tip "PowerShell blockiert das Aktivierungs-Skript?"
    Einmalig für die aktuelle Sitzung erlauben:
    ```powershell
    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
    ```

## 3. Abhängigkeiten installieren

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

`requirements.txt` enthält die **Basis-Pakete** (Django 5.1, `holidays`, `django-otp`, `qrcode`) sowie **Produktions-Pakete** (gunicorn, psycopg, whitenoise, dj-database-url, argon2-cffi). Für die lokale Entwicklung reicht die Basis; die Produktions-Pakete lassen sich problemlos mitinstallieren.

!!! note "Optionale Pakete"
    Einige Pakete sind in `requirements.txt` bewusst **auskommentiert** (z. B. `weasyprint` für echte PDFs, `django-auditlog`, `django-axes`). Sie brauchen teils Systembibliotheken und werden erst auf dem Server scharf geschaltet. Lokal fällt der PDF-Export elegant zurück auf die Druckansicht (Browser: Strg+P) – die View `druck_pdf` fängt ein fehlendes WeasyPrint ab.

## 4. Datenbank aufbauen (Migrationen)

Die **Migrationen** legen das Datenbank-Schema in der lokalen SQLite-Datei `db.sqlite3` an:

```bash
python manage.py migrate
```

!!! info "Was passiert hier?"
    Jede Datei in `nachweis/migrations/` beschreibt einen Schritt des Datenbank-Schemas. `migrate` spielt alle noch nicht angewandten Schritte ein. Beim ersten Lauf entsteht dabei auch `db.sqlite3` neu, falls sie fehlt.

## 5. Demodaten einspielen (seed)

Damit die Oberfläche nicht leer ist, füllt der eigene Management-Befehl **`seed`** die Datenbank mit **fiktiven** Demodaten (keine echten Personen):

```bash
python manage.py seed
```

Der Befehl (`nachweis/management/commands/seed.py`) legt an:

- **3 Teams**: `TBEW` (BEW), `WG Lindenhof` (WG), `Verwaltung`.
- **9 Mitarbeitende** mit den Rollen `Leitung`, `User`, `Admin` – inkl. Django-Gruppen mit gezielten Rechten (DSGVO: **Admin verwaltet Teams/Mitarbeitende, nicht Klient*innen**).
- **33 Klient*innen** mit HBG-Werten, teils fälligen Berichten, teils beendeter Betreuung.
- **Leistungen, 2 Gruppen, Arbeitszeiten (Juni 2026), Abwesenheiten und Stempelungen**.

!!! warning "seed löscht standardmäßig vorhandene Demodaten"
    `python manage.py seed` **leert** zuerst die Demo-Tabellen und befüllt neu (deterministisch über einen festen Zufalls-Seed). Wer nur ergänzen möchte, nutzt:
    ```bash
    python manage.py seed --keep
    ```

### Demo-Logins

Alle Mitarbeitenden-Konten nutzen dasselbe Prototyp-Passwort **`demo12345`**. Der Benutzername ist der **kleingeschriebene Nachname**:

| Benutzername | Rolle | Team | Bemerkung |
|---|---|---|---|
| `berger` | Leitung | TBEW | leitet TBEW **und** WG (Team-Auswertung, Genehmigungen) |
| `neumann` | User | TBEW | Betreuer*in |
| `schuster` | User | TBEW | Betreuer*in |
| `kaiser` | User | TBEW | Betreuer*in |
| `lorenz` | User | TBEW | Betreuer*in |
| `hartmann` | User | WG | Betreuer*in |
| `wolf` | User | WG | Teilzeit-Beispiel (30 h/Woche) |
| `sander` | Admin | Verwaltung | Systemadministration, **kein** Klientenzugriff |
| `peters` | User | Verwaltung | fester Arbeitsplatz, Stempeluhr-Demo |

Zusätzlich legt `seed` zwei technische Superuser an (nur im Prototyp!):

| Benutzername | Passwort | Zweck |
|---|---|---|
| `root` | `root12345` | **Break-Glass-Superuser ohne Mitarbeiter-Profil** – Notzugang, von 2FA-Zwang ausgenommen |
| `admin` | `admin` | Demo-Superuser für den Django-Admin |

!!! danger "Nur für den Prototyp"
    Diese Klartext-Passwörter und Demo-Superuser sind ausschließlich für die lokale Demonstration gedacht. In Produktion gelten Argon2-Hashing, individuelle Passwörter, verpflichtende 2FA (`DJANGO_OTP_REQUIRED=1`) und ein sauber verwahrter Notzugang.

## 6. Entwicklungsserver starten

```bash
python manage.py runserver
```

Danach ist die App erreichbar unter **http://127.0.0.1:8000/**. Melden Sie sich z. B. als `berger` / `demo12345` an, um die Leitungs-Ansichten (Team-Auswertung, Genehmigungen) zu sehen, oder als `neumann`, um die Betreuer*innen-Sicht zu erleben.

!!! tip "Automatisches Neuladen"
    Der `runserver` startet sich bei Code-Änderungen selbst neu. Nach reinen Template-/Static-Änderungen genügt oft ein Neuladen im Browser.

Wichtige Einstiegs-URLs (aus `nachweis/urls.py`):

| Pfad | Ansicht | Route |
|---|---|---|
| `/` | Mein Überblick (Startseite) | `nachweis:start` |
| `/fachleistungsstunden/` | Team-Auswertung (nur Leitung) | `nachweis:dashboard` |
| `/erfassung/` | Leistungserfassung (Grid) | `nachweis:erfassung` |
| `/druck/` | Druck-Leistungsnachweis | `nachweis:druck` |
| `/arbeitszeit/` | Arbeitszeit (Selfservice) | `nachweis:arbeitszeit` |
| `/abwesenheit/` | Urlaub / Freizeitausgleich | `nachweis:abwesenheit` |
| `/admin/` | Django-Admin | – |

## 7. Zwei-Faktor lokal ausprobieren (optional)

Standardmäßig ist 2FA im Prototyp **optional** (`OTP_REQUIRED` = `0`). Wer es testen will, richtet unter `/2fa/setup/` ein TOTP-Gerät ein (QR-Code für eine Authenticator-App). Ab dann verlangt die eigene `OTPErzwingenMiddleware` bei jedem Login den Code. Um 2FA für **alle** zu erzwingen, setzt man vor dem Start die Umgebungsvariable:

=== "Windows (PowerShell)"

    ```powershell
    $env:DJANGO_OTP_REQUIRED = "1"; python manage.py runserver
    ```

=== "macOS / Linux"

    ```bash
    DJANGO_OTP_REQUIRED=1 python manage.py runserver
    ```

!!! note "seed setzt 2FA zurück"
    Ein erneutes `python manage.py seed` (ohne `--keep`) löscht bestehende TOTP-Geräte, damit die Demo-Logins ohne Zweitfaktor nutzbar bleiben.

## 8. Prüfen und Testen

Vor dem Commit lohnen sich ein paar Standard-Checks:

```bash
# Konfiguration & Modelle auf Probleme prüfen
python manage.py check

# Offene Migrationen erkennen (meldet, falls Models geändert wurden)
python manage.py makemigrations --check --dry-run

# Automatische Tests ausführen
python manage.py test
```

!!! note "Teststand"
    Die Datei `nachweis/tests.py` ist aktuell noch ein Platzhalter. Neue Tests gehören hierhin (bzw. in ein `tests/`-Paket) – besonders geeignet ist die **Geschäftslogik in `services.py`** (z. B. Teamsitzungs-Verteilung, Fachleistungsstunden), weil sie ohne HTTP direkt aufrufbar ist.

## 9. Nützliche Alltagsbefehle

| Befehl | Wirkung |
|---|---|
| `python manage.py runserver` | Entwicklungsserver starten |
| `python manage.py migrate` | Datenbank-Schema aktualisieren |
| `python manage.py makemigrations` | Migration aus Model-Änderungen erzeugen |
| `python manage.py seed` / `seed --keep` | Demodaten neu setzen / ergänzen |
| `python manage.py createsuperuser` | eigenen Admin-Zugang anlegen |
| `python manage.py shell` | interaktive Python-Konsole mit Django-Kontext |
| `python manage.py collectstatic` | statische Dateien einsammeln (v. a. Produktion) |

## Datenbank zurücksetzen (Neustart bei Schema-Problemen)

Weil die lokale SQLite-Datei nur Demodaten enthält, ist ein vollständiger Reset ungefährlich:

```bash
# 1. Datenbankdatei löschen
rm db.sqlite3        # Windows PowerShell: Remove-Item db.sqlite3

# 2. Schema neu aufbauen und Demodaten einspielen
python manage.py migrate
python manage.py seed
```

!!! tip "Typischer Ablauf beim ersten Start (Kurzfassung)"
    ```bash
    py -3.12 -m venv .venv && .\.venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    python manage.py migrate
    python manage.py seed
    python manage.py runserver
    # Browser: http://127.0.0.1:8000/  ·  Login: berger / demo12345
    ```

Damit läuft die App lokal. Wie der Code intern aufgebaut ist, erklären die Seiten „Python, Django & MTV-Grundlagen“ und „Projektstruktur“; die Fachlogik dahinter beschreibt die Seite zu `services.py`.
# Migrationen

Diese Seite erklärt, wie aus den Python-Modellen (`nachweis/models.py`) echte Datenbanktabellen werden, wie man das Schema ändert, und was beim Wechsel von **SQLite** zu **PostgreSQL** zu beachten ist. Voraussetzung sind die Begriffe von der Seite [Datenbank-Grundlagen](datenbank-grundlagen.md).

## Das Grundproblem

In `models.py` beschreiben wir die Daten als **Python-Klassen**. Die Datenbank versteht aber kein Python, sondern nur **SQL** (`CREATE TABLE …`, `ALTER TABLE …`). Es braucht also eine Übersetzung vom Modellcode in Datenbank-Befehle – und die muss auch dann funktionieren, wenn sich der Code später ändert (neues Feld, neue Tabelle). Genau das leisten **Migrationen**.

!!! note "Migration = versionierter Bauplan-Schritt"
    Eine Migration ist eine kleine Python-Datei, die **eine Schema-Änderung** beschreibt (z. B. „Tabelle Stempelung anlegen“ oder „Spalte urlaubstage hinzufügen“). Die Migrationen sind durchnummeriert und bauen aufeinander auf – zusammen ergeben sie den kompletten Bauplan der Datenbank. Weil sie im Git-Repository liegen, ist jede Schema-Änderung nachvollziehbar und reproduzierbar.

## Die zwei zentralen Befehle

### `makemigrations` – Änderungen erkennen und aufschreiben

```bash
python manage.py makemigrations
```

Django vergleicht den **aktuellen Stand der Modelle** mit dem **letzten bekannten Migrationsstand** und schreibt die Unterschiede in eine **neue** Migrationsdatei unter `nachweis/migrations/`. Dieser Befehl **ändert die Datenbank noch nicht** – er erzeugt nur die Anleitung.

### `migrate` – Änderungen in die Datenbank einspielen

```bash
python manage.py migrate
```

Django führt alle noch nicht angewandten Migrationen der Reihe nach aus und bringt die Datenbank auf den neuesten Stand (legt Tabellen an, ändert Spalten usw.). Django merkt sich in einer internen Tabelle `django_migrations`, welche Migrationen bereits liefen – deshalb wird jede nur **einmal** angewandt, und `migrate` kann man gefahrlos wiederholen.

```mermaid
flowchart LR
    A["models.py<br/>(Python-Klassen)"] -- makemigrations --> B["Migrationsdatei<br/>0006_....py"]
    B -- migrate --> C[("Datenbank<br/>Tabellen & Spalten")]
```

!!! tip "Merksatz"
    **`makemigrations`** schreibt den Plan (aus Modell-Änderungen). **`migrate`** führt den Plan aus (auf der Datenbank). Erst planen, dann bauen.

## Die Migrationen dieses Projekts

Unter `nachweis/migrations/` liegen aktuell folgende Dateien. Ihre Namen dokumentieren die Entwicklungsgeschichte des Schemas:

| Datei | Was sie einführte |
|---|---|
| `0001_initial.py` | **Startschema**: die ersten Modelle/Tabellen der App |
| `0002_mitarbeiter_user.py` | Feld `user` am Mitarbeiter – die 1:1-Verknüpfung zum Login |
| `0003_mitarbeiter_urlaubstage_mitarbeiter_wochenstunden_and_more.py` | Selfservice-Vorgaben `urlaubstage`, `wochenstunden` (u. a.) |
| `0004_team_alter_mitarbeiter_rolle_klient_team_and_more.py` | **Team**-Modell, Team-Zuordnung für Klient, Anpassung der `rolle` (u. a.) |
| `0005_stempelung.py` | **Stempelung**-Modell (Kommen/Gehen) |

`__init__.py` markiert den Ordner als Python-Paket und gehört nicht zum Schema.

!!! info "Namen kommen automatisch"
    Die etwas sperrigen Dateinamen (`..._and_more.py`) erzeugt Django selbst aus den enthaltenen Änderungen. Man kann beim Erstellen mit `makemigrations -n kurzer_name` auch einen eigenen Namen vergeben.

### Reihenfolge und Abhängigkeiten

Migrationen bauen aufeinander auf: `0005` setzt `0004` voraus, `0004` setzt `0003` voraus usw. Jede Datei nennt ihre Vorgänger im Feld `dependencies`. Deshalb **niemals** bereits eingespielte Migrationsdateien nachträglich verändern oder löschen – das bringt die Kette und die `django_migrations`-Tabelle durcheinander. Änderungen macht man immer über **neue** Migrationen.

## Ein typischer Änderungs-Workflow

Angenommen, an `Klient` soll ein neues Feld ergänzt werden:

1. Feld in `nachweis/models.py` hinzufügen, z. B.:
   ```python
   telefon = models.CharField(max_length=30, blank=True)
   ```
2. Migration erzeugen:
   ```bash
   python manage.py makemigrations
   # -> nachweis/migrations/0006_klient_telefon.py
   ```
3. Erzeugte Datei kurz durchsehen (macht sie das Richtige?).
4. Einspielen:
   ```bash
   python manage.py migrate
   ```
5. Migrationsdatei **mit committen** (sie gehört zum Code).

!!! warning "Neue Pflichtfelder brauchen einen Standardwert"
    Fügt man ein Feld **ohne** `null=True` und **ohne** `default` zu einer Tabelle hinzu, in der schon Zeilen stehen, fragt `makemigrations` interaktiv nach einem Wert für die bestehenden Zeilen – die Datenbank braucht ja für jede vorhandene Zeile einen Wert. Besser gleich `default=…` oder `blank=True`/`null=True` setzen (wie bei den optionalen Feldern der App).

## Nützliche Zusatzbefehle

| Befehl | Zweck |
|---|---|
| `python manage.py showmigrations` | zeigt je Migration, ob sie schon angewandt ist (`[X]` / `[ ]`) |
| `python manage.py sqlmigrate nachweis 0005` | zeigt das **SQL**, das eine Migration ausführen würde (nur Anzeige) |
| `python manage.py migrate nachweis 0004` | fährt gezielt auf einen früheren Stand zurück (Rollback von `0005`) |
| `python manage.py makemigrations --check --dry-run` | prüft in CI, ob Modelle und Migrationen synchron sind |

## Wo landen die Tabellen? – Die aktuelle Konfiguration

Welche Datenbank `migrate` bespielt, steht in `config/settings.py` unter `DATABASES`. Im Prototyp ist das **SQLite**:

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}
```

Die komplette Datenbank ist damit **eine einzige Datei** (`db.sqlite3` im Projektverzeichnis) – kein Server, keine Einrichtung. Ideal zum Entwickeln, aber nicht für den parallelen Mehrbenutzerbetrieb der Produktion gedacht.

## SQLite → PostgreSQL für die Produktion

Für den Produktivbetrieb ist **PostgreSQL** vorgesehen – ein echter Datenbankserver, der viele gleichzeitige Zugriffe, strengere Typprüfung und robustere Sicherung bietet. Der Umstieg ist in den Einstellungen bereits **vorbereitet** und wird über eine Umgebungsvariable ausgelöst:

```python
# PostgreSQL aus Umgebungsvariable (nur wenn gesetzt -> lokal weiter SQLite)
if os.environ.get("DATABASE_URL"):
    import dj_database_url
    DATABASES["default"] = dj_database_url.parse(
        os.environ["DATABASE_URL"], conn_max_age=600, ssl_require=False)
```

Das heißt:

- Ist **keine** `DATABASE_URL` gesetzt (Entwicklungsrechner), bleibt alles bei **SQLite** – nichts zu tun.
- Ist `DATABASE_URL` gesetzt (Server), wird sie mit `dj_database_url` geparst und die App spricht **PostgreSQL**. Eine solche URL sieht z. B. so aus (fiktiv):
  ```
  postgres://benutzer:passwort@db-host:5432/leistungsnachweis
  ```

### So läuft der Wechsel praktisch ab

1. PostgreSQL-Datenbank bereitstellen, Treiber `psycopg`/`psycopg2` und `dj_database_url` installieren.
2. `DATABASE_URL` als Umgebungsvariable setzen.
3. Schema in der **leeren** Postgres-Datenbank aufbauen – dieselben Migrationen wie bei SQLite:
   ```bash
   python manage.py migrate
   ```
4. Superuser/Startdaten anlegen (bzw. Demodaten migrieren).

!!! tip "Dieselben Migrationen für beide Datenbanken"
    Der große Vorteil der Migrationen: Genau **dieselben** Migrationsdateien bauen das Schema sowohl in SQLite als auch in PostgreSQL auf. Django erzeugt für jede Engine das passende SQL. Man muss die Modelle also **nicht** anfassen, um umzuziehen.

!!! warning "Daten wandern nicht automatisch mit"
    `migrate` erzeugt nur die **leeren Tabellen** in der neuen Datenbank – vorhandene SQLite-Inhalte werden dabei **nicht** kopiert. Für einen Datenumzug nutzt man z. B. `dumpdata`/`loaddata` oder ein dediziertes Migrationsskript. Da SQLite Typen lockerer handhabt als PostgreSQL, sollte man nach dem Umzug die Daten prüfen. Für den Prototyp mit fiktiven Demodaten genügt meist ein frischer Aufbau.

### Warum überhaupt PostgreSQL?

| Kriterium | SQLite (Prototyp) | PostgreSQL (Produktion) |
|---|---|---|
| Betrieb | eine Datei, kein Server | eigener Datenbankserver |
| Gleichzeitige Schreibzugriffe | eingeschränkt (Datei-Sperre) | für viele Nutzer\*innen ausgelegt |
| Typ-/Constraint-Prüfung | locker | streng |
| Backup/Skalierung | Datei kopieren | ausgereifte Werkzeuge |
| Empfehlung | Entwicklung, Demo | echter Team-Betrieb |

Damit ist der Weg von den Python-Modellen bis zur produktiven Datenbank vollständig: Modelle in `models.py` → `makemigrations` → Migrationsdateien → `migrate` → Tabellen in SQLite bzw. PostgreSQL.

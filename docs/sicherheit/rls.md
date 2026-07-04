# Datentrennung & Row-Level-Security

Klient*innen sind besonders schützenswerte Daten nach **DSGVO Art. 9** (Gesundheits-
und Sozialdaten). Die Anwendung stellt sicher, dass eine Nutzer*in immer nur die
Klient*innen der **eigenen bzw. geleiteten Teams** sieht. Diese Trennung wird auf
**zwei Ebenen** durchgesetzt:

| Ebene | Wo | Aktiv | Datenbank |
|-------|----|-------|-----------|
| **App-Ebene** | Python/Django ORM (`services.py`) | immer | SQLite & PostgreSQL |
| **DB-Ebene (RLS)** | PostgreSQL Row-Level-Security | opt-in, scharf zu schalten | nur PostgreSQL |

Die App-Ebene ist der Regelfall und immer aktiv. Die DB-Ebene ist eine zusätzliche
**Defense-in-Depth**-Schicht: Selbst bei einem App-Bug (vergessenes Filtern, roher
SQL-Zugriff) verweigert die Datenbank teamfremde Zeilen.

---

## (a) App-Ebene: Scoping im Service-Layer

Die gesamte Sichtbarkeit von Teams und Klient*innen wird zentral in
`nachweis/services.py` entschieden. Views greifen **nie** direkt auf
`Klient.objects.all()` zu, sondern immer über diese Funktionen.

### `teams_fuer(user)`

Liefert die Teams, deren Klient*innen die Nutzer*in sehen darf:

```python
def teams_fuer(user):
    """Teams, deren Klient*innen der/die Nutzer*in sehen darf.
    Admin: keine (kein Klientenzugriff). Leitung: geleitete Team(s) + eigenes.
    User: nur eigenes Team. Break-Glass-Superuser: alle."""
    m = mitarbeiter_fuer(user)
    if m is None:
        return Team.objects.all() if _superuser_ohne_profil(user) else Team.objects.none()
    if m.rolle == Rolle.ADMIN:
        return Team.objects.none()
    ids = set(m.leitet.values_list("id", flat=True)) if m.rolle == Rolle.LEITUNG else set()
    if m.team_id:
        ids.add(m.team_id)
    return Team.objects.filter(id__in=ids)
```

### `klienten_fuer(user)`

Baut auf `teams_fuer` auf und liefert das eigentliche Klient*innen-QuerySet:

```python
def klienten_fuer(user):
    if not user.is_authenticated or ist_admin(user) or ist_verwaltung(user):
        return Klient.objects.none()
    if _superuser_ohne_profil(user):
        return Klient.objects.all()
    return Klient.objects.filter(team__in=teams_fuer(user))
```

### Sichtbarkeitsmatrix

| Rolle | Klient*innen-Sicht |
|-------|--------------------|
| **User** (Betreuer*in) | nur das eigene Team |
| **Leitung** | geleitete Team(s) **+** eigenes Team |
| **Admin** | keine (DSGVO-Trennung: verwaltet nur Teams/Mitarbeiter) |
| **Verwaltung** | keine (Kasse ja, Klientenarbeit nein) |
| **Break-Glass-Superuser** (ohne Profil) | alle |

!!! note "Regressionstests"
    Diese Matrix ist durch Tests abgesichert. Änderungen an `services.py` dürfen
    nur mit grüner Testsuite committet werden:

    ```bash
    docker compose exec web python manage.py test nachweis
    ```

---

## (b) DB-Ebene: PostgreSQL Row-Level-Security (opt-in)

Row-Level-Security (RLS) verlagert die Team-Isolation zusätzlich in die Datenbank.
Sie wirkt auf der Tabelle **`nachweis_klient`** und wird über zwei Bausteine
realisiert: eine **Middleware**, die pro Request den Kontext setzt, und eine
**Policy**, welche die Zeilen filtert.

### Die Middleware `RLSKontext`

Datei `nachweis/middleware.py`. Sie ist in `config/settings.py` als vorletzte
Middleware eingehängt (nach der Authentifizierung und dem Audit-Log, damit
`request.user` bereits feststeht):

```python
MIDDLEWARE = [
    # ...
    'nachweis.middleware.RLSKontext',   # PostgreSQL Row-Level-Security-Kontext (opt-in)
    # ...
]
```

Pro Web-Request setzt sie zwei PostgreSQL-Session-Variablen:

| Session-Variable | Inhalt |
|------------------|--------|
| `app.team_ids` | kommaseparierte, sichtbare Team-IDs (aus `teams_fuer(user)`) |
| `app.bypass` | `'on'` für Superuser / Break-Glass, sonst `'off'` |

```python
class RLSKontext:
    def __call__(self, request):
        if connection.vendor != "postgresql":
            return self.get_response(request)          # SQLite: No-Op
        u = getattr(request, "user", None)
        teams, bypass = "", "off"
        if u is not None and u.is_authenticated:
            from . import services
            if u.is_superuser or _superuser_ohne_profil(u):
                bypass = "on"
            else:
                teams = ",".join(str(i) for i in services.teams_fuer(u).values_list("id", flat=True))
        try:
            with connection.cursor() as cur:
                cur.execute("SELECT set_config('app.team_ids', %s, false)", [teams])
                cur.execute("SELECT set_config('app.bypass', %s, false)", [bypass])
            return self.get_response(request)
        finally:
            try:
                with connection.cursor() as cur:
                    cur.execute("SELECT set_config('app.team_ids', '', false)")
                    cur.execute("SELECT set_config('app.bypass', 'off', false)")
            except Exception:
                pass
```

!!! note "Wichtige Eigenschaften"
    - **Auf SQLite ein No-Op:** Bei `connection.vendor != "postgresql"` gibt die
      Middleware sofort weiter. Lokale Entwicklung bleibt unverändert.
    - **Harmlos ohne Policy:** Solange RLS nicht scharf geschaltet ist, setzt die
      Middleware nur zwei ungenutzte Session-Variablen. Es passiert nichts.
    - **Sauberes Zurücksetzen:** Im `finally`-Block werden die Variablen wieder
      geleert, damit gepoolte Verbindungen keinen Kontext verschleppen.

### Die Policy `fegh_team_isolation`

Scharf geschaltet legt das Management-Command folgende Policy auf `nachweis_klient`
an. Sie erlaubt eine Zeile in **drei** Fällen:

```sql
CREATE POLICY fegh_team_isolation ON nachweis_klient
USING (
    current_setting('app.bypass', true) = 'on'
    OR current_setting('app.team_ids', true) IS NULL
    OR team_id::text = ANY(string_to_array(current_setting('app.team_ids', true), ','))
);
```

| Bedingung | Bedeutung |
|-----------|-----------|
| `app.bypass = 'on'` | Break-Glass-Superuser sieht alles |
| `app.team_ids IS NULL` | **kein** Kontext gesetzt → voller Zugriff |
| `team_id ∈ app.team_ids` | Zeile gehört zu einem sichtbaren Team |

!!! tip "Warum der NULL-Fall voller Zugriff bedeutet"
    Migrationen, `manage.py`-Commands und Seed-Skripte laufen **ohne** gesetzten
    Kontext (die Middleware greift nur bei Web-Requests). Ohne die NULL-Regel
    würden `migrate` und `seed` keine Zeilen sehen und fehlschlagen. Der zweite
    Parameter `true` in `current_setting(..., true)` liefert `NULL` statt eines
    Fehlers, wenn die Variable nicht existiert.

### `FORCE ROW LEVEL SECURITY`

Beim Aktivieren werden **beide** Schalter gesetzt:

```sql
ALTER TABLE nachweis_klient ENABLE ROW LEVEL SECURITY;
ALTER TABLE nachweis_klient FORCE  ROW LEVEL SECURITY;
```

!!! warning "FORCE ist entscheidend"
    Normalerweise ist der **Tabellen-Owner** (die Rolle, mit der die App verbindet)
    von RLS ausgenommen. Ohne `FORCE` liefe die Policy ins Leere, weil die
    Django-App genau mit dieser Owner-Rolle verbindet. `FORCE ROW LEVEL SECURITY`
    unterwirft auch den Owner der Policy.

---

## Scharfschalten / Ausschalten

Alles läuft über das Management-Command `rls_setup`
(`nachweis/management/commands/rls_setup.py`):

```bash
# Status anzeigen (ENABLE / FORCE Flags)
docker compose exec web python manage.py rls_setup

# RLS aktivieren – DB verweigert teamfremde Klient*innen-Zeilen
docker compose exec web python manage.py rls_setup --enable

# RLS deaktivieren – zurück auf reines App-Scoping
docker compose exec web python manage.py rls_setup --disable
```

Das Command ist **reversibel** und auf SQLite ein No-Op:

```python
if connection.vendor != "postgresql":
    self.stdout.write("RLS ist nur für PostgreSQL. Lokal (SQLite) gibt es nichts zu tun.")
    return
```

`--disable` entfernt Policy und beide RLS-Flags sauber:

```sql
DROP POLICY IF EXISTS fegh_team_isolation ON nachweis_klient;
ALTER TABLE nachweis_klient NO FORCE ROW LEVEL SECURITY;
ALTER TABLE nachweis_klient DISABLE ROW LEVEL SECURITY;
```

---

## Warum opt-in?

!!! note "Bewusst nicht standardmäßig aktiv"
    - **PostgreSQL-only:** RLS existiert in SQLite nicht. Lokal ist die Funktion
      nicht testbar, daher wäre ein Default-Enable irreführend.
    - **Reversibel:** Ein falsch gesetzter Kontext kann Nutzer*innen aussperren.
      `--disable` stellt in Sekunden den App-Scoping-Zustand wieder her.
    - **Erst auf Staging testen:** Vor dem Produktivbetrieb auf einer
      **Postgres-Staging-DB** verifizieren, nicht direkt live scharf schalten.

---

## Test-Anleitung (Postgres-Staging)

1. RLS aktivieren:

    ```bash
    docker compose exec web python manage.py rls_setup --enable
    ```

2. Je Rolle im Browser einloggen und die Klient*innen-Liste prüfen:

    | Login | Erwartete Sicht |
    |-------|-----------------|
    | `neumann` | nur Team **TBEW** |
    | `berger` | **TBEW + WG** (Leitung) |
    | `sander` | **keine** Klient*innen |
    | `peters` | **keine** Klient*innen |
    | Superuser | **alle** Klient*innen |

3. **Belegungsliste speichern** testen (Schreibpfad, nicht nur Lesen) – die Policy
   gilt auch für `INSERT`/`UPDATE`/`DELETE`.

4. Audit-Log und normale Nachweis-Ansichten stichprobenartig durchklicken.

!!! danger "Bei Problemen sofort abschalten"
    Sperrt RLS unerwartet Nutzer*innen aus oder scheitern Schreibvorgänge, sofort:

    ```bash
    docker compose exec web python manage.py rls_setup --disable
    ```

    Die App fällt damit auf das immer aktive App-Scoping zurück – ohne Datenverlust.

---

## Ausblick: weitere Tabellen

Aktuell schützt RLS nur `nachweis_klient` – die zentralen Art.-9-Stammdaten.
Abgeleitete Tabellen wie `Leistung`, `Gruppe` oder `Kasse` besitzen keine eigene
`team_id`, sondern hängen über einen Fremdschlüssel am Klienten. Sie ließen sich
per **Subquery-Policy** ergänzen, z. B.:

```sql
CREATE POLICY fegh_team_isolation ON nachweis_leistung
USING (
    current_setting('app.bypass', true) = 'on'
    OR current_setting('app.team_ids', true) IS NULL
    OR klient_id IN (
        SELECT id FROM nachweis_klient
        WHERE team_id::text = ANY(string_to_array(current_setting('app.team_ids', true), ','))
    )
);
```

!!! tip "Erweiterung vorbereitet"
    Da die Middleware `app.team_ids` und `app.bypass` bereits pro Request setzt,
    kostet die Ausweitung auf weitere Tabellen nur je eine zusätzliche Policy –
    kein neuer Anwendungscode. Vor Produktivnutzung gilt auch hier: erst auf
    Postgres-Staging testen.

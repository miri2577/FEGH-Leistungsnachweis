"""Row-Level-Security (PostgreSQL) für die Klient*innen-Tabelle scharf schalten.

Opt-in / reversibel:
    python manage.py rls_setup --enable     # DB verweigert teamfremde Klient*innen-Zeilen
    python manage.py rls_setup --disable    # zurück auf reines App-Scoping
    python manage.py rls_setup              # Status anzeigen

Die Policy nutzt die Session-Variablen, die RLSKontext (Middleware) pro Web-Request
setzt: app.team_ids (sichtbare Team-IDs) und app.bypass ('on' = Break-Glass-Superuser).
Ohne gesetzten Kontext (Migrationen/Management-Commands) ist der Zugriff voll –
so bleiben seed/migrate funktionsfähig. Nur PostgreSQL; auf SQLite ein No-Op.

Defense-in-Depth: schützt die Art.-9-Stammdaten (Klient*in) auf DB-Ebene selbst bei
einem App-Bug. Vor dem Produktivbetrieb auf einer Postgres-Staging-DB testen.
"""
from django.core.management.base import BaseCommand
from django.db import connection

TABELLE = "nachweis_klient"
POLICY = "fegh_team_isolation"


class Command(BaseCommand):
    help = "PostgreSQL Row-Level-Security für Klient*innen aktivieren/deaktivieren (opt-in)."

    def add_arguments(self, parser):
        g = parser.add_mutually_exclusive_group()
        g.add_argument("--enable", action="store_true", help="RLS-Policy anlegen und erzwingen")
        g.add_argument("--disable", action="store_true", help="RLS-Policy entfernen")

    def handle(self, *args, **opts):
        if connection.vendor != "postgresql":
            self.stdout.write("RLS ist nur für PostgreSQL. Lokal (SQLite) gibt es nichts zu tun.")
            return

        with connection.cursor() as cur:
            if opts["enable"]:
                cur.execute(f"ALTER TABLE {TABELLE} ENABLE ROW LEVEL SECURITY;")
                cur.execute(f"ALTER TABLE {TABELLE} FORCE ROW LEVEL SECURITY;")
                cur.execute(f"DROP POLICY IF EXISTS {POLICY} ON {TABELLE};")
                cur.execute(f"""
                    CREATE POLICY {POLICY} ON {TABELLE}
                    USING (
                        current_setting('app.bypass', true) = 'on'
                        OR current_setting('app.team_ids', true) IS NULL
                        OR team_id::text = ANY(string_to_array(current_setting('app.team_ids', true), ','))
                    );
                """)
                self.stdout.write(self.style.SUCCESS(f"RLS AKTIV auf {TABELLE} (Team-Isolation erzwungen)."))
            elif opts["disable"]:
                cur.execute(f"DROP POLICY IF EXISTS {POLICY} ON {TABELLE};")
                cur.execute(f"ALTER TABLE {TABELLE} NO FORCE ROW LEVEL SECURITY;")
                cur.execute(f"ALTER TABLE {TABELLE} DISABLE ROW LEVEL SECURITY;")
                self.stdout.write(self.style.WARNING(f"RLS DEAKTIVIERT auf {TABELLE} (nur noch App-Scoping)."))

            cur.execute("SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname=%s", [TABELLE])
            r = cur.fetchone()
            self.stdout.write(f"Status {TABELLE}: ENABLE={r[0]} FORCE={r[1]}")

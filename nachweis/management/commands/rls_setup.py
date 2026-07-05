"""Row-Level-Security (PostgreSQL) für die sensiblen Tabellen scharf schalten.

Opt-in / reversibel:
    python manage.py rls_setup --enable     # DB verweigert teamfremde Zeilen
    python manage.py rls_setup --disable    # zurück auf reines App-Scoping
    python manage.py rls_setup              # Status anzeigen

Die Policy nutzt die Session-Variablen, die RLSKontext (Middleware) pro Web-Request
setzt: app.team_ids (sichtbare Team-IDs) und app.bypass ('on' = Break-Glass-Superuser).
Ohne gesetzten Kontext (Migrationen/Management-Commands) ist der Zugriff voll –
so bleiben seed/migrate funktionsfähig. Nur PostgreSQL; auf SQLite ein No-Op.

Abgedeckt: Klient*innen-Stammdaten, Leistungen (inkl. Art.-9-Freitexte), Termine,
Gruppen sowie die gesamte Kassenführung. Jede Tabelle wird über ihren Team-Bezug
gefiltert (direkt per team_id oder über Klient*in/Mitarbeiter*in/Kasse).

Defense-in-Depth: schützt die Daten auf DB-Ebene selbst bei einem App-Bug.
Vor dem Produktivbetrieb auf einer Postgres-Staging-DB testen (ein normaler
User darf danach ausschließlich Zeilen des eigenen Teams sehen).
"""
from django.core.management.base import BaseCommand
from django.db import connection

POLICY = "fegh_team_isolation"

# Break-Glass-Superuser ODER kein Kontext (Migration/Seed) => voller Zugriff.
_BYPASS = ("current_setting('app.bypass', true) = 'on' "
           "OR current_setting('app.team_ids', true) IS NULL")


def _match(col):
    """Team-ID-Spalte gegen die sichtbaren Team-IDs des Requests prüfen."""
    return (f"{col}::text = ANY(string_to_array("
            "current_setting('app.team_ids', true), ','))")


# Tabelle -> USING-Prädikat: welche Zeilen zum Team-Kontext gehören.
# Der gemeinsame Bypass (_BYPASS) wird beim Anlegen vorangestellt.
TABELLEN = {
    "nachweis_klient": _match("team_id"),
    "nachweis_kasse":  _match("team_id"),
    "nachweis_leistung": (
        "EXISTS (SELECT 1 FROM nachweis_klient k "
        f"WHERE k.id = nachweis_leistung.klient_id AND {_match('k.team_id')})"),
    "nachweis_termin": (
        "EXISTS (SELECT 1 FROM nachweis_mitarbeiter m "
        f"WHERE m.id = nachweis_termin.mitarbeiter_id AND {_match('m.team_id')})"),
    "nachweis_gruppe": (
        "EXISTS (SELECT 1 FROM nachweis_gruppe_teilnehmer gt "
        "JOIN nachweis_klient k ON k.id = gt.klient_id "
        f"WHERE gt.gruppe_id = nachweis_gruppe.id AND {_match('k.team_id')})"),
    "nachweis_kassenmonat": (
        "EXISTS (SELECT 1 FROM nachweis_kasse k "
        f"WHERE k.id = nachweis_kassenmonat.kasse_id AND {_match('k.team_id')})"),
    "nachweis_kassenbuchung": (
        "EXISTS (SELECT 1 FROM nachweis_kassenmonat km "
        "JOIN nachweis_kasse k ON k.id = km.kasse_id "
        f"WHERE km.id = nachweis_kassenbuchung.monat_id AND {_match('k.team_id')})"),
    "nachweis_zaehlprotokoll": (
        "EXISTS (SELECT 1 FROM nachweis_kassenmonat km "
        "JOIN nachweis_kasse k ON k.id = km.kasse_id "
        f"WHERE km.id = nachweis_zaehlprotokoll.monat_id AND {_match('k.team_id')})"),
}


class Command(BaseCommand):
    help = "PostgreSQL Row-Level-Security für die sensiblen Tabellen aktivieren/deaktivieren (opt-in)."

    def add_arguments(self, parser):
        g = parser.add_mutually_exclusive_group()
        g.add_argument("--enable", action="store_true", help="RLS-Policies anlegen und erzwingen")
        g.add_argument("--disable", action="store_true", help="RLS-Policies entfernen")

    def handle(self, *args, **opts):
        if connection.vendor != "postgresql":
            self.stdout.write("RLS ist nur für PostgreSQL. Lokal (SQLite) gibt es nichts zu tun.")
            return

        with connection.cursor() as cur:
            for tabelle, using in TABELLEN.items():
                if opts["enable"]:
                    cur.execute(f"ALTER TABLE {tabelle} ENABLE ROW LEVEL SECURITY;")
                    cur.execute(f"ALTER TABLE {tabelle} FORCE ROW LEVEL SECURITY;")
                    cur.execute(f"DROP POLICY IF EXISTS {POLICY} ON {tabelle};")
                    cur.execute(
                        f"CREATE POLICY {POLICY} ON {tabelle} USING ({_BYPASS} OR {using});")
                elif opts["disable"]:
                    cur.execute(f"DROP POLICY IF EXISTS {POLICY} ON {tabelle};")
                    cur.execute(f"ALTER TABLE {tabelle} NO FORCE ROW LEVEL SECURITY;")
                    cur.execute(f"ALTER TABLE {tabelle} DISABLE ROW LEVEL SECURITY;")
                cur.execute("SELECT relrowsecurity, relforcerowsecurity "
                            "FROM pg_class WHERE relname=%s", [tabelle])
                r = cur.fetchone()
                self.stdout.write(f"{tabelle}: ENABLE={r[0]} FORCE={r[1]}")

        if opts["enable"]:
            self.stdout.write(self.style.SUCCESS(
                "RLS AKTIV – Team-Isolation auf allen genannten Tabellen erzwungen."))
        elif opts["disable"]:
            self.stdout.write(self.style.WARNING(
                "RLS DEAKTIVIERT – nur noch App-Scoping."))

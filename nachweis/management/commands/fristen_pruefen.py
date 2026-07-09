"""Prüft die Bewilligungs-/KÜ-Fristen aller Klient*innen in Betreuung (Slice 1b).

Listet Klient*innen, deren aktive Bewilligung in ≤ VORLAUF Tagen ausläuft, sowie
Klient*innen ganz ohne aktive Bewilligung (keine rechtssichere Kostenzusage).
Gedacht als täglicher Cron-Job – Grundlage für spätere Benachrichtigungen.

Aufruf:  python manage.py fristen_pruefen [--vorlauf-tage 70] [--team TBEW]
Exit-Code 0 = keine fehlenden Bewilligungen, 1 = mindestens eine fehlt (für Monitoring).
"""
from django.core.management.base import BaseCommand

from nachweis import services
from nachweis.models import Klient, Status


class Command(BaseCommand):
    help = "Prüft Bewilligungs-/KÜ-Fristen (auslaufend / fehlend)."

    def add_arguments(self, parser):
        parser.add_argument("--vorlauf-tage", type=int, default=70,
                            help="Vorlauf in Tagen für 'läuft bald aus' (Default 70 = 10 Wochen).")
        parser.add_argument("--team", type=str, default="",
                            help="nur ein Team (Name) prüfen.")

    def handle(self, *args, **opts):
        klienten = Klient.objects.filter(status=Status.BETREUUNG)
        if opts["team"]:
            klienten = klienten.filter(team__name=opts["team"])
        fristen = services.bewilligung_fristen(klienten, vorlauf_tage=opts["vorlauf_tage"])
        fehlt = [f for f in fristen if f["fehlt"]]
        auslauf = [f for f in fristen if not f["fehlt"]]

        if fehlt:
            self.stdout.write(self.style.ERROR(f"\n{len(fehlt)} Klient*in(nen) OHNE aktive Bewilligung:"))
            for f in fehlt:
                self.stdout.write(f"  • {f['klient'].name} (Team {f['klient'].team.name if f['klient'].team else '—'})")

        if auslauf:
            self.stdout.write(self.style.WARNING(
                f"\n{len(auslauf)} Bewilligung(en) laufen in <= {opts['vorlauf_tage']} Tagen aus:"))
            for f in auslauf:
                stand = (f"seit {abs(f['tage_bis'])} T abgelaufen" if f["tage_bis"] < 0
                         else f"in {f['tage_bis']} T")
                az = f" · Az {f['bewilligung'].aktenzeichen}" if f["bewilligung"].aktenzeichen else ""
                self.stdout.write(f"  • {f['klient'].name}: endet {f['gueltig_bis']:%d.%m.%Y} ({stand}){az}")

        if not fristen:
            self.stdout.write(self.style.SUCCESS("Keine auslaufenden oder fehlenden Bewilligungen."))
        else:
            self.stdout.write(f"\nSumme: {len(fehlt)} fehlend, {len(auslauf)} auslaufend "
                              f"(geprüft: {klienten.count()} in Betreuung).")

        if fehlt:
            raise SystemExit(1)

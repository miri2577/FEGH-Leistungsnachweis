"""Löschkonzept-Report + Anonymisierung per CLI (DSGVO Art. 5/17, § 84 SGB X).

Trockenlauf (Standard) listet beendete Betreuungen, deren Aufbewahrungsfrist
abgelaufen ist, samt der Aktionen, die eine Anonymisierung ausführen würde.
Erst --apply führt sie tatsächlich aus (mit --ja gegen versehentliche Läufe).

Aufruf:
  python manage.py loeschfristen                 # Report (nichts wird geändert)
  python manage.py loeschfristen --klient 42     # nur eine*n prüfen
  python manage.py loeschfristen --apply --ja    # fällige anonymisieren (echt!)
Exit-Code 0 = ok, 2 = fällige vorhanden (für Monitoring im Trockenlauf).
"""
from django.core.management.base import BaseCommand

from nachweis import services_loeschfristen as lf
from nachweis.models import Klient


class Command(BaseCommand):
    help = "Löschkonzept: fällige Betreuungen berichten / anonymisieren."

    def add_arguments(self, parser):
        parser.add_argument("--klient", type=int, default=0, help="nur diese Klient-ID.")
        parser.add_argument("--apply", action="store_true",
                            help="Anonymisierung wirklich ausführen (sonst Trockenlauf).")
        parser.add_argument("--ja", action="store_true",
                            help="Sicherheitsbestätigung für --apply.")

    def handle(self, *args, **opts):
        anwenden = opts["apply"] and opts["ja"]

        # Lesezugriffs-Protokoll (eigene kurze Frist) aufräumen – unabhängig von fälligen
        # Betreuungen, damit die Protokolldaten nicht unbegrenzt wachsen.
        if anwenden:
            n = lf.zugriffslog_aufraeumen()
            if n:
                self.stdout.write(self.style.SUCCESS(
                    f"{n} abgelaufene Zugriffsprotokoll-Eintrag/-Einträge gelöscht."))

        if opts["klient"]:
            k = Klient.objects.filter(pk=opts["klient"]).first()
            if not k:
                self.stderr.write("Klient*in nicht gefunden.")
                return
            faellige = [lf.loeschstatus(k)] if lf.loeschstatus(k)["fach_faellig"] else []
        else:
            faellige = lf.faellige_klienten()

        if not faellige:
            self.stdout.write(self.style.SUCCESS("Keine fälligen Betreuungen – nichts zu tun."))
            return

        if opts["apply"] and not opts["ja"]:
            self.stdout.write(self.style.WARNING(
                "--apply ohne --ja: Trockenlauf. Zum echten Ausführen zusätzlich --ja setzen."))

        self.stdout.write(f"\n{len(faellige)} fällige Betreuung(en):\n")
        for st in faellige:
            k = st["klient"]
            stufe = "voll" if st["voll_faellig"] else "fachdaten"
            report = lf.anonymisieren(k, stufe=stufe, apply=anwenden)
            kopf = self.style.ERROR(f"• {k.name}") if anwenden else f"• {k.name}"
            self.stdout.write(f"{kopf}  (Ende {st['betreuungsende']}, Stufe {stufe})")
            for a in report["aktionen"]:
                self.stdout.write(f"    {'✓' if anwenden else '–'} {a}")
            if not report["aktionen"]:
                self.stdout.write("    (keine Fachdaten mehr)")

        if anwenden:
            self.stdout.write(self.style.SUCCESS(f"\n{len(faellige)} Betreuung(en) anonymisiert."))
        else:
            self.stdout.write(self.style.WARNING(
                f"\nTrockenlauf – nichts geändert. Mit --apply --ja ausführen."))
            raise SystemExit(2)

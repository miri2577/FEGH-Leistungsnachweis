"""Befüllt die Datenbank mit FIKTIVEN Demodaten (Prototyp, kein Datenschutz-Bezug).

Aufruf:  python manage.py seed          (leert vorhandene Demodaten & befüllt neu)
         python manage.py seed --keep   (nur ergänzen, nichts löschen)

Struktur & Größenordnungen (AL/kLE pro Monat, HBG) sind der Excel nachempfunden,
alle Namen sind frei erfunden.
"""
import random
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

from nachweis.models import (Mitarbeiter, Klient, Leistung, Gruppe, Parameter,
                             Leistungsart, Rolle, Status)

JAHR = 2026
RNG = random.Random(42)

MA_NAMEN = [
    ("Berger", "Katrin", Rolle.TEAMLEITUNG),
    ("Neumann", "Stefan", Rolle.BETREUER),
    ("Schuster", "Melanie", Rolle.BETREUER),
    ("Kaiser", "Tobias", Rolle.BETREUER),
    ("Lorenz", "Sabine", Rolle.BETREUER),
    ("Hartmann", "David", Rolle.BETREUER),
    ("Wolf", "Nadja", Rolle.BETREUER),
]

# frei erfundene Klient-Namen
NACHNAMEN = ["Ackermann","Baumann","Brandt","Bergmann","Christ","Dietrich","Engel","Falk",
             "Förster","Gruber","Hausmann","Jacobi","Kettler","Lindner","Marquardt","Nowak",
             "Ostermann","Petersen","Quandt","Reinhardt","Sander","Thiele","Ulrich","Vogel",
             "Wegner","Zimmer","Adler","Bauer","Conradi","Denner","Ehlers","Fuchs","Görlitz"]
VORNAMEN = ["Alex","Bianca","Carsten","Diana","Erik","Frauke","Georg","Hanna","Ingo","Jana",
            "Kai","Lena","Marco","Nina","Olaf","Petra","Rico","Sina","Timo","Ute","Vera",
            "Willi","Yvonne","Zoe","Ben","Clara","Dennis","Elke","Falko","Gina","Heiko","Ida","Jonas"]

# HBG -> (AL/Monat, kLE/Monat) – nachempfundene Größenordnungen
HBG_WERTE = {
    1: (Decimal("8.815"), Decimal("8.5")),
    2: (Decimal("10.965"), Decimal("10.5")),
    3: (Decimal("15.05"), Decimal("14.5")),
    4: (Decimal("18.92"), Decimal("18.5")),
}

TAETIGKEITEN_FS = ["Hausbesuch", "direkte Betreuung", "Begleitung Amt", "Krisengespräch"]
TAETIGKEITEN_WFS = ["Verlaufsdokumentation", "Fallbesprechung", "Bericht an THFD"]


class Command(BaseCommand):
    help = "Befüllt die DB mit fiktiven Demodaten."

    def add_arguments(self, parser):
        parser.add_argument("--keep", action="store_true", help="vorhandene Daten nicht löschen")

    def handle(self, *args, **opts):
        if not opts["keep"]:
            for M in (Leistung, Gruppe, Klient, Mitarbeiter, Parameter):
                M.objects.all().delete()
            self.stdout.write("Vorhandene Demodaten gelöscht.")

        Parameter.objects.get_or_create(
            jahr=JAHR,
            defaults=dict(teamsitzung_wochentag=3, teamsitzung_dauer_std=Decimal("3.0")))

        mitarbeiter = []
        for nn, vn, rolle in MA_NAMEN:
            m = Mitarbeiter.objects.create(
                name=nn, vorname=vn, kuerzel=(nn[:3] + vn[:2]).lower(), rolle=rolle)
            mitarbeiter.append(m)
        betreuer = [m for m in mitarbeiter if m.rolle == Rolle.BETREUER]

        klienten = []
        for i in range(33):
            hbg = RNG.choice([1, 1, 2, 2, 2, 3, 3, 4])
            al, kle = HBG_WERTE[hbg]
            bez = betreuer[i % len(betreuer)]
            k = Klient.objects.create(
                nachname=NACHNAMEN[i % len(NACHNAMEN)],
                vorname=VORNAMEN[i % len(VORNAMEN)],
                geburtsdatum=date(RNG.randint(1965, 2002), RNG.randint(1, 12), RNG.randint(1, 28)),
                bezugsbetreuer=bez, al=al, kle=kle, hbg=hbg,
                status=Status.BEENDIGUNG if i in (7, 18, 30) else Status.BETREUUNG,
                person_id=f"BE-{100000 + i}",
            )
            klienten.append(k)

        # Leistungen: je Klient einige Einträge über Jan–Jun 2026
        n_leist = 0
        for k in klienten:
            if k.status == Status.BEENDIGUNG:
                continue
            for _ in range(RNG.randint(4, 8)):
                monat = RNG.randint(1, 6)
                tag = RNG.randint(1, 28)
                art = RNG.choices(
                    [Leistungsart.FS, Leistungsart.WFS, Leistungsart.FZ, Leistungsart.FUS],
                    weights=[6, 3, 2, 1])[0]
                beginn_h = RNG.randint(8, 15)
                dauer_min = RNG.choice([45, 60, 75, 90, 120])
                beginn = time(beginn_h, RNG.choice([0, 15, 30]))
                ende = (datetime(2000, 1, 1, beginn.hour, beginn.minute)
                        + timedelta(minutes=dauer_min)).time()
                if art == Leistungsart.FS:
                    taet = RNG.choice(TAETIGKEITEN_FS)
                elif art == Leistungsart.WFS:
                    taet = RNG.choice(TAETIGKEITEN_WFS)
                elif art == Leistungsart.FZ:
                    taet = "Fahrtzeit"
                else:
                    taet = "Büro"
                Leistung.objects.create(
                    datum=date(JAHR, monat, tag), klient=k, leistungsart=art,
                    taetigkeit=taet, betreuer=k.bezugsbetreuer, beginn=beginn, ende=ende)
                n_leist += 1

        # zwei Gruppen mit Teilnehmern
        aktive = [k for k in klienten if k.status == Status.BETREUUNG]
        g1 = Gruppe.objects.create(datum=date(JAHR, 5, 6), thema="Kochgruppe",
                                   leistungsart=Leistungsart.FS, beginn=time(10, 0), ende=time(12, 0),
                                   anz_ma=2)
        g1.teilnehmer.set(RNG.sample(aktive, 6))
        g2 = Gruppe.objects.create(datum=date(JAHR, 6, 3), thema="Freizeitgruppe",
                                   leistungsart=Leistungsart.FS, beginn=time(14, 0), ende=time(16, 30),
                                   anz_ma=1)
        g2.teilnehmer.set(RNG.sample(aktive, 5))

        # Demo-Superuser (nur Prototyp!)
        User = get_user_model()
        if not User.objects.filter(username="admin").exists():
            User.objects.create_superuser("admin", "admin@example.com", "admin")
            self.stdout.write(self.style.WARNING("Superuser angelegt: admin / admin (nur Demo!)"))

        self.stdout.write(self.style.SUCCESS(
            f"Fertig: {len(mitarbeiter)} Mitarbeiter, {len(klienten)} Klienten, "
            f"{n_leist} Leistungen, 2 Gruppen."))

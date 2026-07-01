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
                             Leistungsart, Rolle, Status, Team, Teamtyp, Arbeitszeit,
                             Abwesenheit, AbwesenheitArt, AbwesenheitStatus)

JAHR = 2026
RNG = random.Random(42)

# (Nachname, Vorname, Rolle, Team-Schlüssel)  – Teams: "TBEW", "WG", "VW" (Verwaltung)
MA_NAMEN = [
    ("Berger", "Katrin", Rolle.LEITUNG, "TBEW"),     # leitet TBEW + WG
    ("Neumann", "Stefan", Rolle.USER, "TBEW"),
    ("Schuster", "Melanie", Rolle.USER, "TBEW"),
    ("Kaiser", "Tobias", Rolle.USER, "TBEW"),
    ("Lorenz", "Sabine", Rolle.USER, "TBEW"),
    ("Hartmann", "David", Rolle.USER, "WG"),
    ("Wolf", "Nadja", Rolle.USER, "WG"),
    ("Sander", "Ulrike", Rolle.ADMIN, "VW"),          # Systemadministration (kein Klientenzugriff)
    ("Peters", "Frank", Rolle.USER, "VW"),            # Verwaltung (fester Arbeitsplatz)
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


def _gruppe(name, modelle):
    """Django-Gruppe mit allen Rechten (add/change/delete/view) auf die genannten Modelle."""
    from django.contrib.auth.models import Group, Permission
    g, _ = Group.objects.get_or_create(name=name)
    perms = Permission.objects.filter(content_type__app_label="nachweis",
                                      content_type__model__in=modelle)
    g.permissions.set(perms)
    return g


class Command(BaseCommand):
    help = "Befüllt die DB mit fiktiven Demodaten."

    def add_arguments(self, parser):
        parser.add_argument("--keep", action="store_true", help="vorhandene Daten nicht löschen")

    def handle(self, *args, **opts):
        if not opts["keep"]:
            for M in (Arbeitszeit, Abwesenheit, Leistung, Gruppe, Klient, Mitarbeiter, Team, Parameter):
                M.objects.all().delete()
            self.stdout.write("Vorhandene Demodaten gelöscht.")

        Parameter.objects.get_or_create(
            jahr=JAHR,
            defaults=dict(teamsitzung_wochentag=3, teamsitzung_dauer_std=Decimal("3.0")))

        # Teams
        team_tbew = Team.objects.create(name="TBEW", typ=Teamtyp.BEW)
        team_wg = Team.objects.create(name="WG Lindenhof", typ=Teamtyp.WG)
        team_vw = Team.objects.create(name="Verwaltung", typ=Teamtyp.VERWALTUNG)
        TEAMS = {"TBEW": team_tbew, "WG": team_wg, "VW": team_vw}

        # Django-Gruppen mit gezielten Rechten (DSGVO: Admin verwaltet Teams/MA, NICHT Klienten)
        gruppe_admin = _gruppe("Administration", ["team", "mitarbeiter"])
        gruppe_leitung = _gruppe("Leitung",
                                 ["klient", "gruppe", "parameter", "leistung", "abwesenheit"])

        User = get_user_model()
        mitarbeiter = []
        for nn, vn, rolle, tkey in MA_NAMEN:
            uname = nn.lower()
            user = User.objects.filter(username=uname).first()
            if not user:
                user = User.objects.create_user(uname, f"{uname}@example.com", "demo12345")
            user.first_name, user.last_name = vn, nn
            user.is_staff = rolle in (Rolle.LEITUNG, Rolle.ADMIN)   # dürfen in den Django-Admin
            user.is_superuser = False                               # kein Superuser (Rechte via Gruppe)
            user.save()
            user.groups.clear()
            if rolle == Rolle.ADMIN:
                user.groups.add(gruppe_admin)
            elif rolle == Rolle.LEITUNG:
                user.groups.add(gruppe_leitung)
            m = Mitarbeiter.objects.create(
                user=user, name=nn, vorname=vn, kuerzel=(nn[:3] + vn[:2]).lower(),
                rolle=rolle, team=TEAMS[tkey])
            mitarbeiter.append(m)

        # Break-Glass: technischer Superuser OHNE Mitarbeiter-Profil (Notzugang)
        if not User.objects.filter(username="root").exists():
            User.objects.create_superuser("root", "root@example.com", "root12345")

        # Berger leitet TBEW + WG
        berger = next(m for m in mitarbeiter if m.name == "Berger")
        berger.leitet.set([team_tbew, team_wg])

        betr_tbew = [m for m in mitarbeiter if m.team == team_tbew and m.rolle == Rolle.USER] or [berger]
        betr_wg = [m for m in mitarbeiter if m.team == team_wg and m.rolle == Rolle.USER] or betr_tbew

        heute = date.today()
        klienten = []
        cnt = {"tbew": 0, "wg": 0}
        for i in range(33):
            hbg = RNG.choice([1, 1, 2, 2, 2, 3, 3, 4])
            al, kle = HBG_WERTE[hbg]
            in_wg = (i % 4 == 0)
            team = team_wg if in_wg else team_tbew
            pool = betr_wg if in_wg else betr_tbew
            key = "wg" if in_wg else "tbew"
            bez = pool[cnt[key] % len(pool)]
            cnt[key] += 1
            kue = None
            if i % 5 == 0:
                kue = heute + timedelta(days=RNG.choice([25, 40, 55]))     # Bericht fällig (<10 Wochen)
            elif i % 5 == 1:
                kue = heute + timedelta(days=RNG.choice([120, 160, 200]))  # noch nicht fällig
            k = Klient.objects.create(
                nachname=NACHNAMEN[i % len(NACHNAMEN)],
                vorname=VORNAMEN[i % len(VORNAMEN)],
                geburtsdatum=date(RNG.randint(1965, 2002), RNG.randint(1, 12), RNG.randint(1, 28)),
                team=team, bezugsbetreuer=bez, al=al, kle=kle, hbg=hbg, kue_bis=kue,
                status=Status.BEENDIGUNG if i in (7, 18, 30) else Status.BETREUUNG,
                person_id=f"BE-{100000 + i}",
            )
            klienten.append(k)
        betreuer = [m for m in mitarbeiter if m.rolle == Rolle.USER and m.team != team_vw]

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

        # Teilzeit-Beispiel
        wolf = next((m for m in mitarbeiter if m.name == "Wolf"), None)
        if wolf:
            wolf.wochenstunden = Decimal("30.0"); wolf.save()

        # Arbeitszeiten für Juni 2026 (voller Monat), Juli bewusst leer -> "fehlende Nachweise"
        n_az = 0
        for m in mitarbeiter:
            soll_h = float(m.wochenstunden) / 5
            eo = 8 * 60 + int(round((soll_h + 0.5) * 60))     # Ende = 08:00 + Soll + 30 Min Pause
            ende = time(eo // 60, eo % 60)
            for tag in range(1, 31):
                d = date(JAHR, 6, tag)
                if d.weekday() < 5:
                    Arbeitszeit.objects.create(mitarbeiter=m, datum=d, beginn=time(8, 0),
                                               ende=ende, pause_min=30)
                    n_az += 1

        # Abwesenheiten: 1 genehmigt, 1 beantragt
        if len(betreuer) >= 2:
            Abwesenheit.objects.create(mitarbeiter=betreuer[0], art=AbwesenheitArt.URLAUB,
                                       von=date(JAHR, 5, 11), bis=date(JAHR, 5, 15),
                                       status=AbwesenheitStatus.GENEHMIGT, kommentar="Frühjahrsurlaub")
            Abwesenheit.objects.create(mitarbeiter=betreuer[1], art=AbwesenheitArt.URLAUB,
                                       von=date(JAHR, 7, 20), bis=date(JAHR, 7, 24),
                                       status=AbwesenheitStatus.BEANTRAGT, kommentar="Sommerurlaub")
            Abwesenheit.objects.create(mitarbeiter=betreuer[0], art=AbwesenheitArt.FREIZEITAUSGLEICH,
                                       von=date(JAHR, 6, 5), bis=date(JAHR, 6, 5),
                                       status=AbwesenheitStatus.GENEHMIGT)

        self.stdout.write(self.style.SUCCESS(
            f"Fertig: {len(mitarbeiter)} Mitarbeiter, {len(klienten)} Klienten, "
            f"{n_leist} Leistungen, 2 Gruppen, {n_az} Arbeitszeiten, 3 Abwesenheiten."))
        self.stdout.write("Demo-Logins (Passwort: demo12345):")
        for m in mitarbeiter:
            self.stdout.write(f"  {m.user.username:12s} · {m.get_rolle_display():18s} · "
                              f"Team {m.team.name if m.team else '-'} · {m.klienten.count()} eigene Klient*innen")

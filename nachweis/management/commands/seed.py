"""Befüllt die Datenbank mit FIKTIVEN Demodaten (Prototyp, kein Datenschutz-Bezug).

Aufruf:  python manage.py seed          (leert vorhandene Demodaten & befüllt neu)
         python manage.py seed --keep   (nur ergänzen, nichts löschen)

Struktur & Größenordnungen (AL/kLE pro Monat, HBG) sind der Excel nachempfunden,
alle Namen sind frei erfunden.
"""
import os
import random
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

from nachweis.models import (Mitarbeiter, Klient, Leistung, Gruppe, Parameter,
                             Leistungsart, Rolle, Status, Team, Teamtyp, Arbeitszeit,
                             Abwesenheit, AbwesenheitArt, AbwesenheitStatus, Stempelung,
                             Kasse, Kassenmonat, Kassenbuchung, Zaehlprotokoll, Termin)

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
        parser.add_argument("--leer", action="store_true",
                            help="Leerstart: Demodaten entfernen, KEINE anlegen (echter Produktivstart)")

    def handle(self, *args, **opts):
        if not opts["keep"]:
            for M in (Zaehlprotokoll, Kassenbuchung, Kassenmonat, Kasse, Termin,
                      Stempelung, Arbeitszeit, Abwesenheit, Leistung, Gruppe, Klient,
                      Mitarbeiter, Team, Parameter):
                M.objects.all().delete()
            # 2FA-Geräte zurücksetzen -> Demo-Logins bleiben ohne 2FA nutzbar (OTP_REQUIRED=0)
            try:
                from django_otp.plugins.otp_totp.models import TOTPDevice
                from django_otp.plugins.otp_static.models import StaticDevice
                TOTPDevice.objects.all().delete()
                StaticDevice.objects.all().delete()
            except Exception:
                pass
            # Alt-Superuser 'admin/admin' aus früheren Seeds entfernen (wird nicht mehr angelegt).
            get_user_model().objects.filter(username="admin", is_superuser=True).delete()
            self.stdout.write("Vorhandene Demodaten gelöscht.")

        Parameter.objects.get_or_create(
            jahr=JAHR,
            defaults=dict(teamsitzung_wochentag=3, teamsitzung_dauer_std=Decimal("3.0")))

        # Rechte-Gruppen sicherstellen (auch für den Leerstart nötig)
        from nachweis.accounts import ensure_gruppen
        ensure_gruppen()

        if opts.get("leer"):
            self.stdout.write(self.style.SUCCESS("Leerstart bereit – keine Demodaten angelegt."))
            self.stdout.write(
                "Nächste Schritte für den echten Produktivstart:\n"
                "  1) Superuser (Break-Glass) anlegen:  python manage.py createsuperuser\n"
                "  2) Einloggen -> Sidebar 'Teams' -> reale Teams anlegen (BEW/WG/Verwaltung)\n"
                "  3) 'Mitarbeiter-Verwaltung' -> Mitarbeiter anlegen; jede*r erhält einen\n"
                "     Aktivierungslink und vergibt das eigene Passwort selbst\n"
                "  4) Als Leitung -> 'Belegungsliste' -> Klient*innen anlegen")
            return

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
            user.is_staff = False        # KEIN Django-Admin für App-Rollen (Team-Scoping-Bypass vermeiden)
            user.is_superuser = False
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

        # Break-Glass: technischer Superuser OHNE Mitarbeiter-Profil (Notzugang).
        # Kein statisches Default-Passwort auf produktiven/öffentlichen Instanzen:
        # Passwort aus Env (DJANGO_SEED_ROOT_PASSWORD); nur im lokalen DEBUG-Modus als
        # Bequemlichkeit 'root12345'. Sonst gar nicht anlegen (dann via 'createsuperuser').
        root_pw = os.environ.get("DJANGO_SEED_ROOT_PASSWORD") or ("root12345" if settings.DEBUG else "")
        if root_pw:
            if not User.objects.filter(username="root").exists():
                User.objects.create_superuser("root", "root@example.com", root_pw)
                self.stdout.write(self.style.WARNING("Break-Glass-Superuser 'root' angelegt."))
        else:
            self.stdout.write("Kein DJANGO_SEED_ROOT_PASSWORD gesetzt und DEBUG=0 – "
                              "kein Seed-Superuser (bei Bedarf 'manage.py createsuperuser').")

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

        # Demo-Dokumentationen auf ein paar der jüngsten Leistungen (fürs Dashboard)
        DOKU_TEXTE = [
            "Hausbesuch: aktuelle Situation besprochen, Wohnung in gutem Zustand. "
            "Klient*in wirkt stabil; Termine für anstehende Amtsgänge vereinbart.",
            "Begleitung zum Fachdienst. Anliegen geklärt, Folgetermin notiert; "
            "Rückmeldung an die Bezugsbetreuung erfolgt.",
            "Krisengespräch nach Konflikt in der WG. Deeskalation gelungen, "
            "gemeinsame Vereinbarung getroffen; Beobachtung in der Folgewoche.",
            "Unterstützung bei der Antragstellung (Eingliederungshilfe). Unterlagen "
            "vollständig zusammengestellt, Versand vorbereitet.",
        ]
        for i, l in enumerate(Leistung.objects.exclude(auto=True).order_by("-datum", "-id")[:10]):
            l.dokumentation = DOKU_TEXTE[i % len(DOKU_TEXTE)]
            l.save(update_fields=["dokumentation"])

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

        # Demo: wiederkehrende Leistung (monatliche Fallsupervision, 2. Dienstag)
        from nachweis.models import WiederkehrendeLeistung, Rhythmus, Anrechnung
        WiederkehrendeLeistung.objects.get_or_create(
            bezeichnung="Fallsupervision",
            defaults=dict(leistungsart=Leistungsart.KLE, rhythmus=Rhythmus.MONATLICH,
                          wochentag=1, woche_im_monat=2, dauer_std=Decimal("1.5"),
                          anrechnung=Anrechnung.TEILER, feiertage_aussparen=True))

        # Demo-Termine im Wochenkalender (aktuelle Woche, damit die Ansicht gefüllt ist)
        montag = date.today() - timedelta(days=date.today().weekday())
        slots = [time(9, 0), time(10, 30), time(13, 0), time(14, 30)]
        for m in [x for x in mitarbeiter if x.rolle == Rolle.USER and x.team == team_tbew]:
            eigene = list(Klient.objects.filter(bezugsbetreuer=m, status=Status.BETREUUNG)[:3])
            for i, k in enumerate(eigene):
                beg = slots[i % len(slots)]
                Termin.objects.create(mitarbeiter=m, klient=k, ort="Klientenwohnung",
                                      datum=montag + timedelta(days=(i * 2) % 5),
                                      beginn=beg, ende=time(beg.hour + 1, beg.minute))
            Termin.objects.create(mitarbeiter=m, datum=montag + timedelta(days=3),
                                  beginn=time(9, 0), ende=time(10, 30), titel="Teamsitzung")

        # (Kein 'admin/admin'-Superuser mehr – Sicherheitsrisiko, siehe Break-Glass 'root' oben.)

        # Teilzeit-Beispiel
        wolf = next((m for m in mitarbeiter if m.name == "Wolf"), None)
        if wolf:
            wolf.wochenstunden = Decimal("30.0"); wolf.save()

        # Arbeitszeiten für Juni 2026 (voller Monat, bereits GENEHMIGT), Juli leer -> "fehlende Nachweise"
        from nachweis.models import Genehmigungsstatus
        n_az = 0
        for m in mitarbeiter:
            soll_h = float(m.wochenstunden) / 5
            eo = 8 * 60 + int(round((soll_h + 0.5) * 60))     # Ende = 08:00 + Soll + 30 Min Pause
            ende = time(eo // 60, eo % 60)
            for tag in range(1, 31):
                d = date(JAHR, 6, tag)
                if d.weekday() < 5:
                    Arbeitszeit.objects.create(mitarbeiter=m, datum=d, beginn=time(8, 0),
                                               ende=ende, pause_min=30,
                                               status=Genehmigungsstatus.GENEHMIGT)
                    n_az += 1
        # ein paar OFFENE Freigaben (Anfang Juli) für zwei TBEW-Mitarbeiter -> Leitung berger sieht sie
        for m in [x for x in mitarbeiter if x.name in ("Neumann", "Schuster")]:
            for tag in (1, 2, 3):
                d = date(JAHR, 7, tag)
                if d.weekday() < 5:
                    Arbeitszeit.objects.create(mitarbeiter=m, datum=d, beginn=time(8, 0),
                                               ende=time(16, 30), pause_min=30,
                                               status=Genehmigungsstatus.BEANTRAGT)
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

        # Stempelungen für Verwaltungs-MA (fester Arbeitsplatz): abgeschlossene Vortage
        # + heute offen "eingestempelt" (damit die Live-Uhr sichtbar tickt)
        from django.utils import timezone as _tz
        from datetime import datetime as _dt, time as _t
        peters = next((m for m in mitarbeiter if m.name == "Peters"), None)
        if peters:
            tz = _tz.get_current_timezone()
            for back in range(1, 4):
                d = date.today() - timedelta(days=back)
                if d.weekday() < 5:
                    b = _tz.make_aware(_dt.combine(d, _t(8, 30)), tz)
                    e = _tz.make_aware(_dt.combine(d, _t(16, 30)), tz)
                    Stempelung.objects.create(mitarbeiter=peters, beginn=b, ende=e)
            # heute offen eingestempelt seit 08:15
            b = _tz.make_aware(_dt.combine(date.today(), _t(8, 15)), tz)
            if b < _tz.localtime():
                Stempelung.objects.create(mitarbeiter=peters, beginn=b)

        # Demo-Kasse TBEW (Juni 2026) – aus der Excel-Vorlage Abrechnung0626.xlsx
        kasse = Kasse.objects.create(team=team_tbew, bezeichnung="Kassenbuch TBEW", kostenstelle="8300")
        km = Kassenmonat.objects.create(kasse=kasse, jahr=JAHR, monat=6, vortrag=Decimal("266.80"))
        # FIKTIVE Buchungen (nur erfundene Namen – keine echten Personendaten!)
        buchungen = [
            (1, 1, "Ausflug Fahrkarten", "0", "8.00", "5320310"),
            (2, 1, "Klient Baumann", "0", "8.49", "5170800"),
            (3, 1, "Klient Brandt", "0", "4.00", "5600000"),
            (4, 2, "Treffpunkt Lebensmittel", "0", "28.95", "5600000"),
            (5, 4, "Gruppe", "0", "15.37", "5600000"),
            (6, 4, "QZ/Teamsitzung", "0", "12.54", "5600000"),
            (7, 5, "Gruppe", "0", "28.96", "5600000"),
            (8, 10, "Klientin Engel", "0", "3.60", "5320310"),
            (9, 11, "Klient Gruber", "0", "8.30", "5170800"),
            (10, 12, "Gruppe", "0", "24.44", "5600000"),
            (11, 16, "Treffpunkt Küche", "0", "21.70", ""),
            (12, 17, "Klient Falk", "0", "5.40", ""),
            (13, 17, "TBEW Briefmarken", "0", "55.00", ""),
            (14, 29, "Kasseneinlage", "500.00", "0", ""),
        ]
        for nr, tag, text, ein, aus, konto in buchungen:
            Kassenbuchung.objects.create(
                monat=km, bel_nr=nr, datum=date(JAHR, 6, tag), text=text,
                einnahme=Decimal(ein), ausgabe=Decimal(aus),
                buchungsdatum=date(JAHR, 6, 30), kontonr=konto, kostenstelle="8300")
        # Zählprotokoll (Bargeld 542,05 = Buchbestand -> Differenz 0)
        Zaehlprotokoll.objects.create(monat=km, datum=date(JAHR, 6, 30),
                                      n50=1, n20=18, n10=13, m2=1, m005=1)

        self.stdout.write(self.style.SUCCESS(
            f"Fertig: {len(mitarbeiter)} Mitarbeiter, {len(klienten)} Klienten, "
            f"{n_leist} Leistungen, 2 Gruppen, {n_az} Arbeitszeiten, 3 Abwesenheiten, "
            f"1 Kasse ({km.buchungen.count()} Buchungen, Endbestand {km.endbestand})."))
        self.stdout.write("Demo-Logins (Passwort: demo12345):")
        for m in mitarbeiter:
            self.stdout.write(f"  {m.user.username:12s} · {m.get_rolle_display():18s} · "
                              f"Team {m.team.name if m.team else '-'} · {m.klienten.count()} eigene Klient*innen")

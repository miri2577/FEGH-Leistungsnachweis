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
                             Kasse, Kassenmonat, Kassenbuchung, Zaehlprotokoll, Termin,
                             Monatsfreigabe, Rechnung, Vorkommnis, Angebot)

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

# Senats-Systematik (Beschluss 3/2026): bewilligte individuelle FLS PRO WOCHE je HBG
# (Demo-Werte, gerundet); AL/Monat = FLS/Woche × 4,3482 (365,25/7/12).
# kLE ist EINHEITLICH je Klient*in und Kalendertag (HBG-unabhängig).
FLS_WOCHE_HBG = {
    1: Decimal("2.089"), 2: Decimal("2.950"), 3: Decimal("3.810"), 4: Decimal("4.686"),
    5: Decimal("5.546"), 6: Decimal("6.406"), 7: Decimal("7.267"), 8: Decimal("8.127"),
    9: Decimal("9.003"), 10: Decimal("9.863"), 11: Decimal("10.738"), 12: Decimal("11.599"),
}
WOCHEN_JE_MONAT = Decimal("365.25") / 7 / 12          # 4.348214…
KLE_JE_TAG = Decimal("0.722")                          # Demo (Senats-Tool Output 3.)
KLE_MONAT = (KLE_JE_TAG * (Decimal("365.25") / 12)).quantize(Decimal("0.001"))
# HBG -> (AL/Monat, kLE/Monat) für die Demo-Klient*innen
HBG_WERTE = {h: ((w * WOCHEN_JE_MONAT).quantize(Decimal("0.001")), KLE_MONAT)
             for h, w in FLS_WOCHE_HBG.items()}

TAETIGKEITEN_FS = ["Hausbesuch", "direkte Betreuung", "Begleitung Amt", "Krisengespräch"]
TAETIGKEITEN_WFS = ["Verlaufsdokumentation", "Fallbesprechung", "Bericht an THFD"]

# frei erfundene Kostenträger (Rechnungsempfänger für die Abrechnung)
BEZIRKE = ["Bezirksamt Mitte von Berlin", "Bezirksamt Pankow von Berlin",
           "Bezirksamt Neukölln von Berlin", "Bezirksamt Charlottenburg-Wilmersdorf"]


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
            # Monatsfreigabe/Rechnung zuerst (Monatsfreigabe.klient ist PROTECT).
            # Klient VOR Angebot (Belegung.angebot ist PROTECT, hängt aber an Klient-CASCADE);
            # Vorkommnis/Angebot VOR Team (team ist PROTECT). Klientenkonto/FEM/Kontaktperson/
            # Belegung/Ziel/Bericht kaskadieren mit dem Klienten.
            for M in (Monatsfreigabe, Rechnung, Zaehlprotokoll, Kassenbuchung, Kassenmonat,
                      Kasse, Termin, Stempelung, Arbeitszeit, Abwesenheit, Leistung, Gruppe,
                      Klient, Vorkommnis, Angebot, Mitarbeiter, Team, Parameter):
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
            # Demo-LOGINS mit bekanntem Passwort entfernen (nur die Seed-Benutzernamen,
            # niemals Superuser oder real angelegte Konten) – wichtig für den Leerstart!
            demo_namen = [nn.lower() for nn, _v, _r, _t in MA_NAMEN]
            geloescht, _ = (get_user_model().objects
                            .filter(username__in=demo_namen, is_superuser=False).delete())
            self.stdout.write(f"Vorhandene Demodaten gelöscht (inkl. {geloescht} Demo-Login(s)).")

        p, _ = Parameter.objects.get_or_create(
            jahr=JAHR,
            defaults=dict(teamsitzung_wochentag=3, teamsitzung_dauer_std=Decimal("3.0"),
                          fls_preis=Decimal("45.46"), kle_je_tag=KLE_JE_TAG))
        # HBG-Tabelle (individuelle FLS/Woche, Senats-Tool Output 5. – Demo-Werte)
        from nachweis.models import HBGSatz
        for h, w in FLS_WOCHE_HBG.items():
            HBGSatz.objects.get_or_create(parameter=p, hbg=h, defaults={"fls_woche": w})

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
            # kue_bis (KÜ-Ende / Bericht-Frist) wird jetzt aus der aktiven Bewilligung
            # gezogen (sync_cache_aus_bewilligung); al/kle bleiben als Fallback-Kontingent.
            k = Klient.objects.create(
                nachname=NACHNAMEN[i % len(NACHNAMEN)],
                vorname=VORNAMEN[i % len(VORNAMEN)],
                geburtsdatum=date(RNG.randint(1965, 2002), RNG.randint(1, 12), RNG.randint(1, 28)),
                team=team, bezugsbetreuer=bez, al=al, kle=kle, hbg=hbg,
                status=Status.BEENDIGUNG if i in (7, 18, 30) else Status.BETREUUNG,
                person_id=f"BE-{100000 + i}",
                kostentraeger=BEZIRKE[i % len(BEZIRKE)],
            )
            klienten.append(k)
        betreuer = [m for m in mitarbeiter if m.rolle == Rolle.USER and m.team != team_vw]

        # ---- Kostenträger (Bezirksämter) FRÜH anlegen: Bewilligungen & Rechnungen
        # brauchen sie als FK (E-Mail/Leitweg-ID → XRechnung/Mail, Debitorenkonto → DATEV).
        from nachweis.models import Kostentraeger, KostentraegerTyp
        kt_by_name = {}
        for idx_kt, name in enumerate(dict.fromkeys(BEZIRKE)):
            slug = name.split()[-1].lower().replace("ö", "oe").replace("ü", "ue")
            kt, _ = Kostentraeger.objects.get_or_create(name=name, defaults={
                "typ": KostentraegerTyp.BEZIRKSAMT,
                "email": f"leistungsabrechnung@{slug}.berlin.example",
                "leitweg_id": f"11-{RNG.randint(1000, 9999)}-{RNG.randint(10, 99)}",
                "debitorenkonto": str(10001 + idx_kt),
                "adresse": f"{name}\nMusterstr. 1\n10000 Berlin"})
            kt_by_name[name] = kt

        # ---- Bewilligungen als FÜHRENDES Abrechnungsobjekt (behebt die FLS-„ohne
        # Bewilligung"-Flut). Die allermeisten laufen lange; nur wenige laufen bald aus,
        # sind abgelaufen oder fehlen ganz (frischer Zugang) → Fristen-Panel realistisch.
        from nachweis.models import Bewilligung, BewilligungStatus
        SOON = {2, 9, 14, 21, 27}      # Bewilligung läuft in < 10 Wochen aus (Bericht fällig)
        EXPIRED = {5, 24}              # abgelaufen → Verlängerung nötig (keine aktive Bewilligung)
        OHNE = {11}                    # frischer Zugang, Bewilligung noch nicht erteilt
        n_bew = 0
        for i, k in enumerate(klienten):
            if i in OHNE:
                continue
            von = heute - timedelta(days=RNG.choice([180, 240, 300, 360, 420]))
            if i in (7, 18, 30):                    # BEENDIGUNG: historisch, KÜ ausgelaufen
                bis, st = heute - timedelta(days=RNG.choice([25, 55, 90])), BewilligungStatus.ABGELAUFEN
            elif i in SOON:
                bis, st = heute + timedelta(days=RNG.choice([25, 40, 55, 65])), BewilligungStatus.AKTIV
            elif i in EXPIRED:
                bis, st = heute - timedelta(days=RNG.choice([8, 20, 35])), BewilligungStatus.AKTIV
            else:
                bis, st = heute + timedelta(days=RNG.choice([250, 320, 400, 480, 540])), BewilligungStatus.AKTIV
            Bewilligung.objects.create(
                klient=k, kostentraeger=kt_by_name.get(k.kostentraeger),
                aktenzeichen=k.person_id, hbg=k.hbg, status=st,
                gueltig_von=von, gueltig_bis=bis,
                fls_woche=FLS_WOCHE_HBG[k.hbg], kle_tag=KLE_JE_TAG)   # save() → sync_cache_aus_bewilligung
            n_bew += 1

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

        # Demo: wiederkehrende Leistung (monatliche Fallsupervision, 2. Dienstag).
        # Handreichung Beschluss 3/2026, Nr. 2.3: FALLsupervision ist eine weitere
        # fallspezifische Leistung (WFS) – Teamsupervision wäre fallunspezifisch (kLE).
        from nachweis.models import WiederkehrendeLeistung, Rhythmus, Anrechnung
        WiederkehrendeLeistung.objects.get_or_create(
            bezeichnung="Fallsupervision",
            defaults=dict(leistungsart=Leistungsart.WFS, rhythmus=Rhythmus.MONATLICH,
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
        # Zuständigkeit: nur Verantwortliche*r + Vertretung (+ Leitung/Verwaltung) sehen die Kasse
        _neumann = next((m for m in mitarbeiter if m.name == "Neumann"), None)
        _schuster = next((m for m in mitarbeiter if m.name == "Schuster"), None)
        kasse = Kasse.objects.create(team=team_tbew, bezeichnung="Kassenbuch TBEW", kostenstelle="8300",
                                     verantwortlich=_neumann, vertretung=_schuster)
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

        # Demo-Abrechnung (Juni 2026): Monatsfreigaben in verschiedenen Zuständen + eine Rechnung.
        from nachweis.models import Freigabestatus
        from nachweis import services as _svc
        from django.utils import timezone as _tz2
        MONAT_ABR = 6
        jetzt = _tz2.now()
        aktive_tbew = [k for k in klienten if k.status == Status.BETREUUNG and k.team == team_tbew]
        muster = ([Freigabestatus.OFFEN] * 3 + [Freigabestatus.EINGEREICHT] * 3
                  + [Freigabestatus.FREIGEGEBEN] * 4)
        freigegeben = []
        for k, st in zip(aktive_tbew, muster):
            fls = _svc.druck_nachweis(k, JAHR, MONAT_ABR)["fls_summe"]
            betrag = _svc.betrag_fuer(fls, JAHR)
            mf = Monatsfreigabe.objects.create(
                klient=k, jahr=JAHR, monat=MONAT_ABR, status=st,
                fls_summe=(fls if st != Freigabestatus.OFFEN else Decimal("0")),
                betrag=(betrag if st != Freigabestatus.OFFEN else Decimal("0")))
            if st in (Freigabestatus.EINGEREICHT, Freigabestatus.FREIGEGEBEN):
                mf.eingereicht_am, mf.eingereicht_von = jetzt, k.bezugsbetreuer
            if st == Freigabestatus.FREIGEGEBEN:
                mf.freigegeben_am, mf.freigegeben_von = jetzt, berger
                freigegeben.append(mf)
            mf.save()
        n_rech = 0
        if len(freigegeben) >= 2:
            _svc.rechnung_erstellen(
                freigegeben[:2], freigegeben[0].klient.kostentraeger or BEZIRKE[0],
                JAHR, MONAT_ABR, date(JAHR, 7, 1), berger, notiz="Sammelrechnung (Demo)")
            n_rech = 1

        # ---- Rechnungssteller-Stammsatz (E-Rechnung/DATEV, FREI ERFUNDEN – kein realer Träger) ----
        from nachweis.models import (Rechnungsstatus, Rechnungssteller, Zahlung,
                                     Mahnung, Mahnstufe)
        rs = Rechnungssteller.load()
        rs.name = "Sozialträger Musterwerk gGmbH (Demo)"
        rs.strasse, rs.plz, rs.ort = "Demoallee 12", "10115", "Berlin"
        rs.ust_id = "DE123456789"
        rs.iban, rs.bic, rs.bank = "DE02120300000000202051", "BYLADEM1001", "Demo-Bank Berlin"
        rs.kontakt_name, rs.kontakt_mail = "Buchhaltung (Demo)", "buchhaltung@example.org"
        rs.datev_berater, rs.datev_mandant, rs.datev_erloeskonto = "1234567", "10001", "8125"
        rs.save()

        # ---- Voller Jahres-Rechnungslauf Jan–Mai 2026 (Verwaltungs-Demo) ----
        # Pro Monat je Kostenträger EINE Sammelrechnung; danach realistische Zustände:
        # bezahlt / teilbezahlt / offen (camt-Abgleich) / überfällig+Mahnung / storniert+Gutschrift.
        erf = peters or berger
        aktive_alle = [k for k in klienten if k.status == Status.BETREUUNG]
        hist_rechnungen = []
        for monat in range(1, 6):
            for k in aktive_alle:
                fls_i = k.al or Decimal("0")
                Monatsfreigabe.objects.create(
                    klient=k, jahr=JAHR, monat=monat, status=Freigabestatus.FREIGEGEBEN,
                    fls_summe=fls_i, kle_summe=k.kle, betrag=_svc.betrag_fuer(fls_i, JAHR, k.kle),
                    eingereicht_am=jetzt, eingereicht_von=k.bezugsbetreuer,
                    freigegeben_am=jetzt, freigegeben_von=berger)
            neu, _ohne = _svc.rechnungslauf(JAHR, monat, date(JAHR, monat + 1, 1), berger)
            hist_rechnungen.extend(neu)
        # Historien-Rechnungen sind gestellt (Rechnungslauf legt sie als Entwurf an)
        Rechnung.objects.filter(id__in=[r.id for r in hist_rechnungen]).update(
            status=Rechnungsstatus.GESTELLT)
        for r in hist_rechnungen:
            r.status = Rechnungsstatus.GESTELLT

        n_zahlung = n_mahnung = n_gut = 0
        gutschrift_gesetzt = False
        for idx, r in enumerate(sorted(hist_rechnungen, key=lambda x: (x.monat, x.nummer))):
            rest = idx % 10
            if rest == 0 and r.monat <= 2:                       # alt & unbezahlt → überfällig + Mahnung
                Mahnung.objects.create(rechnung=r, stufe=Mahnstufe.ERINNERUNG,
                                       datum=r.faelligkeit + timedelta(days=7), erstellt_von=erf)
                n_mahnung += 1
                if r.monat == 1:
                    Mahnung.objects.create(rechnung=r, stufe=Mahnstufe.MAHNUNG_1,
                                           datum=r.faelligkeit + timedelta(days=28), erstellt_von=erf)
                    n_mahnung += 1
            elif rest == 1 and r.monat >= 4:                     # jung & offen → für camt-Abgleich
                pass
            elif rest == 2 and r.monat >= 4 and not gutschrift_gesetzt:
                _g, _err = _svc.gutschrift_erstellen(r, erf)     # storniert + Gutschrift
                if _g:
                    gutschrift_gesetzt = True
                    n_gut += 1
            elif rest == 3:                                      # teilbezahlt
                Zahlung.objects.create(rechnung=r, datum=r.datum + timedelta(days=18),
                                       betrag=(r.betrag * Decimal("0.6")).quantize(Decimal("0.01")),
                                       erfasst_von=erf, notiz="Teilzahlung (Demo)")
                n_zahlung += 1
            else:                                                # voll bezahlt
                Zahlung.objects.create(rechnung=r, datum=r.datum + timedelta(days=RNG.choice([12, 18, 25])),
                                       betrag=r.betrag, erfasst_von=erf, notiz="Zahlungseingang (camt.053)")
                n_zahlung += 1

        # ================= Reichhaltige Demodaten (Fach-/Stationär-Module, alle FIKTIV) =========
        from nachweis.models import (Kostentraeger, KostentraegerTyp, AngebotsTyp, Erreichbarkeit,
                                     Zimmer, Belegung, VorkommnisKategorie, VorkommnisStatus,
                                     Qualifikation, QualifikationArt, Kontaktperson, KontaktRolle,
                                     Klientenkonto, KlientenkontoTyp, Kontobuchung, FEM, FEMArt,
                                     Ziel, ZielArt, ZielStatus)
        from django.utils import timezone as _tz3

        # (Kostenträger werden bereits oben angelegt – siehe kt_by_name.)

        # Anschrift + gesetzliche Betreuung bei einigen Klient*innen
        strassen = ["Lindenweg", "Ahornstr.", "Seestr.", "Parkallee", "Buchenweg", "Amselgasse"]
        for i, k in enumerate(klienten[:14]):
            k.strasse = f"{RNG.choice(strassen)} {RNG.randint(1, 80)}"
            k.plz, k.ort = f"1{RNG.randint(0, 4)}{RNG.randint(100, 999)}", "Berlin"
            if i % 3 == 0:
                k.betreuung_name = f"Betreuungsverein {RNG.choice(['Mitte', 'Nord', 'Süd'])} e. V."
                k.betreuung_telefon = f"030-{RNG.randint(200000, 999999)}"
                k.betreuung_umfang = RNG.choice(["Vermögens- und Gesundheitssorge",
                                                 "Aufenthaltsbestimmung, Behördenangelegenheiten"])
                k.betreuung_bis = heute + timedelta(days=RNG.choice([40, 120, 300]))
            k.save()

        wg_klienten = [k for k in klienten if k.team == team_wg and k.status == Status.BETREUUNG]

        # Wohnform (stationär) mit Zimmern + Belegungen
        angebot = Angebot.objects.create(
            name="Wohnform Lindenhof", team=team_wg, typ=AngebotsTyp.BESONDERE_WOHNFORM,
            erreichbarkeit=Erreichbarkeit.TAG_NACHT, plaetze=8, adresse="Lindenhof 5, 12000 Berlin")
        zimmer = [Zimmer.objects.create(angebot=angebot, name=nr, plaetze=pl, etage=et)
                  for nr, pl, et in [("101", 1, "EG"), ("102", 2, "EG"), ("103", 1, "1. OG"),
                                     ("104", 1, "1. OG"), ("105", 2, "1. OG")]]
        for idx, k in enumerate(wg_klienten):
            Belegung.objects.create(klient=k, angebot=angebot, zimmer=zimmer[idx % len(zimmer)],
                                    einzug=heute - timedelta(days=RNG.randint(60, 600)))

        # Vorkommnisse: eines meldepflichtig OFFEN (Dashboard/Nav rot), eines abgeschlossen
        if wg_klienten:
            Vorkommnis.objects.create(
                datum=heute - timedelta(days=1), kategorie=VorkommnisKategorie.GEWALT,
                team=team_wg, klient=wg_klienten[0], erstellt_von=betr_wg[0],
                beschreibung="Verbaler Konflikt zwischen zwei Bewohner*innen im Gemeinschaftsraum.",
                sofortmassnahmen="Personen getrennt, Einzelgespräche geführt.")
        Vorkommnis.objects.create(
            datum=heute - timedelta(days=20), kategorie=VorkommnisKategorie.UNFALL,
            team=team_tbew, klient=klienten[1], erstellt_von=betr_tbew[0],
            beschreibung="Sturz im Bad, keine Verletzung.", status=VorkommnisStatus.ABGESCHLOSSEN,
            gemeldet_am=heute - timedelta(days=19), gemeldet_an="WTG-Aufsicht",
            massnahmen="Rutschmatte angebracht, Betreuung sensibilisiert.",
            abgeschlossen_am=heute - timedelta(days=15), abgeschlossen_von=berger)

        # Qualifikationen (eine läuft bald ab -> Fällig-Panel)
        n_qual = 0
        for m in [m for m in mitarbeiter if m.rolle == Rolle.USER and m.team != team_vw][:5]:
            Qualifikation.objects.create(mitarbeiter=m, art=QualifikationArt.QUALIFIKATION,
                                         bezeichnung="Staatl. anerk. Heilerziehungspfleger*in",
                                         erworben_am=date(2015, 6, 30))
            Qualifikation.objects.create(mitarbeiter=m, art=QualifikationArt.FORTBILDUNG, pflicht=True,
                                         bezeichnung="Erste-Hilfe-Auffrischung",
                                         gueltig_bis=heute + timedelta(days=RNG.choice([15, 25, 400])))
            n_qual += 2

        # Kontaktpersonen bei einigen Klient*innen
        for k in klienten[:8]:
            Kontaktperson.objects.create(klient=k, rolle=KontaktRolle.ANGEHOERIGE,
                                         name=f"{RNG.choice(VORNAMEN)} {k.nachname}",
                                         funktion=RNG.choice(["Mutter", "Bruder", "Tochter", "Vater"]),
                                         telefon=f"030-{RNG.randint(100000, 999999)}", notfall=True)
            Kontaktperson.objects.create(klient=k, rolle=KontaktRolle.ARZT,
                                         name=f"Dr. {RNG.choice(NACHNAMEN)}", funktion="Hausärztliche Praxis",
                                         telefon=f"030-{RNG.randint(100000, 999999)}")

        # Barbetragskonten mit Buchungen (positiver Saldo)
        for k in wg_klienten[:4]:
            konto = Klientenkonto.objects.create(klient=k, typ=KlientenkontoTyp.BARBETRAG)
            Kontobuchung.objects.create(konto=konto, datum=heute - timedelta(days=30),
                                        betrag=Decimal("125.00"), zweck="Barbetrag Monat",
                                        beleg_nr=f"B{RNG.randint(100, 999)}", erfasst_von=betr_wg[0])
            for _ in range(RNG.randint(2, 4)):
                Kontobuchung.objects.create(konto=konto, datum=heute - timedelta(days=RNG.randint(1, 25)),
                                            betrag=Decimal(str(RNG.choice([-5, -8, -12, -20]))),
                                            zweck=RNG.choice(["Kiosk", "Friseur", "Ausflug", "Hygieneartikel"]),
                                            erfasst_von=betr_wg[0])

        # FEM: eine laufend (Genehmigung läuft bald ab -> Warnung), eine beendet
        if wg_klienten:
            FEM.objects.create(klient=wg_klienten[0], art=FEMArt.BETTGITTER,
                               beginn=_tz3.now() - timedelta(days=10), grund="Erhebliche Sturzgefahr nachts.",
                               angeordnet_von="Dr. Vogel / gesetzl. Betreuung", genehmigung_az="XVII 123/26",
                               genehmigt_bis=heute + timedelta(days=20), einwilligung=True,
                               gemeldet_am=heute - timedelta(days=9), erfasst_von=betr_wg[0])
            if len(wg_klienten) > 1:
                FEM.objects.create(klient=wg_klienten[1], art=FEMArt.TUER,
                                   beginn=_tz3.now() - timedelta(days=40), ende=_tz3.now() - timedelta(days=30),
                                   grund="Weglauftendenz mit Selbstgefährdung.", genehmigung_az="XVII 90/26",
                                   erfasst_von=betr_wg[0])

        # Teilhabe: ein paar Ziele je aktiver Klient*in (Teilhabe-Reiter)
        ZIELE = ["Eigenständige Haushaltsführung stärken", "Tagesstruktur stabilisieren",
                 "Soziale Kontakte aufbauen", "Umgang mit Ämtern selbständig bewältigen",
                 "Medikamenteneinnahme eigenverantwortlich"]
        n_ziel = 0
        for k in [k for k in klienten if k.status == Status.BETREUUNG][:12]:
            for titel in RNG.sample(ZIELE, RNG.randint(1, 3)):
                Ziel.objects.create(klient=k, art=RNG.choice([ZielArt.HANDLUNGSZIEL, ZielArt.RICHTUNGSZIEL]),
                                    titel=titel, status=ZielStatus.AKTIV)
                n_ziel += 1

        self.stdout.write(self.style.SUCCESS(
            f"Stationär/QM-Demo: {Kostentraeger.objects.count()} Kostenträger, "
            f"1 Wohnform ({len(zimmer)} Zimmer, {len(wg_klienten)} Belegungen), "
            f"{Vorkommnis.objects.count()} Vorkommnisse, {n_qual} Qualifikationen, "
            f"{Kontaktperson.objects.count()} Kontakte, {Klientenkonto.objects.count()} Barbetragskonten, "
            f"{FEM.objects.count()} FEM, {n_ziel} Ziele."))

        from nachweis.models import Rechnung as _R
        self.stdout.write(self.style.SUCCESS(
            f"Abrechnung/Verwaltung: {n_bew} Bewilligungen, {_R.objects.count()} Rechnungen "
            f"(Jahreslauf Jan–Mai + Juni), {n_zahlung} Zahlungen, {n_mahnung} Mahnungen, "
            f"{n_gut} Gutschrift(en), Rechnungssteller-Stammsatz gesetzt."))
        self.stdout.write(self.style.SUCCESS(
            f"Fertig: {len(mitarbeiter)} Mitarbeiter, {len(klienten)} Klienten, "
            f"{n_leist} Leistungen, 2 Gruppen, {n_az} Arbeitszeiten, 3 Abwesenheiten, "
            f"1 Kasse ({km.buchungen.count()} Buchungen, Endbestand {km.endbestand}), "
            f"{len(muster)} Monatsfreigaben (Demo 06.2026), {n_rech} Juni-Rechnung."))
        self.stdout.write("Demo-Logins (Passwort: demo12345):")
        for m in mitarbeiter:
            self.stdout.write(f"  {m.user.username:12s} · {m.get_rolle_display():18s} · "
                              f"Team {m.team.name if m.team else '-'} · {m.klienten.count()} eigene Klient*innen")

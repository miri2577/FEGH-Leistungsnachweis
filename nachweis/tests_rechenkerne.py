"""Regressionstests fuer die abrechnungsrelevanten Rechenkerne.

Sichern genau die Zahlen ab, fuer die die App existiert: Dauer-/Mitternachts-
Logik, Gruppen-Teiler, Teamsitzung mit Berliner Feiertagen, ISO-Wochen,
Wochenauslastung (AL/KLE), amtlicher Druck-Nachweis, Kassenbestand und
Zaehlprotokoll-Differenz. Ergaenzen die Team-Isolationstests (tests.py).
"""
from datetime import date, time
from decimal import Decimal

from django.test import TestCase

from nachweis import services
from nachweis.models import (
    Team, Teamtyp, Mitarbeiter, Klient, Status, Leistung, Leistungsart, Gruppe,
    Arbeitszeit, Kasse, Kassenmonat, Kassenbuchung, Zaehlprotokoll, Parameter,
    WiederkehrendeLeistung, Rhythmus, Anrechnung, _stunden,
)


class DauerLogikTests(TestCase):
    """_stunden / dauer_stunden inkl. Mitternacht, Rundung, Leerfaelle."""

    def test_normale_dauer(self):
        self.assertEqual(_stunden(time(9, 0), time(11, 30)), Decimal("2.5"))

    def test_ueber_mitternacht(self):
        # Nacht-/Bereitschaftsdienst 22:00–06:00 = 8 h (Ende am Folgetag)
        self.assertEqual(_stunden(time(22, 0), time(6, 0)), Decimal("8"))

    def test_gleiche_zeit_null(self):
        self.assertEqual(_stunden(time(10, 0), time(10, 0)), Decimal("0"))

    def test_fehlende_zeit_null(self):
        self.assertEqual(_stunden(time(9, 0), None), Decimal("0"))
        self.assertEqual(_stunden(None, None), Decimal("0"))

    def test_rundung_half_up(self):
        # 20 Minuten = 0.3333… -> auf 3 Nachkommastellen 0.333
        self.assertEqual(_stunden(time(9, 0), time(9, 20)), Decimal("0.333"))

    def test_arbeitszeit_netto_mit_pause(self):
        az = Arbeitszeit(beginn=time(8, 0), ende=time(16, 0), pause_min=30)
        self.assertEqual(az.dauer_stunden, Decimal("7.5"))

    def test_arbeitszeit_pause_groesser_brutto_null(self):
        az = Arbeitszeit(beginn=time(9, 0), ende=time(9, 10), pause_min=60)
        self.assertEqual(az.dauer_stunden, Decimal("0"))


class GruppeTeilerTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="TBEW")
        self.ma = Mitarbeiter.objects.create(name="Betreuer", team=self.team)
        self.k1 = Klient.objects.create(nachname="A", bezugsbetreuer=self.ma, team=self.team)
        self.k2 = Klient.objects.create(nachname="B", bezugsbetreuer=self.ma, team=self.team)

    def _gruppe(self, anz_ma=1, teilnehmer=()):
        g = Gruppe.objects.create(datum=date(2026, 3, 10), thema="G",
                                  leistungsart=Leistungsart.FS,
                                  beginn=time(10, 0), ende=time(12, 0), anz_ma=anz_ma)
        for k in teilnehmer:
            g.teilnehmer.add(k)
        return g

    def test_zeit_pro_klient_2h_2teiln_1ma(self):
        g = self._gruppe(anz_ma=1, teilnehmer=(self.k1, self.k2))
        self.assertEqual(g.zeit_pro_klient, Decimal("1"))     # 2h / 2 / 1

    def test_zeit_pro_klient_2h_2teiln_2ma(self):
        g = self._gruppe(anz_ma=2, teilnehmer=(self.k1, self.k2))
        self.assertEqual(g.zeit_pro_klient, Decimal("0.5"))   # 2h / 2 / 2

    def test_zeit_pro_klient_ohne_teilnehmer_null(self):
        g = self._gruppe(anz_ma=1, teilnehmer=())
        self.assertEqual(g.zeit_pro_klient, Decimal("0"))

    def test_gruppen_anteile_fls_und_kle(self):
        self._gruppe(anz_ma=1, teilnehmer=(self.k1, self.k2))   # FS -> zaehlt als FLS
        anteile = services.gruppen_anteile(2026)
        self.assertEqual(anteile[self.k1.id]["gesamt"], Decimal("1"))
        self.assertEqual(anteile[self.k1.id]["fls"], Decimal("1"))
        self.assertEqual(anteile[self.k1.id]["kle"], Decimal("0"))


class KlientKennzahlenTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="TBEW")
        self.ma = Mitarbeiter.objects.create(name="Betreuer", team=self.team)

    def test_fls_gesamt_und_kle_anteil(self):
        k = Klient.objects.create(nachname="A", bezugsbetreuer=self.ma,
                                  al=Decimal("10"), kle=Decimal("5"))
        self.assertEqual(k.fls_gesamt, Decimal("15"))
        self.assertEqual(k.fls_gesamt_jahr, Decimal("180"))
        self.assertEqual(k.kle_anteil, Decimal("0.333"))

    def test_kle_anteil_null_bei_leerem_kontingent(self):
        k = Klient.objects.create(nachname="B", bezugsbetreuer=self.ma,
                                  al=Decimal("0"), kle=Decimal("0"))
        self.assertEqual(k.kle_anteil, Decimal("0"))


class TeamsitzungFeiertageTests(TestCase):
    def test_donnerstage_ohne_feiertage(self):
        tage = services.teamsitzungstage(2026)          # Default Donnerstag
        self.assertTrue(all(d.weekday() == 3 for d in tage))
        self.assertTrue(50 <= len(tage) <= 53)
        # Christi Himmelfahrt 2026 (14.05.) ist ein Donnerstag UND Berliner Feiertag
        himmelfahrt = date(2026, 5, 14)
        self.assertEqual(himmelfahrt.weekday(), 3)
        self.assertIn(himmelfahrt, services.berliner_feiertage(2026))
        self.assertNotIn(himmelfahrt, tage)             # -> nicht als Sitzungstag

    def test_werktage_schliesst_feiertag_aus(self):
        # Mo 11.05. – Fr 15.05.2026: 5 Werktage, aber Do 14.05. ist Feiertag -> 4
        self.assertEqual(services.werktage(date(2026, 5, 11), date(2026, 5, 15)), 4)

    def test_werktage_ende_vor_beginn_null(self):
        self.assertEqual(services.werktage(date(2026, 5, 15), date(2026, 5, 11)), 0)


class IsoWochenTests(TestCase):
    def test_wochenbereich_montag_sonntag(self):
        mo, so = services.iso_wochenbereich(2026, 10)
        self.assertEqual(mo.weekday(), 0)               # Montag
        self.assertEqual(so.weekday(), 6)               # Sonntag
        self.assertEqual((so - mo).days, 6)

    def test_kw53_fallback_in_52_wochen_jahr(self):
        # 2026 hat 53 ISO-Wochen? Test robust: nicht existierende KW faellt auf KW1 zurueck
        mo, _ = services.iso_wochenbereich(2026, 99)
        self.assertEqual(mo, date.fromisocalendar(2026, 1, 1))


class WochenauslastungTests(TestCase):
    def setUp(self):
        # Teamsitzung neutralisieren (Dauer 0), damit AL/KLE isoliert pruefbar sind
        Parameter.objects.create(jahr=2026, teamsitzung_dauer_std=Decimal("0"))
        self.team = Team.objects.create(name="TBEW")
        self.ma = Mitarbeiter.objects.create(name="Betreuer", team=self.team)
        self.k = Klient.objects.create(nachname="A", bezugsbetreuer=self.ma, team=self.team,
                                       al=Decimal("52"), kle=Decimal("0"),
                                       status=Status.BETREUUNG)

    def test_al_ist_und_soll(self):
        mo, _ = services.iso_wochenbereich(2026, 10)
        Leistung.objects.create(datum=mo, klient=self.k, leistungsart=Leistungsart.FS,
                                betreuer=self.ma, beginn=time(10, 0), ende=time(12, 0))
        res = services.wochenauslastung(Klient.objects.filter(pk=self.k.pk), 2026, 10)
        zeile = res["zeilen"][self.k.id]
        self.assertEqual(zeile["al"], Decimal("2"))             # 2h FS -> AL
        self.assertEqual(zeile["kle"], Decimal("0"))
        self.assertEqual(zeile["soll_al"], Decimal("11.959"))   # 52 × 12/52,1786 (365,25/7 Wochen/Jahr)
        self.assertEqual(zeile["soll_kle"], Decimal("0"))

    def test_kle_leistung_zaehlt_als_kle(self):
        mo, _ = services.iso_wochenbereich(2026, 10)
        Leistung.objects.create(datum=mo, klient=self.k, leistungsart=Leistungsart.KLE,
                                betreuer=self.ma, beginn=time(10, 0), ende=time(11, 0))
        res = services.wochenauslastung(Klient.objects.filter(pk=self.k.pk), 2026, 10)
        zeile = res["zeilen"][self.k.id]
        self.assertEqual(zeile["kle"], Decimal("1"))
        self.assertEqual(zeile["al"], Decimal("0"))


class DruckUndFlsTests(TestCase):
    def setUp(self):
        Parameter.objects.create(jahr=2026, teamsitzung_dauer_std=Decimal("0"))
        self.team = Team.objects.create(name="TBEW")
        self.ma = Mitarbeiter.objects.create(name="Betreuer", team=self.team)
        self.k = Klient.objects.create(nachname="A", bezugsbetreuer=self.ma, team=self.team,
                                       al=Decimal("10"), kle=Decimal("0"))
        Leistung.objects.create(datum=date(2026, 3, 10), klient=self.k,
                                leistungsart=Leistungsart.FS, betreuer=self.ma,
                                beginn=time(10, 0), ende=time(12, 0))     # 2h FLS
        Leistung.objects.create(datum=date(2026, 3, 10), klient=self.k,
                                leistungsart=Leistungsart.FZ, betreuer=self.ma,
                                beginn=time(12, 0), ende=time(13, 0))     # 1h, keine FLS

    def test_druck_nachweis_fls_summe(self):
        d = services.druck_nachweis(self.k, 2026, 3)
        self.assertEqual(d["fls_summe"], Decimal("2"))    # nur FS/WFS/BAO
        self.assertEqual(d["gesamt"], Decimal("3"))       # alle Arten

    def test_fachleistungsstunden_ist_und_rest(self):
        zeilen, _summe = services.fachleistungsstunden(2026, Klient.objects.filter(pk=self.k.pk))
        z = zeilen[0]
        self.assertEqual(z["kontingent_monat"], Decimal("10"))    # AL-Soll/Monat (Feld al)
        self.assertEqual(z["kontingent_jahr"], Decimal("120"))
        self.assertEqual(z["ist"], Decimal("2"))          # nur AL (FS); FZ zählt NICHT zur AL
        self.assertEqual(z["rest"], Decimal("118"))


class ZeitreiheSerienKonsistenzTests(TestCase):
    """P2: auslastung_zeitreihe zählt FLS-Serien mit -> Chart == Tabelle (Dashboard konsistent)."""
    def setUp(self):
        Parameter.objects.create(jahr=2026, teamsitzung_dauer_std=Decimal("0"))
        self.team = Team.objects.create(name="TBEW")
        self.ma = Mitarbeiter.objects.create(name="B", team=self.team, kuerzel="b")
        self.k = Klient.objects.create(nachname="A", bezugsbetreuer=self.ma, team=self.team,
                                       al=Decimal("10"), kle=Decimal("0"), status=Status.BETREUUNG)
        WiederkehrendeLeistung.objects.create(
            bezeichnung="Fallsupervision", leistungsart=Leistungsart.WFS,
            rhythmus=Rhythmus.WOECHENTLICH, wochentag=1, dauer_std=Decimal("1.0"),
            anrechnung=Anrechnung.FEST, wert_pro_klient=Decimal("1.0"), feiertage_aussparen=False)

    def test_chart_gleich_tabelle(self):
        qs = Klient.objects.filter(pk=self.k.pk)
        _z, summe = services.fachleistungsstunden(2026, qs)
        zr = services.auslastung_zeitreihe(2026, qs)
        self.assertGreater(float(summe["ist"]), 0)                # Serie zählt in der Tabelle
        self.assertAlmostEqual(float(summe["ist"]), zr["jahr"]["ist"], places=1)   # Chart == Tabelle


class KasseTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="TBEW")
        self.kasse = Kasse.objects.create(team=self.team)
        self.monat = Kassenmonat.objects.create(kasse=self.kasse, jahr=2026, monat=3,
                                                vortrag=Decimal("100"))

    def test_endbestand_und_summen(self):
        Kassenbuchung.objects.create(monat=self.monat, bel_nr=1, datum=date(2026, 3, 2),
                                     text="Einnahme", einnahme=Decimal("50"))
        Kassenbuchung.objects.create(monat=self.monat, bel_nr=2, datum=date(2026, 3, 5),
                                     text="Ausgabe", ausgabe=Decimal("20"))
        self.assertEqual(self.monat.einnahmen, Decimal("50"))
        self.assertEqual(self.monat.ausgaben, Decimal("20"))
        self.assertEqual(self.monat.endbestand, Decimal("130"))   # 100 + 50 - 20

    def test_naechste_bel_nr(self):
        self.assertEqual(self.monat.naechste_bel_nr(), 1)
        Kassenbuchung.objects.create(monat=self.monat, bel_nr=1, datum=date(2026, 3, 2),
                                     text="x", einnahme=Decimal("1"))
        Kassenbuchung.objects.create(monat=self.monat, bel_nr=2, datum=date(2026, 3, 3),
                                     text="y", einnahme=Decimal("1"))
        self.assertEqual(self.monat.naechste_bel_nr(), 3)

    def test_zaehlprotokoll_bargeld_gesamt(self):
        z = Zaehlprotokoll.objects.create(monat=self.monat, n100=1, n50=2, n5=1, m1=3,
                                          m050=2, m001=5)
        # 100 + 2*50 + 5 + 3*1 + 2*0.50 + 5*0.01 = 209.05
        self.assertEqual(z.bargeld_gesamt, Decimal("209.05"))

    def test_zaehlprotokoll_differenz_null_bei_uebereinstimmung(self):
        # Buchbestand: 200 + 9.05 - 0 = 209.05 ; Bargeld: 200 + 5 + 4 + 0.05 = 209.05
        self.monat.vortrag = Decimal("200")
        self.monat.save(update_fields=["vortrag"])
        Kassenbuchung.objects.create(monat=self.monat, bel_nr=1, datum=date(2026, 3, 2),
                                     text="Einnahme", einnahme=Decimal("9.05"))
        z = Zaehlprotokoll.objects.create(monat=self.monat, n100=2, n5=1, m2=2, m001=5)
        self.assertEqual(z.neuer_bestand, Decimal("209.05"))
        self.assertEqual(z.bargeld_gesamt, Decimal("209.05"))
        self.assertEqual(z.differenz, Decimal("0"))


class SerienterminTests(TestCase):
    """Wiederkehrende Leistungen: Termin-Berechnung je Rhythmus."""

    def _wl(self, **kw):
        kw.setdefault("bezeichnung", "S")
        kw.setdefault("feiertage_aussparen", False)
        return WiederkehrendeLeistung(**kw)

    def test_woechentlich_donnerstag(self):
        wl = self._wl(rhythmus=Rhythmus.WOECHENTLICH, wochentag=3)
        from nachweis import services
        d = services.serientermine(wl, date(2026, 5, 1), date(2026, 5, 31))
        self.assertEqual(d, [date(2026, 5, 7), date(2026, 5, 14), date(2026, 5, 21), date(2026, 5, 28)])

    def test_feiertage_aussparen(self):
        wl = self._wl(rhythmus=Rhythmus.WOECHENTLICH, wochentag=3, feiertage_aussparen=True)
        from nachweis import services
        d = services.serientermine(wl, date(2026, 5, 1), date(2026, 5, 31))
        self.assertNotIn(date(2026, 5, 14), d)              # Christi Himmelfahrt
        self.assertIn(date(2026, 5, 7), d)

    def test_zweiwoechentlich(self):
        wl = self._wl(rhythmus=Rhythmus.ZWEIWOECHENTLICH, wochentag=3, gilt_ab=date(2026, 5, 7))
        from nachweis import services
        d = services.serientermine(wl, date(2026, 5, 1), date(2026, 6, 30))
        self.assertEqual(d, [date(2026, 5, 7), date(2026, 5, 21), date(2026, 6, 4), date(2026, 6, 18)])

    def test_monatlich_nter_wochentag(self):
        wl = self._wl(rhythmus=Rhythmus.MONATLICH, wochentag=3, woche_im_monat=1)   # 1. Donnerstag
        from nachweis import services
        d = services.serientermine(wl, date(2026, 5, 1), date(2026, 7, 31))
        self.assertEqual(d, [date(2026, 5, 7), date(2026, 6, 4), date(2026, 7, 2)])

    def test_monatlich_fester_tag(self):
        wl = self._wl(rhythmus=Rhythmus.MONATLICH, tag_im_monat=15)
        from nachweis import services
        d = services.serientermine(wl, date(2026, 5, 1), date(2026, 7, 31))
        self.assertEqual(d, [date(2026, 5, 15), date(2026, 6, 15), date(2026, 7, 15)])

    def test_vierteljaehrlich(self):
        wl = self._wl(rhythmus=Rhythmus.VIERTELJAEHRLICH, monat_im_jahr=1, tag_im_monat=1)
        from nachweis import services
        d = services.serientermine(wl, date(2026, 1, 1), date(2026, 12, 31))
        self.assertEqual(d, [date(2026, 1, 1), date(2026, 4, 1), date(2026, 7, 1), date(2026, 10, 1)])

    def test_jaehrlich(self):
        wl = self._wl(rhythmus=Rhythmus.JAEHRLICH, monat_im_jahr=6, tag_im_monat=1)
        from nachweis import services
        d = services.serientermine(wl, date(2026, 1, 1), date(2026, 12, 31))
        self.assertEqual(d, [date(2026, 6, 1)])


class SerienBeitragTests(TestCase):
    """Anrechnung je Klient*in + Integration in Druck-Nachweis."""

    def setUp(self):
        Parameter.objects.create(jahr=2026, teamsitzung_dauer_std=Decimal("0"))  # Teamsitzung neutral
        self.team = Team.objects.create(name="TBEW")
        self.ma = Mitarbeiter.objects.create(name="B", team=self.team)
        self.k1 = Klient.objects.create(nachname="A", bezugsbetreuer=self.ma, team=self.team,
                                        al=Decimal("10"), status=Status.BETREUUNG)
        self.k2 = Klient.objects.create(nachname="B", bezugsbetreuer=self.ma, team=self.team,
                                        status=Status.BETREUUNG)

    def test_teiler_geteilt_durch_klienten(self):
        from nachweis import services
        WiederkehrendeLeistung.objects.create(
            bezeichnung="Teamsitzung 2", rhythmus=Rhythmus.WOECHENTLICH, wochentag=3,
            dauer_std=Decimal("4"), anrechnung=Anrechnung.TEILER, feiertage_aussparen=False)
        sb = services.serien_beitraege(self.k1, date(2026, 5, 4), date(2026, 5, 10))  # 1 Do (07.05.)
        self.assertEqual(len(sb), 1)
        self.assertEqual(sb[0]["stunden"], Decimal("2"))       # 4 h ÷ 2 Klient*innen
        self.assertEqual(sb[0]["leistungsart"], Leistungsart.KLE)

    def test_fester_wert_je_klient(self):
        from nachweis import services
        WiederkehrendeLeistung.objects.create(
            bezeichnung="Supervision", rhythmus=Rhythmus.MONATLICH, tag_im_monat=10,
            anrechnung=Anrechnung.FEST, wert_pro_klient=Decimal("0.5"), feiertage_aussparen=False)
        sb = services.serien_beitraege(self.k1, date(2026, 5, 1), date(2026, 5, 31))
        self.assertEqual(len(sb), 1)
        self.assertEqual(sb[0]["stunden"], Decimal("0.5"))     # fest, unabhängig von Anzahl

    def test_nur_kalender_faellt_aus_nachweis(self):
        from nachweis import services
        WiederkehrendeLeistung.objects.create(
            bezeichnung="Info", rhythmus=Rhythmus.WOECHENTLICH, wochentag=3,
            anrechnung=Anrechnung.KALENDER, feiertage_aussparen=False)
        self.assertEqual(services.serien_beitraege(self.k1, date(2026, 5, 1), date(2026, 5, 31)), [])

    def test_beendete_erhalten_keinen_anteil(self):
        from nachweis import services
        self.k1.status = Status.BEENDIGUNG
        self.k1.save(update_fields=["status"])
        WiederkehrendeLeistung.objects.create(
            bezeichnung="X", rhythmus=Rhythmus.WOECHENTLICH, wochentag=3,
            dauer_std=Decimal("2"), feiertage_aussparen=False)
        self.assertEqual(services.serien_beitraege(self.k1, date(2026, 5, 1), date(2026, 5, 31)), [])

    def test_team_scoping(self):
        from nachweis import services
        anderes = Team.objects.create(name="WG")
        WiederkehrendeLeistung.objects.create(
            bezeichnung="Nur WG", team=anderes, rhythmus=Rhythmus.WOECHENTLICH, wochentag=3,
            dauer_std=Decimal("2"), feiertage_aussparen=False)
        self.assertEqual(services.serien_beitraege(self.k1, date(2026, 5, 1), date(2026, 5, 31)), [])

    def test_druck_nachweis_enthaelt_serie(self):
        from nachweis import services
        WiederkehrendeLeistung.objects.create(
            bezeichnung="Supervision", leistungsart=Leistungsart.KLE, rhythmus=Rhythmus.MONATLICH,
            tag_im_monat=10, anrechnung=Anrechnung.FEST, wert_pro_klient=Decimal("0.5"),
            feiertage_aussparen=False)
        d = services.druck_nachweis(self.k1, 2026, 5)
        treffer = [e for e in d["eintraege"] if e["bezeichnung"] == "Supervision"]
        self.assertEqual(len(treffer), 1)
        self.assertEqual(treffer[0]["datum"], date(2026, 5, 10))
        self.assertEqual(treffer[0]["stunden"], Decimal("0.5"))

"""Tests für den Abrechnungs-Workflow (Freigabe MA→Leitung→Verwaltung) + Rechnungen.

Sichert die Rechte-Kette und die DSGVO-Trennung (Verwaltung ohne Klientenzugriff)
sowie die Betragsberechnung (FLS × FLS-Preis) und Storno (Positionen wieder frei).
"""
import json
from datetime import date, time
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, Client, override_settings
from django.contrib.auth import get_user_model

LOCMEM = "django.core.mail.backends.locmem.EmailBackend"

from . import services
from .models import (Team, Teamtyp, Mitarbeiter, Klient, Rolle, Status, Leistung,
                     Leistungsart, Parameter, Monatsfreigabe, Rechnung, Freigabestatus,
                     Gruppe, Rechnungsstatus)

User = get_user_model()


class AbrechnungTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.team_a = Team.objects.create(name="A", typ=Teamtyp.BEW)
        cls.team_b = Team.objects.create(name="B", typ=Teamtyp.BEW)
        cls.team_vw = Team.objects.create(name="VW", typ=Teamtyp.VERWALTUNG)
        Parameter.objects.create(jahr=2026, fls_preis=Decimal("50"))

        def ma(u, team, rolle, leitet=None):
            usr = User.objects.create_user(u, password="pw")
            m = Mitarbeiter.objects.create(user=usr, name=u.title(), rolle=rolle, team=team)
            if leitet:
                m.leitet.set(leitet)
            return usr, m

        cls.uA, cls.mA = ma("ada", cls.team_a, Rolle.USER)
        cls.uL, cls.mL = ma("lea", cls.team_a, Rolle.LEITUNG, [cls.team_a])
        cls.uV, cls.mV = ma("val", cls.team_vw, Rolle.USER)     # Team Verwaltung
        cls.uB, cls.mB = ma("ben", cls.team_b, Rolle.USER)
        cls.kA = Klient.objects.create(nachname="Alpha", team=cls.team_a, bezugsbetreuer=cls.mA,
                                       status=Status.BETREUUNG, kostentraeger="Bezirksamt X",
                                       person_id="AZ-1")
        Leistung.objects.create(datum=date(2026, 6, 10), klient=cls.kA,
                                leistungsart=Leistungsart.FS, betreuer=cls.mA,
                                beginn=time(10, 0), ende=time(12, 0))   # 2 h FS

    def cl(self, u):
        c = Client()
        c.force_login(u)
        return c

    def _aktion(self, u, klient, aktion, **extra):
        d = {"klient": klient.id, "jahr": 2026, "monat": 6, "aktion": aktion}
        d.update(extra)
        return self.cl(u).post("/abrechnung/aktion/", d)

    # --- Rechenkern -----------------------------------------------------
    def test_betrag_berechnung(self):
        self.assertEqual(services.betrag_fuer(Decimal("2"), 2026), Decimal("100.00"))

    def test_betrag_mit_kle_pauschale(self):
        # Senats-Systematik: Betrag = (FLS + kLE) × FLS-Satz
        self.assertEqual(services.betrag_fuer(Decimal("2"), 2026, Decimal("15")),
                         Decimal("850.00"))

    def test_kle_monat_stunden(self):
        p = Parameter.objects.get(jahr=2026)
        p.kle_je_tag = Decimal("0.5")
        p.save()
        # Juni 2026 hat 30 Kalendertage -> 15,0 Std kLE-Pauschale
        self.assertEqual(services.kle_monat_stunden(2026, 6), Decimal("15.000"))
        # tagesgenau bei unterjährigem Austritt: KÜ endet am 3.6. -> nur 3 Tage
        self.assertEqual(services.kle_monat_stunden(2026, 6, bis=date(2026, 6, 3)), Decimal("1.500"))
        # tagesgenau bei Einzug am 25.6. -> 25..30 = 6 Tage
        self.assertEqual(services.kle_monat_stunden(2026, 6, von=date(2026, 6, 25)), Decimal("3.000"))

    def test_snapshot_enthaelt_kle_und_beendete_ohne(self):
        p = Parameter.objects.get(jahr=2026)
        p.kle_je_tag = Decimal("0.5")
        p.save()
        self._aktion(self.uA, self.kA, "fertig")          # 2h FS dokumentiert
        mf = Monatsfreigabe.objects.get(klient=self.kA, jahr=2026, monat=6)
        self.assertEqual(mf.fls_summe, Decimal("2.000"))
        self.assertEqual(mf.kle_summe, Decimal("15.000")) # 0,5 × 30 Tage
        self.assertEqual(mf.betrag, Decimal("850.00"))    # (2+15) × 50 €
        # Beendete Klient*innen erhalten keine kLE-Pauschale
        self.kA.status = Status.BEENDIGUNG
        self.kA.save(update_fields=["status"])
        mf.status = "offen"
        mf.save()
        self._aktion(self.uA, self.kA, "fertig")
        mf.refresh_from_db()
        self.assertEqual(mf.kle_summe, Decimal("0"))

    def test_rechnungsnummer_fortlaufend(self):
        self.assertEqual(services.naechste_rechnungsnummer(2026), "2026-0001")

    # --- Workflow / Rechte ---------------------------------------------
    def test_workflow_ma_meldet_fertig_leitung_gibt_frei(self):
        self._aktion(self.uA, self.kA, "fertig")
        mf = Monatsfreigabe.objects.get(klient=self.kA, jahr=2026, monat=6)
        self.assertEqual(mf.status, Freigabestatus.EINGEREICHT)
        self.assertEqual(mf.fls_summe, Decimal("2.000"))       # festgeschrieben
        self.assertEqual(mf.betrag, Decimal("100.00"))

        r = self._aktion(self.uA, self.kA, "freigeben")        # User darf NICHT freigeben
        self.assertEqual(r.status_code, 403)
        mf.refresh_from_db()
        self.assertEqual(mf.status, Freigabestatus.EINGEREICHT)

        self._aktion(self.uL, self.kA, "freigeben")            # Leitung gibt frei
        mf.refresh_from_db()
        self.assertEqual(mf.status, Freigabestatus.FREIGEGEBEN)

    def test_zurueckweisen_setzt_hinweis_und_offen(self):
        self._aktion(self.uA, self.kA, "fertig")
        self._aktion(self.uL, self.kA, "zurueckweisen", hinweis="bitte FZ ergänzen")
        mf = Monatsfreigabe.objects.get(klient=self.kA)
        self.assertEqual(mf.status, Freigabestatus.OFFEN)
        self.assertEqual(mf.hinweis, "bitte FZ ergänzen")

    def test_fremdteam_klient_kein_zugriff(self):
        kB = Klient.objects.create(nachname="Beta", team=self.team_b, bezugsbetreuer=self.mB,
                                   status=Status.BETREUUNG)
        r = self._aktion(self.uA, kB, "fertig")                 # ada (Team A) auf Team-B-Klient
        self.assertEqual(r.status_code, 404)

    # --- Verwaltung / DSGVO --------------------------------------------
    def test_verwaltung_darf_abrechnen_user_nicht(self):
        self.assertTrue(services.darf_abrechnen(self.uV))
        self.assertFalse(services.darf_abrechnen(self.uA))

    def test_verwaltung_hat_keinen_klientenzugriff(self):
        self.assertEqual(services.klienten_fuer(self.uV).count(), 0)

    def test_abrechnung_leitet_verwaltung_zu_rechnungen(self):
        r = self.cl(self.uV).get("/abrechnung/")
        self.assertRedirects(r, "/rechnungen/", fetch_redirect_response=False)

    def test_abrechnung_seite_zeigt_klient(self):
        r = self.cl(self.uA).get("/abrechnung/?monat=6&jahr=2026")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Alpha")

    # --- § 18 Anlage 4 örV: Soll/Ist-Struktur der Monatsrechnung --------
    def test_snapshot_paragraph18_struktur(self):
        """Ist-Split einzeln/Gruppe, Soll nach Bescheid, Vorschuss (§ 18 Abs. 2/3)."""
        p = Parameter.objects.get(jahr=2026)
        p.kle_je_tag = Decimal("0.5")
        p.save()
        self.kA.al = Decimal("12.827")               # bewilligt/Monat (Bescheid)
        self.kA.save(update_fields=["al"])
        # Gruppe: 2 h, 2 Teilnehmer, 1 MA -> 1,0 h je Klient*in (FLS-Art FS)
        g = Gruppe.objects.create(datum=date(2026, 6, 15), thema="Kochgruppe",
                                  leistungsart=Leistungsart.FS,
                                  beginn=time(10, 0), ende=time(12, 0), anz_ma=1)
        kB2 = Klient.objects.create(nachname="Gamma", team=self.team_a,
                                    bezugsbetreuer=self.mA, status=Status.BETREUUNG)
        g.teilnehmer.set([self.kA, kB2])

        self._aktion(self.uA, self.kA, "fertig")
        mf = Monatsfreigabe.objects.get(klient=self.kA, jahr=2026, monat=6)
        self.assertEqual(mf.fls_einzeln, Decimal("2.000"))    # 2 h FS manuell
        self.assertEqual(mf.fls_gruppe, Decimal("1.000"))     # Gruppen-Anteil
        self.assertEqual(mf.fls_summe, Decimal("3.000"))      # einzeln + Gruppe
        self.assertEqual(mf.soll_fls, Decimal("12.827"))      # nach Bescheid
        # Vorschuss = (Soll + Ø-kLE/Monat) × Satz = (12,827 + 0,5×30,4375) × 50
        self.assertEqual(mf.vorschuss, Decimal("1402.29"))
        # Konsistenz mit dem amtlichen Nachweis
        d = services.druck_nachweis(self.kA, 2026, 6)
        self.assertEqual(mf.fls_summe, d["fls_summe"])

    def test_eabrechnung_export(self):
        self._aktion(self.uA, self.kA, "fertig")
        self._aktion(self.uL, self.kA, "freigeben")
        mf = Monatsfreigabe.objects.get(klient=self.kA)
        self.cl(self.uV).post("/rechnungen/neu/", {
            "ids": str(mf.id), "empfaenger": "Bezirksamt X", "datum": "2026-07-01"})
        r = Rechnung.objects.get()
        resp = self.cl(self.uV).get(f"/rechnungen/{r.id}/eabrechnung/")
        self.assertEqual(resp.status_code, 200)
        inhalt = resp.content.decode("utf-8-sig")
        self.assertIn("a_Zeitraum", inhalt)                   # § 18 Abs. 3 Buchst. a
        self.assertIn("f_Anzahl_kLE", inhalt)                 # Buchst. f
        self.assertIn("i_PTL_Std", inhalt)                    # Buchst. i/j (Psychotherapie)
        self.assertIn("d2_abrechenbare_FLS", inhalt)          # § 18 Abs. 4 (abrechenbare FLS)
        self.assertIn("Erbringungsfiktion", inhalt)           # Ist/Soll-Kennzeichnung
        self.assertIn("k_Rechnungsbetrag_EUR", inhalt)        # Buchst. k
        self.assertIn("AZ-1", inhalt)                         # Kennzeichen statt Name
        # User darf nicht exportieren
        self.assertEqual(self.cl(self.uA).get(f"/rechnungen/{r.id}/eabrechnung/").status_code, 302)

    def test_rechnung_erstellen_markiert_abgerechnet_und_storno_gibt_frei(self):
        self._aktion(self.uA, self.kA, "fertig")
        self._aktion(self.uL, self.kA, "freigeben")
        mf = Monatsfreigabe.objects.get(klient=self.kA)

        r = self.cl(self.uV).post("/rechnungen/neu/", {
            "ids": str(mf.id), "empfaenger": "Bezirksamt X", "datum": "2026-07-01"})
        self.assertEqual(r.status_code, 302)
        rech = Rechnung.objects.get()
        self.assertEqual(rech.betrag, Decimal("100.00"))
        mf.refresh_from_db()
        self.assertEqual(mf.status, Freigabestatus.ABGERECHNET)
        self.assertEqual(mf.rechnung_id, rech.id)

        r2 = self.cl(self.uA).post("/rechnungen/neu/", {"ids": str(mf.id)})   # User: verboten
        self.assertEqual(r2.status_code, 403)

        self.cl(self.uV).post(f"/rechnungen/{rech.id}/status/", {"status": "storniert"})
        mf.refresh_from_db()
        self.assertEqual(mf.status, Freigabestatus.FREIGEGEBEN)      # wieder frei
        self.assertIsNone(mf.rechnung_id)


class Paragraf18Tests(TestCase):
    """§ 18 Abs. 3/4 Anlage 4 örV: Erbringungsfiktion (Soll statt Ist), PTL, a–k-Aufstellung."""
    def setUp(self):
        from .models import Bewilligung
        self.team = Team.objects.create(name="T18", typ=Teamtyp.BEW)
        self.p = Parameter.objects.create(jahr=2026, fls_preis=Decimal("50"),
                                          erbringungsfiktion=True)
        u = User.objects.create_user("l18", password="x")
        self.lu = Mitarbeiter.objects.create(user=u, name="L", rolle=Rolle.LEITUNG, kuerzel="l")
        self.lu.leitet.set([self.team])
        self.k = Klient.objects.create(nachname="K", team=self.team, bezugsbetreuer=self.lu,
                                       status=Status.BETREUUNG, al=Decimal("10"))
        Leistung.objects.create(datum=date(2026, 6, 10), klient=self.k, leistungsart=Leistungsart.FS,
                                betreuer=self.lu, beginn=time(9, 0), ende=time(12, 0))   # 3 h Ist

    def _al(self, wert):
        Klient.objects.filter(pk=self.k.pk).update(al=Decimal(wert))
        self.k.refresh_from_db()

    def _mf(self):
        mf = Monatsfreigabe.objects.create(klient=self.k, jahr=2026, monat=6)
        services.freigabe_snapshot(mf)
        mf.save()
        return mf

    def test_erbringungsfiktion_bucht_soll(self):
        mf = self._mf()
        self.assertEqual(mf.soll_fls, Decimal("10"))
        self.assertEqual(mf.fls_summe, Decimal("3.000"))          # Ist nachrichtlich
        self.assertEqual(mf.abrechenbare_fls, Decimal("10"))      # Soll abgerechnet
        self.assertEqual(mf.betrag, Decimal("500.00"))            # 10 × 50 (kLE 0)

    def test_ohne_fiktion_bucht_ist(self):
        self.p.erbringungsfiktion = False
        self.p.save()
        mf = self._mf()
        self.assertEqual(mf.abrechenbare_fls, Decimal("3.000"))
        self.assertEqual(mf.betrag, Decimal("150.00"))            # 3 × 50

    def test_ptl_a_wird_berechnet_und_addiert(self):
        from .models import Bewilligung
        self.p.ptl_preis = Decimal("100")
        self.p.save()
        Bewilligung.objects.create(klient=self.k, fls_woche=Decimal("2"), ptl="A",
                                   gueltig_von=date(2026, 1, 1), status="aktiv")
        mf = self._mf()
        self.assertAlmostEqual(float(mf.ptl_stunden), 4.348, places=2)   # 1 h/Woche × 4,3482
        self.assertGreater(mf.ptl_betrag, Decimal("0"))
        # Gesamt = FLS-/kLE-Anteil (abrechenbar × Satz) + PTL-Betrag
        fls_anteil = services.betrag_fuer(mf.abrechenbare_fls, 2026, mf.kle_summe)
        self.assertEqual(mf.betrag, fls_anteil + mf.ptl_betrag)

    def test_aufstellung_a_bis_k(self):
        mf = self._mf()
        r = Rechnung.objects.create(nummer="2026-9001", empfaenger="Bezirksamt", jahr=2026,
                                    monat=6, datum=date(2026, 7, 1), betrag=mf.betrag)
        Monatsfreigabe.objects.filter(pk=mf.pk).update(rechnung=r)
        a = services.paragraf18_aufstellung(r)
        self.assertEqual(a["soll"], Decimal("10"))                # d
        self.assertEqual(a["ist"], Decimal("3.000"))             # e
        self.assertEqual(a["abrechenbar"], Decimal("10"))
        self.assertTrue(a["nach_soll"])
        self.assertEqual(a["zwischensumme"], Decimal("10"))      # g (10 FLS + 0 kLE)
        self.assertEqual(a["zwischenbetrag"], Decimal("500.00")) # h
        self.assertEqual(a["rechnungsbetrag"], Decimal("500.00"))# k

    def test_detail_zeigt_aufstellung(self):
        mf = self._mf()
        r = Rechnung.objects.create(nummer="2026-9002", empfaenger="Bezirksamt", jahr=2026,
                                    monat=6, datum=date(2026, 7, 1), betrag=mf.betrag)
        Monatsfreigabe.objects.filter(pk=mf.pk).update(rechnung=r)
        # Verwaltung darf abrechnen -> Detailseite mit a–k-Aufstellung
        uv = User.objects.create_user("v18", password="x")
        Mitarbeiter.objects.create(user=uv, name="V", rolle=Rolle.USER,
                                   team=Team.objects.create(name="VW18", typ=Teamtyp.VERWALTUNG),
                                   kuerzel="v")
        c = Client(); c.force_login(uv)
        resp = c.get(f"/rechnungen/{r.id}/")
        self.assertContains(resp, "Aufstellung der Monatsrechnung")
        self.assertContains(resp, "Erbringungsfiktion")

    # --- Regression (adversarialer Geld-Review): Snapshot bewertet den ---------
    # --- LEISTUNGSMONAT, nicht den (späteren) Freigabezeitpunkt ---------------
    def test_ptl_folgt_leistungsmonat_nicht_heute(self):
        """PTL wird zum Leistungsmonat aufgelöst: eine im Folgemonat auslaufende
        PTL-Bewilligung zählt für ihren Monat, nicht für spätere (Befund 1/6)."""
        from .models import Bewilligung
        self.p.ptl_preis = Decimal("100"); self.p.save()
        Bewilligung.objects.create(klient=self.k, fls_woche=Decimal("2"), ptl="B",
                                   gueltig_von=date(2026, 1, 1), gueltig_bis=date(2026, 3, 31),
                                   status="aktiv")
        Bewilligung.objects.create(klient=self.k, fls_woche=Decimal("2"), ptl="",
                                   gueltig_von=date(2026, 4, 1), status="aktiv")
        mf_maerz = Monatsfreigabe.objects.create(klient=self.k, jahr=2026, monat=3)
        services.freigabe_snapshot(mf_maerz)
        mf_mai = Monatsfreigabe.objects.create(klient=self.k, jahr=2026, monat=5)
        services.freigabe_snapshot(mf_mai)
        self.assertGreater(mf_maerz.ptl_stunden, Decimal("0"))   # PTL B galt im März
        self.assertEqual(mf_mai.ptl_stunden, Decimal("0"))       # ab April keine PTL

    def test_soll_folgt_monats_bewilligung(self):
        """Soll/abrechenbare FLS stammen aus der zum Monat gültigen Bewilligung –
        ein späterer Änderungsbescheid verändert den Alt-Monat nicht (Befund 2)."""
        from .models import Bewilligung
        Bewilligung.objects.create(klient=self.k, fls_woche=Decimal("2"),
                                   gueltig_von=date(2026, 1, 1), gueltig_bis=date(2026, 3, 31),
                                   status="aktiv")
        b2 = Bewilligung.objects.create(klient=self.k, fls_woche=Decimal("4"),
                                        gueltig_von=date(2026, 4, 1), status="aktiv")
        mf_maerz = Monatsfreigabe.objects.create(klient=self.k, jahr=2026, monat=3)
        services.freigabe_snapshot(mf_maerz)
        mf_mai = Monatsfreigabe.objects.create(klient=self.k, jahr=2026, monat=5)
        services.freigabe_snapshot(mf_mai)
        self.assertLess(mf_maerz.soll_fls, mf_mai.soll_fls)      # März 2, Mai 4 FLS/Woche
        self.assertEqual(mf_mai.soll_fls, b2.al_monat)

    def test_kle_folgt_kue_ende(self):
        """kLE-Pauschale nur für Monate bis zum KÜ-Ende (monatsscharf, Befund 4)."""
        self.p.kle_je_tag = Decimal("0.5"); self.p.save()
        Klient.objects.filter(pk=self.k.pk).update(kue_bis=date(2026, 6, 30))
        self.k.refresh_from_db()
        mf_juni = Monatsfreigabe.objects.create(klient=self.k, jahr=2026, monat=6)
        services.freigabe_snapshot(mf_juni)
        mf_juli = Monatsfreigabe.objects.create(klient=self.k, jahr=2026, monat=7)
        services.freigabe_snapshot(mf_juli)
        self.assertGreater(mf_juni.kle_summe, Decimal("0"))      # KÜ deckt Juni
        self.assertEqual(mf_juli.kle_summe, Decimal("0"))        # nach KÜ-Ende keine kLE

    def test_nach_soll_flag_nur_bei_fiktion(self):
        """Der Fiktionshinweis folgt dem festgeschriebenen Flag, nicht der zufälligen
        Gleichheit Ist == Soll (Befund 3)."""
        self.p.erbringungsfiktion = False; self.p.save()
        self._al("3")                                   # Soll == Ist (3 h), aber keine Fiktion
        mf = self._mf()
        r = Rechnung.objects.create(nummer="2026-9003", empfaenger="Bezirksamt", jahr=2026,
                                    monat=6, datum=date(2026, 7, 1), betrag=mf.betrag)
        Monatsfreigabe.objects.filter(pk=mf.pk).update(rechnung=r)
        a = services.paragraf18_aufstellung(r)
        self.assertEqual(a["abrechenbar"], a["soll"])   # Werte gleich …
        self.assertFalse(a["nach_soll"])                # … aber KEINE Erbringungsfiktion

    def test_zwischenbetrag_reconciliert_mit_rechnungsbetrag(self):
        """h + PTL (+ Tagessatz) == k, auch wenn positionsweise Rundung vom Aggregat
        abweicht (round-then-sum ≠ sum-then-round, Befund 5)."""
        self.p.fls_preis = Decimal("1")
        self.p.kle_je_tag = Decimal("0.333500")         # × 30 Tage = 10,005 h/Monat -> 10,01 € je Pos.
        self.p.save()
        Klient.objects.filter(pk=self.k.pk).update(al=Decimal("0"))
        self.k.refresh_from_db()
        k2 = Klient.objects.create(nachname="R2", team=self.team, bezugsbetreuer=self.lu,
                                   status=Status.BETREUUNG, al=Decimal("0"))
        mfs = []
        for kl in (self.k, k2):
            mf = Monatsfreigabe.objects.create(klient=kl, jahr=2026, monat=6)
            services.freigabe_snapshot(mf); mf.save()
            mfs.append(mf)
        gesamt = sum((mf.betrag for mf in mfs), Decimal("0"))
        r = Rechnung.objects.create(nummer="2026-9006", empfaenger="Bezirksamt", jahr=2026,
                                    monat=6, datum=date(2026, 7, 1), betrag=gesamt)
        Monatsfreigabe.objects.filter(pk__in=[m.pk for m in mfs]).update(rechnung=r)
        a = services.paragraf18_aufstellung(r)
        self.assertEqual(gesamt, Decimal("20.02"))                       # 2 × 10,01 (positionsweise)
        self.assertEqual(a["zwischenbetrag"] + a["ptl_betrag"], a["rechnungsbetrag"])

    def test_ptl_preis_immun_gegen_spaetere_parameteraenderung(self):
        """Nach dem Abrechnen geänderte PTL-Sätze verändern den Beleg nicht – der
        Stückpreis wird aus dem Snapshot rückgerechnet (Befund 7)."""
        from .models import Bewilligung
        self.p.ptl_preis = Decimal("100"); self.p.save()
        Bewilligung.objects.create(klient=self.k, fls_woche=Decimal("2"), ptl="A",
                                   gueltig_von=date(2026, 1, 1), status="aktiv")
        mf = self._mf()
        r = Rechnung.objects.create(nummer="2026-9005", empfaenger="Bezirksamt", jahr=2026,
                                    monat=6, datum=date(2026, 7, 1), betrag=mf.betrag)
        Monatsfreigabe.objects.filter(pk=mf.pk).update(rechnung=r)
        self.p.ptl_preis = Decimal("999"); self.p.save()          # nachträgliche Änderung
        a = services.paragraf18_aufstellung(r)
        self.assertEqual(a["ptl_betrag"], mf.ptl_betrag)          # Betrag festgeschrieben
        self.assertEqual((a["ptl_std"] * a["ptl_preis"]).quantize(Decimal("0.01")),
                         a["ptl_betrag"])                          # Stückpreis passt zum Betrag


class MailVersandTests(TestCase):
    """Rechnungs-/Mahnungsversand per E-Mail (PDF-Anhang, Versand protokolliert)."""
    def setUp(self):
        from .models import Kostentraeger
        self.team = Team.objects.create(name="TM", typ=Teamtyp.BEW)
        Parameter.objects.create(jahr=2026, fls_preis=Decimal("50"))
        uv = User.objects.create_user("vmail", password="x")
        Mitarbeiter.objects.create(user=uv, name="V", rolle=Rolle.USER, kuerzel="v",
                                   team=Team.objects.create(name="VWm", typ=Teamtyp.VERWALTUNG))
        self.uv = uv
        uu = User.objects.create_user("umail", password="x")
        Mitarbeiter.objects.create(user=uu, name="U", rolle=Rolle.USER, team=self.team, kuerzel="u")
        self.uu = uu
        self.kt = Kostentraeger.objects.create(name="Bezirksamt X", email="rechnung@ba.de")
        self.r = Rechnung.objects.create(nummer="2026-7001", empfaenger="Bezirksamt X",
                                         kostentraeger=self.kt, jahr=2026, monat=6,
                                         datum=date(2026, 7, 1), betrag=Decimal("500.00"),
                                         status=Rechnungsstatus.ENTWURF)

    def _cl(self, u):
        c = Client(); c.force_login(u); return c

    @override_settings(EMAIL_AKTIV=True, EMAIL_BACKEND=LOCMEM)
    @patch("nachweis.views_abrechnung._weasy_pdf", return_value=b"%PDF-1.4 fake")
    def test_rechnung_mail_versendet_und_protokolliert(self, _pdf):
        from django.core import mail
        self._cl(self.uv).post(f"/rechnungen/{self.r.id}/mail/", {})
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertEqual(msg.to, ["rechnung@ba.de"])
        self.assertEqual(len(msg.attachments), 1)                 # PDF hängt an
        self.assertIn(self.r.nummer, msg.subject)
        self.r.refresh_from_db()
        self.assertIsNotNone(self.r.gesendet_am)
        self.assertEqual(self.r.gesendet_an, "rechnung@ba.de")
        self.assertEqual(self.r.status, Rechnungsstatus.GESTELLT)  # Versand stellt zugleich

    @override_settings(EMAIL_AKTIV=True, EMAIL_BACKEND=LOCMEM)
    @patch("nachweis.views_abrechnung._weasy_pdf", return_value=b"%PDF")
    def test_mail_abweichende_adresse_abgelehnt(self, _pdf):
        # Schutz vor Fehlversand (Art. 33/34 DSGVO): eine von der hinterlegten Kostenträger-
        # Adresse abweichende Eingabe wird NICHT versendet – Sozialdaten nur an geprüfte Adresse.
        from django.core import mail
        self._cl(self.uv).post(f"/rechnungen/{self.r.id}/mail/", {"email": "fremd@example.com"})
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(EMAIL_AKTIV=True, EMAIL_BACKEND=LOCMEM)
    @patch("nachweis.views_abrechnung._weasy_pdf", return_value=b"%PDF")
    def test_mail_hinterlegte_adresse_erlaubt(self, _pdf):
        from django.core import mail
        self._cl(self.uv).post(f"/rechnungen/{self.r.id}/mail/", {"email": "rechnung@ba.de"})
        self.assertEqual(mail.outbox[0].to, ["rechnung@ba.de"])

    def test_mail_nur_verwaltung(self):
        resp = self._cl(self.uu).post(f"/rechnungen/{self.r.id}/mail/", {})
        self.assertEqual(resp.status_code, 403)

    def test_status_stornierte_rechnung_nicht_reaktivierbar(self):
        self.r.status = Rechnungsstatus.STORNIERT
        self.r.save(update_fields=["status"])
        self._cl(self.uv).post(f"/rechnungen/{self.r.id}/status/",
                               {"status": Rechnungsstatus.GESTELLT})
        self.r.refresh_from_db()
        self.assertEqual(self.r.status, Rechnungsstatus.STORNIERT)   # Endzustand, kein Zurück

    def test_status_gestellt_nicht_zu_entwurf(self):
        self.r.status = Rechnungsstatus.GESTELLT
        self.r.save(update_fields=["status"])
        self._cl(self.uv).post(f"/rechnungen/{self.r.id}/status/",
                               {"status": Rechnungsstatus.ENTWURF})
        self.r.refresh_from_db()
        self.assertEqual(self.r.status, Rechnungsstatus.GESTELLT)    # GESTELLT->ENTWURF gesperrt

    def test_fehlermeldung_erscheint_rot_nicht_gruen(self):
        # Regression: Fehlermeldungen wurden früher grün (als Erfolg) gerendert. Der zentrale
        # Messages-Block muss eine error-Meldung ROT (var(--bad)) ausgeben.
        self.r.status = Rechnungsstatus.STORNIERT
        self.r.save(update_fields=["status"])
        resp = self._cl(self.uv).post(f"/rechnungen/{self.r.id}/status/",
                                      {"status": Rechnungsstatus.GESTELLT}, follow=True)
        html = resp.content.decode()
        self.assertIn("nicht zulässig", html)          # die Fehlermeldung erscheint
        self.assertIn("var(--bad)", html)              # und wird rot dargestellt (nicht grün)

    @override_settings(EMAIL_AKTIV=True, EMAIL_BACKEND=LOCMEM)
    @patch("nachweis.views_abrechnung._weasy_pdf", return_value=b"%PDF")
    def test_ohne_empfaenger_kein_versand(self, _pdf):
        from django.core import mail
        self.kt.email = ""; self.kt.save()
        self._cl(self.uv).post(f"/rechnungen/{self.r.id}/mail/", {})
        self.assertEqual(len(mail.outbox), 0)
        self.r.refresh_from_db()
        self.assertIsNone(self.r.gesendet_am)

    @override_settings(EMAIL_AKTIV=True, EMAIL_BACKEND=LOCMEM)
    @patch("nachweis.views_abrechnung._weasy_pdf", return_value=None)
    def test_ohne_pdf_engine_kein_versand(self, _pdf):
        from django.core import mail
        self._cl(self.uv).post(f"/rechnungen/{self.r.id}/mail/", {})
        self.assertEqual(len(mail.outbox), 0)
        self.r.refresh_from_db()
        self.assertIsNone(self.r.gesendet_am)

    @override_settings(EMAIL_AKTIV=True, EMAIL_BACKEND=LOCMEM)
    @patch("nachweis.views_abrechnung._weasy_pdf", return_value=b"%PDF")
    def test_storniert_wird_nicht_versendet(self, _pdf):
        from django.core import mail
        self.r.status = Rechnungsstatus.STORNIERT; self.r.save()
        self._cl(self.uv).post(f"/rechnungen/{self.r.id}/mail/", {})
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(EMAIL_AKTIV=False, EMAIL_BACKEND=LOCMEM)
    @patch("nachweis.views_abrechnung._weasy_pdf", return_value=b"%PDF")
    def test_ohne_smtp_konfig_kein_versand(self, _pdf):
        from django.core import mail
        self._cl(self.uv).post(f"/rechnungen/{self.r.id}/mail/", {})
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(EMAIL_AKTIV=True, EMAIL_BACKEND=LOCMEM)
    @patch("nachweis.views_abrechnung._weasy_pdf", return_value=b"%PDF")
    def test_mahnung_mail(self, _pdf):
        from django.core import mail
        from .models import Mahnung
        self.r.status = Rechnungsstatus.GESTELLT; self.r.save()
        m = Mahnung.objects.create(rechnung=self.r, stufe=1, datum=date(2026, 8, 1), frist_tage=14)
        self._cl(self.uv).post(f"/mahnung/{m.id}/mail/", {})
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(len(mail.outbox[0].attachments), 1)
        m.refresh_from_db()
        self.assertIsNotNone(m.gesendet_am)
        self.assertEqual(m.gesendet_an, "rechnung@ba.de")


class RechnungslaufTests(TestCase):
    """Ein-Klick-Rechnungslauf: je Kostenträger eine Sammelrechnung, atomar,
    Nachweise ohne Kostenträger übersprungen."""
    def setUp(self):
        self.team = Team.objects.create(name="TR", typ=Teamtyp.BEW)
        Parameter.objects.create(jahr=2026, fls_preis=Decimal("50"))
        uv = User.objects.create_user("vlauf", password="x")
        Mitarbeiter.objects.create(user=uv, name="V", rolle=Rolle.USER, kuerzel="v",
                                   team=Team.objects.create(name="VWl", typ=Teamtyp.VERWALTUNG))
        self.uv = uv
        uu = User.objects.create_user("ulauf", password="x")
        self.mu = Mitarbeiter.objects.create(user=uu, name="U", rolle=Rolle.USER,
                                             team=self.team, kuerzel="u")
        self.uu = uu
        self.k1 = Klient.objects.create(nachname="A", team=self.team, bezugsbetreuer=self.mu,
                                        status=Status.BETREUUNG, kostentraeger="Bezirksamt Mitte")
        self.k2 = Klient.objects.create(nachname="B", team=self.team, bezugsbetreuer=self.mu,
                                        status=Status.BETREUUNG, kostentraeger="Bezirksamt Nord")
        self.k3 = Klient.objects.create(nachname="C", team=self.team, bezugsbetreuer=self.mu,
                                        status=Status.BETREUUNG, kostentraeger="")   # ohne KT
        for k, betr in ((self.k1, "100"), (self.k2, "200"), (self.k3, "50")):
            Monatsfreigabe.objects.create(klient=k, jahr=2026, monat=6,
                                          status=Freigabestatus.FREIGEGEBEN,
                                          betrag=Decimal(betr), fls_summe=Decimal("2"))

    def _cl(self, u):
        c = Client(); c.force_login(u); return c

    def test_lauf_erstellt_je_kostentraeger(self):
        self._cl(self.uv).post("/rechnungslauf/", {"jahr": 2026, "monat": 6, "datum": "2026-07-01"})
        self.assertEqual(Rechnung.objects.count(), 2)          # k3 ohne KT übersprungen
        self.assertEqual(sorted(r.betrag for r in Rechnung.objects.all()),
                         [Decimal("100"), Decimal("200")])
        self.assertEqual(Monatsfreigabe.objects.get(klient=self.k1).status, Freigabestatus.ABGERECHNET)
        self.assertEqual(Monatsfreigabe.objects.get(klient=self.k3).status, Freigabestatus.FREIGEGEBEN)

    def test_fk_gruppierung_trennt_gleichen_freitext(self):
        # Bug-Fix: gleicher Freitext-Kostenträger, aber verschiedene strukturierte
        # FK-Bewilligungen -> zwei getrennte Rechnungen mit KORREKTEM FK (nicht eine falsche).
        from .models import (Kostentraeger, KostentraegerTyp, Bewilligung, BewilligungStatus)
        kt_mitte = Kostentraeger.objects.create(name="BA Mitte", typ=KostentraegerTyp.BEZIRKSAMT,
                                                leitweg_id="11-1-1")
        kt_pankow = Kostentraeger.objects.create(name="BA Pankow", typ=KostentraegerTyp.BEZIRKSAMT,
                                                 leitweg_id="11-2-2")
        for k, kt in ((self.k1, kt_mitte), (self.k2, kt_pankow)):
            k.kostentraeger = "Bezirksamt X"        # identischer Freitext bei beiden
            k.save()
            Bewilligung.objects.create(klient=k, kostentraeger=kt, status=BewilligungStatus.AKTIV,
                                       gueltig_von=date(2026, 1, 1), gueltig_bis=date(2026, 12, 31))
        self._cl(self.uv).post("/rechnungslauf/", {"jahr": 2026, "monat": 6, "datum": "2026-07-01"})
        rechnungen = {r.kostentraeger_id: r for r in Rechnung.objects.all()}
        self.assertEqual(len(rechnungen), 2)                  # nach FK getrennt, nicht zusammengefasst
        self.assertEqual(rechnungen[kt_mitte.id].betrag, Decimal("100"))
        self.assertEqual(rechnungen[kt_pankow.id].betrag, Decimal("200"))

    def test_zweiter_lauf_erzeugt_keine_dubletten(self):
        self._cl(self.uv).post("/rechnungslauf/", {"jahr": 2026, "monat": 6, "datum": "2026-07-01"})
        self._cl(self.uv).post("/rechnungslauf/", {"jahr": 2026, "monat": 6, "datum": "2026-07-01"})
        self.assertEqual(Rechnung.objects.count(), 2)          # keine erneute Fakturierung

    def test_nur_verwaltung(self):
        r = self._cl(self.uu).post("/rechnungslauf/", {"jahr": 2026, "monat": 6})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(Rechnung.objects.count(), 0)

    def test_service_gruppiert_und_ueberspringt(self):
        erstellt, ohne = services.rechnungslauf(2026, 6, date(2026, 7, 1), self.mu)
        self.assertEqual(len(erstellt), 2)
        self.assertEqual(ohne, 1)


class EditLockTests(TestCase):
    """Harte Festschreibung: eingereichte/abgerechnete Monate sind gegen Änderung gesperrt
    (Nachweis-Druck = Original)."""
    def setUp(self):
        self.team = Team.objects.create(name="TL", typ=Teamtyp.BEW)
        u = User.objects.create_user("mlock", password="x")
        self.m = Mitarbeiter.objects.create(user=u, name="M", rolle=Rolle.USER,
                                             team=self.team, kuerzel="m")
        self.k = Klient.objects.create(nachname="Sperr", team=self.team, bezugsbetreuer=self.m,
                                       status=Status.BETREUUNG)
        self.c = Client(); self.c.force_login(u)

    def _sperren(self, status=Freigabestatus.EINGEREICHT):
        Monatsfreigabe.objects.create(klient=self.k, jahr=2026, monat=6, status=status)

    def _save(self, **extra):
        payload = {"klient": self.k.id, "leistungsart": Leistungsart.FS, "datum": "2026-06-10",
                   "beginn": "09:00", "ende": "10:00"}
        payload.update(extra)
        return self.c.post("/api/leistungen/save/", data=json.dumps(payload),
                           content_type="application/json")

    def _leistung(self, tag):
        return Leistung.objects.create(datum=tag, klient=self.k, betreuer=self.m,
                                       leistungsart=Leistungsart.FS, beginn=time(9, 0), ende=time(10, 0))

    def test_offener_monat_erlaubt_speichern(self):
        self.assertEqual(self._save().status_code, 200)

    def test_eingereichter_monat_sperrt_speichern(self):
        self._sperren()
        self.assertEqual(self._save().status_code, 409)

    def test_abgerechneter_monat_sperrt_speichern(self):
        self._sperren(Freigabestatus.ABGERECHNET)
        self.assertEqual(self._save().status_code, 409)

    def test_zurueckgewiesen_offen_erlaubt_wieder(self):
        self._sperren(Freigabestatus.OFFEN)          # zurückgewiesen = wieder offen
        self.assertEqual(self._save().status_code, 200)

    def test_verschieben_in_gesperrten_monat_blockiert(self):
        l = self._leistung(date(2026, 5, 10))        # offener Mai
        self._sperren()                              # Juni gesperrt
        self.assertEqual(self._save(id=l.id, datum="2026-06-10").status_code, 409)

    def test_wegschieben_aus_gesperrtem_monat_blockiert(self):
        l = self._leistung(date(2026, 6, 10))        # gesperrter Juni
        self._sperren()
        self.assertEqual(self._save(id=l.id, datum="2026-07-10").status_code, 409)

    def test_loeschen_blockiert(self):
        l = self._leistung(date(2026, 6, 10))
        self._sperren()
        r = self.c.post("/api/leistungen/delete/", data=json.dumps({"id": l.id}),
                        content_type="application/json")
        self.assertEqual(r.status_code, 409)
        self.assertTrue(Leistung.objects.filter(pk=l.id).exists())

    def test_gruppe_blockiert_wenn_teilnehmer_monat_gesperrt(self):
        from .models import Gruppe as G
        self._sperren()
        self.c.post("/gruppen/save/", {"thema": "Kochen", "datum": "2026-06-15",
                    "leistungsart": Leistungsart.FS, "beginn": "10:00", "ende": "12:00",
                    "anz_ma": "1", "teilnehmer": [str(self.k.id)]})
        self.assertEqual(G.objects.count(), 0)

    def test_feld_speichern_blockiert(self):
        self._sperren()
        self.c.post("/unterwegs/speichern/", {"klient": self.k.id, "datum": "2026-06-10",
                    "beginn": "09:00", "ende": "10:00", "leistungsart": Leistungsart.FS,
                    "doku_minuten": "0"})
        self.assertEqual(Leistung.objects.filter(klient=self.k, datum=date(2026, 6, 10)).count(), 0)


class TeilerFestschreibungTests(TestCase):
    """Teamsitzung/Serien werden durch die Klientenzahl geteilt – für festgeschriebene
    Monate bleibt der Teiler fixiert, damit der Nachweis-Druck reproduzierbar ist."""
    def setUp(self):
        self.team = Team.objects.create(name="TT", typ=Teamtyp.BEW)
        u = User.objects.create_user("mteiler", password="x")
        self.m = Mitarbeiter.objects.create(user=u, name="M", rolle=Rolle.USER,
                                             team=self.team, kuerzel="m")
        self.p = Parameter.objects.create(jahr=2026, fls_preis=Decimal("50"),
                                          teamsitzung_dauer_std=Decimal("3"), teamsitzung_wochentag=3)
        self.k = Klient.objects.create(nachname="A", team=self.team, bezugsbetreuer=self.m,
                                       status=Status.BETREUUNG)
        Klient.objects.create(nachname="B", team=self.team, bezugsbetreuer=self.m,
                              status=Status.BETREUUNG)

    def _snapshot(self):
        mf = Monatsfreigabe.objects.create(klient=self.k, jahr=2026, monat=6,
                                           status=Freigabestatus.EINGEREICHT)
        services.freigabe_snapshot(mf); mf.save()
        return mf

    def _dritte(self):
        Klient.objects.create(nachname="C", team=self.team, bezugsbetreuer=self.m,
                              status=Status.BETREUUNG)

    def _ts_stunden(self):
        d = services.druck_nachweis(self.k, 2026, 6)
        ts = [e for e in d["eintraege"] if e["bezeichnung"] == "Teamsitzung"]
        return ts[0]["stunden"] if ts else None

    def test_snapshot_speichert_teiler(self):
        mf = self._snapshot()
        self.assertEqual(mf.teiler_global, 2)          # 2 Klient*innen in Betreuung
        self.assertEqual(mf.teiler_team, 2)

    def test_druck_nutzt_fixierten_teiler(self):
        self._snapshot()                               # Teiler = 2 fixiert
        self._dritte()                                 # live-Teiler jetzt 3
        self.assertEqual(self._ts_stunden(), Decimal("1.500"))   # 3 h ÷ 2 (fixiert)

    def test_offener_monat_nutzt_live_teiler(self):
        self._dritte()                                 # kein Snapshot -> live-Teiler 3
        self.assertEqual(self._ts_stunden(), Decimal("1.000"))   # 3 h ÷ 3

    def test_reprint_immun_gegen_teamwechsel_bei_teamserie(self):
        """HOCH-Befund: eine team-bezogene FLS-Serie darf im Nachdruck nicht wegfallen,
        wenn der Klient nach Freigabe das Team wechselt (Druck = eingefrorene Rechnung)."""
        from .models import WiederkehrendeLeistung, Rhythmus, Anrechnung, Team as T
        WiederkehrendeLeistung.objects.create(
            bezeichnung="Fallsupervision", team=self.team, leistungsart=Leistungsart.WFS,
            rhythmus=Rhythmus.WOECHENTLICH, wochentag=1, anrechnung=Anrechnung.TEILER,
            dauer_std=Decimal("2"), aktiv=True, gilt_ab=date(2026, 1, 1))
        mf = self._snapshot()
        frozen = services.druck_nachweis(self.k, 2026, 6)["fls_summe"]
        self.assertGreater(frozen, Decimal("0"))
        self.assertEqual(frozen, mf.fls_summe)         # Druck == eingefrorene Rechnung
        neues = T.objects.create(name="TX", typ=Teamtyp.BEW)
        Klient.objects.filter(pk=self.k.pk).update(team=neues)   # Team-Wechsel nach Freigabe
        self.k.refresh_from_db()
        self.assertEqual(services.druck_nachweis(self.k, 2026, 6)["fls_summe"], frozen)

    def test_reprint_immun_gegen_status_beendigung(self):
        """HOCH-Befund: eine spätere Beendigung darf den bereits abgerechneten Nachweis
        nicht auf 0 fallen lassen."""
        self._snapshot()
        frozen = self._ts_stunden()                    # 1,5 (Teamsitzung 3 h ÷ 2)
        Klient.objects.filter(pk=self.k.pk).update(status=Status.BEENDIGUNG)
        self.k.refresh_from_db()
        self.assertEqual(self._ts_stunden(), frozen)   # trotz Beendigung unverändert

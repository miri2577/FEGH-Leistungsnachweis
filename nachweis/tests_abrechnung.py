"""Tests für den Abrechnungs-Workflow (Freigabe MA→Leitung→Verwaltung) + Rechnungen.

Sichert die Rechte-Kette und die DSGVO-Trennung (Verwaltung ohne Klientenzugriff)
sowie die Betragsberechnung (FLS × FLS-Preis) und Storno (Positionen wieder frei).
"""
from datetime import date, time
from decimal import Decimal

from django.test import TestCase, Client
from django.contrib.auth import get_user_model

from . import services
from .models import (Team, Teamtyp, Mitarbeiter, Klient, Rolle, Status, Leistung,
                     Leistungsart, Parameter, Monatsfreigabe, Rechnung, Freigabestatus,
                     Gruppe)

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

"""Tests P4: Vorkommnis-Meldewesen (§ 37a/WTG/§ 8a) + DATEV-Buchungsstapel-Export."""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import (Team, Teamtyp, Mitarbeiter, Rolle, Klient, Status,
                     Vorkommnis, VorkommnisStatus, Kostentraeger, Rechnung,
                     Rechnungsstatus, Rechnungstyp, Rechnungssteller)

User = get_user_model()


class QMBasis(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="TBEW", typ=Teamtyp.values[0])
        self.lu = User.objects.create_user("chef", password="x")
        m = Mitarbeiter.objects.create(user=self.lu, name="Chef", rolle=Rolle.LEITUNG, kuerzel="c")
        m.leitet.set([self.team])
        self.mu = User.objects.create_user("ma", password="x")
        self.ma = Mitarbeiter.objects.create(user=self.mu, name="MA", rolle=Rolle.USER,
                                             team=self.team, kuerzel="m")
        self.k = Klient.objects.create(nachname="K", team=self.team,
                                       bezugsbetreuer=self.ma, status=Status.BETREUUNG)


class VorkommnisTests(QMBasis):
    def _melden(self, client_obj, **extra):
        daten = {"datum": date.today().isoformat(), "kategorie": "gewalt",
                 "team": self.team.id, "klient": self.k.id,
                 "beschreibung": "Vorfall im Hausflur.",
                 "sofortmassnahmen": "Getrennt, beruhigt."}
        daten.update(extra)
        return client_obj.post(reverse("nachweis:vorkommnis_speichern"), daten)

    def test_nav_badge_meldepflichtig(self):
        """Roter Nav-Badge: meldepflichtiges Vorkommnis ohne dokumentierte Meldung."""
        self.client.force_login(self.lu)
        # noch nichts -> kein Badge
        self.assertEqual(self.client.get(reverse("nachweis:start")).context["nav_vork_meldung"], 0)
        v = Vorkommnis.objects.create(datum=date.today(), kategorie="gewalt", team=self.team,
                                      beschreibung="x", erstellt_von=self.ma)
        self.assertEqual(self.client.get(reverse("nachweis:start")).context["nav_vork_meldung"], 1)
        # Meldung dokumentiert -> Badge weg
        v.gemeldet_am = date.today(); v.gemeldet_an = "WTG-Aufsicht"; v.save()
        self.assertEqual(self.client.get(reverse("nachweis:start")).context["nav_vork_meldung"], 0)
        # nicht meldepflichtige Kategorie zählt nicht
        Vorkommnis.objects.create(datum=date.today(), kategorie="beschwerde", team=self.team,
                                  beschreibung="y", erstellt_von=self.ma)
        self.assertEqual(self.client.get(reverse("nachweis:start")).context["nav_vork_meldung"], 0)

    def test_ma_erfasst_und_sieht_eigene(self):
        self.client.force_login(self.mu)
        resp = self._melden(self.client)
        self.assertEqual(resp.status_code, 302)
        v = Vorkommnis.objects.get()
        self.assertEqual(v.erstellt_von, self.ma)
        self.assertTrue(v.meldung_faellig)                    # Gewalt ohne Meldung
        seite = self.client.get(reverse("nachweis:vorkommnisse"))
        self.assertContains(seite, "Meldung fällig")

    def test_leitung_sieht_team_ma_nur_eigene(self):
        self.client.force_login(self.mu)
        self._melden(self.client)
        # zweiter MA sieht das Vorkommnis NICHT
        u2 = User.objects.create_user("ma2", password="x")
        Mitarbeiter.objects.create(user=u2, name="M2", rolle=Rolle.USER,
                                   team=self.team, kuerzel="m2")
        c2 = self.client.__class__()
        c2.force_login(u2)
        self.assertNotContains(c2.get(reverse("nachweis:vorkommnisse")), "Hausflur")
        # Leitung sieht es
        cl = self.client.__class__()
        cl.force_login(self.lu)
        self.assertContains(cl.get(reverse("nachweis:vorkommnisse")), "gewalt".title()[:0] or "Gewalt")

    def test_abschluss_blockiert_ohne_auswertung_und_meldung(self):
        self.client.force_login(self.mu)
        self._melden(self.client)
        v = Vorkommnis.objects.get()
        cl = self.client.__class__()
        cl.force_login(self.lu)
        cl.post(reverse("nachweis:vorkommnis_status"),
                {"id": v.id, "aktion": "abschliessen"})
        v.refresh_from_db()
        self.assertNotEqual(v.status, VorkommnisStatus.ABGESCHLOSSEN)   # keine Auswertung
        # Auswertung + Meldung nachtragen -> Abschluss klappt
        cl.post(reverse("nachweis:vorkommnis_speichern"), {
            "id": v.id, "datum": v.datum.isoformat(), "kategorie": "gewalt",
            "team": self.team.id, "beschreibung": v.beschreibung,
            "massnahmen": "Deeskalationsschulung geplant.",
            "gemeldet_an": "WTG-Aufsicht", "gemeldet_am": date.today().isoformat()})
        cl.post(reverse("nachweis:vorkommnis_status"),
                {"id": v.id, "aktion": "abschliessen"})
        v.refresh_from_db()
        self.assertEqual(v.status, VorkommnisStatus.ABGESCHLOSSEN)
        self.assertEqual(v.abgeschlossen_am, date.today())

    def test_ma_darf_nicht_abschliessen(self):
        self.client.force_login(self.mu)
        self._melden(self.client)
        v = Vorkommnis.objects.get()
        resp = self.client.post(reverse("nachweis:vorkommnis_status"),
                                {"id": v.id, "aktion": "abschliessen"})
        self.assertEqual(resp.status_code, 403)

    def test_beschwerde_nicht_meldepflichtig(self):
        self.client.force_login(self.mu)
        self._melden(self.client, kategorie="beschwerde")
        self.assertFalse(Vorkommnis.objects.get().meldung_faellig)

    def test_freitexte_nicht_in_history(self):
        self.client.force_login(self.mu)
        self._melden(self.client)
        v = Vorkommnis.objects.get()
        h = v.history.first()
        self.assertFalse(hasattr(h, "beschreibung"))
        self.assertFalse(hasattr(h, "massnahmen"))


class DatevExportTests(TestCase):
    def setUp(self):
        vw = Team.objects.create(name="Verwaltung", typ=Teamtyp.VERWALTUNG)
        self.u = User.objects.create_user("verw", password="x")
        Mitarbeiter.objects.create(user=self.u, name="V", rolle=Rolle.USER,
                                   team=vw, kuerzel="v")
        self.client.force_login(self.u)
        s = Rechnungssteller.load()
        s.datev_berater = "1234567"
        s.datev_mandant = "10001"
        s.datev_erloeskonto = "8125"
        s.save()
        self.kt = Kostentraeger.objects.create(name="Bezirksamt Test",
                                               debitorenkonto="10001")
        self.r = Rechnung.objects.create(nummer="2026-0400", empfaenger=self.kt.name,
                                         kostentraeger=self.kt, jahr=2026, monat=5,
                                         datum=date(2026, 6, 5), betrag=Decimal("1234.56"),
                                         status=Rechnungsstatus.GESTELLT)

    def _export(self):
        return self.client.get(reverse("nachweis:datev_export"),
                               {"von": "2026-06-01", "bis": "2026-06-30"})

    def test_extf_export(self):
        resp = self._export()
        self.assertEqual(resp.status_code, 200)
        text = resp.content.decode("cp1252")
        self.assertTrue(text.startswith('"EXTF";700;21'))
        self.assertIn('1234,56;"S";"EUR"', text)
        self.assertIn("10001;8125", text)                      # Debitor;Erlöskonto
        self.assertIn('"2026-0400"', text)
        self.assertIn("0506", text)                            # Belegdatum TTMM

    def test_gutschrift_haben_kennzeichen(self):
        Rechnung.objects.create(nummer="2026-0401", empfaenger=self.kt.name,
                                kostentraeger=self.kt, jahr=2026, monat=5,
                                datum=date(2026, 6, 10), betrag=Decimal("-200.00"),
                                typ=Rechnungstyp.GUTSCHRIFT,
                                status=Rechnungsstatus.GESTELLT)
        text = self._export().content.decode("cp1252")
        self.assertIn('200,00;"H"', text)                      # Gutschrift = Haben
        self.assertIn("Gutschrift 2026-0401", text)

    def test_fehlendes_debitorenkonto_blockt(self):
        self.kt.debitorenkonto = ""
        self.kt.save()
        resp = self._export()
        self.assertEqual(resp.status_code, 302)                # redirect + Fehlermeldung
        self.assertEqual(Rechnung.objects.count(), 1)          # nichts kaputt

    def test_nur_verwaltung(self):
        team = Team.objects.create(name="TBEW", typ=Teamtyp.values[0])
        nu = User.objects.create_user("norm", password="x")
        Mitarbeiter.objects.create(user=nu, name="N", rolle=Rolle.USER, team=team, kuerzel="n")
        self.client.force_login(nu)
        self.assertEqual(self._export().status_code, 302)

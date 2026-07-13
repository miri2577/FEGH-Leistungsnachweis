"""Tests Storno & Historisierung: Gutschriften (beleghafter Storno) + simple-history."""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from . import services
from .models import (Team, Teamtyp, Mitarbeiter, Rolle, Klient, Status,
                     Kostentraeger, Rechnung, Rechnungsstatus, Rechnungstyp,
                     Zahlung, Monatsfreigabe, Freigabestatus, Bewilligung)

User = get_user_model()


class GutschriftTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="TBEW", typ=Teamtyp.values[0])
        self.betr = Mitarbeiter.objects.create(
            user=User.objects.create_user("b", password="x"),
            name="B", rolle=Rolle.USER, team=self.team, kuerzel="b")
        self.k = Klient.objects.create(nachname="K", team=self.team,
                                       bezugsbetreuer=self.betr, status=Status.BETREUUNG)
        self.r = Rechnung.objects.create(nummer="2026-0200", empfaenger="Bezirksamt Test",
                                         jahr=2026, monat=6, datum=date(2026, 7, 1),
                                         betrag=Decimal("300.00"),
                                         status=Rechnungsstatus.GESTELLT)
        self.mf = Monatsfreigabe.objects.create(klient=self.k, jahr=2026, monat=6,
                                                status=Freigabestatus.ABGERECHNET,
                                                rechnung=self.r, betrag=Decimal("300.00"))

    def test_gutschrift_storniert_beleghaft(self):
        g, fehler = services.gutschrift_erstellen(self.r, self.betr)
        self.assertIsNone(fehler)
        self.assertEqual(g.typ, Rechnungstyp.GUTSCHRIFT)
        self.assertEqual(g.betrag, Decimal("-300.00"))
        self.assertEqual(g.storno_zu, self.r)
        self.assertNotEqual(g.nummer, self.r.nummer)          # eigene Nummer
        self.r.refresh_from_db()
        self.assertEqual(self.r.status, Rechnungsstatus.STORNIERT)
        self.mf.refresh_from_db()
        self.assertEqual(self.mf.status, Freigabestatus.FREIGEGEBEN)   # wieder abrechenbar
        self.assertIsNone(self.mf.rechnung_id)

    def test_entwurf_braucht_keine_gutschrift(self):
        self.r.status = Rechnungsstatus.ENTWURF
        self.r.save(update_fields=["status"])
        g, fehler = services.gutschrift_erstellen(self.r, self.betr)
        self.assertIsNone(g)
        self.assertIn("gestellte", fehler)

    def test_mit_zahlung_geblockt(self):
        Zahlung.objects.create(rechnung=self.r, datum=date.today(), betrag=Decimal("100.00"))
        g, fehler = services.gutschrift_erstellen(self.r, self.betr)
        self.assertIsNone(g)
        self.assertIn("Zahlungen", fehler)

    def test_keine_doppelte_gutschrift(self):
        g1, _ = services.gutschrift_erstellen(self.r, self.betr)
        self.assertIsNotNone(g1)
        # Original ist jetzt storniert -> zweiter Versuch scheitert am Status-Guard
        g2, fehler = services.gutschrift_erstellen(self.r, self.betr)
        self.assertIsNone(g2)
        self.assertIsNotNone(fehler)

    def test_gutschrift_selbst_nicht_stornierbar(self):
        g, _ = services.gutschrift_erstellen(self.r, self.betr)
        g2, fehler = services.gutschrift_erstellen(g, self.betr)
        self.assertIsNone(g2)
        self.assertIn("nicht erneut", fehler)

    def test_gutschrift_erscheint_nicht_in_offenen_posten(self):
        g, _ = services.gutschrift_erstellen(self.r, self.betr)
        self.assertFalse(g.ist_offen)         # negativer offener Betrag = keine Forderung


class StornoViewTests(TestCase):
    def setUp(self):
        team = Team.objects.create(name="Verwaltung", typ=Teamtyp.VERWALTUNG)
        self.u = User.objects.create_user("verw", password="x")
        self.m = Mitarbeiter.objects.create(user=self.u, name="V", rolle=Rolle.USER,
                                            team=team, kuerzel="v")
        self.client.force_login(self.u)
        self.r = Rechnung.objects.create(nummer="2026-0201", empfaenger="Bezirksamt Test",
                                         jahr=2026, monat=6, datum=date(2026, 7, 1),
                                         betrag=Decimal("100.00"),
                                         status=Rechnungsstatus.GESTELLT)

    def test_direktes_storno_gestellter_rechnung_geblockt(self):
        resp = self.client.post(reverse("nachweis:rechnung_status", args=[self.r.id]),
                                {"status": "storniert"})
        self.assertEqual(resp.status_code, 302)
        self.r.refresh_from_db()
        self.assertEqual(self.r.status, Rechnungsstatus.GESTELLT)      # unverändert

    def test_direktes_storno_entwurf_erlaubt(self):
        self.r.status = Rechnungsstatus.ENTWURF
        self.r.save(update_fields=["status"])
        self.client.post(reverse("nachweis:rechnung_status", args=[self.r.id]),
                         {"status": "storniert"})
        self.r.refresh_from_db()
        self.assertEqual(self.r.status, Rechnungsstatus.STORNIERT)

    def test_gutschrift_view(self):
        resp = self.client.post(reverse("nachweis:rechnung_gutschrift", args=[self.r.id]))
        self.assertEqual(resp.status_code, 302)
        g = Rechnung.objects.get(typ=Rechnungstyp.GUTSCHRIFT)
        self.assertEqual(g.storno_zu, self.r)
        # Detailseite der Gutschrift rendert mit Banner
        d = self.client.get(reverse("nachweis:rechnung_detail", args=[g.id]))
        self.assertContains(d, "Gutschrift")
        self.assertContains(d, self.r.nummer)

    def test_xrechnung_fuer_gutschrift_geblockt(self):
        self.client.post(reverse("nachweis:rechnung_gutschrift", args=[self.r.id]))
        g = Rechnung.objects.get(typ=Rechnungstyp.GUTSCHRIFT)
        resp = self.client.get(reverse("nachweis:rechnung_xrechnung", args=[g.id]))
        self.assertEqual(resp.status_code, 302)               # redirect statt XML


class HistorieTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="TBEW", typ=Teamtyp.values[0])
        self.betr = Mitarbeiter.objects.create(
            user=User.objects.create_user("b2", password="x"),
            name="B", rolle=Rolle.USER, team=self.team, kuerzel="b2")

    def test_rechnung_versioniert(self):
        r = Rechnung.objects.create(nummer="2026-0202", empfaenger="Bezirksamt Test",
                                    jahr=2026, monat=6, datum=date(2026, 7, 1),
                                    betrag=Decimal("100.00"))
        r.status = Rechnungsstatus.GESTELLT
        r.save()
        self.assertEqual(r.history.count(), 2)                # anlegen + ändern
        delta = r.history.first().diff_against(r.history.last())
        self.assertIn("status", [c.field for c in delta.changes])

    def test_bewilligung_versioniert(self):
        kt = Kostentraeger.objects.create(name="Bezirksamt Test")
        k = Klient.objects.create(nachname="K", team=self.team,
                                  bezugsbetreuer=self.betr, status=Status.BETREUUNG)
        b = Bewilligung.objects.create(klient=k, kostentraeger=kt,
                                       fls_woche=Decimal("2.95"), kle_tag=Decimal("0.722167"))
        b.fls_woche = Decimal("3.81")
        b.save()
        self.assertEqual(b.history.count(), 2)
        aelteste = b.history.last()
        self.assertEqual(aelteste.fls_woche, Decimal("2.95"))  # alter Stand rekonstruierbar

"""Tests Phase 3 / Slice 3a: Controlling-Cockpit (Erlöse, OP, Quoten, Funnel, Zugriff)."""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import (Team, Teamtyp, Mitarbeiter, Rolle, Klient, Status,
                     Rechnung, Rechnungsstatus, Rechnungstyp, Zahlung)
from .views_controlling import _erloese_je_monat, _op_stand

User = get_user_model()


class ControllingBasis(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="TBEW", typ=Teamtyp.values[0])
        lu = User.objects.create_user("chef", password="x")
        m = Mitarbeiter.objects.create(user=lu, name="Chef", rolle=Rolle.LEITUNG, kuerzel="ch")
        m.leitet.set([self.team])
        self.leitung = lu
        vw_team = Team.objects.create(name="Verwaltung", typ=Teamtyp.VERWALTUNG)
        vu = User.objects.create_user("verw", password="x")
        Mitarbeiter.objects.create(user=vu, name="V", rolle=Rolle.USER, team=vw_team, kuerzel="v")
        self.verwaltung = vu
        uu = User.objects.create_user("norm", password="x")
        Mitarbeiter.objects.create(user=uu, name="N", rolle=Rolle.USER, team=self.team, kuerzel="n")
        self.user = uu


class ErloeseTests(ControllingBasis):
    def test_fakturiert_saldiert_gutschriften(self):
        Rechnung.objects.create(nummer="2026-0301", empfaenger="BA", jahr=2026, monat=5,
                                datum=date(2026, 6, 1), betrag=Decimal("1000.00"),
                                status=Rechnungsstatus.GESTELLT)
        Rechnung.objects.create(nummer="2026-0302", empfaenger="BA", jahr=2026, monat=5,
                                datum=date(2026, 6, 15), betrag=Decimal("-200.00"),
                                typ=Rechnungstyp.GUTSCHRIFT,
                                status=Rechnungsstatus.GESTELLT)
        Rechnung.objects.create(nummer="2026-0303", empfaenger="BA", jahr=2026, monat=5,
                                datum=date(2026, 6, 20), betrag=Decimal("500.00"),
                                status=Rechnungsstatus.ENTWURF)      # zählt NICHT
        fakturiert, _ = _erloese_je_monat(2026)
        self.assertEqual(fakturiert[6], Decimal("800.00"))           # 1000 - 200

    def test_zahlungseingang_nach_zahldatum(self):
        r = Rechnung.objects.create(nummer="2026-0304", empfaenger="BA", jahr=2026, monat=5,
                                    datum=date(2026, 6, 1), betrag=Decimal("300.00"),
                                    status=Rechnungsstatus.GESTELLT)
        Zahlung.objects.create(rechnung=r, datum=date(2026, 7, 3), betrag=Decimal("300.00"))
        _, eingang = _erloese_je_monat(2026)
        self.assertEqual(eingang[6], Decimal("0"))
        self.assertEqual(eingang[7], Decimal("300.00"))

    def test_op_stand(self):
        Rechnung.objects.create(nummer="2026-0305", empfaenger="BA", jahr=2026, monat=5,
                                datum=date.today() - timedelta(days=60),
                                faellig_am=date.today() - timedelta(days=30),
                                betrag=Decimal("100.00"), status=Rechnungsstatus.GESTELLT)
        op = _op_stand()
        self.assertEqual(op["anzahl"], 1)
        self.assertEqual(op["n_ueberfaellig"], 1)
        self.assertEqual(op["ueberfaellig"], Decimal("100.00"))


class ControllingViewTests(ControllingBasis):
    def test_leitung_und_verwaltung_sehen_cockpit(self):
        for u in (self.leitung, self.verwaltung):
            self.client.force_login(u)
            resp = self.client.get(reverse("nachweis:controlling"))
            self.assertEqual(resp.status_code, 200, u.username)
            self.assertContains(resp, "Controlling")

    def test_normaler_user_nicht(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse("nachweis:controlling"))
        self.assertEqual(resp.status_code, 302)          # redirect zu start
        resp = self.client.get(reverse("nachweis:controlling_csv"))
        self.assertEqual(resp.status_code, 302)

    def test_csv_export(self):
        Rechnung.objects.create(nummer="2026-0306", empfaenger="BA", jahr=2026, monat=5,
                                datum=date(2026, 3, 1), betrag=Decimal("250.00"),
                                status=Rechnungsstatus.BEZAHLT)
        self.client.force_login(self.verwaltung)
        resp = self.client.get(reverse("nachweis:controlling_csv"), {"jahr": 2026})
        self.assertEqual(resp.status_code, 200)
        text = resp.content.decode("utf-8-sig")
        self.assertIn("03.2026;250.00", text)
        self.assertIn("SUMME;250.00", text)

    def test_kaputte_parameter_kein_500(self):
        self.client.force_login(self.leitung)
        resp = self.client.get(reverse("nachweis:controlling"), {"jahr": "abc", "monat": "xx"})
        self.assertEqual(resp.status_code, 200)          # Fallback auf heute


class DashboardZugriffTests(ControllingBasis):
    """FLS-/Vergütungs-Dashboard: Leitung UND Verwaltung (Finanz-Hub, read-only),
    normale Betreuer*innen sowie Admin sind gesperrt."""
    def setUp(self):
        super().setUp()
        self.k = Klient.objects.create(
            nachname="Muster", team=self.team,
            bezugsbetreuer=Mitarbeiter.objects.get(user=self.user),
            status=Status.BETREUUNG)

    def test_leitung_sieht_dashboard(self):
        self.client.force_login(self.leitung)
        self.assertEqual(self.client.get(reverse("nachweis:dashboard")).status_code, 200)

    def test_verwaltung_sieht_alle_klienten(self):
        self.client.force_login(self.verwaltung)
        r = self.client.get(reverse("nachweis:dashboard"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["kennzahlen"]["klienten"], 1)          # sieht alle
        self.assertTrue(any(z["klient"].id == self.k.id for z in r.context["zeilen"]))

    def test_normaler_user_gesperrt(self):
        self.client.force_login(self.user)
        r = self.client.get(reverse("nachweis:dashboard"))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("nachweis:start"))
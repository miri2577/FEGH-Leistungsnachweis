"""Tests Klient-Fallakte (Detailseite + Reiter) und Belegungslisten-Badges."""
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from . import services
from .models import (Team, Teamtyp, Mitarbeiter, Rolle, Klient, Status,
                     Leistung, Leistungsart, Kostentraeger, Bewilligung,
                     BewilligungStatus)

User = get_user_model()


class FallakteBasis(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="TBEW", typ=Teamtyp.BEW)
        self.u = User.objects.create_user("chef", password="x")
        self.lu = Mitarbeiter.objects.create(user=self.u, name="Chef", rolle=Rolle.LEITUNG, kuerzel="c")
        self.lu.leitet.set([self.team])
        self.k = Klient.objects.create(nachname="Alpha", vorname="A", team=self.team,
                                       bezugsbetreuer=self.lu, status=Status.BETREUUNG, hbg=3)
        self.client.force_login(self.u)


class FallakteViewTests(FallakteBasis):
    def test_detail_zeigt_reiter_und_kennzahlen(self):
        r = self.client.get(reverse("nachweis:klient_detail", args=[self.k.id]))
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        self.assertIn("fa-tabs", html)              # Reiter-Leiste
        self.assertIn("Alpha", html)
        self.assertIn("aktive Ziele", html)         # KPI-Kachel

    def test_verlauf_zeigt_dokumentierte_leistungen(self):
        Leistung.objects.create(datum=date(2026, 6, 1), klient=self.k,
                                leistungsart=Leistungsart.FS, betreuer=self.lu,
                                dokumentation="Hausbesuch, Gespräch geführt.")
        Leistung.objects.create(datum=date(2026, 6, 2), klient=self.k,
                                leistungsart=Leistungsart.FS, betreuer=self.lu)  # ohne Doku
        r = self.client.get(reverse("nachweis:klient_verlauf", args=[self.k.id]))
        self.assertContains(r, "Hausbesuch, Gespräch geführt.")
        self.assertContains(r, "1 Eintrag")         # nur die dokumentierte zählt

    def test_fremdes_team_404(self):
        fremd = Klient.objects.create(nachname="Fremd",
                                      team=Team.objects.create(name="X", typ=Teamtyp.BEW),
                                      bezugsbetreuer=self.lu, status=Status.BETREUUNG)
        for name in ("klient_detail", "klient_verlauf"):
            self.assertEqual(self.client.get(
                reverse(f"nachweis:{name}", args=[fremd.id])).status_code, 404)

    def test_belegungsliste_hat_oeffnen_statt_vieler_buttons(self):
        r = self.client.get(reverse("nachweis:belegungsliste"))
        html = r.content.decode()
        self.assertIn(f"/klient/{self.k.id}/", html)   # Name/Öffnen -> Fallakte
        self.assertIn("Öffnen", html)


class HinweisBadgeTests(FallakteBasis):
    def test_keine_bewilligung_badge(self):
        hinweise = services.klient_hinweise(self.k)
        self.assertTrue(any("keine Bewilligung" in h["text"] for h in hinweise))

    def test_auslaufende_bewilligung_badge(self):
        kt = Kostentraeger.objects.create(name="Bezirksamt Mitte")
        Bewilligung.objects.create(klient=self.k, kostentraeger=kt,
                                   gueltig_von=date.today() - timedelta(days=300),
                                   gueltig_bis=date.today() + timedelta(days=30),
                                   status=BewilligungStatus.AKTIV)
        hinweise = services.klient_hinweise(self.k)
        self.assertTrue(any("endet in" in h["text"] for h in hinweise))

    def test_beendete_betreuung_keine_hinweise(self):
        self.k.status = Status.BEENDIGUNG
        self.k.save()
        self.assertEqual(services.klient_hinweise(self.k), [])

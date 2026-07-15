"""Tests Barbetrags-/Verwahrgeldverwaltung (treuhänderische Klientenkonten)."""
from datetime import date
from decimal import Decimal

from django.test import TestCase, Client
from django.contrib.auth import get_user_model

from . import services_loeschfristen as lf
from .models import (Team, Teamtyp, Mitarbeiter, Rolle, Klient, Status,
                     Klientenkonto, Kontobuchung)

User = get_user_model()


class KlientenkontoTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="TK", typ=Teamtyp.BEW)
        u = User.objects.create_user("mk", password="x")
        self.m = Mitarbeiter.objects.create(user=u, name="M", rolle=Rolle.USER,
                                            team=self.team, kuerzel="m")
        self.k = Klient.objects.create(nachname="Barb", team=self.team,
                                       bezugsbetreuer=self.m, status=Status.BETREUUNG)
        self.tb = Team.objects.create(name="TKB", typ=Teamtyp.BEW)
        mb = Mitarbeiter.objects.create(user=User.objects.create_user("mb2", password="x"),
                                        name="B", rolle=Rolle.USER, team=self.tb, kuerzel="b2")
        self.kb = Klient.objects.create(nachname="Fremd", team=self.tb,
                                        bezugsbetreuer=mb, status=Status.BETREUUNG)
        self.c = Client(); self.c.force_login(u)

    def test_konto_anlegen_und_buchen(self):
        self.c.post(f"/klienten/{self.k.id}/konto/anlegen/", {"typ": "barbetrag"})
        konto = self.k.konten.first()
        self.c.post(f"/klienten/{self.k.id}/konto/buchung/",
                    {"konto": konto.id, "betrag": "100", "zweck": "Einzahlung", "datum": "2026-07-01"})
        self.c.post(f"/klienten/{self.k.id}/konto/buchung/",
                    {"konto": konto.id, "betrag": "-30,50", "zweck": "Kiosk", "datum": "2026-07-02"})
        self.assertEqual(konto.saldo, Decimal("69.50"))

    def test_ueberziehung_blockiert(self):
        konto = Klientenkonto.objects.create(klient=self.k)
        self.c.post(f"/klienten/{self.k.id}/konto/buchung/",
                    {"konto": konto.id, "betrag": "-50", "zweck": "zu viel"})
        self.assertEqual(konto.buchungen.count(), 0)

    def test_konto_mit_buchungen_nicht_loeschbar(self):
        konto = Klientenkonto.objects.create(klient=self.k)
        Kontobuchung.objects.create(konto=konto, datum=date(2026, 7, 1),
                                    betrag=Decimal("10"), zweck="x")
        self.c.post(f"/klienten/{self.k.id}/konto/loeschen/", {"id": konto.id})
        self.assertTrue(Klientenkonto.objects.filter(pk=konto.pk).exists())

    def test_fremdteam_kein_zugriff(self):
        konto = Klientenkonto.objects.create(klient=self.kb)
        self.assertEqual(self.c.get(f"/klienten/{self.kb.id}/konto/").status_code, 404)
        # auch Buchen auf Fremdkonto über eigene Klient-URL scheitert
        self.c.post(f"/klienten/{self.k.id}/konto/buchung/",
                    {"konto": konto.id, "betrag": "10", "zweck": "hack"})
        self.assertEqual(konto.buchungen.count(), 0)

    def test_anonymisierung_loescht_konten(self):
        Klientenkonto.objects.create(klient=self.k)
        lf.anonymisieren(self.k, stufe="voll", apply=True)
        self.assertEqual(self.k.konten.count(), 0)

    def test_seite_laedt(self):
        r = self.c.get(f"/klienten/{self.k.id}/konto/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Barbetrag")

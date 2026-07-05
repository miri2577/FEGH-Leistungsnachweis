"""Tests für den Unterwegs-Modus (mobile Vor-Ort-Doku): Besuch + separate WFS-Doku,
Team-Scoping, Verwaltung ausgeschlossen."""
from datetime import date, time, timedelta
from decimal import Decimal

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone

from . import services
from .models import (Team, Teamtyp, Mitarbeiter, Klient, Rolle, Status,
                     Leistung, Leistungsart, Termin)

User = get_user_model()


class FeldTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.team = Team.objects.create(name="T", typ=Teamtyp.BEW)
        cls.team_vw = Team.objects.create(name="VW", typ=Teamtyp.VERWALTUNG)
        cls.team_b = Team.objects.create(name="B", typ=Teamtyp.BEW)
        cls.uA = User.objects.create_user("ada", password="pw")
        cls.mA = Mitarbeiter.objects.create(user=cls.uA, name="Ada", rolle=Rolle.USER, team=cls.team)
        cls.uV = User.objects.create_user("val", password="pw")
        cls.mV = Mitarbeiter.objects.create(user=cls.uV, name="Val", rolle=Rolle.USER, team=cls.team_vw)
        cls.uB = User.objects.create_user("ben", password="pw")
        cls.mB = Mitarbeiter.objects.create(user=cls.uB, name="Ben", rolle=Rolle.USER, team=cls.team_b)
        cls.kA = Klient.objects.create(nachname="Alpha", team=cls.team, bezugsbetreuer=cls.mA,
                                       status=Status.BETREUUNG)
        cls.kB = Klient.objects.create(nachname="Beta", team=cls.team_b, bezugsbetreuer=cls.mB,
                                       status=Status.BETREUUNG)

    def cl(self, u):
        c = Client()
        c.force_login(u)
        return c

    def test_seite_zeigt_heutigen_termin(self):
        Termin.objects.create(mitarbeiter=self.mA, klient=self.kA, datum=timezone.localdate(),
                              beginn=time(10, 0), ende=time(10, 45))
        r = self.cl(self.uA).get("/unterwegs/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Alpha")

    def test_speichern_erzeugt_besuch_und_wfs_doku(self):
        r = self.cl(self.uA).post("/unterwegs/speichern/", {
            "klient": self.kA.id, "datum": "2026-06-10", "beginn": "10:00", "ende": "10:45",
            "leistungsart": "FS", "taetigkeit": "Hausbesuch", "dokumentation": "Verlauf",
            "doku_minuten": "15"})
        self.assertEqual(r.status_code, 302)
        ls = Leistung.objects.filter(klient=self.kA, datum=date(2026, 6, 10))
        self.assertEqual(ls.count(), 2)
        besuch = ls.get(leistungsart="FS")
        doku = ls.get(leistungsart="WFS")
        self.assertEqual(besuch.dauer_stunden, Decimal("0.750"))
        self.assertEqual((doku.beginn, doku.ende), (time(10, 45), time(11, 0)))
        self.assertEqual(doku.dauer_stunden, Decimal("0.250"))
        self.assertEqual(doku.taetigkeit, "Dokumentation")

    def test_ohne_doku_zeit_nur_ein_eintrag(self):
        self.cl(self.uA).post("/unterwegs/speichern/", {
            "klient": self.kA.id, "datum": "2026-06-11", "beginn": "09:00", "ende": "10:00",
            "leistungsart": "FS", "doku_minuten": "0"})
        self.assertEqual(Leistung.objects.filter(klient=self.kA, datum=date(2026, 6, 11)).count(), 1)

    def test_fremdteam_klient_nicht_speicherbar(self):
        self.cl(self.uA).post("/unterwegs/speichern/", {
            "klient": self.kB.id, "datum": "2026-06-10", "beginn": "10:00", "ende": "11:00"})
        self.assertEqual(Leistung.objects.filter(klient=self.kB).count(), 0)

    def test_verwaltung_umgeleitet(self):
        r = self.cl(self.uV).get("/unterwegs/")
        self.assertEqual(r.status_code, 302)          # Verwaltung -> keine Klientenarbeit

    def test_termin_wird_verknuepft_und_dokumentiert(self):
        t = Termin.objects.create(mitarbeiter=self.mA, klient=self.kA, datum=date(2026, 6, 10),
                                  beginn=time(10, 0), ende=time(10, 45))
        self.cl(self.uA).post("/unterwegs/speichern/", {
            "klient": self.kA.id, "termin": t.id, "datum": "2026-06-10",
            "beginn": "10:00", "ende": "10:45", "leistungsart": "FS", "doku_minuten": "0"})
        besuch = Leistung.objects.get(klient=self.kA, leistungsart="FS", datum=date(2026, 6, 10))
        self.assertEqual(besuch.termin_id, t.id)
        self.assertTrue(t.dokumentationen.exists())

    def test_undokumentierte_termine_erinnerung(self):
        vor3 = timezone.localdate() - timedelta(days=3)
        t = Termin.objects.create(mitarbeiter=self.mA, klient=self.kA, datum=vor3,
                                  beginn=time(9, 0), ende=time(10, 0))
        self.assertIn(t, services.undokumentierte_termine(self.mA))
        # nach Dokumentation (verknüpfte Leistung) verschwindet die Erinnerung
        Leistung.objects.create(datum=vor3, klient=self.kA, leistungsart=Leistungsart.FS,
                                betreuer=self.mA, beginn=time(9, 0), ende=time(10, 0), termin=t)
        self.assertNotIn(t, services.undokumentierte_termine(self.mA))

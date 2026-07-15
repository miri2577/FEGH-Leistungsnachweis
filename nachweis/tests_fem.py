"""Tests FEM-Dokumentation (freiheitsentziehende Maßnahmen)."""
from datetime import date, datetime, timedelta

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone

from . import services_loeschfristen as lf
from .models import Team, Teamtyp, Mitarbeiter, Rolle, Klient, Status, FEM

User = get_user_model()


class FEMTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="TF", typ=Teamtyp.BEW)
        u = User.objects.create_user("mf", password="x")
        self.m = Mitarbeiter.objects.create(user=u, name="M", rolle=Rolle.USER,
                                            team=self.team, kuerzel="m")
        self.k = Klient.objects.create(nachname="Fem", team=self.team,
                                       bezugsbetreuer=self.m, status=Status.BETREUUNG)
        self.tb = Team.objects.create(name="TFB", typ=Teamtyp.BEW)
        mb = Mitarbeiter.objects.create(user=User.objects.create_user("mfb", password="x"),
                                        name="B", rolle=Rolle.USER, team=self.tb, kuerzel="b")
        self.kb = Klient.objects.create(nachname="Fremd", team=self.tb,
                                        bezugsbetreuer=mb, status=Status.BETREUUNG)
        self.c = Client(); self.c.force_login(u)

    def test_anlegen(self):
        self.c.post(f"/klienten/{self.k.id}/fem/speichern/", {
            "art": "fixierung", "beginn": "2026-07-01T10:00", "grund": "Sturzgefahr",
            "genehmigung_az": "XVII 123/26", "einwilligung": "on"})
        self.assertEqual(self.k.fem_massnahmen.count(), 1)
        f = self.k.fem_massnahmen.first()
        self.assertTrue(f.laeuft)
        self.assertTrue(f.einwilligung)

    def test_beenden(self):
        f = FEM.objects.create(klient=self.k, art="fixierung",
                               beginn=timezone.now(), grund="x")
        self.c.post(f"/klienten/{self.k.id}/fem/beenden/", {"id": f.id})
        f.refresh_from_db()
        self.assertFalse(f.laeuft)

    def test_genehmigung_faellig_markiert(self):
        FEM.objects.create(klient=self.k, art="tuer", beginn=timezone.now(), grund="x",
                           genehmigt_bis=date.today() + timedelta(days=10))
        r = self.c.get(f"/klienten/{self.k.id}/fem/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "warnrow")

    def test_loeschen(self):
        f = FEM.objects.create(klient=self.k, art="bettgitter", beginn=timezone.now(), grund="x")
        self.c.post(f"/klienten/{self.k.id}/fem/loeschen/", {"id": f.id})
        self.assertEqual(FEM.objects.count(), 0)

    def test_fremdteam_kein_zugriff(self):
        self.assertEqual(self.c.get(f"/klienten/{self.kb.id}/fem/").status_code, 404)

    def test_anonymisierung_loescht(self):
        FEM.objects.create(klient=self.k, art="fixierung", beginn=timezone.now(), grund="x")
        lf.anonymisieren(self.k, stufe="voll", apply=True)
        self.assertEqual(self.k.fem_massnahmen.count(), 0)

"""Tests Fortbildungs-/Qualifikationsverwaltung."""
from datetime import date, timedelta

from django.test import TestCase, Client
from django.contrib.auth import get_user_model

from .models import Team, Teamtyp, Mitarbeiter, Rolle, Qualifikation

User = get_user_model()


class QualifikationTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="TQ", typ=Teamtyp.BEW)
        lu = User.objects.create_user("lq", password="x")
        self.lead = Mitarbeiter.objects.create(user=lu, name="L", rolle=Rolle.LEITUNG, kuerzel="l")
        self.lead.leitet.set([self.team])
        self.ma = Mitarbeiter.objects.create(
            user=User.objects.create_user("mq", password="x"), name="Muster",
            rolle=Rolle.USER, team=self.team, kuerzel="mu")
        self.tb = Team.objects.create(name="TQB", typ=Teamtyp.BEW)
        self.fremd = Mitarbeiter.objects.create(
            user=User.objects.create_user("fq", password="x"), name="Fremd",
            rolle=Rolle.USER, team=self.tb, kuerzel="fx")
        self.c = Client(); self.c.force_login(lu)

    def test_anlegen(self):
        self.c.post("/qualifikationen/speichern/", {
            "mitarbeiter": self.ma.id, "art": "fortbildung",
            "bezeichnung": "Erste-Hilfe", "gueltig_bis": "2027-01-01", "pflicht": "on"})
        self.assertEqual(self.ma.qualifikationen.count(), 1)
        q = self.ma.qualifikationen.first()
        self.assertEqual(q.bezeichnung, "Erste-Hilfe")
        self.assertTrue(q.pflicht)

    def test_fremdteam_ma_nicht_zuweisbar(self):
        self.c.post("/qualifikationen/speichern/", {
            "mitarbeiter": self.fremd.id, "art": "fortbildung", "bezeichnung": "X"})
        self.assertEqual(Qualifikation.objects.count(), 0)

    def test_faellig_panel(self):
        Qualifikation.objects.create(mitarbeiter=self.ma, bezeichnung="Bald ab",
                                     gueltig_bis=date.today() + timedelta(days=10))
        Qualifikation.objects.create(mitarbeiter=self.ma, bezeichnung="Weit",
                                     gueltig_bis=date.today() + timedelta(days=300))
        r = self.c.get("/qualifikationen/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Fällig / abgelaufen")
        self.assertContains(r, "Bald ab")

    def test_loeschen(self):
        q = Qualifikation.objects.create(mitarbeiter=self.ma, bezeichnung="Weg")
        self.c.post("/qualifikationen/loeschen/", {"id": q.id})
        self.assertEqual(Qualifikation.objects.count(), 0)

    def test_fremdteam_quali_nicht_loeschbar(self):
        q = Qualifikation.objects.create(mitarbeiter=self.fremd, bezeichnung="Fremd-Q")
        self.c.post("/qualifikationen/loeschen/", {"id": q.id})
        self.assertTrue(Qualifikation.objects.filter(pk=q.pk).exists())

    def test_user_kein_zugriff(self):
        self.c.force_login(self.ma.user)
        self.assertEqual(self.c.get("/qualifikationen/").status_code, 302)

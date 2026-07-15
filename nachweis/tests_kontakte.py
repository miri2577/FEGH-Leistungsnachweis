"""Tests Kontaktpersonen-Management (Beteiligtenstruktur je Klient*in)."""
from django.test import TestCase, Client
from django.contrib.auth import get_user_model

from . import services_loeschfristen as lf
from .models import (Team, Teamtyp, Mitarbeiter, Rolle, Klient, Status, Kontaktperson)

User = get_user_model()


class KontakteTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="TK", typ=Teamtyp.BEW)
        u = User.objects.create_user("mk", password="x")
        self.m = Mitarbeiter.objects.create(user=u, name="M", rolle=Rolle.USER,
                                            team=self.team, kuerzel="m")
        self.k = Klient.objects.create(nachname="K", team=self.team, bezugsbetreuer=self.m,
                                       status=Status.BETREUUNG)
        self.team_b = Team.objects.create(name="TB", typ=Teamtyp.BEW)
        ub = User.objects.create_user("mb", password="x")
        self.mb = Mitarbeiter.objects.create(user=ub, name="B", rolle=Rolle.USER,
                                             team=self.team_b, kuerzel="b")
        self.kb = Klient.objects.create(nachname="B", team=self.team_b, bezugsbetreuer=self.mb,
                                        status=Status.BETREUUNG)
        self.c = Client(); self.c.force_login(u)

    def test_anlegen_und_liste(self):
        self.c.post(f"/kontakte/{self.k.id}/speichern/", {
            "rolle": "arzt", "name": "Dr. Meier", "telefon": "030-1", "notfall": "on"})
        self.assertEqual(self.k.kontakte.count(), 1)
        kp = self.k.kontakte.first()
        self.assertEqual(kp.name, "Dr. Meier")
        self.assertTrue(kp.notfall)
        self.assertContains(self.c.get(f"/kontakte/{self.k.id}/"), "Dr. Meier")

    def test_bearbeiten(self):
        kp = Kontaktperson.objects.create(klient=self.k, name="Alt", rolle="angehoerige")
        self.c.post(f"/kontakte/{self.k.id}/speichern/",
                    {"id": kp.id, "rolle": "angehoerige", "name": "Neu"})
        kp.refresh_from_db()
        self.assertEqual(kp.name, "Neu")

    def test_loeschen(self):
        kp = Kontaktperson.objects.create(klient=self.k, name="X", rolle="notfall")
        self.c.post(f"/kontakte/{self.k.id}/loeschen/", {"id": kp.id})
        self.assertEqual(self.k.kontakte.count(), 0)

    def test_fremdteam_kein_zugriff(self):
        self.assertEqual(self.c.get(f"/kontakte/{self.kb.id}/").status_code, 404)

    def test_speichern_fremdklient_kontakt_gescopt(self):
        # Fremdklient-Kontakt lässt sich nicht über die eigene Klient-URL manipulieren
        kp = Kontaktperson.objects.create(klient=self.kb, name="Fremd", rolle="arzt")
        r = self.c.post(f"/kontakte/{self.k.id}/speichern/",
                        {"id": kp.id, "rolle": "arzt", "name": "Hack"})
        self.assertEqual(r.status_code, 403)
        kp.refresh_from_db()
        self.assertEqual(kp.name, "Fremd")

    def test_name_pflicht(self):
        self.c.post(f"/kontakte/{self.k.id}/speichern/", {"rolle": "arzt", "name": ""})
        self.assertEqual(self.k.kontakte.count(), 0)

    def test_anonymisierung_loescht_kontakte(self):
        Kontaktperson.objects.create(klient=self.k, name="Angeh", rolle="angehoerige")
        lf.anonymisieren(self.k, stufe="voll", apply=True)
        self.assertEqual(self.k.kontakte.count(), 0)

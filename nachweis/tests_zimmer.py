"""Tests Zimmer-/Platzverwaltung (stationäre Wohnform)."""
from datetime import date, timedelta

from django.test import TestCase, Client
from django.contrib.auth import get_user_model

from .models import (Team, Teamtyp, Mitarbeiter, Rolle, Klient, Status,
                     Angebot, AngebotsTyp, Belegung, Zimmer)

User = get_user_model()


class ZimmerTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="TZ", typ=Teamtyp.BEW)
        lu = User.objects.create_user("lz", password="x")
        self.lead = Mitarbeiter.objects.create(user=lu, name="L", rolle=Rolle.LEITUNG, kuerzel="l")
        self.lead.leitet.set([self.team])
        self.angebot = Angebot.objects.create(name="Wohnheim A", team=self.team,
                                              typ=AngebotsTyp.BESONDERE_WOHNFORM, plaetze=10)
        self.k = Klient.objects.create(nachname="Wohn", team=self.team,
                                       bezugsbetreuer=self.lead, status=Status.BETREUUNG)
        self.c = Client(); self.c.force_login(lu)

    def test_zimmer_anlegen(self):
        self.c.post(f"/angebote/{self.angebot.id}/zimmer/",
                    {"name": "101", "plaetze": "2", "etage": "EG", "aktiv": "on"})
        self.assertEqual(self.angebot.zimmer.count(), 1)
        self.assertEqual(self.angebot.zimmer.first().plaetze, 2)

    def test_belegung_und_frei(self):
        z = Zimmer.objects.create(angebot=self.angebot, name="102", plaetze=2)
        Belegung.objects.create(klient=self.k, angebot=self.angebot, zimmer=z,
                                einzug=date.today() - timedelta(days=5))
        r = self.c.get(f"/angebote/{self.angebot.id}/zimmer/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Wohn")
        self.assertEqual(z.belegt_am(date.today()), 1)

    def test_zimmer_unique_je_angebot(self):
        Zimmer.objects.create(angebot=self.angebot, name="101")
        self.c.post(f"/angebote/{self.angebot.id}/zimmer/", {"name": "101", "plaetze": "1"})
        self.assertEqual(self.angebot.zimmer.filter(name="101").count(), 1)

    def test_loeschen_behaelt_belegung(self):
        z = Zimmer.objects.create(angebot=self.angebot, name="103")
        b = Belegung.objects.create(klient=self.k, angebot=self.angebot, zimmer=z, einzug=date.today())
        self.c.post("/zimmer/loeschen/", {"id": z.id})
        b.refresh_from_db()
        self.assertIsNone(b.zimmer_id)
        self.assertTrue(Belegung.objects.filter(pk=b.pk).exists())

    def test_belegung_mit_zimmer_zuweisen(self):
        z = Zimmer.objects.create(angebot=self.angebot, name="104")
        self.c.post("/belegung/speichern/", {
            "angebot": self.angebot.id, "klient": self.k.id,
            "einzug": date.today().isoformat(), "zimmer": z.id})
        self.assertEqual(self.k.belegungen.first().zimmer_id, z.id)

    def test_fremd_team_kein_zugriff(self):
        tb = Team.objects.create(name="TZB", typ=Teamtyp.BEW)
        ab = Angebot.objects.create(name="Fremd", team=tb, typ=AngebotsTyp.BESONDERE_WOHNFORM)
        self.assertEqual(self.c.get(f"/angebote/{ab.id}/zimmer/").status_code, 404)

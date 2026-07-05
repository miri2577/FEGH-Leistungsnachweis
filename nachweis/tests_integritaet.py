"""Datenmodell-Absicherung (P2): Team-Löschung darf keine abhängigen Datensätze
mitreißen (PROTECT statt CASCADE/SET_NULL) und Beleg-Nummern sind je Kassenmonat
eindeutig (kein Doppel bei Parallelzugriff)."""
from datetime import date

from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase, Client
from django.contrib.auth import get_user_model

from .models import (Team, Teamtyp, Mitarbeiter, Klient, Rolle, Status,
                     Kasse, Kassenmonat, Kassenbuchung)

User = get_user_model()


class IntegritaetTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.team = Team.objects.create(name="T", typ=Teamtyp.BEW)
        cls.team_vw = Team.objects.create(name="VW", typ=Teamtyp.VERWALTUNG)
        cls.admin_u = User.objects.create_user("adm", password="pw")
        cls.admin_m = Mitarbeiter.objects.create(user=cls.admin_u, name="Adm",
                                                 rolle=Rolle.ADMIN, team=cls.team_vw)
        cls.mA = Mitarbeiter.objects.create(name="Betr", rolle=Rolle.USER, team=cls.team)

    def _cl(self, u):
        c = Client()
        c.force_login(u)
        return c

    # --- Team-Löschung schützt abhängige Datensätze ---------------------
    def test_team_mit_kasse_nicht_loeschbar_kasse_bleibt(self):
        t2 = Team.objects.create(name="T2", typ=Teamtyp.BEW)      # keine Mitglieder/Klienten
        Kasse.objects.create(team=t2, bezeichnung="K")
        self._cl(self.admin_u).post("/teams/aktion/", {"id": t2.id, "aktion": "loeschen"})
        self.assertTrue(Team.objects.filter(pk=t2.id).exists())    # früher CASCADE -> jetzt geschützt
        self.assertTrue(Kasse.objects.filter(team=t2).exists())    # Kassenbuch überlebt

    def test_klient_team_protect_backstop(self):
        Klient.objects.create(nachname="X", team=self.team, bezugsbetreuer=self.mA,
                              status=Status.BETREUUNG)
        with self.assertRaises(ProtectedError):                    # DB-Backstop unabhängig von der View
            with transaction.atomic():
                self.team.delete()

    def test_team_ohne_abhaengige_loeschbar(self):
        leer = Team.objects.create(name="leer", typ=Teamtyp.BEW)
        self._cl(self.admin_u).post("/teams/aktion/", {"id": leer.id, "aktion": "loeschen"})
        self.assertFalse(Team.objects.filter(pk=leer.id).exists())

    # --- Beleg-Nr eindeutig je Kassenmonat -----------------------------
    def test_belegnr_eindeutig_pro_kassenmonat(self):
        kasse = Kasse.objects.create(team=self.team, bezeichnung="K")
        km = Kassenmonat.objects.create(kasse=kasse, jahr=2026, monat=6)
        Kassenbuchung.objects.create(monat=km, bel_nr=1, datum=date(2026, 6, 1), text="a")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Kassenbuchung.objects.create(monat=km, bel_nr=1, datum=date(2026, 6, 2), text="b")

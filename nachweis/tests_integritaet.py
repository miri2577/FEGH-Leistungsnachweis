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

    # --- Kasse: nur Verantwortliche/Vertretung/Leitung sehen sie -------
    def test_kasse_nur_fuer_zustaendige(self):
        from . import services
        kasse = Kasse.objects.create(team=self.team, bezeichnung="K")
        uV1 = User.objects.create_user("vera", password="pw")
        mV1 = Mitarbeiter.objects.create(user=uV1, name="Vera", rolle=Rolle.USER, team=self.team)
        uV2 = User.objects.create_user("veit", password="pw")
        mV2 = Mitarbeiter.objects.create(user=uV2, name="Veit", rolle=Rolle.USER, team=self.team)
        uX = User.objects.create_user("xavo", password="pw")
        Mitarbeiter.objects.create(user=uX, name="Xavo", rolle=Rolle.USER, team=self.team)
        uL = User.objects.create_user("lena", password="pw")
        mL = Mitarbeiter.objects.create(user=uL, name="Lena", rolle=Rolle.LEITUNG, team=self.team)
        mL.leitet.set([self.team])

        # ohne Zuständigkeit: normale User sehen die Kasse NICHT, Leitung schon
        self.assertFalse(services.kassen_fuer(uV1).exists())
        self.assertFalse(services.kassen_fuer(uX).exists())
        self.assertTrue(services.kassen_fuer(uL).exists())

        # Leitung legt Zuständigkeit fest
        r = self._cl(uL).post("/kasse/zustaendigkeit/",
                              {"kasse": kasse.id, "verantwortlich": mV1.id, "vertretung": mV2.id})
        self.assertEqual(r.status_code, 302)
        kasse.refresh_from_db()
        self.assertEqual(kasse.verantwortlich_id, mV1.id)
        # jetzt sehen Verantwortliche*r + Vertretung die Kasse, andere weiterhin nicht
        self.assertTrue(services.kassen_fuer(uV1).exists())
        self.assertTrue(services.kassen_fuer(uV2).exists())
        self.assertFalse(services.kassen_fuer(uX).exists())

        # normaler User darf die Zuständigkeit NICHT ändern
        r = self._cl(uX).post("/kasse/zustaendigkeit/", {"kasse": kasse.id, "verantwortlich": mV2.id})
        self.assertEqual(r.status_code, 403)

    # --- Beleg-Nr eindeutig je Kassenmonat -----------------------------
    def test_belegnr_eindeutig_pro_kassenmonat(self):
        kasse = Kasse.objects.create(team=self.team, bezeichnung="K")
        km = Kassenmonat.objects.create(kasse=kasse, jahr=2026, monat=6)
        Kassenbuchung.objects.create(monat=km, bel_nr=1, datum=date(2026, 6, 1), text="a")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Kassenbuchung.objects.create(monat=km, bel_nr=1, datum=date(2026, 6, 2), text="b")

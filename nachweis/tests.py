"""Regressionstests für die Team-/Datentrennung (DSGVO-Kern).

Diese Tests sichern dauerhaft ab, dass Nutzer*innen NUR Daten ihres/ihrer
Team(s) sehen und der Admin keinen Klientenzugriff hat – auch wenn die App
für viele Teams wächst. Bei einem Scoping-Fehler schlagen sie fehl.
"""
import json
from datetime import date, time

from django.test import TestCase, Client
from django.contrib.auth import get_user_model

from . import services
from .models import Team, Teamtyp, Mitarbeiter, Klient, Rolle, Status, Termin

User = get_user_model()


class TeamIsolationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.team_a = Team.objects.create(name="Team A", typ=Teamtyp.BEW)
        cls.team_b = Team.objects.create(name="Team B", typ=Teamtyp.BEW)
        cls.team_vw = Team.objects.create(name="Verwaltung", typ=Teamtyp.VERWALTUNG)

        def ma(username, team, rolle, leitet=None):
            u = User.objects.create_user(username, password="pw-egal")
            m = Mitarbeiter.objects.create(user=u, name=username.title(), rolle=rolle, team=team)
            if leitet:
                m.leitet.set(leitet)
            return u, m

        cls.uA, cls.mA = ma("anna", cls.team_a, Rolle.USER)
        cls.uB, cls.mB = ma("bea", cls.team_b, Rolle.USER)
        cls.uLA, cls.mLA = ma("lea", cls.team_a, Rolle.LEITUNG, [cls.team_a])
        cls.uAdmin, cls.mAdmin = ma("adam", cls.team_vw, Rolle.ADMIN)

        cls.kA = Klient.objects.create(nachname="Alpha", team=cls.team_a,
                                       bezugsbetreuer=cls.mA, status=Status.BETREUUNG)
        cls.kB = Klient.objects.create(nachname="Beta", team=cls.team_b,
                                       bezugsbetreuer=cls.mB, status=Status.BETREUUNG)

    def cl(self, u):
        c = Client()
        c.force_login(u)
        return c

    # --- Kern-Scoping ---------------------------------------------------
    def test_klienten_fuer_team_scoped(self):
        self.assertIn(self.kA, services.klienten_fuer(self.uA))
        self.assertNotIn(self.kB, services.klienten_fuer(self.uA))
        self.assertIn(self.kB, services.klienten_fuer(self.uB))
        self.assertNotIn(self.kA, services.klienten_fuer(self.uB))

    def test_admin_hat_keinen_klientenzugriff(self):
        self.assertEqual(services.klienten_fuer(self.uAdmin).count(), 0)

    def test_leitung_sieht_nur_geleitetes_team(self):
        self.assertIn(self.kA, services.klienten_fuer(self.uLA))
        self.assertNotIn(self.kB, services.klienten_fuer(self.uLA))

    # --- Suche ----------------------------------------------------------
    def _such_klienten(self, user, q):
        d = json.loads(self.cl(user).get(f"/api/suche/?q={q}").content)
        return [i["titel"] for k in d["kategorien"] if k["key"] == "klienten" for i in k["items"]]

    def test_suche_kein_fremdteam_klient(self):
        self.assertEqual(self._such_klienten(self.uA, "Beta"), [])   # Fremdteam-Klient nicht findbar
        self.assertTrue(any("Alpha" in t for t in self._such_klienten(self.uA, "Alpha")))

    def test_suche_admin_ohne_klienten(self):
        d = json.loads(self.cl(self.uAdmin).get("/api/suche/?q=Alpha").content)
        self.assertNotIn("klienten", [k["key"] for k in d["kategorien"]])

    # --- IDOR / Objektebene --------------------------------------------
    def test_druck_fremdklient_404(self):
        r = self.cl(self.uA).get(f"/druck/?klient={self.kB.id}&monat=6&jahr=2026")
        self.assertEqual(r.status_code, 404)

    def test_termin_fremd_nicht_loeschbar(self):
        t = Termin.objects.create(mitarbeiter=self.mB, datum=date(2026, 7, 1), beginn=time(10, 0))
        self.cl(self.uA).post("/kalender/delete/", {"id": t.id, "jahr": 2026, "kw": 27})
        self.assertTrue(Termin.objects.filter(id=t.id).exists())     # nicht gelöscht

    def test_termin_move_eigenes(self):
        t = Termin.objects.create(mitarbeiter=self.mA, datum=date(2026, 7, 1), beginn=time(10, 0))
        r = self.cl(self.uA).post("/kalender/move/", {"id": t.id, "datum": "2026-07-03"})
        self.assertEqual(r.status_code, 200)
        t.refresh_from_db()
        self.assertEqual(t.datum, date(2026, 7, 3))

    def test_termin_move_fremd_verboten(self):
        t = Termin.objects.create(mitarbeiter=self.mB, datum=date(2026, 7, 1), beginn=time(10, 0))
        r = self.cl(self.uA).post("/kalender/move/", {"id": t.id, "datum": "2026-07-03"})
        self.assertEqual(r.status_code, 403)
        t.refresh_from_db()
        self.assertEqual(t.datum, date(2026, 7, 1))    # unverändert (nur eigene verschiebbar)

    def test_kalender_nur_eigenes_team(self):
        r = self.cl(self.uA).get("/kalender/")
        self.assertContains(r, "Anna")        # eigenes Team
        self.assertNotContains(r, "Bea")      # Fremdteam nicht sichtbar

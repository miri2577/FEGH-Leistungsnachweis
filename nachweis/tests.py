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

    # --- Suche (POST: Suchbegriff darf nicht im Query-String/Log landen) ----
    def _such_klienten(self, user, q):
        d = json.loads(self.cl(user).post("/api/suche/", {"q": q}).content)
        return [i["titel"] for k in d["kategorien"] if k["key"] == "klienten" for i in k["items"]]

    def test_suche_kein_fremdteam_klient(self):
        self.assertEqual(self._such_klienten(self.uA, "Beta"), [])   # Fremdteam-Klient nicht findbar
        self.assertTrue(any("Alpha" in t for t in self._such_klienten(self.uA, "Alpha")))

    def test_suche_admin_ohne_klienten(self):
        d = json.loads(self.cl(self.uAdmin).post("/api/suche/", {"q": "Alpha"}).content)
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
        self.assertEqual(t.datum, date(2026, 7, 1))    # unverändert (User: nur eigene)

    def test_leitung_kann_teamtermin_verschieben(self):
        t = Termin.objects.create(mitarbeiter=self.mA, datum=date(2026, 7, 1), beginn=time(10, 0))
        r = self.cl(self.uLA).post("/kalender/move/", {"id": t.id, "datum": "2026-07-03"})
        self.assertEqual(r.status_code, 200)              # Leitung darf Team-Termine
        t.refresh_from_db()
        self.assertEqual(t.datum, date(2026, 7, 3))

    def test_leitung_nicht_fremdteam_termin(self):
        t = Termin.objects.create(mitarbeiter=self.mB, datum=date(2026, 7, 1), beginn=time(10, 0))
        r = self.cl(self.uLA).post("/kalender/move/", {"id": t.id, "datum": "2026-07-03"})
        self.assertEqual(r.status_code, 403)              # nur geleitete Teams

    def test_termin_zeit_aendern(self):
        t = Termin.objects.create(mitarbeiter=self.mA, datum=date(2026, 7, 1),
                                  beginn=time(9, 0), ende=time(10, 0))
        r = self.cl(self.uA).post("/kalender/zeit/", {"id": t.id, "beginn": "11:15", "ende": "12:00"})
        self.assertEqual(r.status_code, 200)
        t.refresh_from_db()
        self.assertEqual((t.beginn, t.ende), (time(11, 15), time(12, 0)))

    def test_termin_zeit_fremd_verboten(self):
        t = Termin.objects.create(mitarbeiter=self.mB, datum=date(2026, 7, 1), beginn=time(9, 0))
        r = self.cl(self.uA).post("/kalender/zeit/", {"id": t.id, "beginn": "11:00", "ende": "12:00"})
        self.assertEqual(r.status_code, 403)
        t.refresh_from_db()
        self.assertEqual(t.beginn, time(9, 0))            # unverändert

    def test_kalender_nur_eigenes_team(self):
        r = self.cl(self.uA).get("/kalender/")
        # präzise auf die MA-Namenszelle der Matrix prüfen (nicht auf Substring 'Bea',
        # das sonst z. B. in 'Bearbeiten' matcht)
        self.assertContains(r, 'class="mxname">Anna')     # eigenes Team
        self.assertNotContains(r, 'class="mxname">Bea')   # Fremdteam nicht sichtbar

    def test_fehlzeiten_statistik(self):
        from datetime import date
        from decimal import Decimal
        from .models import Abwesenheit, AbwesenheitArt, AbwesenheitStatus
        from . import services
        self.mA.wochenstunden = Decimal("40.0"); self.mA.save()   # Tagessoll 8,0
        # 5 Werktage Krank (Mo–Fr) + 3 Werktage Urlaub, genehmigt, im Jahr 2026
        Abwesenheit.objects.create(mitarbeiter=self.mA, art=AbwesenheitArt.KRANK,
                                   von=date(2026, 1, 5), bis=date(2026, 1, 9),
                                   status=AbwesenheitStatus.GENEHMIGT)
        Abwesenheit.objects.create(mitarbeiter=self.mA, art=AbwesenheitArt.URLAUB,
                                   von=date(2026, 2, 2), bis=date(2026, 2, 4),
                                   status=AbwesenheitStatus.GENEHMIGT)
        # nicht genehmigt -> zählt nicht
        Abwesenheit.objects.create(mitarbeiter=self.mA, art=AbwesenheitArt.KRANK,
                                   von=date(2026, 3, 2), bis=date(2026, 3, 6),
                                   status=AbwesenheitStatus.BEANTRAGT)
        stat = services.fehlzeiten_statistik([self.mA], 2026, heute=date(2026, 12, 31))
        r = stat[0]
        self.assertEqual(r["tage"]["krank"], 5)
        self.assertEqual(r["tage"]["urlaub"], 3)
        self.assertEqual(r["summe"], 8)
        self.assertEqual(r["fehlstunden"], Decimal("64.000"))     # 8 Tage × 8,0
        # Krankquote = 5 / Werktage-2026 × 100
        self.assertAlmostEqual(r["krankquote"], round(5 / r["basis"] * 100, 1))

    def test_fehlzeiten_seite_nur_leitung(self):
        self.assertEqual(self.cl(self.uA).get("/fehlzeiten/").status_code, 403)
        self.assertEqual(self.cl(self.uLA).get("/fehlzeiten/").status_code, 200)

    def test_urlaub_ueberlappung_warnung(self):
        from datetime import date
        from .models import Abwesenheit, AbwesenheitArt, AbwesenheitStatus
        from . import services
        # zweite*r Team-A-MA schon genehmigt abwesend im überlappenden Zeitraum
        u2 = User.objects.create_user("tom", password="pw")
        m2 = Mitarbeiter.objects.create(user=u2, name="Tom", rolle=Rolle.USER, team=self.team_a)
        Abwesenheit.objects.create(mitarbeiter=m2, art=AbwesenheitArt.URLAUB,
                                   von=date(2026, 8, 10), bis=date(2026, 8, 14),
                                   status=AbwesenheitStatus.GENEHMIGT)
        antrag = Abwesenheit.objects.create(mitarbeiter=self.mA, art=AbwesenheitArt.URLAUB,
                                            von=date(2026, 8, 12), bis=date(2026, 8, 18),
                                            status=AbwesenheitStatus.BEANTRAGT)
        # Service findet die Überschneidung
        ueberlappt = services.team_ueberlappung(antrag)
        self.assertEqual([o.mitarbeiter for o in ueberlappt], [m2])
        # Leitung sieht die Warnung
        r = self.cl(self.uLA).get("/abwesenheit/")
        self.assertContains(r, "gleichzeitig abwesend")
        self.assertContains(r, "Tom")
        # fremdes Team überlappt nicht
        mfb = Mitarbeiter.objects.create(
            user=User.objects.create_user("uwe", password="pw"),
            name="Uwe", rolle=Rolle.USER, team=self.team_b)
        Abwesenheit.objects.create(mitarbeiter=mfb, art=AbwesenheitArt.URLAUB,
                                   von=date(2026, 8, 12), bis=date(2026, 8, 18),
                                   status=AbwesenheitStatus.GENEHMIGT)
        self.assertEqual([o.mitarbeiter for o in services.team_ueberlappung(antrag)], [m2])

    def test_kalender_tag_und_monat_rendern(self):
        for ansicht in ("tag", "monat", "woche"):
            r = self.cl(self.uA).get(f"/kalender/?ansicht={ansicht}")
            self.assertEqual(r.status_code, 200, ansicht)

    def test_kalender_titel_neben_klient_sichtbar(self):
        """Ein Termin mit Klient*in UND Titel darf den Titel nicht verschlucken –
        das Popover-Label zeigt beides (voll_anzeige)."""
        Termin.objects.create(mitarbeiter=self.mA, klient=self.kA, datum=date(2026, 7, 2),
                              beginn=time(20, 12), titel="Hausbesuch")
        r = self.cl(self.uA).get("/kalender/?ansicht=monat&jahr=2026&monat=7")
        self.assertContains(r, "Alpha · Hausbesuch")        # Klient + Titel im data-label

    def test_kalender_druck_ohne_ansicht_zeigt_woche(self):
        """Review-Regression: Standard-Ansicht ist jetzt der Monat, das Druck-Template
        kennt aber nur die Woche -> der Druck muss die Woche erzwingen (sonst leer)."""
        r = self.cl(self.uA).get("/kalender/druck/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Kalenderwoche")            # Wochen-Layout gerendert
        self.assertNotContains(r, "Keine Mitarbeiter*innen im Team.")

    def test_kalender_extremes_jahr_kein_500(self):
        """Review-Regression: _jahr klemmt jetzt -> kein ValueError-500 bei jahr<1/>9999."""
        for jahr in ("0", "99999", "-5"):
            r = self.cl(self.uA).get(f"/kalender/?ansicht=monat&jahr={jahr}")
            self.assertEqual(r.status_code, 200, jahr)

    # --- Termin anlegen: Mitarbeiter-Zuweisung (Klick ins leere Feld) ---
    def test_leitung_legt_termin_fuer_teammitglied_an(self):
        r = self.cl(self.uLA).post("/kalender/save/", {
            "datum": "2026-07-06", "beginn": "10:00", "titel": "Fallgespräch",
            "mitarbeiter": self.mA.id})
        self.assertEqual(r.status_code, 302)
        t = Termin.objects.get(titel="Fallgespräch")
        self.assertEqual(t.mitarbeiter_id, self.mA.id)    # dem Teammitglied zugeordnet

    def test_user_kann_mitarbeiter_nicht_setzen(self):
        r = self.cl(self.uA).post("/kalender/save/", {
            "datum": "2026-07-06", "beginn": "10:00", "titel": "SelbstNur",
            "mitarbeiter": self.mB.id})    # Fremd-MA angehängt -> muss ignoriert werden
        self.assertEqual(r.status_code, 302)
        t = Termin.objects.get(titel="SelbstNur")
        self.assertEqual(t.mitarbeiter_id, self.mA.id)    # bleibt bei sich selbst

    def test_leitung_nicht_fuer_fremdteam_anlegen(self):
        r = self.cl(self.uLA).post("/kalender/save/", {
            "datum": "2026-07-06", "beginn": "10:00", "titel": "FremdAnlage",
            "mitarbeiter": self.mB.id})    # mB ist Team B, nicht geleitet
        t = Termin.objects.get(titel="FremdAnlage")
        self.assertEqual(t.mitarbeiter_id, self.mLA.id)   # Fallback auf Leitung selbst

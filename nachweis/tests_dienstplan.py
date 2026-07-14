"""Tests Dienstplanung — jetzt Teil der Kalender-Monatsmatrix (ein Planungsbrett:
ambulant = Klient-Termine, stationär = Schichtdienste)."""
from datetime import date, time
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import (Team, Teamtyp, Mitarbeiter, Rolle, Schichtart, Dienst,
                     Angebot, AngebotsTyp, Erreichbarkeit, Abwesenheit,
                     AbwesenheitArt, AbwesenheitStatus, Klient, Status, Termin)

User = get_user_model()


class DienstplanBasis(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="WG-Team", typ=Teamtyp.values[0])
        self.lu = User.objects.create_user("chef", password="x")
        m = Mitarbeiter.objects.create(user=self.lu, name="Chef", rolle=Rolle.LEITUNG, kuerzel="c")
        m.leitet.set([self.team])
        self.ma = Mitarbeiter.objects.create(
            user=User.objects.create_user("ma", password="x"),
            name="Muster", rolle=Rolle.USER, team=self.team, kuerzel="mu")
        self.client.force_login(self.lu)

    def _matrix(self, **params):
        p = {"ansicht": "monat", "team": self.team.id, "jahr": 2026, "monat": 7}
        p.update(params)
        return self.client.get(reverse("nachweis:kalender"), p)


class SchichtartTests(TestCase):
    def test_defaults_aus_migration(self):
        kuerzel = set(Schichtart.objects.values_list("kuerzel", flat=True))
        self.assertTrue({"F", "S", "N"}.issubset(kuerzel))
        n = Schichtart.objects.get(name="Nachtdienst")
        self.assertTrue(n.ist_nachtdienst)

    def test_dauer_ueber_mitternacht(self):
        n = Schichtart.objects.get(name="Nachtdienst")      # 21:00–07:00
        self.assertEqual(n.dauer_stunden, Decimal("10.000"))
        f = Schichtart.objects.get(name="Frühdienst")       # 06:30–14:30
        self.assertEqual(f.dauer_stunden, Decimal("8.000"))


class PlanungsmatrixTests(DienstplanBasis):
    def test_alte_dienstplan_url_leitet_auf_kalender(self):
        resp = self.client.get(reverse("nachweis:dienstplan"),
                               {"team": self.team.id, "jahr": 2026, "monat": 7})
        self.assertEqual(resp.status_code, 302)
        self.assertIn("ansicht=monat", resp["Location"])
        self.assertIn("monat=7", resp["Location"])
        self.assertEqual(self.client.get(resp["Location"]).status_code, 200)

    def test_matrix_dienste_und_summen(self):
        f = Schichtart.objects.get(kuerzel="F")
        Dienst.objects.create(mitarbeiter=self.ma, datum=date(2026, 7, 1), schichtart=f)
        Dienst.objects.create(mitarbeiter=self.ma, datum=date(2026, 7, 2), schichtart=f)
        resp = self._matrix()
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Muster")
        self.assertContains(resp, "16,0")                    # 2 × 8 Std (dt. Komma)

    def test_matrix_vereint_dienst_und_termin(self):
        """Kern der Fusion: Schichtdienst (stationär) und Klient-Termin (ambulant)
        erscheinen in derselben Matrix; die Summe zählt beides."""
        f = Schichtart.objects.get(kuerzel="F")
        Dienst.objects.create(mitarbeiter=self.ma, datum=date(2026, 7, 1), schichtart=f)
        k = Klient.objects.create(nachname="Wera", team=self.team,
                                  bezugsbetreuer=self.ma, status=Status.BETREUUNG)
        Termin.objects.create(mitarbeiter=self.ma, klient=k, datum=date(2026, 7, 1),
                              beginn=time(9, 0), ende=time(10, 0))
        resp = self._matrix()
        self.assertContains(resp, 'class="mxd"')             # Dienst-Block
        self.assertContains(resp, k.kuerzel_anzeige)         # Termin-Chip
        self.assertContains(resp, "9,0")                     # 8 h Dienst + 1 h Termin

    def test_dienst_setzen_ersetzen_loeschen(self):
        f = Schichtart.objects.get(kuerzel="F")
        s = Schichtart.objects.get(kuerzel="S")
        self.client.post(reverse("nachweis:dienst_setzen"), {
            "mitarbeiter": self.ma.id, "datum": "2026-07-01", "schichtart": f.id})
        self.assertEqual(Dienst.objects.get().schichtart, f)
        # anderen Dienst am selben Tag setzen -> ersetzt
        self.client.post(reverse("nachweis:dienst_setzen"), {
            "mitarbeiter": self.ma.id, "datum": "2026-07-01", "schichtart": s.id})
        self.assertEqual(Dienst.objects.count(), 1)
        self.assertEqual(Dienst.objects.get().schichtart, s)
        # leer = löschen
        self.client.post(reverse("nachweis:dienst_setzen"), {
            "mitarbeiter": self.ma.id, "datum": "2026-07-01", "schichtart": ""})
        self.assertEqual(Dienst.objects.count(), 0)

    def test_abwesenheit_im_raster_sichtbar(self):
        Abwesenheit.objects.create(mitarbeiter=self.ma, art=AbwesenheitArt.URLAUB,
                                   von=date(2026, 7, 6), bis=date(2026, 7, 10),
                                   status=AbwesenheitStatus.GENEHMIGT)
        self.assertContains(self._matrix(), "data-abw")

    def test_nachtbesetzungs_luecke(self):
        Angebot.objects.create(name="Wohnform Nacht", team=self.team,
                               typ=AngebotsTyp.BESONDERE_WOHNFORM,
                               erreichbarkeit=Erreichbarkeit.TAG_NACHT, plaetze=6)
        self.assertContains(self._matrix(), "Nachtbesetzung unvollständig")
        # ein Nachtdienst mit Angebots-Bezug -> ein Tag weniger Lücke
        n = Schichtart.objects.get(kuerzel="N")
        a = Angebot.objects.get()
        self.client.post(reverse("nachweis:dienst_setzen"), {
            "mitarbeiter": self.ma.id, "datum": "2026-07-01",
            "schichtart": n.id, "angebot": a.id})
        self.assertContains(self._matrix(), "30 Nacht(-Dienst) offen")  # 31 Tage - 1

    def test_ma_sieht_dienste_aber_setzt_keine(self):
        f = Schichtart.objects.get(kuerzel="F")
        Dienst.objects.create(mitarbeiter=self.ma, datum=date(2026, 7, 1), schichtart=f)
        self.client.force_login(self.ma.user)
        resp = self._matrix()
        self.assertContains(resp, 'class="mxd"')             # Dienst sichtbar (Aushang)
        self.assertNotContains(resp, "mxp-sa")               # keine Setz-UI
        self.assertNotContains(resp, "Nachtbesetzung")       # Warnung nur Leitung
        self.assertEqual(self.client.post(
            reverse("nachweis:dienst_setzen"), {}).status_code, 403)
        self.assertEqual(self.client.get(
            reverse("nachweis:schichtarten")).status_code, 403)

    def test_fremdes_team_ma_nicht_planbar(self):
        fremd = Mitarbeiter.objects.create(
            user=User.objects.create_user("fx", password="x"),
            name="Fremd", rolle=Rolle.USER, kuerzel="fx",
            team=Team.objects.create(name="Anderes", typ=Teamtyp.values[0]))
        f = Schichtart.objects.get(kuerzel="F")
        resp = self.client.post(reverse("nachweis:dienst_setzen"), {
            "mitarbeiter": fremd.id, "datum": "2026-07-01", "schichtart": f.id})
        self.assertEqual(resp.status_code, 404)              # team-gescopt

    def test_schichtart_anlegen(self):
        resp = self.client.post(reverse("nachweis:schichtarten"), {
            "name": "Zwischendienst", "kuerzel": "Z", "beginn": "11:00",
            "ende": "19:00", "farbe": "#178a9b", "aktiv": "on"})
        self.assertEqual(resp.status_code, 302)
        z = Schichtart.objects.get(name="Zwischendienst")
        self.assertEqual(z.dauer_stunden, Decimal("8.000"))

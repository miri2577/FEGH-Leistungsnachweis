"""Tests Wirkungsmessung (Berliner Wirkungsdimensionen, Ist/Soll 7er-Skala)."""
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import (Team, Teamtyp, Mitarbeiter, Rolle, Klient, Status,
                     Wirkungsdimension, Wirkungseinschaetzung, WirkungsAnlass,
                     WirkungsPerspektive, Ziel, ZielArt)

User = get_user_model()


class WirkungBasis(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="TBEW", typ=Teamtyp.values[0])
        self.u = User.objects.create_user("betr", password="x")
        self.betr = Mitarbeiter.objects.create(user=self.u, name="B", rolle=Rolle.USER,
                                               team=self.team, kuerzel="b")
        self.k = Klient.objects.create(nachname="K", team=self.team,
                                       bezugsbetreuer=self.betr, status=Status.BETREUUNG)
        self.client.force_login(self.u)
        self.dim = Wirkungsdimension.objects.get(
            name="Psychische/emotionale Stabilität und Gesundheit")


class DimensionenTests(TestCase):
    def test_acht_berliner_dimensionen_aus_migration(self):
        self.assertEqual(Wirkungsdimension.objects.count(), 8)
        self.assertEqual(Wirkungsdimension.objects.filter(bereich="person").count(), 5)
        self.assertEqual(Wirkungsdimension.objects.filter(bereich="familie").count(), 3)
        namen = set(Wirkungsdimension.objects.values_list("name", flat=True))
        self.assertIn("Entwicklung, Selbstständigkeit und Teilhabe", namen)
        self.assertIn("Erziehungs- und Beziehungskompetenz", namen)


class WirkungViewTests(WirkungBasis):
    def _erfassen(self, **extra):
        daten = {"klient": self.k.id, "dimension": self.dim.id,
                 "datum": date.today().isoformat(), "anlass": "beginn",
                 "perspektive": "fachkraft", "ist": "5", "soll": "4"}
        daten.update(extra)
        return self.client.post(reverse("nachweis:wirkung_speichern"), daten)

    def test_erfassen_und_verlauf(self):
        self._erfassen()
        self._erfassen(anlass="fortschreibung", ist="3", soll="2",
                       datum=(date.today() + timedelta(days=180)).isoformat())
        resp = self.client.get(reverse("nachweis:wirkung", args=[self.k.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Psychische/emotionale")
        self.assertContains(resp, "+2")                      # Delta 5 -> 3 = Verbesserung

    def test_skala_grenzen(self):
        self._erfassen(ist="8")                              # außerhalb 1-7
        self.assertEqual(Wirkungseinschaetzung.objects.count(), 0)
        self._erfassen(ist="0", soll="9")
        self.assertEqual(Wirkungseinschaetzung.objects.count(), 0)
        self._erfassen(ist="7", soll="1")
        self.assertEqual(Wirkungseinschaetzung.objects.count(), 1)

    def test_perspektiven_getrennt(self):
        """AV Hilfeplanung: Einschätzungen ALLER Beteiligten werden erfasst."""
        self._erfassen(perspektive="fachkraft", ist="5", soll="4")
        self._erfassen(perspektive="klient", ist="3", soll="3")
        self.assertEqual(Wirkungseinschaetzung.objects.count(), 2)
        werte = {e.perspektive: e.ist for e in Wirkungseinschaetzung.objects.all()}
        self.assertEqual(werte[WirkungsPerspektive.FACHKRAFT], 5)
        self.assertEqual(werte[WirkungsPerspektive.KLIENT], 3)

    def test_fremdes_team_kein_zugriff(self):
        fu = User.objects.create_user("fremd", password="x")
        Mitarbeiter.objects.create(user=fu, name="F", rolle=Rolle.USER,
                                   team=Team.objects.create(name="X", typ=Teamtyp.values[0]),
                                   kuerzel="f")
        self.client.force_login(fu)
        self.assertEqual(self.client.get(
            reverse("nachweis:wirkung", args=[self.k.id])).status_code, 404)

    def test_loeschen_nur_leitung(self):
        self._erfassen()
        e = Wirkungseinschaetzung.objects.get()
        resp = self.client.post(reverse("nachweis:wirkung_loeschen"), {"id": e.id})
        self.assertEqual(resp.status_code, 403)

    def test_kommentar_nicht_in_history(self):
        self._erfassen(kommentar="Sehr persönliche Einschätzung")
        e = Wirkungseinschaetzung.objects.get()
        self.assertFalse(hasattr(e.history.first(), "kommentar"))


class RohpaketWirkungTests(WirkungBasis):
    def test_rohpaket_enthaelt_wirkung_und_zielerreichung(self):
        from .models import Bericht, Berichtsvorlage
        Wirkungseinschaetzung.objects.create(
            klient=self.k, dimension=self.dim, datum=date.today(),
            anlass=WirkungsAnlass.BEGINN, ist=5, soll=4)
        Ziel.objects.create(klient=self.k, art=ZielArt.HANDLUNGSZIEL,
                            titel="Testziel", erreicht_grad=75)
        b = Bericht.objects.create(klient=self.k,
                                   vorlage=Berichtsvorlage.objects.first(),
                                   zeitraum_von=date.today() - timedelta(days=30),
                                   zeitraum_bis=date.today())
        resp = self.client.get(reverse("nachweis:bericht_rohpaket", args=[b.id]))
        d = resp.json()
        self.assertEqual(len(d["wirkung"]), 1)
        self.assertEqual(d["wirkung"][0]["ist"], 5)
        self.assertEqual(d["ziele"][0]["erreicht_grad"], 75)
        md = self.client.get(reverse("nachweis:bericht_rohpaket", args=[b.id]),
                             {"format": "md"}).content.decode()
        self.assertIn("Wirkungsdimensionen", md)
        self.assertIn("Ist 5 → Soll 4", md)
        self.assertIn("Zielerreichung 75 %", md)

    def test_leitziel_terminologie(self):
        """Labels folgen dem Berliner ZLP-Formular (Leitziel/Teilhabeziel)."""
        z = Ziel.objects.create(klient=self.k, art=ZielArt.RICHTUNGSZIEL, titel="T")
        self.assertEqual(z.get_art_display(), "Leitziel")

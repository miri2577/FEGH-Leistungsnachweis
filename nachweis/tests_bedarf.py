"""Tests ICF-Bedarfsermittlung (Teilhabeinstrument Berlin / TIB)."""
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import (Team, Teamtyp, Mitarbeiter, Rolle, Klient, Status,
                     TibLebensbereich, Bedarfsermittlung, BedarfsEinschaetzung,
                     TibAnlass, TeilhabeStatus)

User = get_user_model()


class LebensbereichTests(TestCase):
    def test_12_berliner_lebensbereiche(self):
        self.assertEqual(TibLebensbereich.objects.count(), 12)
        namen = set(TibLebensbereich.objects.values_list("name", flat=True))
        self.assertIn("Mobilität", namen)
        self.assertIn("Arbeit und Beschäftigung", namen)
        # d8 dreifach aufgeteilt
        self.assertEqual(TibLebensbereich.objects.filter(icf_code="d8").count(), 3)


class BedarfBasis(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="TBEW", typ=Teamtyp.BEW)
        self.u = User.objects.create_user("chef", password="x")
        self.lu = Mitarbeiter.objects.create(user=self.u, name="Chef", rolle=Rolle.LEITUNG, kuerzel="c")
        self.lu.leitet.set([self.team])
        self.k = Klient.objects.create(nachname="K", team=self.team,
                                       bezugsbetreuer=self.lu, status=Status.BETREUUNG)
        self.client.force_login(self.u)


class BedarfViewTests(BedarfBasis):
    def _neu(self, anlass="erst"):
        self.client.post(reverse("nachweis:bedarf_neu"),
                         {"klient": self.k.id, "datum": "2026-07-01", "anlass": anlass})
        return self.k.bedarfsermittlungen.latest("id")

    def test_seite_und_erhebung_anlegen(self):
        r = self.client.get(reverse("nachweis:bedarf", args=[self.k.id]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Lebensbereich" if False else "Bedarf")   # Sub-Nav
        b = self._neu()
        self.assertEqual(b.anlass, TibAnlass.ERST)

    def test_einschaetzungen_speichern(self):
        b = self._neu()
        lb = TibLebensbereich.objects.get(icf_code="d4")   # Mobilität
        self.client.post(reverse("nachweis:bedarf_speichern"), {
            "erhebung": b.id,
            f"lb_{lb.id}_relevant": "on",
            f"lb_{lb.id}_gelingt": "Nutzt Rollstuhl selbstständig.",
            f"lb_{lb.id}_barrieren": "Bordsteinkanten im Wohnumfeld.",
            f"lb_{lb.id}_status": "liegt_vor",
            f"lb_{lb.id}_unterst": "Begleitung bei Außenwegen, 2×/Woche"})
        e = b.einschaetzungen.get(lebensbereich=lb)
        self.assertTrue(e.relevant)
        self.assertEqual(e.teilhabe_status, TeilhabeStatus.LIEGT_VOR)
        self.assertIn("Rollstuhl", e.gelingt)
        # leere Lebensbereiche legen keinen Datensatz an
        self.assertEqual(b.einschaetzungen.count(), 1)

    def test_fortschreibung_uebernimmt_vorlage(self):
        b1 = self._neu()
        lb = TibLebensbereich.objects.get(icf_code="d5")
        BedarfsEinschaetzung.objects.create(bedarfsermittlung=b1, lebensbereich=lb,
                                            relevant=True, gelingt="Wäsche selbst",
                                            teilhabe_status=TeilhabeStatus.LIEGT_VOR)
        b2 = self._neu(anlass="fortschreibung")
        e = b2.einschaetzungen.get(lebensbereich=lb)
        self.assertEqual(e.gelingt, "Wäsche selbst")     # aus Vorlage übernommen
        self.assertTrue(e.relevant)

    def test_freitext_nicht_in_history(self):
        b = self._neu()
        lb = TibLebensbereich.objects.first()
        e = BedarfsEinschaetzung.objects.create(bedarfsermittlung=b, lebensbereich=lb,
                                                gelingt="Sehr persönlicher Text")
        self.assertFalse(hasattr(e.history.first(), "gelingt"))

    def test_fremdes_team_404(self):
        fremd = Klient.objects.create(nachname="Fremd",
                                      team=Team.objects.create(name="X", typ=Teamtyp.BEW),
                                      bezugsbetreuer=self.lu, status=Status.BETREUUNG)
        self.assertEqual(self.client.get(
            reverse("nachweis:bedarf", args=[fremd.id])).status_code, 404)

    def test_loeschen_nur_leitung(self):
        b = self._neu()
        u2 = User.objects.create_user("ma", password="x")
        Mitarbeiter.objects.create(user=u2, name="MA", rolle=Rolle.USER, team=self.team, kuerzel="m")
        self.client.force_login(u2)
        self.assertEqual(self.client.post(reverse("nachweis:bedarf_loeschen"),
                                          {"erhebung": b.id}).status_code, 403)

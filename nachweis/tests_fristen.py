"""Tests Wiedervorlagen-/Fristen-Dashboard."""
from datetime import date, timedelta

from django.test import TestCase, Client
from django.contrib.auth import get_user_model

from . import services
from .models import Team, Teamtyp, Mitarbeiter, Rolle, Klient, Status

User = get_user_model()


class FristenTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="TF", typ=Teamtyp.BEW)
        u = User.objects.create_user("mf", password="x")
        self.m = Mitarbeiter.objects.create(user=u, name="M", rolle=Rolle.LEITUNG, kuerzel="m")
        self.m.leitet.set([self.team])
        self.c = Client(); self.c.force_login(u)

    def _klient(self, **kw):
        kw.setdefault("status", Status.BETREUUNG)
        return Klient.objects.create(nachname="K", team=self.team, bezugsbetreuer=self.m, **kw)

    def _items(self):
        return services.fristen_uebersicht(services.klienten_fuer(self.m.user))

    def test_kue_ende_erscheint(self):
        self._klient(kue_bis=date.today() + timedelta(days=30))
        self.assertIn("KÜ-Ende / Bericht fällig", [i["art"] for i in self._items()])

    def test_ueberfaellig_markiert(self):
        self._klient(betreuung_bis=date.today() - timedelta(days=5), betreuung_name="Verein")
        b = [i for i in self._items() if i["art"] == "Gesetzl. Betreuung endet"][0]
        self.assertTrue(b["ueberfaellig"])

    def test_horizont_schneidet_ferne_ab(self):
        self._klient(kue_bis=date.today() + timedelta(days=200))
        self.assertEqual(self._items(), [])

    def test_beendete_klienten_nicht(self):
        self._klient(kue_bis=date.today() + timedelta(days=10), status=Status.BEENDIGUNG)
        self.assertEqual(self._items(), [])

    def test_anonymisierte_nicht(self):
        from django.utils import timezone
        k = self._klient(kue_bis=date.today())
        Klient.objects.filter(pk=k.pk).update(anonymisiert_am=timezone.now())
        self.assertEqual(self._items(), [])

    def test_seite_laedt(self):
        self._klient(kue_bis=date.today())
        r = self.c.get("/fristen/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Wiedervorlagen")

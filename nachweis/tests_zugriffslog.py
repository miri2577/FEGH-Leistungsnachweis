"""Tests: Lesezugriffs-Protokoll auf Art-9-Detailseiten (DSGVO-Rechenschaft, § 22 BDSG)
und dessen eigene Aufbewahrungsfrist (Aufräumung)."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from . import services_loeschfristen as lf
from .models import Team, Teamtyp, Mitarbeiter, Rolle, Klient, Status, Zugriffslog

User = get_user_model()


class ZugriffslogTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="TBEW", typ=Teamtyp.BEW)
        self.u = User.objects.create_user("betreuer", password="x")
        self.m = Mitarbeiter.objects.create(user=self.u, name="Betreuer", rolle=Rolle.USER,
                                            team=self.team, kuerzel="b")
        self.k = Klient.objects.create(nachname="Muster", team=self.team,
                                       bezugsbetreuer=self.m, status=Status.BETREUUNG)
        self.client.force_login(self.u)

    def test_fallakte_aufruf_wird_protokolliert(self):
        self.assertEqual(Zugriffslog.objects.count(), 0)
        self.client.get(reverse("nachweis:klient_detail", args=[self.k.id]))
        log = Zugriffslog.objects.get()
        self.assertEqual(log.klient, self.k)
        self.assertEqual(log.mitarbeiter, self.m)
        self.assertEqual(log.bereich, "fallakte")

    def test_bedarf_und_berichte_werden_protokolliert(self):
        self.client.get(reverse("nachweis:bedarf", args=[self.k.id]))
        self.client.get(reverse("nachweis:berichte", args=[self.k.id]))
        self.assertTrue(Zugriffslog.objects.filter(klient=self.k, bereich="bedarf").exists())
        self.assertTrue(Zugriffslog.objects.filter(klient=self.k, bereich="bericht").exists())

    def test_fremde_akte_ohne_zugriff_wird_nicht_protokolliert(self):
        # Klient*in eines fremden Teams -> klienten_fuer liefert sie nicht -> 404, kein Log
        fremd_team = Team.objects.create(name="Anderes", typ=Teamtyp.BEW)
        fm = Mitarbeiter.objects.create(name="F", rolle=Rolle.USER, team=fremd_team, kuerzel="f")
        fremd = Klient.objects.create(nachname="Fremd", team=fremd_team, bezugsbetreuer=fm,
                                      status=Status.BETREUUNG)
        resp = self.client.get(reverse("nachweis:klient_detail", args=[fremd.id]))
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(Zugriffslog.objects.filter(klient=fremd).count(), 0)

    def test_aufraeumung_loescht_nur_alte_eintraege(self):
        alt = Zugriffslog.objects.create(mitarbeiter=self.m, klient=self.k, bereich="fallakte")
        # auto_now_add überschreiben: 430 Tage alt (> 1 Jahr)
        Zugriffslog.objects.filter(pk=alt.pk).update(zeit=timezone.now() - timedelta(days=430))
        Zugriffslog.objects.create(mitarbeiter=self.m, klient=self.k, bereich="bericht")  # frisch
        n = lf.zugriffslog_aufraeumen()
        self.assertEqual(n, 1)
        self.assertEqual(Zugriffslog.objects.count(), 1)
        self.assertEqual(Zugriffslog.objects.get().bereich, "bericht")

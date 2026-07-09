"""Tests Slice 1b: Kontingent- & Fristenüberwachung (Bewilligungs-Fristen,
Plausibilität in der Abrechnung, Cron-Command)."""
from datetime import date, time, timedelta
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from . import services
from .models import (Mitarbeiter, Team, Teamtyp, Rolle, Klient, Status,
                     Kostentraeger, Bewilligung, BewilligungStatus, Leistung, Leistungsart)

User = get_user_model()


class FristenTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="TBEW", typ=Teamtyp.values[0])
        self.betr = Mitarbeiter.objects.create(
            user=User.objects.create_user("betr", password="x"),
            name="Betr", rolle=Rolle.USER, team=self.team, kuerzel="betr")
        self.kt = Kostentraeger.objects.create(name="Bezirksamt Mitte von Berlin")

    def _klient(self, nachname):
        return Klient.objects.create(nachname=nachname, team=self.team,
                                     bezugsbetreuer=self.betr, status=Status.BETREUUNG)

    def _bew(self, klient, tage_bis_ende, status=BewilligungStatus.AKTIV, **kw):
        return Bewilligung.objects.create(
            klient=klient, kostentraeger=self.kt, fls_woche=Decimal("2.95"),
            kle_tag=Decimal("0.722167"), gueltig_von=date.today() - timedelta(days=30),
            gueltig_bis=date.today() + timedelta(days=tage_bis_ende), status=status, **kw)

    def test_auslaufende_bewilligung_erscheint(self):
        k = self._klient("Bald")
        self._bew(k, tage_bis_ende=30)
        fr = services.bewilligung_fristen(Klient.objects.all())
        self.assertEqual(len(fr), 1)
        self.assertFalse(fr[0]["fehlt"])
        self.assertEqual(fr[0]["klient"], k)
        self.assertAlmostEqual(fr[0]["tage_bis"], 30, delta=1)

    def test_lange_laufende_bewilligung_erscheint_nicht(self):
        k = self._klient("Lang")
        self._bew(k, tage_bis_ende=200)
        self.assertEqual(services.bewilligung_fristen(Klient.objects.all()), [])

    def test_fehlende_bewilligung_ist_kritisch(self):
        k = self._klient("Ohne")           # gar keine Bewilligung
        fr = services.bewilligung_fristen(Klient.objects.all())
        self.assertEqual(len(fr), 1)
        self.assertTrue(fr[0]["fehlt"])
        self.assertIsNone(fr[0]["bewilligung"])

    def test_nur_abgelaufene_zaehlt_als_fehlend(self):
        k = self._klient("Abgelaufen")
        # aktive, aber gestern beendet -> aktive_bewilligung() findet keine gültige
        self._bew(k, tage_bis_ende=-1)
        fr = services.bewilligung_fristen(Klient.objects.all())
        self.assertEqual(len(fr), 1)
        self.assertTrue(fr[0]["fehlt"])

    def test_sortierung_fehlt_zuerst(self):
        k1 = self._klient("Auslauf"); self._bew(k1, tage_bis_ende=10)
        self._klient("Fehlt")
        fr = services.bewilligung_fristen(Klient.objects.all())
        self.assertEqual(len(fr), 2)
        self.assertTrue(fr[0]["fehlt"])          # fehlende zuerst
        self.assertFalse(fr[1]["fehlt"])

    def test_beendete_klienten_ignoriert(self):
        k = self._klient("Weg"); k.status = Status.BEENDIGUNG; k.save()
        self.assertEqual(services.bewilligung_fristen(Klient.objects.all()), [])


class AbrechnungPlausibilitaetTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="TBEW", typ=Teamtyp.values[0])
        self.betr = Mitarbeiter.objects.create(
            user=User.objects.create_user("betr2", password="x"),
            name="Betr", rolle=Rolle.USER, team=self.team, kuerzel="betr")
        self.kt = Kostentraeger.objects.create(name="Bezirksamt Mitte von Berlin")
        p = services.get_parameter(date.today().year)
        p.fls_preis = Decimal("45.4568"); p.kle_je_tag = Decimal("0.722167"); p.save()
        self.k = Klient.objects.create(nachname="Voll", team=self.team,
                                       bezugsbetreuer=self.betr, status=Status.BETREUUNG)

    def _leistung_stunden(self, h):
        Leistung.objects.create(datum=date.today(), klient=self.k, leistungsart=Leistungsart.FS,
                                taetigkeit="Hausbesuch", betreuer=self.betr,
                                beginn=time(8, 0), ende=time(8 + h, 0))

    def test_ueber_kontingent_wird_markiert(self):
        # kleines Kontingent (fls_woche 0,5 -> al ~2,17/Monat), aber 6 dokumentierte Stunden
        Bewilligung.objects.create(klient=self.k, kostentraeger=self.kt,
                                   fls_woche=Decimal("0.5"), kle_tag=Decimal("0.722167"),
                                   gueltig_von=date.today() - timedelta(days=10))
        self._leistung_stunden(6)
        heute = date.today()
        z = services.abrechnungsuebersicht(Klient.objects.filter(pk=self.k.pk), heute.year, heute.month)[0]
        self.assertTrue(z["ueber_kontingent"])
        self.assertFalse(z["ohne_bewilligung"])

    def test_im_kontingent_nicht_markiert(self):
        Bewilligung.objects.create(klient=self.k, kostentraeger=self.kt,
                                   fls_woche=Decimal("3.81"), kle_tag=Decimal("0.722167"),
                                   gueltig_von=date.today() - timedelta(days=10))
        self._leistung_stunden(2)
        heute = date.today()
        z = services.abrechnungsuebersicht(Klient.objects.filter(pk=self.k.pk), heute.year, heute.month)[0]
        self.assertFalse(z["ueber_kontingent"])

    def test_ohne_bewilligung_wird_markiert(self):
        self._leistung_stunden(2)          # dokumentiert, aber keine Bewilligung
        heute = date.today()
        z = services.abrechnungsuebersicht(Klient.objects.filter(pk=self.k.pk), heute.year, heute.month)[0]
        self.assertTrue(z["ohne_bewilligung"])


class FristenCommandTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="TBEW", typ=Teamtyp.values[0])
        self.betr = Mitarbeiter.objects.create(
            user=User.objects.create_user("betr3", password="x"),
            name="Betr", rolle=Rolle.USER, team=self.team, kuerzel="betr")
        self.kt = Kostentraeger.objects.create(name="Bezirksamt Mitte von Berlin")

    def test_command_meldet_auslaufend(self):
        k = Klient.objects.create(nachname="Bald", team=self.team,
                                  bezugsbetreuer=self.betr, status=Status.BETREUUNG)
        Bewilligung.objects.create(klient=k, kostentraeger=self.kt, fls_woche=Decimal("2.95"),
                                   kle_tag=Decimal("0.722167"),
                                   gueltig_bis=date.today() + timedelta(days=20))
        out = StringIO()
        call_command("fristen_pruefen", stdout=out)      # kein fehlt -> Exit 0
        self.assertIn("laufen in", out.getvalue())

    def test_command_exit1_bei_fehlender(self):
        Klient.objects.create(nachname="Ohne", team=self.team,
                              bezugsbetreuer=self.betr, status=Status.BETREUUNG)
        with self.assertRaises(SystemExit):
            call_command("fristen_pruefen", stdout=StringIO())

"""Tests Slice 1a: Bewilligung als führendes Objekt + Cache-Sync (Abrechnung bleibt grün)."""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from . import services
from .models import (Mitarbeiter, Team, Teamtyp, Rolle, Klient, Status,
                     Kostentraeger, Bewilligung, BewilligungStatus)

User = get_user_model()


def _leitung(team):
    u = User.objects.create_user(username="chef", password="x")
    m = Mitarbeiter.objects.create(user=u, name="Chef", rolle=Rolle.LEITUNG, kuerzel="chef")
    m.leitet.set([team])
    return u, m


class BewilligungModellTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="TBEW", typ=Teamtyp.values[0])
        self.betr = Mitarbeiter.objects.create(
            user=User.objects.create_user("betr", password="x"),
            name="Betr", rolle=Rolle.USER, team=self.team, kuerzel="betr")
        self.kt = Kostentraeger.objects.create(name="Bezirksamt TK")
        self.k = Klient.objects.create(nachname="Galow", team=self.team,
                                       bezugsbetreuer=self.betr, status=Status.BETREUUNG)

    def _bew(self, **kw):
        d = dict(klient=self.k, kostentraeger=self.kt, aktenzeichen="AZ-1",
                 fls_woche=Decimal("2.95"), kle_tag=Decimal("0.722167"),
                 gueltig_von=date.today() - timedelta(days=10),
                 gueltig_bis=date.today() + timedelta(days=300),
                 status=BewilligungStatus.AKTIV)
        d.update(kw)
        return Bewilligung.objects.create(**d)

    def test_monatswerte_abgeleitet(self):
        b = self._bew()
        self.assertAlmostEqual(float(b.al_monat), 12.827, places=2)   # 2,95 × 4,3482
        self.assertAlmostEqual(float(b.kle_monat), 21.981, places=2)  # 0,722167 × 30,4375

    def test_sync_setzt_klient_cache(self):
        b = self._bew()
        self.k.refresh_from_db()
        self.assertAlmostEqual(float(self.k.al), 12.827, places=2)
        self.assertAlmostEqual(float(self.k.kle), 21.981, places=2)
        self.assertEqual(self.k.kue_bis, b.gueltig_bis)
        self.assertEqual(self.k.kostentraeger, "Bezirksamt TK")   # Freitext-Cache aus FK

    def test_aktive_bewilligung_und_fortschreibung(self):
        alt = self._bew(gueltig_von=date.today() - timedelta(days=400),
                        gueltig_bis=date.today() - timedelta(days=1),
                        status=BewilligungStatus.ABGELAUFEN, fls_woche=Decimal("2.089"))
        neu = self._bew(fls_woche=Decimal("3.81"), vorgaenger=alt)
        self.assertEqual(self.k.aktive_bewilligung(), neu)          # abgelaufene zählt nicht
        self.k.refresh_from_db()
        self.assertAlmostEqual(float(self.k.al), float(neu.al_monat), places=2)

    def test_aktive_bewilligung_nutzt_prefetch_ohne_query(self):
        # N+1-Fix: bei vorgeladenen Bewilligungen filtert aktive_bewilligung in Python und
        # löst KEINEN zusätzlichen Query aus – liefert aber dasselbe Ergebnis wie der Query.
        self._bew(gueltig_von=date.today() - timedelta(days=400),
                  gueltig_bis=date.today() - timedelta(days=1),
                  status=BewilligungStatus.ABGELAUFEN)
        neu = self._bew(fls_woche=Decimal("3.81"))
        k = Klient.objects.prefetch_related("bewilligungen").get(pk=self.k.pk)
        with self.assertNumQueries(0):
            b = k.aktive_bewilligung()
        self.assertEqual(b, neu)

    def test_migrations_rueckrechnung_roundtrip(self):
        # Bestand: Klient mit Monatswerten (wie vor der Migration). Die Migration leitet
        # daraus FLS/Woche = al/4,3482 und kLE/Tag = kle/30,4375 ab; die Bewilligung rechnet
        # zurück auf al_monat/kle_monat -> muss die Ausgangswerte ~erhalten (Rundung <0,001).
        from .models import WOCHEN_JE_MONAT, TAGE_JE_MONAT
        al, kle = Decimal("12.827"), Decimal("21.981")
        fls_woche = (al / WOCHEN_JE_MONAT)
        kle_tag = (kle / TAGE_JE_MONAT)
        b = self._bew(fls_woche=fls_woche, kle_tag=kle_tag)
        self.assertAlmostEqual(float(b.al_monat), float(al), places=2)
        self.assertAlmostEqual(float(b.kle_monat), float(kle), places=2)

    def test_abrechnung_liest_synchronisierten_cache(self):
        p = services.get_parameter(date.today().year)
        p.fls_preis = Decimal("45.4568")
        p.save()
        self._bew()
        # Vorschuss liest weiter al/kle (jetzt aus der Bewilligung gespeist) -> > 0
        v = services.vorschuss_monat(self.k, date.today().year)
        self.assertGreater(v, 0)


class BewilligungViewTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="TBEW", typ=Teamtyp.values[0])
        self.betr = Mitarbeiter.objects.create(
            user=User.objects.create_user("betr2", password="x"),
            name="Betr", rolle=Rolle.USER, team=self.team, kuerzel="betr")
        self.u, self.m = _leitung(self.team)
        self.kt = Kostentraeger.objects.create(name="Bezirksamt TK")
        self.k = Klient.objects.create(nachname="Galow", team=self.team,
                                       bezugsbetreuer=self.betr, status=Status.BETREUUNG)
        self.client.force_login(self.u)

    def test_bewilligungen_seite(self):
        resp = self.client.get(reverse("nachweis:bewilligungen", args=[self.k.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Bewilligungen")

    def test_speichern_erzeugt_und_synct(self):
        resp = self.client.post(reverse("nachweis:bewilligung_speichern"), {
            "klient": self.k.id, "kostentraeger": self.kt.id, "aktenzeichen": "AZ-9",
            "leistungstyp": "FLS", "gueltig_von": "2026-01-01", "gueltig_bis": "2026-12-31",
            "fls_woche": "3,81", "kle_tag": "0,722167", "status": "aktiv"})
        self.assertEqual(resp.status_code, 302)
        b = Bewilligung.objects.get(klient=self.k)
        self.assertEqual(b.aktenzeichen, "AZ-9")
        self.k.refresh_from_db()
        self.assertAlmostEqual(float(self.k.al), float(b.al_monat), places=2)

    def test_klient_form_ueberschreibt_nicht_bei_aktiver_bewilligung(self):
        Bewilligung.objects.create(klient=self.k, kostentraeger=self.kt,
                                   fls_woche=Decimal("3.81"), kle_tag=Decimal("0.722167"),
                                   gueltig_von=date.today() - timedelta(days=5),
                                   gueltig_bis=date.today() + timedelta(days=90))
        self.k.refresh_from_db()
        al_vorher = self.k.al
        # Klient-Formular speichern mit anderem al -> darf NICHT überschreiben
        self.client.post(reverse("nachweis:klient_speichern"), {
            "id": self.k.id, "nachname": "Galow", "team": str(self.team.id),
            "bezugsbetreuer": str(self.betr.id), "status": "Betreuung",
            "al": "99", "kle": "99", "hbg": ""})
        self.k.refresh_from_db()
        self.assertEqual(self.k.al, al_vorher)     # unverändert (Bewilligung ist führend)

    def test_kostentraeger_liste(self):
        resp = self.client.get(reverse("nachweis:kostentraeger_liste"))
        self.assertEqual(resp.status_code, 200)

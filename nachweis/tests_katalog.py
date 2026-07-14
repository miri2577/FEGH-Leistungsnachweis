"""Tests M1: Leistungskatalog + Entgeltsatz-Zeitscheiben (Mehr-Bereichs-Fundament)."""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from . import services
from .models import (Team, Teamtyp, Mitarbeiter, Rolle, Kostentraeger,
                     Leistungskatalog, Entgeltsatz, Abrechnungseinheit)

User = get_user_model()


class KatalogDefaultsTests(TestCase):
    def test_standard_eintraege_aus_migration(self):
        namen = set(Leistungskatalog.objects.values_list("name", flat=True))
        self.assertTrue(any("FLS Eingliederungshilfe" in n for n in namen))
        self.assertTrue(any("kLE" in n for n in namen))
        self.assertTrue(any("Jugendhilfe" in n and "ambulante" in n for n in namen))
        self.assertTrue(any("Tagessatz Jugendhilfe" in n for n in namen))
        self.assertTrue(any("besondere Wohnform" in n for n in namen))

    def test_jugendhilfe_saetze_2026_hinterlegt(self):
        """Öffentliche landeseinheitliche Sätze (VK Jugend 02/2025) ab 01.01.2026."""
        jug = Leistungskatalog.objects.get(name__contains="ambulante Jugendhilfe")
        betraege = {str(s.betrag) for s in jug.saetze.all()}
        self.assertIn("86.4400", betraege)     # mit Leitungsanteil
        self.assertIn("79.2900", betraege)     # ohne


class ZeitscheibenTests(TestCase):
    def setUp(self):
        self.k = Leistungskatalog.objects.create(name="Test-Tagessatz",
                                                 einheit=Abrechnungseinheit.TAGESSATZ)
        self.kt = Kostentraeger.objects.create(name="Jugendamt Test")

    def test_fortschreibung_preist_um(self):
        Entgeltsatz.objects.create(katalog=self.k, gueltig_von=date(2025, 1, 1),
                                   gueltig_bis=date(2025, 12, 31), betrag=Decimal("150"))
        Entgeltsatz.objects.create(katalog=self.k, gueltig_von=date(2026, 1, 1),
                                   betrag=Decimal("156"))
        alt = services.entgeltsatz_fuer(self.k, stichtag=date(2025, 6, 1))
        neu = services.entgeltsatz_fuer(self.k, stichtag=date(2026, 6, 1))
        self.assertEqual(alt.betrag, Decimal("150"))
        self.assertEqual(neu.betrag, Decimal("156"))       # Stichtag entscheidet

    def test_traegerspezifisch_gewinnt(self):
        Entgeltsatz.objects.create(katalog=self.k, gueltig_von=date(2026, 1, 1),
                                   betrag=Decimal("156"))                       # alle
        Entgeltsatz.objects.create(katalog=self.k, gueltig_von=date(2026, 1, 1),
                                   kostentraeger=self.kt, betrag=Decimal("160"))  # individuell
        s = services.entgeltsatz_fuer(self.k, kostentraeger=self.kt,
                                      stichtag=date(2026, 6, 1))
        self.assertEqual(s.betrag, Decimal("160"))
        # anderer Kostenträger ohne Individualsatz -> landeseinheitlich
        kt2 = Kostentraeger.objects.create(name="Anderes Amt")
        s2 = services.entgeltsatz_fuer(self.k, kostentraeger=kt2,
                                       stichtag=date(2026, 6, 1))
        self.assertEqual(s2.betrag, Decimal("156"))

    def test_variante(self):
        Entgeltsatz.objects.create(katalog=self.k, gueltig_von=date(2026, 1, 1),
                                   variante="mit Leitungsanteil", betrag=Decimal("86.44"))
        Entgeltsatz.objects.create(katalog=self.k, gueltig_von=date(2026, 1, 1),
                                   variante="ohne Leitungsanteil", betrag=Decimal("79.29"))
        s = services.entgeltsatz_fuer(self.k, stichtag=date(2026, 6, 1),
                                      variante="ohne Leitungsanteil")
        self.assertEqual(s.betrag, Decimal("79.29"))

    def test_kein_satz_vor_beginn(self):
        Entgeltsatz.objects.create(katalog=self.k, gueltig_von=date(2026, 1, 1),
                                   betrag=Decimal("156"))
        self.assertIsNone(services.entgeltsatz_fuer(self.k, stichtag=date(2025, 6, 1)))


class KatalogViewTests(TestCase):
    def setUp(self):
        team = Team.objects.create(name="TBEW", typ=Teamtyp.values[0])
        self.u = User.objects.create_user("chef", password="x")
        m = Mitarbeiter.objects.create(user=self.u, name="C", rolle=Rolle.LEITUNG, kuerzel="c")
        m.leitet.set([team])
        self.client.force_login(self.u)

    def test_seite_und_satz_anlegen(self):
        resp = self.client.get(reverse("nachweis:leistungskatalog"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Jugendhilfe")
        k = Leistungskatalog.objects.first()
        resp = self.client.post(reverse("nachweis:leistungskatalog"), {
            "aktion": "satz", "katalog": k.id, "betrag": "45,4568",
            "gueltig_von": "2026-01-01", "kommentar": "Test"})
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Entgeltsatz.objects.filter(katalog=k, betrag=Decimal("45.4568")).exists())

    def test_eintrag_anlegen(self):
        self.client.post(reverse("nachweis:leistungskatalog"), {
            "aktion": "eintrag", "name": "Tagesgruppe § 32", "einheit": "oeffnungstag"})
        self.assertTrue(Leistungskatalog.objects.filter(name="Tagesgruppe § 32").exists())

    def test_nur_leitung(self):
        nu = User.objects.create_user("norm", password="x")
        Mitarbeiter.objects.create(user=nu, name="N", rolle=Rolle.USER,
                                   team=Team.objects.first(), kuerzel="n")
        self.client.force_login(nu)
        resp = self.client.get(reverse("nachweis:leistungskatalog"))
        self.assertEqual(resp.status_code, 403)

    def test_bewilligung_mit_katalog(self):
        from .models import Klient, Status, Bewilligung
        team = Team.objects.first()
        betr = Mitarbeiter.objects.create(
            user=User.objects.create_user("b", password="x"),
            name="B", rolle=Rolle.USER, team=team, kuerzel="b")
        k = Klient.objects.create(nachname="K", team=team, bezugsbetreuer=betr,
                                  status=Status.BETREUUNG)
        kat = Leistungskatalog.objects.get(name__contains="ambulante Jugendhilfe")
        resp = self.client.post(reverse("nachweis:bewilligung_speichern"), {
            "klient": k.id, "leistungstyp": "FLS", "katalog": kat.id,
            "fls_woche": "3,0", "kle_tag": "0", "status": "aktiv"})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Bewilligung.objects.get(klient=k).katalog, kat)

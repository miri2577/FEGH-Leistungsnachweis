"""Tests Mahnwesen / Offene Posten: Zahlungsstand, Mahnstufen, Fälligkeit, Views."""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from . import services
from .models import (Team, Teamtyp, Mitarbeiter, Rolle, Klient, Status,
                     Kostentraeger, Rechnung, Rechnungsstatus, Zahlung, Mahnung,
                     Monatsfreigabe, Freigabestatus, Rechnungssteller)

User = get_user_model()


def _verwaltung():
    team = Team.objects.create(name="Verwaltung", typ=Teamtyp.VERWALTUNG)
    u = User.objects.create_user("verw", password="x")
    Mitarbeiter.objects.create(user=u, name="Verw", rolle=Rolle.USER, team=team, kuerzel="vw")
    return u


class ZahlungsstandTests(TestCase):
    def setUp(self):
        self.r = Rechnung.objects.create(nummer="2026-0100", empfaenger="Bezirksamt Test",
                                         jahr=2026, monat=6, datum=date(2026, 7, 1),
                                         faellig_am=date(2026, 7, 31),
                                         betrag=Decimal("100.00"),
                                         status=Rechnungsstatus.GESTELLT)

    def test_vollzahlung_setzt_bezahlt(self):
        Zahlung.objects.create(rechnung=self.r, datum=date(2026, 7, 20), betrag=Decimal("100.00"))
        self.r.refresh_from_db()
        self.assertEqual(self.r.status, Rechnungsstatus.BEZAHLT)
        self.assertEqual(self.r.offener_betrag, Decimal("0.00"))

    def test_teilzahlung_bleibt_gestellt(self):
        Zahlung.objects.create(rechnung=self.r, datum=date(2026, 7, 20), betrag=Decimal("40.00"))
        self.r.refresh_from_db()
        self.assertEqual(self.r.status, Rechnungsstatus.GESTELLT)
        self.assertEqual(self.r.offener_betrag, Decimal("60.00"))
        self.assertTrue(self.r.ist_offen)

    def test_zahlung_loeschen_reaktiviert(self):
        z = Zahlung.objects.create(rechnung=self.r, datum=date(2026, 7, 20), betrag=Decimal("100.00"))
        self.r.refresh_from_db()
        self.assertEqual(self.r.status, Rechnungsstatus.BEZAHLT)
        z.delete()
        self.r.refresh_from_db()
        self.assertEqual(self.r.status, Rechnungsstatus.GESTELLT)

    def test_ueberfaellig_berechnung(self):
        self.assertEqual(self.r.tage_ueberfaellig(date(2026, 8, 10)), 10)
        self.assertEqual(self.r.tage_ueberfaellig(date(2026, 7, 21)), -10)

    def test_faelligkeit_fallback_ohne_faellig_am(self):
        self.r.faellig_am = None
        self.assertEqual(self.r.faelligkeit, date(2026, 7, 31))   # datum + 30

    def test_mahnstufen_kette(self):
        self.assertEqual(self.r.mahnstufe, 0)
        Mahnung.objects.create(rechnung=self.r, stufe=1, datum=date(2026, 8, 5))
        Mahnung.objects.create(rechnung=self.r, stufe=2, datum=date(2026, 8, 25))
        self.assertEqual(self.r.mahnstufe, 2)
        m = self.r.mahnungen.get(stufe=2)
        self.assertEqual(m.zahlbar_bis, date(2026, 8, 25) + timedelta(days=14))


class RechnungErstellenFaelligkeitTests(TestCase):
    def test_faellig_am_aus_kostentraeger_zahlungsziel(self):
        team = Team.objects.create(name="TBEW", typ=Teamtyp.values[0])
        betr = Mitarbeiter.objects.create(user=User.objects.create_user("b", password="x"),
                                          name="B", rolle=Rolle.USER, team=team, kuerzel="b")
        kt = Kostentraeger.objects.create(name="Bezirksamt Test", zahlungsziel_tage=21)
        from .models import Bewilligung
        k = Klient.objects.create(nachname="K", team=team, bezugsbetreuer=betr,
                                  status=Status.BETREUUNG)
        Bewilligung.objects.create(klient=k, kostentraeger=kt, fls_woche=Decimal("2.95"),
                                   kle_tag=Decimal("0.722167"))
        mf = Monatsfreigabe.objects.create(klient=k, jahr=2026, monat=6,
                                           status=Freigabestatus.FREIGEGEBEN,
                                           betrag=Decimal("50"))
        r = services.rechnung_erstellen([mf], kt.name, 2026, 6, date(2026, 7, 1), betr)
        self.assertEqual(r.faellig_am, date(2026, 7, 22))          # +21 Tage
        self.assertEqual(r.kostentraeger, kt)


class MahnwesenViewTests(TestCase):
    def setUp(self):
        self.u = _verwaltung()
        self.client.force_login(self.u)
        s = Rechnungssteller.load()
        s.name = "Muster gGmbH"; s.iban = "DE02120300000000202051"
        s.kontakt_name = "M"; s.kontakt_tel = "1"; s.kontakt_mail = "m@example.org"; s.save()
        self.r = Rechnung.objects.create(nummer="2026-0101", empfaenger="Bezirksamt Test",
                                         jahr=2026, monat=6, datum=date.today() - timedelta(days=60),
                                         faellig_am=date.today() - timedelta(days=30),
                                         betrag=Decimal("200.00"),
                                         status=Rechnungsstatus.GESTELLT)

    def test_op_liste_zeigt_ueberfaellige(self):
        resp = self.client.get(reverse("nachweis:offene_posten"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "2026-0101")
        self.assertContains(resp, "überfällig")

    def test_zahlung_erfassen_view(self):
        resp = self.client.post(reverse("nachweis:zahlung_erfassen", args=[self.r.id]),
                                {"datum": date.today().isoformat(), "betrag": "200,00"})
        self.assertEqual(resp.status_code, 302)
        self.r.refresh_from_db()
        self.assertEqual(self.r.status, Rechnungsstatus.BEZAHLT)

    def test_mahnung_erstellen_und_druck(self):
        resp = self.client.post(reverse("nachweis:mahnung_erstellen", args=[self.r.id]),
                                {"frist_tage": "14"})
        self.assertEqual(resp.status_code, 302)
        m = self.r.mahnungen.get()
        self.assertEqual(m.stufe, 1)
        druck = self.client.get(reverse("nachweis:mahnung_druck", args=[m.id]))
        self.assertEqual(druck.status_code, 200)
        self.assertContains(druck, "Zahlungserinnerung")
        self.assertContains(druck, "200,00")            # deutsche Lokalisierung: Komma

    def test_bezahlte_rechnung_nicht_mahnbar(self):
        Zahlung.objects.create(rechnung=self.r, datum=date.today(), betrag=Decimal("200.00"))
        resp = self.client.post(reverse("nachweis:mahnung_erstellen", args=[self.r.id]), {})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self.r.mahnungen.count(), 0)

    # ---- Regressionstests aus dem adversarialen Review ----

    def test_storno_mit_zahlung_geblockt(self):
        """Geld-Schutz: Storno gäbe Positionen zur Doppel-Fakturierung frei."""
        Zahlung.objects.create(rechnung=self.r, datum=date.today(), betrag=Decimal("50.00"))
        resp = self.client.post(reverse("nachweis:rechnung_status", args=[self.r.id]),
                                {"status": "storniert"})
        self.assertEqual(resp.status_code, 302)
        self.r.refresh_from_db()
        self.assertNotEqual(self.r.status, Rechnungsstatus.STORNIERT)   # geblockt

    def test_zahlung_auf_entwurf_geblockt(self):
        self.r.status = Rechnungsstatus.ENTWURF
        self.r.save(update_fields=["status"])
        resp = self.client.post(reverse("nachweis:zahlung_erfassen", args=[self.r.id]),
                                {"betrag": "200,00"})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self.r.zahlungen.count(), 0)
        self.r.refresh_from_db()
        self.assertEqual(self.r.status, Rechnungsstatus.ENTWURF)        # unverändert

    def test_ueberzahlung_geblockt(self):
        resp = self.client.post(reverse("nachweis:zahlung_erfassen", args=[self.r.id]),
                                {"betrag": "2000,00"})                  # Rechnung: 200 €
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self.r.zahlungen.count(), 0)

    def test_kaputte_eingaben_kein_500(self):
        for wert in ("NaN", "Infinity", "abc", "-5"):
            resp = self.client.post(reverse("nachweis:zahlung_erfassen", args=[self.r.id]),
                                    {"betrag": wert})
            self.assertEqual(resp.status_code, 302, f"betrag={wert}")
        resp = self.client.post(reverse("nachweis:mahnung_erstellen", args=[self.r.id]),
                                {"frist_tage": "14a"})
        self.assertEqual(resp.status_code, 302)                         # Default statt 500
        resp = self.client.post(reverse("nachweis:zahlung_loeschen"), {"id": "abc"})
        self.assertEqual(resp.status_code, 404)                         # 404 statt 500

    def test_mahnung_vor_faelligkeit_geblockt(self):
        self.r.faellig_am = date.today() + timedelta(days=10)           # noch nicht fällig
        self.r.save(update_fields=["faellig_am"])
        resp = self.client.post(reverse("nachweis:mahnung_erstellen", args=[self.r.id]), {})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self.r.mahnungen.count(), 0)

    def test_folgestufe_erst_nach_fristablauf(self):
        Mahnung.objects.create(rechnung=self.r, stufe=1, datum=date.today(), frist_tage=14)
        resp = self.client.post(reverse("nachweis:mahnung_erstellen", args=[self.r.id]), {})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self.r.mahnungen.count(), 1)                   # keine 2. Stufe am selben Tag
        # Frist der Vorstufe abgelaufen -> Folgestufe erlaubt
        self.r.mahnungen.update(datum=date.today() - timedelta(days=20))
        self.client.post(reverse("nachweis:mahnung_erstellen", args=[self.r.id]), {})
        self.assertEqual(self.r.mahnungen.count(), 2)

    def test_storno_race_ueberschreibt_nicht(self):
        """zahlungsstand_aktualisieren darf einen parallelen Storno nie überschreiben."""
        z = Zahlung.objects.create(rechnung=self.r, datum=date.today(), betrag=Decimal("200.00"))
        # Simulierter paralleler Storno: DB hat bereits storniert, Instanz weiß es nicht
        Rechnung.objects.filter(pk=self.r.pk).update(status=Rechnungsstatus.STORNIERT)
        alte_instanz = z.rechnung
        alte_instanz.status = Rechnungsstatus.GESTELLT                  # veralteter In-Memory-Stand
        alte_instanz.zahlungsstand_aktualisieren()
        self.r.refresh_from_db()
        self.assertEqual(self.r.status, Rechnungsstatus.STORNIERT)      # bleibt storniert

    def test_nicht_verwaltung_kommt_nicht_rein(self):
        team = Team.objects.create(name="TBEW", typ=Teamtyp.values[0])
        nu = User.objects.create_user("normal", password="x")
        Mitarbeiter.objects.create(user=nu, name="N", rolle=Rolle.USER, team=team, kuerzel="n")
        self.client.force_login(nu)
        resp = self.client.get(reverse("nachweis:offene_posten"))
        self.assertEqual(resp.status_code, 302)        # redirect zu start
        resp = self.client.post(reverse("nachweis:zahlung_erfassen", args=[self.r.id]),
                                {"betrag": "1"})
        self.assertEqual(resp.status_code, 403)

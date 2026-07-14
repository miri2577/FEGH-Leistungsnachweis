"""Tests M2: Belegung, Abwesenheits-Regel-Engine (Tz 22 / Beschluss 8/2007), Tagessatz."""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from . import services_belegung
from .models import (Team, Teamtyp, Mitarbeiter, Rolle, Klient, Status,
                     Angebot, AngebotsTyp, Belegung, AbwesenheitsartKlient,
                     KlientAbwesenheit, Leistungskatalog, Entgeltsatz,
                     Abrechnungseinheit, Kostentraeger, Bewilligung)

User = get_user_model()


class BelegungBasis(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="Wohngruppe", typ=Teamtyp.values[0])
        self.u = User.objects.create_user("chef", password="x")
        m = Mitarbeiter.objects.create(user=self.u, name="C", rolle=Rolle.LEITUNG, kuerzel="c")
        m.leitet.set([self.team])
        self.betr = Mitarbeiter.objects.create(
            user=User.objects.create_user("b", password="x"),
            name="B", rolle=Rolle.USER, team=self.team, kuerzel="b")
        self.k = Klient.objects.create(nachname="Kind", team=self.team,
                                       bezugsbetreuer=self.betr, status=Status.BETREUUNG)
        self.katalog = Leistungskatalog.objects.create(
            name="Test-Tagessatz JH", einheit=Abrechnungseinheit.TAGESSATZ)
        Entgeltsatz.objects.create(katalog=self.katalog, gueltig_von=date(2026, 1, 1),
                                   betrag=Decimal("150.00"))
        self.angebot = Angebot.objects.create(name="WG Nord", team=self.team,
                                              typ=AngebotsTyp.WOHNGRUPPE_JUG,
                                              katalog=self.katalog, plaetze=8)
        self.client.force_login(self.u)

    def _belegung(self, einzug=date(2026, 6, 1), auszug=None):
        return Belegung.objects.create(klient=self.k, angebot=self.angebot,
                                       einzug=einzug, auszug=auszug)


class KalenderTests(BelegungBasis):
    def test_voller_monat(self):
        b = self._belegung()
        kal = services_belegung.monatskalender(b, 2026, 6)
        self.assertEqual(kal["summen"]["belegt"], 30)
        self.assertEqual(kal["summen"]["anwesend"], 30)

    def test_aufnahme_und_entlasstag_zaehlen(self):
        b = self._belegung(einzug=date(2026, 6, 10), auszug=date(2026, 6, 20))
        kal = services_belegung.monatskalender(b, 2026, 6)
        self.assertEqual(kal["summen"]["belegt"], 11)          # 10.–20. inkl. beider Tage

    def test_abwesenheit_rueckkehrtag_anwesend(self):
        b = self._belegung()
        art = AbwesenheitsartKlient.objects.get(name__contains="Krankenhaus/Kur (Jugendhilfe)")
        # abwesend 5.–9. (bis = letzter Abwesenheitstag), Rückkehr am 10.
        KlientAbwesenheit.objects.create(belegung=b, art=art,
                                         von=date(2026, 6, 5), bis=date(2026, 6, 9))
        kal = services_belegung.monatskalender(b, 2026, 6)
        self.assertEqual(kal["summen"]["abwesend"], 5)
        self.assertEqual(kal["summen"]["anwesend"], 25)
        self.assertEqual(kal["tage"][9]["status"], "anwesend")  # 10.6. = Index 9

    def test_weiterzahlungsgrenze_je_ereignis(self):
        """Entweichung: max. 14 Tage vergütet, danach 0 % (Tz 22)."""
        b = self._belegung()
        art = AbwesenheitsartKlient.objects.get(name__contains="Entweichung")
        KlientAbwesenheit.objects.create(belegung=b, art=art,
                                         von=date(2026, 6, 1), bis=date(2026, 6, 20))
        kal = services_belegung.monatskalender(b, 2026, 6)
        # Tag 1-14 vergütet (100 %), Tag 15-20 = 0 %
        self.assertEqual(kal["summen"]["verguetet_aequiv"],
                         Decimal("14") + Decimal("10"))         # 14 abw. + 10 anwesend
        self.assertEqual(kal["tage"][14]["anteil"], Decimal("0"))   # 15.6.

    def test_jahreskontingent_kumulativ(self):
        """Beurlaubung: 30 Tage je KALENDERJAHR über mehrere Ereignisse."""
        b = self._belegung(einzug=date(2026, 1, 1))
        art = AbwesenheitsartKlient.objects.get(name__contains="Beurlaubung")
        KlientAbwesenheit.objects.create(belegung=b, art=art,
                                         von=date(2026, 2, 1), bis=date(2026, 2, 25))   # 25 T
        KlientAbwesenheit.objects.create(belegung=b, art=art,
                                         von=date(2026, 6, 1), bis=date(2026, 6, 10))   # +10 = 35
        kal = services_belegung.monatskalender(b, 2026, 6)
        # im Juni sind nur noch 5 Tage im Kontingent (26.–30. Jahres-Tag), Tag 6–10 = 0 %
        abw_verguetet = sum(t["anteil"] for t in kal["tage"] if t["status"] == "abwesend")
        self.assertEqual(abw_verguetet, Decimal("5"))

    def test_freihaltegeld_abzug(self):
        """EGH: volle Vergütung minus Beköstigungssatz (abzug_je_tag)."""
        b = self._belegung()
        art = AbwesenheitsartKlient.objects.get(name="Urlaub/Krankenhaus/Kur (EGH Wohnform)")
        art.abzug_je_tag = Decimal("12.50")
        art.save()
        KlientAbwesenheit.objects.create(belegung=b, art=art,
                                         von=date(2026, 6, 1), bis=date(2026, 6, 4))    # 4 T
        satz = Entgeltsatz.objects.get(katalog=self.katalog)
        kal = services_belegung.monatskalender(b, 2026, 6, satz=satz)
        erwartet = (Decimal("30") * Decimal("150.00")) - 4 * Decimal("12.50")
        self.assertEqual(kal["betrag"], erwartet)

    def test_satz_aufloesung_ueber_bewilligung(self):
        b = self._belegung()
        kt = Kostentraeger.objects.create(name="Jugendamt X")
        Bewilligung.objects.create(klient=self.k, kostentraeger=kt, katalog=self.katalog,
                                   gueltig_von=date(2026, 1, 1))
        Entgeltsatz.objects.create(katalog=self.katalog, kostentraeger=kt,
                                   gueltig_von=date(2026, 1, 1), betrag=Decimal("160.00"))
        satz = services_belegung.satz_fuer_belegung(b, date(2026, 6, 30))
        self.assertEqual(satz.betrag, Decimal("160.00"))        # trägerspezifisch gewinnt

    def test_melde_warnung(self):
        b = self._belegung()
        art = AbwesenheitsartKlient.objects.get(name__contains="Krankenhaus/Kur (Jugendhilfe)")
        KlientAbwesenheit.objects.create(belegung=b, art=art,
                                         von=date.today())                     # Tag 1: keine Warnung
        self.assertEqual(services_belegung.melde_warnungen([b]), [])
        KlientAbwesenheit.objects.all().delete()
        from datetime import timedelta
        KlientAbwesenheit.objects.create(belegung=b, art=art,
                                         von=date.today() - timedelta(days=5))  # Tag 6 > Frist 3
        w = services_belegung.melde_warnungen([b])
        self.assertEqual(len(w), 1)
        # nach Meldung keine Warnung mehr
        a = KlientAbwesenheit.objects.get()
        a.gemeldet_am = date.today()
        a.save()
        self.assertEqual(services_belegung.melde_warnungen([b]), [])


class ReviewFixTests(BelegungBasis):
    """Regressionstests aus dem adversarialen M2-Review."""

    def test_kb_ueber_3_tage_kappt(self):
        """HOCH-Befund: Kurzbesuch war unbegrenzt -> jetzt max. 3 Tage vergütet."""
        b = self._belegung()
        kb = AbwesenheitsartKlient.objects.get(kuerzel="KB")
        KlientAbwesenheit.objects.create(belegung=b, art=kb,
                                         von=date(2026, 6, 1), bis=date(2026, 6, 10))
        kal = services_belegung.monatskalender(b, 2026, 6)
        abw_verguetet = sum(t["anteil"] for t in kal["tage"] if t["status"] == "abwesend")
        self.assertEqual(abw_verguetet, Decimal("3"))           # nur Tag 1–3

    def test_kontingent_clippt_auf_auszug(self):
        """HOCH-Befund: offene Abwesenheit über den Auszug hinaus darf kein
        Jahreskontingent für unvergütete Tage verbrauchen."""
        frh = AbwesenheitsartKlient.objects.get(name="Urlaub/Krankenhaus/Kur (EGH Wohnform)")
        b1 = self._belegung(einzug=date(2026, 1, 1), auszug=date(2026, 1, 20))
        KlientAbwesenheit.objects.create(belegung=b1, art=frh,
                                         von=date(2026, 1, 10))          # offen (vergessen)
        b2 = Belegung.objects.create(klient=self.k, angebot=self.angebot,
                                     einzug=date(2026, 6, 1))
        KlientAbwesenheit.objects.create(belegung=b2, art=frh,
                                         von=date(2026, 6, 1), bis=date(2026, 6, 30))
        kal = services_belegung.monatskalender(b2, 2026, 6)
        # real verbraucht: 11 Tage (10.–20.1.) + Juni-Tage -> Juni voll im 91er-Kontingent
        abw_verguetet = sum(t["anteil"] for t in kal["tage"] if t["status"] == "abwesend")
        self.assertEqual(abw_verguetet, Decimal("30"))

    def test_ueberlappende_abwesenheiten_nicht_doppelt(self):
        url = AbwesenheitsartKlient.objects.get(name__contains="Beurlaubung")
        b = self._belegung(einzug=date(2026, 1, 1))
        KlientAbwesenheit.objects.create(belegung=b, art=url,
                                         von=date(2026, 6, 1), bis=date(2026, 6, 10))
        KlientAbwesenheit.objects.create(belegung=b, art=url,
                                         von=date(2026, 6, 5), bis=date(2026, 6, 15))
        menge = services_belegung._jahres_tagesmenge(self.k, url, date(2026, 6, 30))
        self.assertEqual(len(menge), 15)                        # 1.–15.6., nicht 10+11

    def test_satz_bei_auszug_im_monat(self):
        """Satz-Auflösung am letzten belegten Tag, nicht am Monatsende."""
        kt = Kostentraeger.objects.create(name="Jugendamt Y")
        Bewilligung.objects.create(klient=self.k, kostentraeger=kt, katalog=self.katalog,
                                   gueltig_von=date(2026, 1, 1), gueltig_bis=date(2026, 6, 10))
        Entgeltsatz.objects.create(katalog=self.katalog, kostentraeger=kt,
                                   gueltig_von=date(2026, 1, 1), betrag=Decimal("170.00"))
        b = self._belegung(einzug=date(2026, 6, 1), auszug=date(2026, 6, 10))
        satz = services_belegung.satz_fuer_belegung(b, date(2026, 6, 30))
        self.assertEqual(satz.betrag, Decimal("170.00"))        # trägerspezifisch, trotz Auszug

    def test_einzug_vor_kuenftiger_belegung_geblockt(self):
        Belegung.objects.create(klient=self.k, angebot=self.angebot,
                                einzug=date(2026, 9, 1))        # vorausgeplant, offen
        resp = self.client.post(reverse("nachweis:belegung_speichern"), {
            "angebot": self.angebot.id, "klient": self.k.id, "einzug": "2026-07-01"})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self.k.belegungen.count(), 1)          # Überlappung geblockt

    def test_auszug_leeren_mit_folgebelegung_geblockt(self):
        b1 = self._belegung(einzug=date(2026, 1, 1), auszug=date(2026, 3, 31))
        Belegung.objects.create(klient=self.k, angebot=self.angebot,
                                einzug=date(2026, 4, 1))
        self.client.post(reverse("nachweis:belegung_speichern"),
                         {"id": b1.id, "auszug": ""})           # wieder öffnen -> Overlap
        b1.refresh_from_db()
        self.assertEqual(b1.auszug, date(2026, 3, 31))          # unverändert

    def test_auszug_schliesst_offene_abwesenheit(self):
        b = self._belegung(einzug=date(2026, 6, 1))
        kh = AbwesenheitsartKlient.objects.get(name__contains="Krankenhaus/Kur (Jugendhilfe)")
        a = KlientAbwesenheit.objects.create(belegung=b, art=kh, von=date(2026, 6, 5))
        self.client.post(reverse("nachweis:belegung_speichern"),
                         {"id": b.id, "auszug": "2026-06-20"})
        a.refresh_from_db()
        self.assertEqual(a.bis, date(2026, 6, 20))

    def test_cross_team_einzug_geblockt(self):
        fremd_team = Team.objects.create(name="Anderes eigenes", typ=Teamtyp.values[0])
        Mitarbeiter.objects.get(user=self.u).leitet.add(fremd_team)
        k2 = Klient.objects.create(nachname="Fremd", team=fremd_team,
                                   bezugsbetreuer=self.betr, status=Status.BETREUUNG)
        self.client.post(reverse("nachweis:belegung_speichern"), {
            "angebot": self.angebot.id, "klient": k2.id, "einzug": "2026-06-01"})
        self.assertEqual(k2.belegungen.count(), 0)              # Team-Grenze respektiert

    def test_abwesenheit_ausserhalb_belegung_geblockt(self):
        b = self._belegung(einzug=date(2026, 6, 10), auszug=date(2026, 6, 20))
        kh = AbwesenheitsartKlient.objects.get(name__contains="Krankenhaus/Kur (Jugendhilfe)")
        self.client.post(reverse("nachweis:klient_abwesenheit_speichern"), {
            "belegung": b.id, "art": kh.id, "von": "2026-06-01"})   # vor Einzug
        self.assertEqual(b.abwesenheiten.count(), 0)

    def test_inaktive_art_geblockt(self):
        b = self._belegung()
        kh = AbwesenheitsartKlient.objects.get(name__contains="Krankenhaus/Kur (Jugendhilfe)")
        kh.aktiv = False
        kh.save()
        resp = self.client.post(reverse("nachweis:klient_abwesenheit_speichern"), {
            "belegung": b.id, "art": kh.id, "von": "2026-06-05"})
        self.assertEqual(resp.status_code, 404)

    def test_extremes_jahr_kein_500(self):
        self._belegung()
        for j in ("99999", "-5", "0"):
            resp = self.client.get(reverse("nachweis:belegungskalender",
                                           args=[self.angebot.id]), {"jahr": j})
            self.assertEqual(resp.status_code, 200, f"jahr={j}")


class BelegungViewTests(BelegungBasis):
    def test_angebote_seite_und_kalender(self):
        resp = self.client.get(reverse("nachweis:angebote"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "WG Nord")
        self._belegung()
        resp = self.client.get(reverse("nachweis:belegungskalender", args=[self.angebot.id]),
                               {"jahr": 2026, "monat": 6})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Kind")
        self.assertContains(resp, "4500,00")        # 30 Tage × 150 € (deutsche Lokalisierung)

    def test_einzug_und_doppelbelegung_geblockt(self):
        resp = self.client.post(reverse("nachweis:belegung_speichern"), {
            "angebot": self.angebot.id, "klient": self.k.id, "einzug": "2026-06-01"})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Belegung.objects.count(), 1)
        # zweite laufende Belegung am selben Tag -> geblockt
        self.client.post(reverse("nachweis:belegung_speichern"), {
            "angebot": self.angebot.id, "klient": self.k.id, "einzug": "2026-07-01"})
        self.assertEqual(Belegung.objects.count(), 1)

    def test_auszug_vor_einzug_geblockt(self):
        b = self._belegung(einzug=date(2026, 6, 10))
        self.client.post(reverse("nachweis:belegung_speichern"),
                         {"id": b.id, "auszug": "2026-06-01"})
        b.refresh_from_db()
        self.assertIsNone(b.auszug)

    def test_fremdes_team_kein_zugriff(self):
        fu = User.objects.create_user("fremd", password="x")
        fm = Mitarbeiter.objects.create(user=fu, name="F", rolle=Rolle.LEITUNG, kuerzel="f")
        fm.leitet.set([Team.objects.create(name="Anderes", typ=Teamtyp.values[0])])
        self.client.force_login(fu)
        resp = self.client.get(reverse("nachweis:belegungskalender", args=[self.angebot.id]))
        self.assertEqual(resp.status_code, 404)

    def test_normaler_user_kein_zugriff(self):
        self.client.force_login(self.betr.user)
        self.assertEqual(self.client.get(reverse("nachweis:angebote")).status_code, 403)


class AbwesenheitsartenDefaultTests(TestCase):
    def test_regeln_aus_migration(self):
        arten = {a.name: a for a in AbwesenheitsartKlient.objects.all()}
        self.assertEqual(arten["Entweichung (Jugendhilfe)"].max_tage, 14)
        self.assertEqual(arten["Beurlaubung/Ferien (Jugendhilfe)"].max_tage, 30)
        self.assertEqual(arten["Beurlaubung/Ferien (Jugendhilfe)"].basis, "jahr")
        self.assertEqual(arten["Urlaub/Krankenhaus/Kur (EGH Wohnform)"].max_tage, 91)
        self.assertEqual(arten["Inobhutnahme (Jugendhilfe)"].max_tage, 2)
        # Review-Fix: KB ist auf 3 Tage begrenzt (sonst wäre die FRH-Regel umgehbar)
        self.assertEqual(arten["Kurzbesuch ≤ 3 Tage (EGH Wohnform)"].max_tage, 3)
        # BAO bleibt bewusst unbegrenzt (volle Vergütung mit Berichtspflicht)
        self.assertIsNone(arten["Betreuung am anderen Ort (EGH)"].max_tage)

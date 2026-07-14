"""Tests Selbstzahler / Wohnkosten (WBVG): Vereinbarung, Monatslauf, Zugriff, Storno."""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from . import services_wohnkosten as wk
from .models import (Team, Teamtyp, Mitarbeiter, Rolle, Klient, Status,
                     Wohnkostenvereinbarung, Wohnkostenposition, WohnkostenKategorie,
                     SelbstzahlerRechnung, Rechnungsstatus)

User = get_user_model()


class WohnkostenBasis(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="WG", typ=Teamtyp.BEW)
        self.u = User.objects.create_user("chef", password="x")
        self.lu = Mitarbeiter.objects.create(user=self.u, name="Chef", rolle=Rolle.LEITUNG, kuerzel="c")
        self.lu.leitet.set([self.team])
        self.k = Klient.objects.create(nachname="Bewohner", vorname="B", team=self.team,
                                       bezugsbetreuer=self.lu, status=Status.BETREUUNG)
        self.client.force_login(self.u)

    def _vereinbarung(self, **extra):
        d = dict(klient=self.k, aktiv=True, gueltig_von=date(2026, 1, 1))
        d.update(extra)
        v = Wohnkostenvereinbarung.objects.create(**d)
        Wohnkostenposition.objects.create(vereinbarung=v, kategorie=WohnkostenKategorie.MIETE,
                                          bezeichnung="Grundmiete", monatsbetrag=Decimal("450.00"))
        Wohnkostenposition.objects.create(vereinbarung=v, kategorie=WohnkostenKategorie.VERPFLEGUNG,
                                          bezeichnung="Verpflegung", monatsbetrag=Decimal("230.50"))
        return v


class MonatslaufTests(WohnkostenBasis):
    def test_erzeugt_rechnung_mit_summe(self):
        self._vereinbarung()
        erg = wk.rechnungen_erzeugen(2026, 7, self.lu, Klient.objects.filter(pk=self.k.pk))
        self.assertEqual(len(erg["erstellt"]), 1)
        r = SelbstzahlerRechnung.objects.get()
        self.assertEqual(r.betrag, Decimal("680.50"))
        self.assertEqual(r.positionen.count(), 2)
        self.assertTrue(r.nummer.startswith("WK-2026-"))
        self.assertEqual(r.faellig_am, date(2026, 7, 1))

    def test_kein_doppellauf(self):
        self._vereinbarung()
        wk.rechnungen_erzeugen(2026, 7, self.lu, Klient.objects.all())
        erg = wk.rechnungen_erzeugen(2026, 7, self.lu, Klient.objects.all())
        self.assertEqual(len(erg["erstellt"]), 0)
        self.assertEqual(erg["uebersprungen"], 1)
        self.assertEqual(SelbstzahlerRechnung.objects.count(), 1)

    def test_inaktive_und_ungueltige_uebersprungen(self):
        self._vereinbarung(aktiv=False)
        v2 = self._vereinbarung(gueltig_von=date(2027, 1, 1))   # erst 2027 gültig
        erg = wk.rechnungen_erzeugen(2026, 7, self.lu, Klient.objects.all())
        self.assertEqual(len(erg["erstellt"]), 0)

    def test_mehrdeutige_vereinbarungen_nicht_abgerechnet(self):
        """Review MITTEL: zwei gleichzeitig gültige Vereinbarungen -> kein geratener
        Betrag, sondern als 'mehrdeutig' gemeldet und übersprungen."""
        self._vereinbarung()
        self._vereinbarung()      # zweite, ebenfalls aktiv+gültig ab 2026-01
        erg = wk.rechnungen_erzeugen(2026, 7, self.lu, Klient.objects.all())
        self.assertEqual(len(erg["erstellt"]), 0)
        self.assertEqual(erg["mehrdeutig"], [self.k.name])
        self.assertEqual(SelbstzahlerRechnung.objects.count(), 0)

    def test_storno_erlaubt_neulauf(self):
        self._vereinbarung()
        wk.rechnungen_erzeugen(2026, 7, self.lu, Klient.objects.all())
        r = SelbstzahlerRechnung.objects.get()
        r.status = Rechnungsstatus.STORNIERT
        r.save()
        erg = wk.rechnungen_erzeugen(2026, 7, self.lu, Klient.objects.all())
        self.assertEqual(len(erg["erstellt"]), 1)   # storniert blockt den Constraint nicht


class WohnkostenViewTests(WohnkostenBasis):
    def test_uebersicht_und_position_anlegen(self):
        v = Wohnkostenvereinbarung.objects.create(klient=self.k, aktiv=True)
        self.assertEqual(self.client.get(reverse("nachweis:wohnkosten")).status_code, 200)
        self.client.post(reverse("nachweis:wohnkosten_position_speichern"), {
            "vereinbarung": v.id, "kategorie": "miete",
            "bezeichnung": "Zimmermiete", "monatsbetrag": "399,90"})
        p = Wohnkostenposition.objects.get()
        self.assertEqual(p.monatsbetrag, Decimal("399.90"))

    def test_erzeugen_ueber_view(self):
        self._vereinbarung()
        r = self.client.post(reverse("nachweis:wohnkosten_erzeugen"),
                             {"jahr": 2026, "monat": 7})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(SelbstzahlerRechnung.objects.count(), 1)

    def test_bezahlt_und_storno(self):
        self._vereinbarung()
        wk.rechnungen_erzeugen(2026, 7, self.lu, Klient.objects.all())
        r = SelbstzahlerRechnung.objects.get()
        self.client.post(reverse("nachweis:selbstzahler_aktion"),
                         {"id": r.id, "aktion": "bezahlt"})   # ohne Datum -> heute (plausibel)
        r.refresh_from_db()
        self.assertEqual(r.status, Rechnungsstatus.BEZAHLT)
        self.assertEqual(r.bezahlt_am, date.today())
        self.client.post(reverse("nachweis:selbstzahler_aktion"),
                         {"id": r.id, "aktion": "storno"})
        r.refresh_from_db()
        self.assertEqual(r.status, Rechnungsstatus.STORNIERT)

    def test_pdf_rendert(self):
        self._vereinbarung()
        wk.rechnungen_erzeugen(2026, 7, self.lu, Klient.objects.all())
        r = SelbstzahlerRechnung.objects.get()
        resp = self.client.get(reverse("nachweis:selbstzahler_pdf", args=[r.id]))
        self.assertContains(resp, "Grundmiete")
        self.assertContains(resp, "680,50")               # dt. Komma

    def test_user_ohne_zugriff(self):
        u2 = User.objects.create_user("ma", password="x")
        Mitarbeiter.objects.create(user=u2, name="MA", rolle=Rolle.USER,
                                   team=self.team, kuerzel="m")
        self.client.force_login(u2)
        self.assertEqual(self.client.get(reverse("nachweis:wohnkosten")).status_code, 403)

    def test_fremdes_team_404(self):
        fremd = Klient.objects.create(nachname="Fremd",
                                      team=Team.objects.create(name="X", typ=Teamtyp.BEW),
                                      bezugsbetreuer=self.lu, status=Status.BETREUUNG)
        v = Wohnkostenvereinbarung.objects.create(klient=fremd, aktiv=True)
        self.assertEqual(self.client.get(
            reverse("nachweis:wohnkosten_vereinbarung", args=[v.id])).status_code, 404)

    def test_ungueltiger_betrag_wird_abgelehnt(self):
        """Review MITTEL: Müll-Eingabe darf nicht still als 0,00 gespeichert werden."""
        v = Wohnkostenvereinbarung.objects.create(klient=self.k, aktiv=True)
        self.client.post(reverse("nachweis:wohnkosten_position_speichern"), {
            "vereinbarung": v.id, "kategorie": "miete", "bezeichnung": "X", "monatsbetrag": "abc"})
        self.assertEqual(Wohnkostenposition.objects.count(), 0)     # nicht gespeichert
        # deutsches Format mit Tausenderpunkt wird korrekt geparst
        self.client.post(reverse("nachweis:wohnkosten_position_speichern"), {
            "vereinbarung": v.id, "kategorie": "miete", "bezeichnung": "Y", "monatsbetrag": "1.234,56"})
        self.assertEqual(Wohnkostenposition.objects.get().monatsbetrag, Decimal("1234.56"))

    def test_fremdes_angebot_nicht_anhaengbar(self):
        """Review MITTEL: Angebot eines fremden Teams darf nicht referenzierbar sein."""
        from .models import Angebot, AngebotsTyp
        fremd_team = Team.objects.create(name="Andere WG", typ=Teamtyp.BEW)
        fremd_ang = Angebot.objects.create(name="Fremd-Wohnform", team=fremd_team,
                                           typ=AngebotsTyp.WG_VERBUND, plaetze=4)
        self.client.post(reverse("nachweis:wohnkosten_vereinbarung_anlegen"),
                         {"klient": self.k.id, "angebot": fremd_ang.id})
        v = Wohnkostenvereinbarung.objects.get()
        self.assertIsNone(v.angebot)               # fremdes Angebot nicht übernommen

    def test_bezahlt_am_plausibilitaet(self):
        self._vereinbarung()
        wk.rechnungen_erzeugen(2026, 7, self.lu, Klient.objects.all())
        r = SelbstzahlerRechnung.objects.get()
        # Zukunftsdatum wird abgelehnt
        self.client.post(reverse("nachweis:selbstzahler_aktion"),
                         {"id": r.id, "aktion": "bezahlt", "bezahlt_am": "2099-01-01"})
        r.refresh_from_db()
        self.assertEqual(r.status, Rechnungsstatus.GESTELLT)   # nicht auf bezahlt

    def test_nummernkollision_verwirft_nicht_ganzen_lauf(self):
        """Review HOCH: eine belegte Nummer darf den restlichen Lauf nicht rollbacken."""
        from .models import Angebot
        # zweite Bewohner*in mit eigener Vereinbarung
        k2 = Klient.objects.create(nachname="Zweit", team=self.team,
                                   bezugsbetreuer=self.lu, status=Status.BETREUUNG)
        for k in (self.k, k2):
            v = Wohnkostenvereinbarung.objects.create(klient=k, aktiv=True, gueltig_von=date(2026, 1, 1))
            Wohnkostenposition.objects.create(vereinbarung=v, bezeichnung="Miete", monatsbetrag=Decimal("400"))
        # WK-2026-0001 vorbelegen (simuliert Kollision) – der Lauf muss trotzdem beide bedienen
        SelbstzahlerRechnung.objects.create(nummer="WK-2026-0001", klient=self.k, empfaenger="x",
                                            jahr=2025, monat=1, datum=date(2025, 1, 1), betrag=0,
                                            status=Rechnungsstatus.STORNIERT)
        erg = wk.rechnungen_erzeugen(2026, 7, self.lu, Klient.objects.all())
        self.assertEqual(len(erg["erstellt"]), 2)   # beide erstellt trotz belegter 0001

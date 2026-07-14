"""Tests Phase 2 / Slice 2b: Berichts-Engine (Vorlagen als Daten, Workflow, Fristen)."""
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import (Team, Teamtyp, Mitarbeiter, Rolle, Klient, Status,
                     Bericht, BerichtsStatus, Berichtsvorlage)

User = get_user_model()


class BerichteBasis(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="TBEW", typ=Teamtyp.values[0])
        self.u = User.objects.create_user("betr", password="x")
        self.betr = Mitarbeiter.objects.create(user=self.u, name="Betr", rolle=Rolle.USER,
                                               team=self.team, kuerzel="betr")
        self.k = Klient.objects.create(nachname="Galow", team=self.team,
                                       bezugsbetreuer=self.betr, status=Status.BETREUUNG,
                                       kue_bis=date.today() + timedelta(days=60))
        self.client.force_login(self.u)


class VorlagenTests(TestCase):
    def test_standard_vorlagen_vorhanden(self):
        """Migration 0027: EGH- UND SGB-VIII-Vorlagen (Berichte sehen je Bereich anders aus)."""
        namen = set(Berichtsvorlage.objects.values_list("name", flat=True))
        self.assertIn("Entwicklungsbericht Eingliederungshilfe", namen)
        self.assertIn("Informationsbericht (Vorlage 1.01)", namen)
        self.assertIn("Entwicklungsbericht zur Hilfekonferenz (§ 36 SGB VIII)", namen)
        self.assertIn("Abschlussbericht Hilfe zur Erziehung (SGB VIII)", namen)
        # Gliederungen unterscheiden sich (Wirkungsdimensionen nur SGB VIII)
        jug = Berichtsvorlage.objects.get(name__contains="§ 36")
        egh = Berichtsvorlage.objects.get(name="Entwicklungsbericht Eingliederungshilfe")
        self.assertTrue(any("Wirkungsdimensionen" in a for a in jug.abschnitte))
        self.assertFalse(any("Wirkungsdimensionen" in a for a in egh.abschnitte))


class BerichtWorkflowTests(BerichteBasis):
    def _bericht(self):
        v = Berichtsvorlage.objects.first()
        return Bericht.objects.create(klient=self.k, vorlage=v,
                                      faellig_am=self.k.kue_bis)

    def test_anlegen_ueber_view(self):
        v = Berichtsvorlage.objects.get(name="Informationsbericht (Vorlage 1.01)")
        resp = self.client.post(reverse("nachweis:bericht_speichern"), {
            "klient": self.k.id, "vorlage": v.id,
            "zeitraum_von": "2025-07-01", "zeitraum_bis": "2026-07-01",
            "faellig_am": self.k.kue_bis.isoformat()})
        self.assertEqual(resp.status_code, 302)
        b = Bericht.objects.get()
        self.assertEqual(b.vorlage, v)
        self.assertEqual(b.status, BerichtsStatus.OFFEN)

    def test_text_setzt_in_arbeit(self):
        b = self._bericht()
        self.client.post(reverse("nachweis:bericht_speichern"), {
            "klient": self.k.id, "id": b.id, "inhalt": "Erster Entwurf …"})
        b.refresh_from_db()
        self.assertEqual(b.status, BerichtsStatus.IN_ARBEIT)

    def test_versand_erst_nach_besprechen(self):
        """örV/AV: Bericht ist VOR dem Versand mit Klient*in zu besprechen."""
        b = self._bericht()
        resp = self.client.post(reverse("nachweis:bericht_status"),
                                {"id": b.id, "status": "versendet"})
        self.assertEqual(resp.status_code, 302)
        b.refresh_from_db()
        self.assertNotEqual(b.status, BerichtsStatus.VERSENDET)   # geblockt
        # korrekt: erst besprochen, dann versendet
        self.client.post(reverse("nachweis:bericht_status"), {"id": b.id, "status": "besprochen"})
        self.client.post(reverse("nachweis:bericht_status"), {"id": b.id, "status": "versendet"})
        b.refresh_from_db()
        self.assertEqual(b.status, BerichtsStatus.VERSENDET)
        self.assertIsNotNone(b.besprochen_am)
        self.assertIsNotNone(b.versendet_am)

    def test_versendet_pflegt_klient_feld(self):
        b = self._bericht()
        self.client.post(reverse("nachweis:bericht_status"), {"id": b.id, "status": "besprochen"})
        self.client.post(reverse("nachweis:bericht_status"), {"id": b.id, "status": "versendet"})
        self.k.refresh_from_db()
        self.assertEqual(self.k.versendet_am, date.today())      # „…versendet am" synchron

    def test_ueberfaellig(self):
        b = Bericht.objects.create(klient=self.k, faellig_am=date.today() - timedelta(days=3))
        self.assertTrue(b.ueberfaellig)
        b.status = BerichtsStatus.VERSENDET
        self.assertFalse(b.ueberfaellig)

    def test_workflow_ohne_inhalt_in_history(self):
        b = self._bericht()
        b.inhalt = "Sehr persönlicher Berichtstext"
        b.save()
        # Art-9-Text ist aus der History-Tabelle ausgenommen (excluded_fields)
        self.assertFalse(hasattr(b.history.first(), "inhalt"))


class ReviewFixTests(BerichteBasis):
    """Regressionstests aus dem adversarialen Review (Workflow-Härtung)."""

    def _bericht(self, **kw):
        return Bericht.objects.create(klient=self.k,
                                      vorlage=Berichtsvorlage.objects.first(), **kw)

    def test_versendeter_bericht_festgeschrieben(self):
        b = self._bericht(status=BerichtsStatus.VERSENDET, inhalt="Original")
        resp = self.client.post(reverse("nachweis:bericht_speichern"), {
            "klient": self.k.id, "id": b.id, "inhalt": "Manipuliert"})
        self.assertEqual(resp.status_code, 302)
        b.refresh_from_db()
        self.assertEqual(b.inhalt, "Original")                 # unverändert

    def test_textaenderung_nach_besprechen_erfordert_neues_besprechen(self):
        b = self._bericht(status=BerichtsStatus.BESPROCHEN, inhalt="Alt",
                          besprochen_am=date.today())
        self.client.post(reverse("nachweis:bericht_speichern"), {
            "klient": self.k.id, "id": b.id, "inhalt": "Neu"})
        b.refresh_from_db()
        self.assertEqual(b.status, BerichtsStatus.IN_ARBEIT)   # zurückgesetzt
        self.assertIsNone(b.besprochen_am)

    def test_ruecksprung_loescht_versanddatum(self):
        b = self._bericht(status=BerichtsStatus.BESPROCHEN, besprochen_am=date.today())
        self.client.post(reverse("nachweis:bericht_status"), {"id": b.id, "status": "versendet"})
        b.refresh_from_db()
        self.assertIsNotNone(b.versendet_am)
        self.client.post(reverse("nachweis:bericht_status"), {"id": b.id, "status": "in_arbeit"})
        b.refresh_from_db()
        self.assertIsNone(b.versendet_am)                      # altes Datum gilt nicht mehr

    def test_faellig_default_ist_kue_minus_70(self):
        resp = self.client.get(reverse("nachweis:berichte", args=[self.k.id]))
        erwartet = (self.k.kue_bis - timedelta(days=70)).isoformat()
        self.assertContains(resp, erwartet)                    # 10 Wochen VOR KÜ-Ende

    def test_kaputte_ids_kein_500(self):
        resp = self.client.post(reverse("nachweis:bericht_status"),
                                {"id": "abc", "status": "besprochen"})
        self.assertEqual(resp.status_code, 404)

    def test_rohpaket_no_store(self):
        b = self._bericht()
        resp = self.client.get(reverse("nachweis:bericht_rohpaket", args=[b.id]))
        self.assertEqual(resp["Cache-Control"], "no-store")


class RohpaketTests(BerichteBasis):
    """Slice 2c: Export für FEGH-Bericht (TeilhabeAssist)."""

    def setUp(self):
        super().setUp()
        from .models import Ziel, ZielArt, Leistung, Leistungsart
        from datetime import time
        self.v = Berichtsvorlage.objects.get(name="Informationsbericht (Vorlage 1.01)")
        self.b = Bericht.objects.create(
            klient=self.k, vorlage=self.v,
            zeitraum_von=date.today() - timedelta(days=180),
            zeitraum_bis=date.today())
        rz = Ziel.objects.create(klient=self.k, art=ZielArt.RICHTUNGSZIEL,
                                 titel="Selbstständig wohnen")
        self.z = Ziel.objects.create(klient=self.k, art=ZielArt.HANDLUNGSZIEL,
                                     uebergeordnet=rz, titel="Einkauf allein",
                                     indikator="4 Wochen ohne Begleitung")
        # Doku IM Zeitraum (mit Zielbezug) + Doku AUSSERHALB (darf nicht ins Paket)
        drin = Leistung.objects.create(datum=date.today() - timedelta(days=30),
                                       klient=self.k, leistungsart=Leistungsart.FS,
                                       taetigkeit="Hausbesuch", betreuer=self.betr,
                                       beginn=time(9, 0), ende=time(10, 0),
                                       dokumentation="Einkauf gemeinsam geplant.")
        drin.ziele.add(self.z)
        Leistung.objects.create(datum=date.today() - timedelta(days=400),
                                klient=self.k, leistungsart=Leistungsart.FS,
                                taetigkeit="Alt", betreuer=self.betr,
                                dokumentation="Uralt-Eintrag.")

    def test_json_rohpaket(self):
        resp = self.client.get(reverse("nachweis:bericht_rohpaket", args=[self.b.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("application/json", resp["Content-Type"])
        self.assertNotIn("Galow", resp["Content-Disposition"])   # kein Name im Dateinamen
        d = resp.json()
        self.assertEqual(d["format"], "fegh-berichtspaket")
        self.assertEqual(d["klient"]["nachname"], "Galow")
        self.assertEqual(len(d["verlaufsdokumentation"]), 1)     # nur Zeitraum-Doku
        self.assertEqual(d["verlaufsdokumentation"][0]["zielbezug"], ["Einkauf allein"])
        self.assertEqual(len(d["ziele"]), 2)
        self.assertEqual(d["vorlage"]["abschnitte"][0], "Anlass des Berichts")

    def test_markdown_rohpaket(self):
        resp = self.client.get(reverse("nachweis:bericht_rohpaket", args=[self.b.id]),
                               {"format": "md"})
        self.assertEqual(resp.status_code, 200)
        text = resp.content.decode()
        self.assertIn("# Berichts-Rohpaket", text)
        self.assertIn("Einkauf gemeinsam geplant.", text)
        self.assertNotIn("Uralt-Eintrag.", text)                 # außerhalb des Zeitraums
        self.assertIn("Zielbezug: Einkauf allein", text)

    def test_export_wird_protokolliert(self):
        self.assertIsNone(self.b.exportiert_am)
        self.client.get(reverse("nachweis:bericht_rohpaket", args=[self.b.id]))
        self.b.refresh_from_db()
        self.assertIsNotNone(self.b.exportiert_am)               # -> Auditlog-Feldänderung

    def test_rohpaket_fremdes_team_kein_zugriff(self):
        fremd = User.objects.create_user("fremd2", password="x")
        Mitarbeiter.objects.create(user=fremd, name="F", rolle=Rolle.USER,
                                   team=Team.objects.create(name="WG2", typ=Teamtyp.values[0]),
                                   kuerzel="f2")
        self.client.force_login(fremd)
        resp = self.client.get(reverse("nachweis:bericht_rohpaket", args=[self.b.id]))
        self.assertEqual(resp.status_code, 404)


class BerichtZugriffTests(BerichteBasis):
    def test_seite_und_druck(self):
        b = Bericht.objects.create(klient=self.k,
                                   vorlage=Berichtsvorlage.objects.first(),
                                   inhalt="Text.")
        resp = self.client.get(reverse("nachweis:berichte", args=[self.k.id]))
        self.assertEqual(resp.status_code, 200)
        druck = self.client.get(reverse("nachweis:bericht_druck", args=[b.id]))
        self.assertEqual(druck.status_code, 200)
        self.assertContains(druck, "Text.")

    def test_fremdes_team_kein_zugriff(self):
        fremd = User.objects.create_user("fremd", password="x")
        Mitarbeiter.objects.create(user=fremd, name="F", rolle=Rolle.USER,
                                   team=Team.objects.create(name="WG", typ=Teamtyp.values[0]),
                                   kuerzel="f")
        self.client.force_login(fremd)
        resp = self.client.get(reverse("nachweis:berichte", args=[self.k.id]))
        self.assertEqual(resp.status_code, 404)

    def test_loeschen_nur_leitung(self):
        b = Bericht.objects.create(klient=self.k)
        resp = self.client.post(reverse("nachweis:bericht_loeschen"), {"id": b.id})
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(Bericht.objects.filter(pk=b.pk).exists())

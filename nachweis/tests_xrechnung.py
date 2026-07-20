"""Tests XRechnung-Export (UBL 3.0): Pflichtfelder, USt-Befreiung, Voraussetzungen."""
from datetime import date
from decimal import Decimal
from xml.etree import ElementTree as ET

from django.test import TestCase

from . import xrechnung
from .xrechnung import CAC, CBC, INVOICE_NS, CREDITNOTE_NS
from .models import (Team, Teamtyp, Mitarbeiter, Rolle, Klient, Status,
                     Kostentraeger, KostentraegerTyp, Rechnung, Rechnungsstatus,
                     Monatsfreigabe, Freigabestatus, Rechnungssteller, Rechnungstyp)
from django.contrib.auth import get_user_model

User = get_user_model()


class XRechnungTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="TBEW", typ=Teamtyp.values[0])
        self.betr = Mitarbeiter.objects.create(
            user=User.objects.create_user("betr", password="x"),
            name="Betr", rolle=Rolle.USER, team=self.team, kuerzel="betr")
        self.kt = Kostentraeger.objects.create(
            name="Bezirksamt Mitte von Berlin", typ=KostentraegerTyp.BEZIRKSAMT,
            leitweg_id="11-1001-31", zahlungsziel_tage=30)
        # vollständiger Rechnungssteller
        s = Rechnungssteller.load()
        s.name = "Muster gGmbH"; s.strasse = "Musterstr. 1"; s.plz = "10115"; s.ort = "Berlin"
        s.ust_id = "DE123456789"; s.iban = "DE02120300000000202051"; s.bic = "BYLADEM1001"
        s.kontakt_name = "Frau Muster"; s.kontakt_tel = "+49 30 000000"
        s.kontakt_mail = "rechnung@example.org"
        s.befreiungsgrund = "Steuerfrei nach § 4 Nr. 16 UStG"; s.save()
        self.k = Klient.objects.create(nachname="Galow", team=self.team, bezugsbetreuer=self.betr,
                                       status=Status.BETREUUNG, person_id="BE-100001")
        self.r = Rechnung.objects.create(
            nummer="RE-2026-0007", empfaenger=self.kt.name, kostentraeger=self.kt,
            jahr=2026, monat=6, datum=date(2026, 7, 1), betrag=Decimal("1234.56"),
            status=Rechnungsstatus.ENTWURF)
        Monatsfreigabe.objects.create(klient=self.k, jahr=2026, monat=6,
                                      status=Freigabestatus.ABGERECHNET, rechnung=self.r,
                                      betrag=Decimal("1234.56"), fls_summe=Decimal("20"))

    def _xml(self):
        return ET.fromstring(xrechnung.build_ubl(self.r))

    def test_root_und_profil(self):
        root = self._xml()
        self.assertEqual(root.tag, f"{{{INVOICE_NS}}}Invoice")
        cust = root.find(f"{{{CBC}}}CustomizationID").text
        self.assertIn("xrechnung_3.0", cust)

    def test_leitweg_id_in_buyer_reference(self):
        root = self._xml()
        self.assertEqual(root.find(f"{{{CBC}}}BuyerReference").text, "11-1001-31")

    def test_rechnungsnummer_und_betrag(self):
        root = self._xml()
        self.assertEqual(root.find(f"{{{CBC}}}ID").text, "RE-2026-0007")
        payable = root.find(f"{{{CAC}}}LegalMonetaryTotal/{{{CBC}}}PayableAmount").text
        self.assertEqual(payable, "1234.56")

    def test_umsatzsteuerbefreiung_kategorie_E(self):
        root = self._xml()
        cat = root.find(f"{{{CAC}}}TaxTotal/{{{CAC}}}TaxSubtotal/{{{CAC}}}TaxCategory")
        self.assertEqual(cat.find(f"{{{CBC}}}ID").text, "E")
        self.assertEqual(cat.find(f"{{{CBC}}}Percent").text, "0.00")
        self.assertEqual(cat.find(f"{{{CBC}}}TaxExemptionReasonCode").text, "vatex-eu-132-1g")
        self.assertIn("§ 4 Nr. 16", cat.find(f"{{{CBC}}}TaxExemptionReason").text)
        # Steuerbetrag muss 0 sein
        self.assertEqual(root.find(f"{{{CAC}}}TaxTotal/{{{CBC}}}TaxAmount").text, "0.00")

    def test_verkaeufer_und_iban(self):
        xml = xrechnung.build_ubl(self.r).decode()
        self.assertIn("Muster gGmbH", xml)
        self.assertIn("DE02120300000000202051", xml)      # IBAN
        self.assertIn("rechnung@example.org", xml)         # Kontakt-Mail (BG-6)

    def test_eine_position_je_freigabe(self):
        root = self._xml()
        lines = root.findall(f"{{{CAC}}}InvoiceLine")
        self.assertEqual(len(lines), 1)
        self.assertIn("BE-100001", lines[0].find(f"{{{CAC}}}Item/{{{CBC}}}Name").text)

    def test_voraussetzungen_vollstaendig(self):
        self.assertEqual(xrechnung.pruefe_voraussetzungen(self.r), [])

    def test_voraussetzungen_ohne_leitweg(self):
        self.kt.leitweg_id = ""; self.kt.save()
        probleme = xrechnung.pruefe_voraussetzungen(self.r)
        self.assertTrue(any("Leitweg-ID" in p for p in probleme))

    def test_voraussetzungen_unvollstaendiger_steller(self):
        s = Rechnungssteller.load(); s.iban = ""; s.save()
        probleme = xrechnung.pruefe_voraussetzungen(self.r)
        self.assertTrue(any("IBAN" in p for p in probleme))


class GutschriftCreditNoteTests(TestCase):
    """Gutschriften als UBL-CreditNote (Typ 381, positive Beträge, Bezug zur Originalrechnung)."""
    def setUp(self):
        self.team = Team.objects.create(name="TBEW", typ=Teamtyp.values[0])
        self.betr = Mitarbeiter.objects.create(
            user=User.objects.create_user("gbetr", password="x"),
            name="Betr", rolle=Rolle.USER, team=self.team, kuerzel="gb")
        self.kt = Kostentraeger.objects.create(
            name="Bezirksamt Mitte von Berlin", typ=KostentraegerTyp.BEZIRKSAMT,
            leitweg_id="11-1001-31", zahlungsziel_tage=30)
        s = Rechnungssteller.load()
        s.name = "Muster gGmbH"; s.strasse = "Musterstr. 1"; s.plz = "10115"; s.ort = "Berlin"
        s.ust_id = "DE123456789"; s.iban = "DE02120300000000202051"; s.bic = "BYLADEM1001"
        s.kontakt_name = "Frau Muster"; s.kontakt_tel = "+49 30 000000"
        s.kontakt_mail = "rechnung@example.org"
        s.befreiungsgrund = "Steuerfrei nach § 4 Nr. 16 UStG"; s.save()
        self.k = Klient.objects.create(nachname="Galow", team=self.team, bezugsbetreuer=self.betr,
                                       status=Status.BETREUUNG, person_id="BE-100001")
        self.original = Rechnung.objects.create(
            nummer="RE-2026-0007", empfaenger=self.kt.name, kostentraeger=self.kt,
            jahr=2026, monat=6, datum=date(2026, 7, 1), betrag=Decimal("1234.56"),
            status=Rechnungsstatus.GESTELLT)
        self.gut = Rechnung.objects.create(
            nummer="GS-2026-0001", typ=Rechnungstyp.GUTSCHRIFT, storno_zu=self.original,
            empfaenger=self.kt.name, kostentraeger=self.kt, jahr=2026, monat=6,
            datum=date(2026, 7, 2), betrag=Decimal("-1234.56"), status=Rechnungsstatus.ENTWURF)
        Monatsfreigabe.objects.create(klient=self.k, jahr=2026, monat=6,
                                      status=Freigabestatus.ABGERECHNET, rechnung=self.gut,
                                      betrag=Decimal("-1234.56"), fls_summe=Decimal("20"))

    def _cn(self):
        return ET.fromstring(xrechnung.build_ubl(self.gut))

    def test_creditnote_root_und_typecode(self):
        root = self._cn()
        self.assertEqual(root.tag, f"{{{CREDITNOTE_NS}}}CreditNote")
        self.assertEqual(root.find(f"{{{CBC}}}CreditNoteTypeCode").text, "381")
        self.assertIsNone(root.find(f"{{{CBC}}}DueDate"))         # Gutschrift ist nicht zahlbar

    def test_betraege_positiv(self):
        root = self._cn()
        payable = root.find(f"{{{CAC}}}LegalMonetaryTotal/{{{CBC}}}PayableAmount").text
        self.assertEqual(payable, "1234.56")                     # positiv trotz -1234,56 Rechnungsbetrag

    def test_bezug_auf_originalrechnung(self):
        ref = self._cn().find(
            f"{{{CAC}}}BillingReference/{{{CAC}}}InvoiceDocumentReference/{{{CBC}}}ID")
        self.assertIsNotNone(ref)
        self.assertEqual(ref.text, "RE-2026-0007")

    def test_creditnote_line(self):
        root = self._cn()
        lines = root.findall(f"{{{CAC}}}CreditNoteLine")
        self.assertEqual(len(lines), 1)
        self.assertIsNotNone(lines[0].find(f"{{{CBC}}}CreditedQuantity"))
        self.assertEqual(lines[0].find(f"{{{CBC}}}LineExtensionAmount").text, "1234.56")

    def test_creditnote_line_bei_service_gutschrift(self):
        # Realer Pfad: gutschrift_erstellen verknüpft KEINE Position mit der Gutschrift.
        # Ohne synthetische Zeile hätte der Beleg 0 Zeilen -> BR-16/BR-CO-10-Verstoß.
        from . import services
        orig = Rechnung.objects.create(
            nummer="RE-2026-0099", empfaenger=self.kt.name, kostentraeger=self.kt,
            jahr=2026, monat=6, datum=date(2026, 7, 1), betrag=Decimal("500.00"),
            status=Rechnungsstatus.GESTELLT)
        gut, err = services.gutschrift_erstellen(orig, self.betr)
        self.assertIsNone(err)
        self.assertEqual(gut.positionen.count(), 0)          # Service verknüpft keine Position
        root = ET.fromstring(xrechnung.build_ubl(gut))
        lines = root.findall(f"{{{CAC}}}CreditNoteLine")
        self.assertEqual(len(lines), 1)                      # trotzdem genau eine (synthetische) Zeile
        self.assertEqual(lines[0].find(f"{{{CBC}}}LineExtensionAmount").text, "500.00")

    def test_regulaere_rechnung_bleibt_invoice(self):
        root = ET.fromstring(xrechnung.build_ubl(self.original))
        self.assertEqual(root.tag, f"{{{INVOICE_NS}}}Invoice")
        self.assertEqual(root.find(f"{{{CBC}}}InvoiceTypeCode").text, "380")

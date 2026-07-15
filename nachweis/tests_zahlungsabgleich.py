"""Tests camt.053-Import + Zahlungsabgleich."""
from datetime import date
from decimal import Decimal

from django.test import TestCase, Client
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model

from . import camt
from .models import Team, Teamtyp, Mitarbeiter, Rolle, Rechnung, Rechnungsstatus, Zahlung

User = get_user_model()


def _ntry(betrag, cdtdbt, zweck, datum="2026-07-15"):
    return (f'<Ntry><Amt Ccy="EUR">{betrag}</Amt><CdtDbtInd>{cdtdbt}</CdtDbtInd>'
            f'<BookgDt><Dt>{datum}</Dt></BookgDt>'
            f'<NtryDtls><TxDtls><RmtInf><Ustrd>{zweck}</Ustrd></RmtInf></TxDtls></NtryDtls></Ntry>')


def _camt(*entries):
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02">'
            f'<BkToCstmrStmt><Stmt>{"".join(entries)}</Stmt></BkToCstmrStmt></Document>').encode()


class CamtParseTests(TestCase):
    def test_nur_crdt(self):
        e = camt.parse_camt(_camt(_ntry("500.00", "CRDT", "Rechnung 2026-0007"),
                                  _ntry("20.00", "DBIT", "Gebühr")))
        self.assertEqual(len(e), 1)
        self.assertEqual(e[0]["betrag"], Decimal("500.00"))
        self.assertEqual(e[0]["datum"], "2026-07-15")

    def test_ungueltiges_xml(self):
        self.assertIsNone(camt.parse_camt(b"kein xml"))

    def test_rechnungsnummer_erkennen(self):
        self.assertEqual(camt.finde_rechnungsnummer("Ueberw. 2026-0042 BA"), "2026-0042")
        self.assertIsNone(camt.finde_rechnungsnummer("ohne Nummer"))


class ZahlungsabgleichViewTests(TestCase):
    def setUp(self):
        vw = Team.objects.create(name="VWz", typ=Teamtyp.VERWALTUNG)
        self.uv = User.objects.create_user("vz", password="x")
        Mitarbeiter.objects.create(user=self.uv, name="V", rolle=Rolle.USER, team=vw, kuerzel="v")
        self.uu = User.objects.create_user("uz", password="x")
        Mitarbeiter.objects.create(user=self.uu, name="U", rolle=Rolle.USER, kuerzel="u",
                                   team=Team.objects.create(name="Tz", typ=Teamtyp.BEW))
        self.r = Rechnung.objects.create(nummer="2026-0007", empfaenger="BA", jahr=2026, monat=6,
                                         datum=date(2026, 7, 1), betrag=Decimal("500.00"),
                                         status=Rechnungsstatus.GESTELLT)

    def _upload(self, xml, user=None):
        c = Client(); c.force_login(user or self.uv)
        return c.post("/zahlungsabgleich/",
                      {"datei": SimpleUploadedFile("k.xml", xml, content_type="text/xml")})

    def test_bucht_bei_nummer_match(self):
        self._upload(_camt(_ntry("500.00", "CRDT", "Zahlung Rechnung 2026-0007")))
        self.assertEqual(self.r.zahlungen.count(), 1)
        self.r.refresh_from_db()
        self.assertEqual(self.r.status, Rechnungsstatus.BEZAHLT)

    def test_dbit_ignoriert(self):
        self._upload(_camt(_ntry("500.00", "DBIT", "Rechnung 2026-0007")))
        self.assertEqual(Zahlung.objects.count(), 0)

    def test_falsche_nummer_nicht_gebucht(self):
        self._upload(_camt(_ntry("500.00", "CRDT", "Rechnung 2026-9999")))
        self.assertEqual(Zahlung.objects.count(), 0)

    def test_betrag_ueber_offen_nicht_gebucht(self):
        self._upload(_camt(_ntry("999.00", "CRDT", "Rechnung 2026-0007")))
        self.assertEqual(Zahlung.objects.count(), 0)

    def test_kein_doppel_buchen(self):
        xml = _camt(_ntry("500.00", "CRDT", "Rechnung 2026-0007"))
        self._upload(xml)
        self._upload(xml)
        self.assertEqual(Zahlung.objects.count(), 1)

    def test_nur_verwaltung(self):
        c = Client(); c.force_login(self.uu)
        self.assertEqual(c.get("/zahlungsabgleich/").status_code, 302)

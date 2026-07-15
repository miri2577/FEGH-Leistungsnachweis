"""Erzeugt aus einer Rechnung die XRechnung 3.0 als UBL-Invoice-XML (EN16931-konform).

Zielplattform Berlin: OZG-RE (xrechnung-bdr.de) erwartet reine XRechnung-XML (UBL oder
CII gleichwertig) – kein ZUGFeRD-PDF. Wir erzeugen UBL bewusst selbst (stdlib xml.etree),
weil hier genau EIN klar definierter Rechnungstyp vorkommt: die monatliche Sammelrechnung
der Eingliederungshilfe, vollständig umsatzsteuerbefreit nach § 4 Nr. 16 UStG (USt-Kategorie
„E", 0 %). Das gibt volle Feld-Kontrolle, keine fragile Fremd-Library und exakt testbare BTs.

WICHTIG: Vor dem echten Versand die Datei mit dem KoSIT-Validator bzw. dem Online-Prüftool
(xeinkauf.de) gegen die BR-DE-Businessregeln prüfen – dieser Generator erzeugt die Struktur,
nicht die amtliche Konformitätsprüfung. Die Leitweg-ID (BT-10) muss die echte, vom Bezirksamt
vergebene ID sein.
"""
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from xml.etree import ElementTree as ET

from .models import Rechnungssteller, Rechnungstyp

INVOICE_NS = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
CREDITNOTE_NS = "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2"
CAC = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
CBC = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"

# XRechnung 3.0 (aktuell), CIUS von EN16931 – BT-24 Specification identifier
CUSTOMIZATION_ID = ("urn:cen.eu:en16931:2017#compliant#"
                    "urn:xeinkauf.de:kosit:xrechnung_3.0")
PROFILE_ID = "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0"   # BT-23 Geschäftsprozess

# USt-Befreiung Eingliederungshilfe (§ 4 Nr. 16 UStG) -> Kategorie E
VATEX_CODE = "vatex-eu-132-1g"          # BT-121 (EN16931-Pendant zu § 4 Nr. 16)

ET.register_namespace("", INVOICE_NS)
ET.register_namespace("cac", CAC)
ET.register_namespace("cbc", CBC)


def _q2(x) -> str:
    return str(Decimal(x or 0).quantize(Decimal("0.01"), ROUND_HALF_UP))


def _sub(parent, ns, tag, text=None, **attrs):
    el = ET.SubElement(parent, f"{{{ns}}}{tag}", {k.replace("_", ""): v for k, v in attrs.items()})
    if text is not None:
        el.text = str(text)
    return el


def pruefe_voraussetzungen(rechnung) -> list:
    """Liste fehlender Pflichtangaben für eine gültige XRechnung (leer = versandfertig)."""
    probleme = []
    s = Rechnungssteller.load()
    if not s.name:
        probleme.append("Rechnungssteller: Name fehlt")
    if not (s.strasse and s.plz and s.ort):
        probleme.append("Rechnungssteller: Anschrift unvollständig (Straße/PLZ/Ort)")
    if not (s.ust_id or s.steuernummer):
        probleme.append("Rechnungssteller: USt-IdNr. oder Steuernummer fehlt")
    if not s.iban:
        probleme.append("Rechnungssteller: IBAN fehlt")
    if not (s.kontakt_name and s.kontakt_tel and s.kontakt_mail):
        probleme.append("Rechnungssteller: Kontakt (Name/Telefon/E-Mail) unvollständig – für XRechnung Pflicht")
    kt = rechnung.kostentraeger
    if not kt:
        probleme.append("Rechnung: kein strukturierter Kostenträger verknüpft")
    elif not kt.leitweg_id:
        probleme.append(f'Kostenträger „{kt.name}“: Leitweg-ID (BT-10) fehlt')
    return probleme


def _positionen(rechnung):
    return list(rechnung.positionen.select_related("klient"))


def build_ubl(rechnung) -> bytes:
    """Serialisiert die Rechnung als XRechnung-3.0-UBL (bytes, UTF-8, mit XML-Deklaration)."""
    s = Rechnungssteller.load()
    kt = rechnung.kostentraeger
    positionen = _positionen(rechnung)

    # Gutschriften werden als UBL-CreditNote (Typ 381) mit POSITIVEN Beträgen erzeugt –
    # der negative Rechnungsbetrag der App wird betragsmäßig (abs) übernommen, das Vorzeichen
    # steckt in der Dokumentart. Reguläre Rechnungen bleiben UBL-Invoice (Typ 380).
    gutschrift = rechnung.typ == Rechnungstyp.GUTSCHRIFT
    ns_root = CREDITNOTE_NS if gutschrift else INVOICE_NS
    ET.register_namespace("", ns_root)

    root = ET.Element(f"{{{ns_root}}}{'CreditNote' if gutschrift else 'Invoice'}")
    _sub(root, CBC, "CustomizationID", CUSTOMIZATION_ID)
    _sub(root, CBC, "ProfileID", PROFILE_ID)
    _sub(root, CBC, "ID", rechnung.nummer)                      # BT-1
    _sub(root, CBC, "IssueDate", rechnung.datum.isoformat())    # BT-2
    ziel = (kt.zahlungsziel_tage if kt and kt.zahlungsziel_tage else s.zahlungsziel_tage) or 30
    if gutschrift:
        _sub(root, CBC, "CreditNoteTypeCode", "381")            # Gutschrift (keine DueDate)
    else:
        _sub(root, CBC, "DueDate", (rechnung.datum + timedelta(days=ziel)).isoformat())  # BT-9
        _sub(root, CBC, "InvoiceTypeCode", "380")               # Handelsrechnung
    if rechnung.notiz:
        _sub(root, CBC, "Note", rechnung.notiz)                 # BT-22
    _sub(root, CBC, "DocumentCurrencyCode", "EUR")              # BT-5
    _sub(root, CBC, "BuyerReference", (kt.leitweg_id if kt else "") or "")  # BT-10 Leitweg-ID
    # Bezug auf die stornierte Originalrechnung (BG-3, für die Gutschrift maßgeblich).
    if gutschrift and rechnung.storno_zu_id:
        br = _sub(root, CAC, "BillingReference")
        _sub(_sub(br, CAC, "InvoiceDocumentReference"), CBC, "ID", rechnung.storno_zu.nummer)

    # ---- Verkäufer (BG-4) ----
    supplier = _sub(_sub(root, CAC, "AccountingSupplierParty"), CAC, "Party")
    if s.kontakt_mail:
        _sub(supplier, CBC, "EndpointID", s.kontakt_mail, schemeID="EM")   # BT-34
    pn = _sub(supplier, CAC, "PartyName")
    _sub(pn, CBC, "Name", s.name)                              # BT-28
    addr = _sub(supplier, CAC, "PostalAddress")
    _sub(addr, CBC, "StreetName", s.strasse)                  # BT-35
    _sub(addr, CBC, "CityName", s.ort)                        # BT-37
    _sub(addr, CBC, "PostalZone", s.plz)                      # BT-38
    _sub(_sub(addr, CAC, "Country"), CBC, "IdentificationCode", s.land or "DE")  # BT-40
    if s.ust_id:                                              # BT-31 USt-IdNr
        pts = _sub(supplier, CAC, "PartyTaxScheme")
        _sub(pts, CBC, "CompanyID", s.ust_id)
        _sub(_sub(pts, CAC, "TaxScheme"), CBC, "ID", "VAT")
    if s.steuernummer:                                        # BT-32 Steuernummer
        pts = _sub(supplier, CAC, "PartyTaxScheme")
        _sub(pts, CBC, "CompanyID", s.steuernummer)
        _sub(_sub(pts, CAC, "TaxScheme"), CBC, "ID", "FC")
    ple = _sub(supplier, CAC, "PartyLegalEntity")
    _sub(ple, CBC, "RegistrationName", s.name)                # BT-27
    contact = _sub(supplier, CAC, "Contact")                  # BG-6 (XRechnung-Pflicht)
    _sub(contact, CBC, "Name", s.kontakt_name)                # BT-41
    _sub(contact, CBC, "Telephone", s.kontakt_tel)            # BT-42
    _sub(contact, CBC, "ElectronicMail", s.kontakt_mail)      # BT-43

    # ---- Käufer (BG-7) ----
    cust = _sub(_sub(root, CAC, "AccountingCustomerParty"), CAC, "Party")
    if kt and kt.leitweg_id:
        _sub(cust, CBC, "EndpointID", kt.leitweg_id, schemeID="0204")   # BT-49 (Leitweg-Scheme)
    cpn = _sub(cust, CAC, "PartyName")
    _sub(cpn, CBC, "Name", kt.name if kt else rechnung.empfaenger)      # BT-45
    caddr = _sub(cust, CAC, "PostalAddress")
    _sub(caddr, CBC, "StreetName", (kt.adresse if kt and kt.adresse else "") or "")   # BT-50
    _sub(caddr, CBC, "CityName", "Berlin")                    # BT-52 (Bezirksamt in Berlin)
    _sub(caddr, CBC, "PostalZone", "10000")                   # BT-53 (Platzhalter, real pflegen)
    _sub(_sub(caddr, CAC, "Country"), CBC, "IdentificationCode", "DE")  # BT-55
    cple = _sub(cust, CAC, "PartyLegalEntity")
    _sub(cple, CBC, "RegistrationName", kt.name if kt else rechnung.empfaenger)  # BT-44

    # ---- Zahlung (BG-16) ----
    pm = _sub(root, CAC, "PaymentMeans")
    _sub(pm, CBC, "PaymentMeansCode", "58")                   # BT-81 SEPA-Überweisung
    _sub(pm, CBC, "PaymentID", rechnung.nummer)               # BT-83 Verwendungszweck
    pfa = _sub(pm, CAC, "PayeeFinancialAccount")
    _sub(pfa, CBC, "ID", s.iban)                              # BT-84 IBAN
    if s.bank:
        _sub(pfa, CBC, "Name", s.bank)
    if s.bic:
        _sub(_sub(pfa, CAC, "FinancialInstitutionBranch"), CBC, "ID", s.bic)  # BT-86
    pt = _sub(root, CAC, "PaymentTerms")
    _sub(pt, CBC, "Note", f"Zahlbar innerhalb {ziel} Tagen ohne Abzug.")

    # ---- Steuer (BG-23): eine Gruppe Kategorie E ----
    netto = abs(Decimal(rechnung.betrag or 0))            # Gutschrift: Betrag positiv, Art = 381
    tax_total = _sub(root, CAC, "TaxTotal")
    _sub(tax_total, CBC, "TaxAmount", _q2(0), currencyID="EUR")           # BT-110 = 0
    sub = _sub(tax_total, CAC, "TaxSubtotal")
    _sub(sub, CBC, "TaxableAmount", _q2(netto), currencyID="EUR")         # BT-116
    _sub(sub, CBC, "TaxAmount", _q2(0), currencyID="EUR")                 # BT-117 = 0
    cat = _sub(sub, CAC, "TaxCategory")
    _sub(cat, CBC, "ID", "E")                                            # BT-118 Kategorie E
    _sub(cat, CBC, "Percent", _q2(0))                                    # BT-119 = 0
    _sub(cat, CBC, "TaxExemptionReasonCode", VATEX_CODE)                 # BT-121
    _sub(cat, CBC, "TaxExemptionReason", s.befreiungsgrund)              # BT-120
    _sub(_sub(cat, CAC, "TaxScheme"), CBC, "ID", "VAT")

    # ---- Summen (BG-22) ----
    lmt = _sub(root, CAC, "LegalMonetaryTotal")
    _sub(lmt, CBC, "LineExtensionAmount", _q2(netto), currencyID="EUR")  # BT-106
    _sub(lmt, CBC, "TaxExclusiveAmount", _q2(netto), currencyID="EUR")   # BT-109
    _sub(lmt, CBC, "TaxInclusiveAmount", _q2(netto), currencyID="EUR")   # BT-112 (= netto, da 0 % USt)
    _sub(lmt, CBC, "PayableAmount", _q2(netto), currencyID="EUR")        # BT-115

    # ---- Positionen (BG-25): je Monatsnachweis eine Zeile ----
    line_tag = "CreditNoteLine" if gutschrift else "InvoiceLine"
    qty_tag = "CreditedQuantity" if gutschrift else "InvoicedQuantity"
    for i, p in enumerate(positionen, start=1):
        betrag = abs(Decimal(p.betrag or 0))
        line = _sub(root, CAC, line_tag)
        _sub(line, CBC, "ID", str(i))                                    # BT-126
        _sub(line, CBC, qty_tag, "1", unitCode="C62")                   # BT-129/130 (C62 = Stück)
        _sub(line, CBC, "LineExtensionAmount", _q2(betrag), currencyID="EUR")  # BT-131
        item = _sub(line, CAC, "Item")
        if getattr(p, "abrechnungsart", "fls") == "tagessatz":
            bez = (f"Betreuung (Tagessatz) {rechnung.monat:02d}/{rechnung.jahr} · "
                   f"{p.belegungstage} Belegungstag(e)")
        else:
            bez = f"Eingliederungshilfe {rechnung.monat:02d}/{rechnung.jahr}"
        if p.klient.person_id:
            bez += f" · Az {p.klient.person_id}"                        # Fall-Referenz (Kostenträger-Sicht)
        _sub(item, CBC, "Name", bez)                                    # BT-153
        ctc = _sub(item, CAC, "ClassifiedTaxCategory")
        _sub(ctc, CBC, "ID", "E")                                       # BT-151
        _sub(ctc, CBC, "Percent", _q2(0))                              # BT-152
        _sub(_sub(ctc, CAC, "TaxScheme"), CBC, "ID", "VAT")
        price = _sub(line, CAC, "Price")
        _sub(price, CBC, "PriceAmount", _q2(betrag), currencyID="EUR")  # BT-146

    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="utf-8")

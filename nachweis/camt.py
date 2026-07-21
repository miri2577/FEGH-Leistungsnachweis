"""Import von camt.053 (ISO 20022 Kontoauszug) für den Zahlungsabgleich.

Bewusst KONSERVATIV: es werden nur Gutschriften (CRDT) mit einer eindeutig im
Verwendungszweck genannten Rechnungsnummer und passendem Betrag verbucht. Alles
andere wird nur gemeldet – kein blindes Zuordnen nach Betrag.
"""
import re
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree as ET

# Rechnungsnummer JAHR-NNNN (auch mit GS-/Gutschrift-Präfix vor der Jahreszahl irrelevant).
RE_NUMMER = re.compile(r"\b(20\d{2}-\d{3,5})\b")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]          # XML-Namespace strippen


def parse_camt(xml_bytes):
    """Liest die Gutschrifts-Buchungen (CdtDbtInd = CRDT) aus einem camt.053.
    Rückgabe: Liste von {betrag: Decimal, datum: str|None (ISO), verwendungszweck: str}.
    None, wenn die Datei kein gültiges XML ist. Namespace-agnostisch (camt.053.001.02/08)."""
    # DoS-Schutz (Billion Laughs / Entity-Expansion): ein camt.053 hat keine DTD – Dateien mit
    # DOCTYPE-/ENTITY-Deklaration werden abgelehnt, bevor der Parser Entities expandieren kann.
    roh = xml_bytes if isinstance(xml_bytes, (bytes, bytearray)) else str(xml_bytes).encode("utf-8", "ignore")
    kopf = bytes(roh[:8192]).lower()
    if b"<!doctype" in kopf or b"<!entity" in kopf:
        return None
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return None
    eintraege = []
    for ntry in root.iter():
        if _local(ntry.tag) != "Ntry":
            continue
        betrag, cdtdbt, datum, zweck = None, "", None, []
        for el in ntry.iter():
            t = _local(el.tag)
            if t == "Amt" and betrag is None:
                try:
                    betrag = Decimal((el.text or "").strip())
                except (InvalidOperation, TypeError):
                    betrag = None
            elif t == "CdtDbtInd" and not cdtdbt:
                cdtdbt = (el.text or "").strip()
            elif t in ("BookgDt", "ValDt") and datum is None:
                for d in el.iter():
                    if _local(d.tag) in ("Dt", "DtTm") and d.text:
                        datum = d.text.strip()[:10]
            elif t == "Ustrd" and el.text:
                zweck.append(el.text.strip())
        if betrag is not None and cdtdbt == "CRDT":
            eintraege.append({"betrag": betrag, "datum": datum,
                              "verwendungszweck": " ".join(zweck)})
    return eintraege


def finde_rechnungsnummer(text: str):
    m = RE_NUMMER.search(text or "")
    return m.group(1) if m else None


def alle_rechnungsnummern(text: str) -> set:
    """Alle DISTINKTEN Rechnungsnummern im Text – für die Eindeutigkeitsprüfung beim
    camt-Abgleich: automatisch gebucht wird nur bei GENAU EINER Nummer, sonst manuell."""
    return set(RE_NUMMER.findall(text or ""))

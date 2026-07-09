"""Kanonische Liste der 12 Berliner Bezirksämter als Kostenträger der Eingliederungshilfe.

In Berlin sind die Bezirksämter (Ämter für Soziales / Teilhabefachdienste) die örtlichen
Träger der Eingliederungshilfe – für das ambulant betreute Wohnen (TBEW/BEW) rechnet man
gegen den zuständigen Bezirk ab. `ensure_berliner_bezirke()` legt alle 12 idempotent an
(bereits vorhandene bleiben unangetastet); die Leitweg-IDs (XRechnung) bleiben leer und
werden je Bezirk mit den echten Werten aus der Rechnungsstellung gepflegt.
"""

# Amtliche Bezirksnamen (Bezirksamt „… von Berlin"), Reihenfolge = amtliche Bezirksnummer 1–12
BERLINER_BEZIRKE = [
    "Mitte",
    "Friedrichshain-Kreuzberg",
    "Pankow",
    "Charlottenburg-Wilmersdorf",
    "Spandau",
    "Steglitz-Zehlendorf",
    "Tempelhof-Schöneberg",
    "Neukölln",
    "Treptow-Köpenick",
    "Marzahn-Hellersdorf",
    "Lichtenberg",
    "Reinickendorf",
]

DEFAULT_AMT = "Amt für Soziales – Eingliederungshilfe / Teilhabefachdienst"


def bezirk_name(kurz: str) -> str:
    """'Mitte' -> 'Bezirksamt Mitte von Berlin'."""
    return f"Bezirksamt {kurz} von Berlin"


def ensure_berliner_bezirke():
    """Legt fehlende Berliner Bezirksämter als Kostenträger an (idempotent).
    Rückgabe: (neu_angelegt, gesamt_vorhanden)."""
    from .models import Kostentraeger, KostentraegerTyp
    neu = 0
    for kurz in BERLINER_BEZIRKE:
        _, created = Kostentraeger.objects.get_or_create(
            name=bezirk_name(kurz),
            defaults=dict(typ=KostentraegerTyp.BEZIRKSAMT, amt=DEFAULT_AMT, aktiv=True))
        neu += 1 if created else 0
    gesamt = Kostentraeger.objects.filter(
        name__in=[bezirk_name(k) for k in BERLINER_BEZIRKE]).count()
    return neu, gesamt

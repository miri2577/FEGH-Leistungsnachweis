"""Geschäftslogik: Teamsitzung (Berliner Feiertage), Gruppen-Verteilung,
Fachleistungsstunden-Auswertung. Alles aus der Excel-Logik abgeleitet, serverseitig.
"""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

import holidays as _holidays

from .models import Klient, Gruppe, Parameter, Leistungsart, FLS_ARTEN, Status

Q3 = Decimal("0.001")


def berliner_feiertage(jahr: int):
    """Gesetzliche Feiertage in Berlin (inkl. Internationaler Frauentag 8.3.)."""
    return _holidays.Germany(subdiv="BE", years=jahr)


def wochentage_im_jahr(jahr: int, wochentag: int = 3):
    """Alle Tage eines Wochentags (0=Mo … 3=Do) im Jahr."""
    d = date(jahr, 1, 1)
    while d.weekday() != wochentag:
        d += timedelta(days=1)
    out = []
    while d.year == jahr:
        out.append(d)
        d += timedelta(days=7)
    return out


def teamsitzungstage(jahr: int, wochentag: int = 3):
    """Sitzungstage = alle Donnerstage OHNE Berliner Feiertage."""
    fs = berliner_feiertage(jahr)
    return [d for d in wochentage_im_jahr(jahr, wochentag) if d not in fs]


def get_parameter(jahr: int) -> Parameter:
    obj, _ = Parameter.objects.get_or_create(jahr=jahr)
    return obj


def anzahl_klienten() -> int:
    return Klient.objects.count()


def teamsitzung_pro_klient(jahr: int):
    """KLE-Stunden Teamsitzung je Klient/Jahr = Anz. Sitzungstage × Dauer ÷ Anzahl Klienten.
    Rückgabe: (stunden_pro_klient, anzahl_sitzungstage)."""
    p = get_parameter(jahr)
    tage = teamsitzungstage(jahr, p.teamsitzung_wochentag)
    n = anzahl_klienten()
    if not n:
        return Decimal("0"), len(tage)
    pro = (p.teamsitzung_dauer_std * Decimal(len(tage)) / Decimal(n)).quantize(Q3)
    return pro, len(tage)


def teamsitzung_pro_klient_monat(jahr: int, monat: int) -> Decimal:
    p = get_parameter(jahr)
    tage = [d for d in teamsitzungstage(jahr, p.teamsitzung_wochentag) if d.month == monat]
    n = anzahl_klienten()
    if not n:
        return Decimal("0")
    return (p.teamsitzung_dauer_std * Decimal(len(tage)) / Decimal(n)).quantize(Q3)


def gruppen_anteile(jahr: int):
    """Je Klient die Summe der Gruppen-Anteile (gesamt und davon KLE), Jahr.
    Rückgabe: dict[klient_id] = {"gesamt": Decimal, "kle": Decimal, "fls": Decimal}."""
    d = defaultdict(lambda: {"gesamt": Decimal("0"), "kle": Decimal("0"), "fls": Decimal("0")})
    for g in Gruppe.objects.filter(datum__year=jahr).prefetch_related("teilnehmer"):
        anteil = g.zeit_pro_klient
        ist_fls = g.leistungsart in FLS_ARTEN
        ist_kle = g.leistungsart == Leistungsart.KLE
        for k in g.teilnehmer.all():
            d[k.id]["gesamt"] += anteil
            if ist_kle:
                d[k.id]["kle"] += anteil
            if ist_fls:
                d[k.id]["fls"] += anteil
    return d


def fachleistungsstunden(jahr: int):
    """Auswertung je Klient (wie Tab 'Fachleistungsstunden' der Excel).
    Rückgabe: (zeilen, summe)."""
    ts_pro, n_do = teamsitzung_pro_klient(jahr)
    gruppen = gruppen_anteile(jahr)
    zeilen = []
    for k in Klient.objects.select_related("bezugsbetreuer").all():
        manual = list(k.leistungen.filter(datum__year=jahr))
        ist_manual = sum((l.dauer_stunden for l in manual), Decimal("0"))
        fz = sum((l.dauer_stunden for l in manual if l.leistungsart == Leistungsart.FZ), Decimal("0"))
        kle_manual = sum((l.dauer_stunden for l in manual if l.leistungsart == Leistungsart.KLE), Decimal("0"))
        g = gruppen.get(k.id, {"gesamt": Decimal("0"), "kle": Decimal("0"), "fls": Decimal("0")})

        ist = (ist_manual + g["gesamt"] + ts_pro).quantize(Q3)
        kle_ist = (kle_manual + g["kle"] + ts_pro).quantize(Q3)   # Teamsitzung = KLE
        kontingent_m = k.fls_gesamt
        kontingent_j = kontingent_m * 12
        rest = (kontingent_j - ist).quantize(Q3)
        auslastung = (ist / kontingent_j) if kontingent_j else Decimal("0")
        zeilen.append({
            "klient": k,
            "betreuer": k.bezugsbetreuer,
            "kontingent_monat": kontingent_m,
            "kontingent_jahr": kontingent_j,
            "ist": ist,
            "rest": rest,
            "auslastung": auslastung,
            "fz": fz.quantize(Q3),
            "kle_ist": kle_ist,
            "kle_monat": k.kle,
            "al_monat": k.al,
            "kle_anteil": k.kle_anteil,
        })
    summe = {
        "kontingent_jahr": sum((z["kontingent_jahr"] for z in zeilen), Decimal("0")),
        "ist": sum((z["ist"] for z in zeilen), Decimal("0")),
        "rest": sum((z["rest"] for z in zeilen), Decimal("0")),
        "n_donnerstage": n_do,
        "ts_pro_klient_jahr": ts_pro,
    }
    return zeilen, summe

"""Geschäftslogik: Teamsitzung (Berliner Feiertage), Gruppen-Verteilung,
Fachleistungsstunden-Auswertung. Alles aus der Excel-Logik abgeleitet, serverseitig.
"""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

import holidays as _holidays

from .models import Klient, Gruppe, Parameter, Leistungsart, Mitarbeiter, Rolle, FLS_ARTEN, Status

Q3 = Decimal("0.001")


# --------------------------------------------------------------------------
#  Rollen / Sichtbarkeit
# --------------------------------------------------------------------------
def mitarbeiter_fuer(user):
    """Das Mitarbeiter-Profil zum eingeloggten User (oder None)."""
    try:
        return user.mitarbeiter_profil
    except (Mitarbeiter.DoesNotExist, AttributeError):
        return None


def ist_teamleitung(user) -> bool:
    """Nur relevant für Stammdaten-Pflege (Admin), nicht für den Klientenzugriff."""
    if user.is_superuser:
        return True
    m = mitarbeiter_fuer(user)
    return bool(m and m.rolle == Rolle.TEAMLEITUNG)


def klienten_fuer(user):
    """ALLE Klient*innen sind für jedes Teammitglied zugänglich – wie in der Excel,
    damit im Vertretungsfall jede*r die Nachweise führen kann. Nur Filtern schränkt die Anzeige ein."""
    if user.is_authenticated:
        return Klient.objects.all()
    return Klient.objects.none()


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
    pro = (p.teamsitzung_dauer_std * Decimal(len(tage)) / Decimal(n)).quantize(Q3, ROUND_HALF_UP)
    return pro, len(tage)


def teamsitzung_pro_klient_monat(jahr: int, monat: int) -> Decimal:
    p = get_parameter(jahr)
    tage = [d for d in teamsitzungstage(jahr, p.teamsitzung_wochentag) if d.month == monat]
    n = anzahl_klienten()
    if not n:
        return Decimal("0")
    return (p.teamsitzung_dauer_std * Decimal(len(tage)) / Decimal(n)).quantize(Q3, ROUND_HALF_UP)


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


def fachleistungsstunden(jahr: int, klienten=None):
    """Auswertung je Klient (wie Tab 'Fachleistungsstunden' der Excel).
    Teamsitzung wird immer durch ALLE Klienten geteilt; `klienten` schränkt nur die
    angezeigten Zeilen ein (z. B. auf die eigenen). Rückgabe: (zeilen, summe)."""
    ts_pro, n_do = teamsitzung_pro_klient(jahr)
    gruppen = gruppen_anteile(jahr)
    qs = klienten if klienten is not None else Klient.objects.all()
    zeilen = []
    for k in qs.select_related("bezugsbetreuer"):
        manual = list(k.leistungen.filter(datum__year=jahr).exclude(auto=True))
        ist_manual = sum((l.dauer_stunden for l in manual), Decimal("0"))
        fz = sum((l.dauer_stunden for l in manual if l.leistungsart == Leistungsart.FZ), Decimal("0"))
        kle_manual = sum((l.dauer_stunden for l in manual if l.leistungsart == Leistungsart.KLE), Decimal("0"))
        g = gruppen.get(k.id, {"gesamt": Decimal("0"), "kle": Decimal("0"), "fls": Decimal("0")})

        ist = (ist_manual + g["gesamt"] + ts_pro).quantize(Q3, ROUND_HALF_UP)
        kle_ist = (kle_manual + g["kle"] + ts_pro).quantize(Q3, ROUND_HALF_UP)   # Teamsitzung = KLE
        kontingent_m = k.fls_gesamt
        kontingent_j = kontingent_m * 12
        rest = (kontingent_j - ist).quantize(Q3, ROUND_HALF_UP)
        auslastung = (ist / kontingent_j) if kontingent_j else Decimal("0")
        zeilen.append({
            "klient": k,
            "betreuer": k.bezugsbetreuer,
            "kontingent_monat": kontingent_m,
            "kontingent_jahr": kontingent_j,
            "ist": ist,
            "rest": rest,
            "auslastung": auslastung,
            "fz": fz.quantize(Q3, ROUND_HALF_UP),
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
        "ts_dauer": get_parameter(jahr).teamsitzung_dauer_std,
    }
    return zeilen, summe


def druck_nachweis(klient, jahr: int, monat: int):
    """Amtlicher Leistungsnachweis je Klient*in & Monat:
    Einzelnachweis (manuell + Gruppen-Anteile + Teamsitzung je Do) + Kategorie-Summen + Σ FLS."""
    p = get_parameter(jahr)
    n = anzahl_klienten()
    eintraege = []

    for l in klient.leistungen.filter(datum__year=jahr, datum__month=monat).exclude(auto=True):
        eintraege.append({
            "datum": l.datum, "leistungsart": l.leistungsart, "bezeichnung": l.taetigkeit,
            "beginn": l.beginn, "ende": l.ende, "stunden": l.dauer_stunden, "auto": False})

    for g in klient.gruppen.filter(datum__year=jahr, datum__month=monat):
        eintraege.append({
            "datum": g.datum, "leistungsart": g.leistungsart, "bezeichnung": f"Gruppe: {g.thema}",
            "beginn": g.beginn, "ende": g.ende, "stunden": g.zeit_pro_klient, "auto": True})

    ts_share = (p.teamsitzung_dauer_std / Decimal(n)).quantize(Q3, ROUND_HALF_UP) if n else Decimal("0")
    for d in teamsitzungstage(jahr, p.teamsitzung_wochentag):
        if d.month == monat:
            eintraege.append({
                "datum": d, "leistungsart": Leistungsart.KLE, "bezeichnung": "Teamsitzung",
                "beginn": None, "ende": None, "stunden": ts_share, "auto": True})

    eintraege.sort(key=lambda e: (e["datum"], e["beginn"] or __import__("datetime").time(0, 0)))

    labels = dict(Leistungsart.choices)
    summen = []
    total_fls = Decimal("0")
    total_alle = Decimal("0")
    for art in Leistungsart:
        s = sum((e["stunden"] for e in eintraege if e["leistungsart"] == art), Decimal("0"))
        summen.append({"art": art, "label": labels[art], "stunden": s.quantize(Q3, ROUND_HALF_UP),
                       "ist_fls": art in FLS_ARTEN})
        total_alle += s
        if art in FLS_ARTEN:
            total_fls += s

    return {
        "klient": klient, "jahr": jahr, "monat": monat,
        "monat_text": f"{monat:02d}.{jahr}",
        "eintraege": eintraege, "summen": summen,
        "fls_summe": total_fls.quantize(Q3, ROUND_HALF_UP), "gesamt": total_alle.quantize(Q3, ROUND_HALF_UP),
    }

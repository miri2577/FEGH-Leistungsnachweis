"""Geschäftslogik: Teamsitzung (Berliner Feiertage), Gruppen-Verteilung,
Fachleistungsstunden-Auswertung. Alles aus der Excel-Logik abgeleitet, serverseitig.
"""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

import holidays as _holidays

from .models import (Klient, Gruppe, Leistung, Parameter, Leistungsart,
                     Mitarbeiter, Team, Rolle, FLS_ARTEN, Status)

Q3 = Decimal("0.001")


# --------------------------------------------------------------------------
#  Rollen / Sichtbarkeit
#  User    = Betreuer*in: eigenes Team (Vertretung), Dashboard nur eigene Klient*innen
#  Leitung = Klient*innen der geleiteten Team(s), Filter Mitarbeiter/Team
#  Admin   = verwaltet Teams & Mitarbeiter, KEIN Klientenzugriff (DSGVO-Trennung)
# --------------------------------------------------------------------------
def mitarbeiter_fuer(user):
    """Das Mitarbeiter-Profil zum eingeloggten User (oder None)."""
    try:
        return user.mitarbeiter_profil
    except (Mitarbeiter.DoesNotExist, AttributeError):
        return None


def ist_admin(user) -> bool:
    """App-Rolle Admin – hat KEINEN Klientenzugriff (DSGVO-Trennung), auch nicht als Superuser."""
    m = mitarbeiter_fuer(user)
    return bool(m and m.rolle == Rolle.ADMIN)


def _superuser_ohne_profil(user) -> bool:
    """Technischer Break-Glass-Superuser OHNE Mitarbeiter-Profil (Notzugang)."""
    return bool(user.is_superuser and mitarbeiter_fuer(user) is None)


def ist_leitung(user) -> bool:
    """Leitung – für Team-Auswertung & Genehmigungen. Die App-Rolle ist maßgeblich."""
    m = mitarbeiter_fuer(user)
    if m:
        return m.rolle == Rolle.LEITUNG
    return _superuser_ohne_profil(user)


def teams_fuer(user):
    """Teams, deren Klient*innen der/die Nutzer*in sehen darf.
    Admin: keine (kein Klientenzugriff). Leitung: geleitete Team(s) + eigenes.
    User: nur eigenes Team. Break-Glass-Superuser: alle."""
    m = mitarbeiter_fuer(user)
    if m is None:
        return Team.objects.all() if _superuser_ohne_profil(user) else Team.objects.none()
    if m.rolle == Rolle.ADMIN:
        return Team.objects.none()
    ids = set(m.leitet.values_list("id", flat=True)) if m.rolle == Rolle.LEITUNG else set()
    if m.team_id:
        ids.add(m.team_id)
    return Team.objects.filter(id__in=ids)


def klienten_fuer(user):
    """Klient*innen im Zugriff: alle des/der eigenen bzw. geleiteten Team(s).
    Innerhalb des Teams sieht jede*r alle (Vertretung). Admin: keine."""
    if not user.is_authenticated or ist_admin(user):
        return Klient.objects.none()
    if _superuser_ohne_profil(user):
        return Klient.objects.all()
    return Klient.objects.filter(team__in=teams_fuer(user))


def eigene_klienten(user):
    """Nur die Klient*innen, für die der/die Nutzer*in Bezugsbetreuer*in ist."""
    m = mitarbeiter_fuer(user)
    return Klient.objects.filter(bezugsbetreuer=m) if m else Klient.objects.none()


def berichte_faellig(klienten, stichtag=None):
    """Liste der Klient*innen, deren Entwicklungsbericht ansteht (10 Wochen vor KÜ-Ende)."""
    return [k for k in klienten.exclude(kue_bis__isnull=True) if k.bericht_offen(stichtag)]


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
    """Teiler für die Teamsitzung: nur Klient*innen in Betreuung (Beendigung zählt nicht mit)."""
    return Klient.objects.filter(status=Status.BETREUUNG).count()


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

        # Teamsitzung nur für Klient*innen in Betreuung (Beendete zählen nicht mit)
        ts_row = ts_pro if k.status == Status.BETREUUNG else Decimal("0")
        ist = (ist_manual + g["gesamt"] + ts_row).quantize(Q3, ROUND_HALF_UP)
        kle_ist = (kle_manual + g["kle"] + ts_row).quantize(Q3, ROUND_HALF_UP)   # Teamsitzung = KLE
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


def auslastung_zeitreihe(jahr: int, klienten):
    """Ist-FLS & Auslastung je Kalenderwoche / Monat / Jahr für die (gefilterten) Klient*innen.
    Berücksichtigt manuelle Leistungen, Gruppen-Anteile und Teamsitzung – auf deren echten Daten."""
    kl_ids = set(klienten.values_list("id", flat=True))
    kl_list = list(klienten)
    kont_monat = sum((k.fls_gesamt for k in kl_list), Decimal("0"))
    kont_jahr = kont_monat * 12
    kont_woche = (kont_jahr / Decimal(52)) if kont_jahr else Decimal("0")

    ist_monat = [Decimal("0")] * 13          # Index 1..12
    ist_woche = defaultdict(lambda: Decimal("0"))

    def add(d, betrag):
        ist_monat[d.month] += betrag
        ist_woche[d.isocalendar()[1]] += betrag

    for l in Leistung.objects.filter(klient_id__in=kl_ids, datum__year=jahr).exclude(auto=True):
        add(l.datum, l.dauer_stunden)

    for g in Gruppe.objects.filter(datum__year=jahr).prefetch_related("teilnehmer"):
        anteil = g.zeit_pro_klient
        if not anteil:
            continue
        n = sum(1 for k in g.teilnehmer.all() if k.id in kl_ids)
        if n:
            add(g.datum, anteil * n)

    n_active = sum(1 for k in kl_list if k.status == Status.BETREUUNG)
    if n_active:
        p = get_parameter(jahr)
        n_glob = anzahl_klienten()
        share = (p.teamsitzung_dauer_std / Decimal(n_glob)).quantize(Q3, ROUND_HALF_UP) if n_glob else Decimal("0")
        for d in teamsitzungstage(jahr, p.teamsitzung_wochentag):
            add(d, share * n_active)

    def pct(ist, kont):
        return round(float(ist / kont * 100), 1) if kont else 0.0

    monate = [{"label": f"{m:02d}", "ist": round(float(ist_monat[m]), 2),
               "auslastung": pct(ist_monat[m], kont_monat)} for m in range(1, 13)]
    wochen = [{"label": f"KW{w}", "ist": round(float(ist_woche.get(w, 0)), 2),
               "auslastung": pct(ist_woche.get(w, Decimal("0")), kont_woche)} for w in range(1, 53)]
    jahr_ist = sum((ist_monat[m] for m in range(1, 13)), Decimal("0"))

    return {
        "monate": monate,
        "wochen": wochen,
        "kont_monat": round(float(kont_monat), 2),
        "kont_woche": round(float(kont_woche), 2),
        "jahr": {"ist": round(float(jahr_ist), 2), "kontingent": round(float(kont_jahr), 2),
                 "auslastung": pct(jahr_ist, kont_jahr)},
    }


def _feiertage_set(*jahre):
    s = set()
    for j in jahre:
        s |= set(berliner_feiertage(j).keys())
    return s


def werktage(von, bis) -> int:
    """Arbeitstage (Mo–Fr ohne Berliner Feiertage) im Zeitraum [von, bis]."""
    if not (von and bis) or bis < von:
        return 0
    fs = _feiertage_set(*range(von.year, bis.year + 1))
    n, d = 0, von
    while d <= bis:
        if d.weekday() < 5 and d not in fs:
            n += 1
        d += timedelta(days=1)
    return n


def abwesenheitstage(mitarbeiter, von, bis):
    """Menge der Werktage (Mo–Fr) im Zeitraum, die durch nicht abgelehnte Abwesenheiten belegt sind."""
    from .models import AbwesenheitStatus
    tage = set()
    for a in mitarbeiter.abwesenheiten.exclude(status=AbwesenheitStatus.ABGELEHNT):
        d = max(a.von, von)
        e = min(a.bis, bis)
        while d <= e:
            if d.weekday() < 5:
                tage.add(d)
            d += timedelta(days=1)
    return tage


def arbeitszeit_monat(mitarbeiter, jahr: int, monat: int):
    """Ist/Soll-Arbeitszeit & fehlende Nachweistage im Monat für eine*n Mitarbeiter*in."""
    from calendar import monthrange
    from datetime import date as _date
    eintr = list(mitarbeiter.arbeitszeiten.filter(datum__year=jahr, datum__month=monat))
    ist = sum((e.dauer_stunden for e in eintr), Decimal("0"))
    erfasst = {e.datum for e in eintr if e.dauer_stunden > 0}
    anfang = _date(jahr, monat, 1)
    ende = _date(jahr, monat, monthrange(jahr, monat)[1])
    heute = _date.today()
    grenze = min(ende, heute) if (heute.year == jahr and heute.month == monat) else ende
    fs = _feiertage_set(jahr)
    abw = abwesenheitstage(mitarbeiter, anfang, ende)
    fehlend, d = 0, anfang
    while d <= grenze:
        if d.weekday() < 5 and d not in fs and d not in erfasst and d not in abw:
            fehlend += 1
        d += timedelta(days=1)
    wt = werktage(anfang, ende)
    soll = (mitarbeiter.tagessoll * Decimal(wt)).quantize(Q3, ROUND_HALF_UP)
    return {"ist": ist.quantize(Q3, ROUND_HALF_UP), "soll": soll, "werktage": wt,
            "tage_erfasst": len(erfasst), "fehlende_tage": fehlend}


def urlaub_uebersicht(mitarbeiter, jahr: int):
    from .models import AbwesenheitArt, AbwesenheitStatus
    genommen = beantragt = 0
    for a in mitarbeiter.abwesenheiten.filter(art=AbwesenheitArt.URLAUB, von__year=jahr):
        if a.status == AbwesenheitStatus.GENEHMIGT:
            genommen += a.werktage
        elif a.status == AbwesenheitStatus.BEANTRAGT:
            beantragt += a.werktage
    return {"anspruch": mitarbeiter.urlaubstage, "genommen": genommen,
            "beantragt": beantragt, "rest": mitarbeiter.urlaubstage - genommen - beantragt}


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
    if klient.status != Status.BETREUUNG:
        ts_share = Decimal("0")          # Beendete erhalten keinen Teamsitzungs-Anteil
    for d in teamsitzungstage(jahr, p.teamsitzung_wochentag):
        if ts_share and d.month == monat:
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

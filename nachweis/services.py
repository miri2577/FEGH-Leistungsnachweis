"""Geschäftslogik: Teamsitzung (Berliner Feiertage), Gruppen-Verteilung,
Fachleistungsstunden-Auswertung. Alles aus der Excel-Logik abgeleitet, serverseitig.
"""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

import holidays as _holidays
from django.db.models import Q

from .models import (Klient, Gruppe, Leistung, Parameter, Leistungsart,
                     Mitarbeiter, Team, Rolle, FLS_ARTEN, Status,
                     WiederkehrendeLeistung, Rhythmus, Anrechnung)

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


def ist_verwaltung(user) -> bool:
    """Mitarbeiter*in im Team Verwaltung – arbeitet nicht mit Klient*innen
    (keine Leistungs-/Gruppennachweise, keine Klient-Auslastung)."""
    m = mitarbeiter_fuer(user)
    return bool(m and m.ist_verwaltung)


def ohne_klientenarbeit(user) -> bool:
    """True für Rollen/Teams ohne Klientenbezug (Admin oder Verwaltung)."""
    return ist_admin(user) or ist_verwaltung(user)


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
    Innerhalb des Teams sieht jede*r alle (Vertretung). Admin/Verwaltung: keine."""
    if not user.is_authenticated or ist_admin(user) or ist_verwaltung(user):
        return Klient.objects.none()
    if _superuser_ohne_profil(user):
        return Klient.objects.all()
    return Klient.objects.filter(team__in=teams_fuer(user))


def eigene_klienten(user):
    """Nur die Klient*innen, für die der/die Nutzer*in Bezugsbetreuer*in ist."""
    m = mitarbeiter_fuer(user)
    return Klient.objects.filter(bezugsbetreuer=m) if m else Klient.objects.none()


# --------------------------------------------------------------------------
#  Kasse (Kassenbuch) – Verwaltung = Finanz-Hub (sieht/pflegt alle Kassen)
# --------------------------------------------------------------------------
def kassen_fuer(user):
    """Zugängliche Kassen: Verwaltung/Superuser -> alle; Team-Mitglied -> eigenes/geleitete
    Team(s); Admin -> keine (verwaltet Konten, keine Finanzen)."""
    from .models import Kasse
    if not user.is_authenticated or ist_admin(user):
        return Kasse.objects.none()
    if ist_verwaltung(user) or _superuser_ohne_profil(user):
        return Kasse.objects.all()
    return Kasse.objects.filter(team__in=teams_fuer(user))


def kann_buha(user) -> bool:
    """Wer die Buchhaltungs-Felder (Buchungsdatum/Kontonr/Kostenstelle) pflegen darf."""
    return ist_verwaltung(user) or _superuser_ohne_profil(user)


def kassenmonat(kasse, jahr, monat):
    """Holt/erzeugt den Kassenmonat; Vortrag = Endbestand des Vormonats."""
    from .models import Kassenmonat
    km = Kassenmonat.objects.filter(kasse=kasse, jahr=jahr, monat=monat).first()
    if km:
        return km
    pj, pm = (jahr - 1, 12) if monat == 1 else (jahr, monat - 1)
    vor = Kassenmonat.objects.filter(kasse=kasse, jahr=pj, monat=pm).first()
    vortrag = vor.endbestand if vor else Decimal("0")
    return Kassenmonat.objects.create(kasse=kasse, jahr=jahr, monat=monat, vortrag=vortrag)


def kassenblatt_zeilen(monat):
    """Buchungen mit laufendem Bestand (Vortrag + kumuliert Einnahmen − Ausgaben)."""
    saldo = monat.vortrag
    zeilen = []
    for b in monat.buchungen.all():
        saldo = saldo + b.einnahme - b.ausgabe
        zeilen.append({"b": b, "bestand": saldo})
    return zeilen


def letzter_kassenabschluss(kasse):
    """(jahr, monat) für die Druck-Vorbelegung: der zuletzt *abgeschlossene* Monat.
    1) neuester Monat mit erfasstem Zählprotokoll (Datum oder gezähltes Bargeld),
    2) sonst neuester Monat mit Buchungen, 3) sonst der Vormonat."""
    from .models import Kassenmonat, Zaehlprotokoll
    if kasse is None:
        heute = date.today()
        return (heute.year - 1, 12) if heute.month == 1 else (heute.year, heute.month - 1)
    for z in (Zaehlprotokoll.objects.filter(monat__kasse=kasse)
              .select_related("monat").order_by("-monat__jahr", "-monat__monat")):
        if z.datum or z.bargeld_gesamt:
            return z.monat.jahr, z.monat.monat
    km = (Kassenmonat.objects.filter(kasse=kasse, buchungen__isnull=False)
          .order_by("-jahr", "-monat").distinct().first())
    if km:
        return km.jahr, km.monat
    heute = date.today()
    return (heute.year - 1, 12) if heute.month == 1 else (heute.year, heute.month - 1)


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


# --------------------------------------------------------------------------
#  Wiederkehrende Leistungen (feste Serien: Supervision, Fortbildung, …)
#  Additiv zur (weiterhin fest berechneten) Teamsitzung.
# --------------------------------------------------------------------------
def _monatstermin(y: int, m: int, wl):
    """Konkretes Datum einer Serie im Monat (y,m): fester Tag ODER N-ter Wochentag."""
    from calendar import monthrange
    ndays = monthrange(y, m)[1]
    if wl.tag_im_monat:
        return date(y, m, min(wl.tag_im_monat, ndays))
    tage = [date(y, m, d) for d in range(1, ndays + 1) if date(y, m, d).weekday() == wl.wochentag]
    if not tage:
        return None
    if (wl.woche_im_monat or 0) == -1:
        return tage[-1]
    idx = (wl.woche_im_monat or 1) - 1
    return tage[idx] if 0 <= idx < len(tage) else None


def serientermine(wl, von, bis):
    """Alle Termindaten einer wiederkehrenden Leistung im Zeitraum [von, bis]
    (Gültigkeitsfenster beachtet, Berliner Feiertage optional ausgespart)."""
    lo = max(von, wl.gilt_ab) if wl.gilt_ab else von
    hi = min(bis, wl.gilt_bis) if wl.gilt_bis else bis
    if hi < lo:
        return []
    dates = []
    if wl.rhythmus in (Rhythmus.WOECHENTLICH, Rhythmus.ZWEIWOECHENTLICH):
        first = None
        if wl.rhythmus == Rhythmus.ZWEIWOECHENTLICH:
            ref = wl.gilt_ab or date(2024, 1, 1)
            first = ref + timedelta(days=(wl.wochentag - ref.weekday()) % 7)
        d = lo
        while d <= hi:
            if d.weekday() == wl.wochentag and (
                    wl.rhythmus == Rhythmus.WOECHENTLICH or (d - first).days % 14 == 0):
                dates.append(d)
            d += timedelta(days=1)
    else:
        y, m = lo.year, lo.month
        while (y, m) <= (hi.year, hi.month):
            take = True
            if wl.rhythmus == Rhythmus.VIERTELJAEHRLICH:
                take = (m - (wl.monat_im_jahr or 1)) % 3 == 0
            elif wl.rhythmus == Rhythmus.JAEHRLICH:
                take = m == (wl.monat_im_jahr or 1)
            if take:
                d = _monatstermin(y, m, wl)
                if d and lo <= d <= hi:
                    dates.append(d)
            m, y = (1, y + 1) if m == 12 else (m + 1, y)
    if wl.feiertage_aussparen and dates:
        fs = _feiertage_set(*{d.year for d in dates})
        dates = [d for d in dates if d not in fs]
    return dates


def _team_betreuung_counts() -> dict:
    """{team_id: Anzahl Klient*innen in Betreuung} – Teiler für team-bezogene Serien."""
    from collections import Counter
    return dict(Counter(Klient.objects.filter(status=Status.BETREUUNG)
                        .exclude(team__isnull=True).values_list("team_id", flat=True)))


def aktive_serien(nur_nachweis: bool = True):
    qs = WiederkehrendeLeistung.objects.filter(aktiv=True)
    if nur_nachweis:
        qs = qs.exclude(anrechnung=Anrechnung.KALENDER)
    return list(qs.select_related("team"))


def _serien_share(wl, team_counts, global_count) -> Decimal:
    """Anteil je Termin und Klient*in."""
    if wl.anrechnung == Anrechnung.FEST:
        return (wl.wert_pro_klient or Decimal("0")).quantize(Q3, ROUND_HALF_UP)
    n = team_counts.get(wl.team_id, 0) if wl.team_id else global_count
    return (wl.dauer_std / Decimal(n)).quantize(Q3, ROUND_HALF_UP) if n else Decimal("0")


def serien_beitraege(klient, von, bis, serien=None, team_counts=None, global_count=None):
    """[{datum, bezeichnung, leistungsart, stunden}] für eine*n Klient*in aus den
    wiederkehrenden Leistungen im Zeitraum. Nur Status Betreuung, nur im_nachweis.
    serien/team_counts/global_count können vorberechnet übergeben werden (kein N+1)."""
    if klient.status != Status.BETREUUNG:
        return []
    if serien is None:
        serien = aktive_serien()
    if global_count is None:
        global_count = anzahl_klienten()
    if team_counts is None:
        team_counts = _team_betreuung_counts()
    out = []
    for wl in serien:
        if wl.team_id and wl.team_id != klient.team_id:
            continue
        share = _serien_share(wl, team_counts, global_count)
        if not share:
            continue
        for d in serientermine(wl, von, bis):
            out.append({"datum": d, "bezeichnung": wl.bezeichnung,
                        "leistungsart": wl.leistungsart, "stunden": share})
    return out


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
    _serien, _tc, _gc = aktive_serien(), _team_betreuung_counts(), anzahl_klienten()
    qs = (klienten if klienten is not None else Klient.objects.all()).select_related("bezugsbetreuer")
    kl_list = list(qs)
    # Manuelle Leistungen des Jahres in EINEM Query laden und nach Klient gruppieren (kein N+1)
    manual_by_kl = defaultdict(list)
    for l in Leistung.objects.filter(
            klient_id__in=[k.id for k in kl_list], datum__year=jahr).exclude(auto=True):
        manual_by_kl[l.klient_id].append(l)
    zeilen = []
    for k in kl_list:
        manual = manual_by_kl.get(k.id, [])
        ist_manual = sum((l.dauer_stunden for l in manual), Decimal("0"))
        fz = sum((l.dauer_stunden for l in manual if l.leistungsart == Leistungsart.FZ), Decimal("0"))
        kle_manual = sum((l.dauer_stunden for l in manual if l.leistungsart == Leistungsart.KLE), Decimal("0"))
        g = gruppen.get(k.id, {"gesamt": Decimal("0"), "kle": Decimal("0"), "fls": Decimal("0")})

        # Teamsitzung nur für Klient*innen in Betreuung (Beendete zählen nicht mit)
        ts_row = ts_pro if k.status == Status.BETREUUNG else Decimal("0")
        sb = serien_beitraege(k, date(jahr, 1, 1), date(jahr, 12, 31), _serien, _tc, _gc)
        serien_sum = sum((x["stunden"] for x in sb), Decimal("0"))
        serien_kle = sum((x["stunden"] for x in sb if x["leistungsart"] == Leistungsart.KLE), Decimal("0"))
        ist = (ist_manual + g["gesamt"] + ts_row + serien_sum).quantize(Q3, ROUND_HALF_UP)
        kle_ist = (kle_manual + g["kle"] + ts_row + serien_kle).quantize(Q3, ROUND_HALF_UP)  # Teamsitzung/KLE-Serien
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

    # Anzahl ISO-Wochen im Jahr (52 oder 53; der 28.12. liegt stets in der letzten ISO-Woche)
    n_weeks = date(jahr, 12, 28).isocalendar()[1]
    ist_monat = [Decimal("0")] * 13          # Index 1..12 (Kalendermonat)
    ist_woche = defaultdict(lambda: Decimal("0"))

    def add(d, betrag):
        if d.year == jahr:                   # Monatsbuckets: Kalenderjahr
            ist_monat[d.month] += betrag
        iso = d.isocalendar()
        if iso[0] == jahr:                   # Wochenbuckets: ISO-Jahr (Jahresrand korrekt)
            ist_woche[iso[1]] += betrag

    # Etwas über die Kalenderjahr-Grenzen hinaus laden, damit ISO-Randwochen vollständig sind
    von, bis = date(jahr - 1, 12, 29), date(jahr + 1, 1, 3)
    for l in Leistung.objects.filter(klient_id__in=kl_ids, datum__range=(von, bis)).exclude(auto=True):
        add(l.datum, l.dauer_stunden)

    for g in Gruppe.objects.filter(datum__range=(von, bis)).prefetch_related("teilnehmer"):
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
        for j in {jahr - 1, jahr, jahr + 1}:
            for d in teamsitzungstage(j, p.teamsitzung_wochentag):
                if von <= d <= bis:
                    add(d, share * n_active)

    def pct(ist, kont):
        return round(float(ist / kont * 100), 1) if kont else 0.0

    monate = [{"label": f"{m:02d}", "ist": round(float(ist_monat[m]), 2),
               "auslastung": pct(ist_monat[m], kont_monat)} for m in range(1, 13)]
    wochen = [{"label": f"KW{w}", "ist": round(float(ist_woche.get(w, 0)), 2),
               "auslastung": pct(ist_woche.get(w, Decimal("0")), kont_woche)} for w in range(1, n_weeks + 1)]
    jahr_ist = sum((ist_monat[m] for m in range(1, 13)), Decimal("0"))

    return {
        "monate": monate,
        "wochen": wochen,
        "kont_monat": round(float(kont_monat), 2),
        "kont_woche": round(float(kont_woche), 2),
        "jahr": {"ist": round(float(jahr_ist), 2), "kontingent": round(float(kont_jahr), 2),
                 "auslastung": pct(jahr_ist, kont_jahr)},
    }


def _woche_faktor() -> Decimal:
    """Umrechnung Monatswert -> Wochenwert (12 Monate / 52 Wochen)."""
    return Decimal(12) / Decimal(52)


def aktuelle_kw(jahr: int) -> int:
    """Laufende ISO-Kalenderwoche, sofern das heutige ISO-Jahr dem gewählten Jahr
    entspricht – sonst KW 1. (ISO-Jahr, nicht Kalenderjahr, damit der Jahreswechsel
    korrekt behandelt wird: 31.12.2025 gehört ISO zu 2026-W01.)"""
    iso = date.today().isocalendar()
    return iso[1] if iso[0] == jahr else 1


def iso_wochenbereich(jahr: int, kw: int):
    """(Montag, Sonntag) der ISO-Kalenderwoche. Existiert die KW im Jahr nicht
    (z.B. KW53 in 52-Wochen-Jahren), wird auf KW1 zurückgefallen."""
    try:
        mo = date.fromisocalendar(jahr, kw, 1)
    except ValueError:
        mo = date.fromisocalendar(jahr, 1, 1)
    return mo, mo + timedelta(days=6)


def wochenauslastung(klienten, jahr: int, kw: int = None):
    """AL/KLE-Soll & -Ist je Klient*in für eine Kalenderwoche (Default: laufende KW).
    AL + KLE = bewilligte FLS. AL  = direkte Leistung (alles Verbrauchte außer KLE),
    KLE = kalkulatorische Leistungseinheit (KLE-Leistungen + KLE-Gruppen + Teamsitzung).
    Soll/Woche = Monatsbewilligung × 12/52 (Feld al → AL, Feld kle → KLE).
    Die Woche wird exakt über ihren ISO-Datumsbereich (Mo–So) gefiltert – auch über
    Jahresgrenzen hinweg. Rückgabe: {"kw", "zeilen": {klient_id: {...}}, "total": {...}}."""
    if kw is None:
        kw = aktuelle_kw(jahr)
    faktor = _woche_faktor()
    kl_list = list(klienten)
    kl_ids = {k.id for k in kl_list}
    mo, so = iso_wochenbereich(jahr, kw)

    al_ist = defaultdict(lambda: Decimal("0"))
    kle_ist = defaultdict(lambda: Decimal("0"))

    # 1) manuell erfasste Leistungen dieser Woche: KLE separat, alles Übrige zählt als AL
    for l in Leistung.objects.filter(klient_id__in=kl_ids, datum__range=(mo, so)).exclude(auto=True):
        if l.leistungsart == Leistungsart.KLE:
            kle_ist[l.klient_id] += l.dauer_stunden
        else:
            al_ist[l.klient_id] += l.dauer_stunden

    # 2) Gruppen-Anteile dieser Woche: KLE-Gruppen -> KLE, alle übrigen -> AL
    for g in Gruppe.objects.filter(datum__range=(mo, so)).prefetch_related("teilnehmer"):
        anteil = g.zeit_pro_klient
        if not anteil:
            continue
        ziel = kle_ist if g.leistungsart == Leistungsart.KLE else al_ist
        for k in g.teilnehmer.all():
            if k.id in kl_ids:
                ziel[k.id] += anteil

    # 3) Teamsitzung dieser Woche (zählt als KLE) – nur Klient*innen in Betreuung
    p = get_parameter(jahr)
    n_glob = anzahl_klienten()
    if n_glob:
        share = (p.teamsitzung_dauer_std / Decimal(n_glob)).quantize(Q3, ROUND_HALF_UP)
        # ISO-Woche kann über den Jahresrand reichen → Sitzungstage beider Jahre prüfen
        n_ts = sum(1 for j in {mo.year, so.year}
                   for d in teamsitzungstage(j, p.teamsitzung_wochentag) if mo <= d <= so)
        if n_ts:
            for k in kl_list:
                if k.status == Status.BETREUUNG:
                    kle_ist[k.id] += share * n_ts

    # 4) Wiederkehrende Leistungen dieser Woche (KLE -> KLE, sonst -> AL)
    _serien, _tc, _gc = aktive_serien(), _team_betreuung_counts(), anzahl_klienten()
    for k in kl_list:
        for b in serien_beitraege(k, mo, so, _serien, _tc, _gc):
            if b["leistungsart"] == Leistungsart.KLE:
                kle_ist[k.id] += b["stunden"]
            else:
                al_ist[k.id] += b["stunden"]

    zeilen = {}
    for k in kl_list:
        soll_al = ((k.al or Decimal("0")) * faktor).quantize(Q3, ROUND_HALF_UP)
        soll_kle = ((k.kle or Decimal("0")) * faktor).quantize(Q3, ROUND_HALF_UP)
        al = al_ist[k.id].quantize(Q3, ROUND_HALF_UP)
        kle = kle_ist[k.id].quantize(Q3, ROUND_HALF_UP)
        soll = soll_al + soll_kle
        ist = al + kle
        zeilen[k.id] = {
            "klient": k, "soll": soll, "soll_al": soll_al, "soll_kle": soll_kle,
            "ist": ist, "al": al, "kle": kle,
            "auslastung": (ist / soll) if soll else Decimal("0"),
        }

    def _sum(feld):
        return sum((z[feld] for z in zeilen.values()), Decimal("0"))
    total = {"kw": kw, "soll": _sum("soll"), "soll_al": _sum("soll_al"),
             "soll_kle": _sum("soll_kle"), "ist": _sum("ist"),
             "al": _sum("al"), "kle": _sum("kle")}
    total["auslastung"] = (total["ist"] / total["soll"]) if total["soll"] else Decimal("0")
    return {"kw": kw, "zeilen": zeilen, "total": total}


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


def stempel_status(mitarbeiter):
    """Aktueller Stempelstatus + HEUTE erfasste Arbeitszeit (für die Kommen/Gehen-Karte).
    Zählt nur den heutigen Anteil jeder Sitzung – auch bei über Mitternacht laufenden."""
    from datetime import datetime, time
    from django.utils import timezone
    from .models import Stempelung
    if not mitarbeiter:
        return {"eingestempelt": False, "seit": None, "heute_sekunden": 0,
                "abgeschlossen_sekunden": 0, "offen_seit_iso": None}
    jetzt = timezone.localtime()
    heute = jetzt.date()
    tz = timezone.get_current_timezone()
    tag_start = timezone.make_aware(datetime.combine(heute, time.min), tz)

    def anteil_heute(s, bis):
        b = max(timezone.localtime(s.beginn), tag_start)
        return max(0, int((bis - b).total_seconds()))

    # Sitzungen, die heute (mit)laufen: heute begonnen ODER heute beendet
    # (über Mitternacht abgeschlossen) ODER noch offen (evtl. seit gestern)
    sessions = mitarbeiter.stempelungen.filter(
        Q(beginn__date=heute) | Q(ende__date=heute) | Q(ende__isnull=True))
    abgeschlossen = 0
    offen = None
    for s in sessions:
        if s.offen:
            offen = s
        else:
            abgeschlossen += anteil_heute(s, timezone.localtime(s.ende))

    offen_start_geklammert = max(timezone.localtime(offen.beginn), tag_start) if offen else None
    heute_sek = abgeschlossen + (anteil_heute(offen, jetzt) if offen else 0)
    return {
        "eingestempelt": bool(offen),
        "seit": timezone.localtime(offen.beginn) if offen else None,   # echte Startzeit (Anzeige)
        "heute_sekunden": heute_sek,
        "abgeschlossen_sekunden": abgeschlossen,
        # Basis der Live-Uhr: Startzeitpunkt der offenen Sitzung, geklammert auf Mitternacht heute
        "offen_seit_iso": offen_start_geklammert.isoformat() if offen else None,
    }


def stempeln(mitarbeiter):
    """Toggle Kommen/Gehen atomar. Öffnet neue Sitzung oder schließt die offene.
    Die partielle Unique-Constraint verhindert zwei offene Sitzungen. Rückgabe: 'kommen'|'gehen'."""
    from django.db import transaction
    from django.utils import timezone
    with transaction.atomic():
        offen = (mitarbeiter.stempelungen.select_for_update()
                 .filter(ende__isnull=True).order_by("-beginn").first())
        if offen:
            offen.ende = timezone.now()
            offen.save(update_fields=["ende"])
            return "gehen"
        mitarbeiter.stempelungen.create(beginn=timezone.now())   # IntegrityError bei Doppel-Kommen
        return "kommen"


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

    from calendar import monthrange as _mr
    _mvon, _mbis = date(jahr, monat, 1), date(jahr, monat, _mr(jahr, monat)[1])
    for b in serien_beitraege(klient, _mvon, _mbis):
        eintraege.append({
            "datum": b["datum"], "leistungsart": b["leistungsart"], "bezeichnung": b["bezeichnung"],
            "beginn": None, "ende": None, "stunden": b["stunden"], "auto": True})

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

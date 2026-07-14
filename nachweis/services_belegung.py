"""M2: Belegungskalender + Tagessatz-Berechnung ((teil-)stationäre Bereiche).

Tageslogik (Konventionen aus BRV Jug Tz 22 / Beschluss 8/2007):
- Aufnahme- und Entlasstag zählen je als voller Belegungstag.
- Abwesenheit: `von` = erster Abwesenheitstag (Abreisetag), `bis` = letzter
  Abwesenheitstag; der Rückkehrtag wird nicht eingetragen (= Anwesenheit).
- Vergütung je Abwesenheitstag laut Abwesenheitsart (Regeln als Daten):
  verguetung_prozent innerhalb der Weiterzahlungsgrenze (max_tage je Ereignis
  oder kumulativ je Kalenderjahr, je Klient*in), darüber 0 %; abzug_je_tag
  (z. B. Beköstigungssatz) wird an vergüteten Abwesenheitstagen abgezogen.

Kontingent-Zählung (Kalenderjahr-Basis) arbeitet auf TAGESMENGEN je Klient*in
und Art: Überlappende Einträge zählen nicht doppelt, und jeder Tag wird auf den
jeweiligen Belegungszeitraum geclippt — Tage nach dem Auszug (z. B. vergessene
offene Abwesenheit) verbrauchen kein Kontingent.
"""
from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from . import services
from .models import Belegung, KlientAbwesenheit, AbwesenheitsBasis

E2 = Decimal("0.01")


def _abwesenheit_am(abwesenheiten, tag):
    """Die den Tag abdeckende Abwesenheit — bei Überlappung gewinnt deterministisch
    die zuerst beginnende (dann die zuerst erfasste). None wenn anwesend."""
    treffer = [a for a in abwesenheiten if a.abwesend_am(tag)]
    if not treffer:
        return None
    return min(treffer, key=lambda a: (a.von, a.pk))


def _jahres_tagesmenge(klient, art, bis_tag):
    """Menge der Kontingent-relevanten Abwesenheitstage dieser Art im Kalenderjahr
    bis einschließlich `bis_tag` (je Klient*in über alle Belegungen). Dedupliziert
    Überlappungen und clippt jeden Eintrag auf seinen Belegungszeitraum."""
    start_jahr = date(bis_tag.year, 1, 1)
    menge = set()
    qs = (KlientAbwesenheit.objects
          .filter(belegung__klient=klient, art=art, von__lte=bis_tag)
          .select_related("belegung"))
    for a in qs:
        b = a.belegung
        von = max(a.von, start_jahr, b.einzug)
        bis = min(a.bis or bis_tag, bis_tag, b.auszug or bis_tag)
        d = von
        while d <= bis:
            menge.add(d)
            d += timedelta(days=1)
    return menge


def tages_verguetung(abwesenheit, tag, jahres_menge=None) -> Decimal:
    """Vergütungsanteil (0..1) für einen Abwesenheitstag nach den Regeln der Art.
    `jahres_menge` (vorberechnete Tagesmenge, s. o.) vermeidet Query-pro-Tag."""
    art = abwesenheit.art
    if art.max_tage is not None:
        if art.basis == AbwesenheitsBasis.JE_EREIGNIS:
            tag_nr = (tag - abwesenheit.von).days + 1          # 1-basiert
            if tag_nr > art.max_tage:
                return Decimal("0")
        else:                                                   # Kalenderjahr, kumulativ
            menge = (jahres_menge if jahres_menge is not None
                     else _jahres_tagesmenge(abwesenheit.belegung.klient, art, tag))
            verbraucht = sum(1 for d in menge if d <= tag)
            if verbraucht > art.max_tage:
                return Decimal("0")
    return Decimal(art.verguetung_prozent) / 100


def monatskalender(belegung, jahr: int, monat: int, satz=None):
    """Tagesliste + Summen einer Belegung im Monat. `satz` = Entgeltsatz-Objekt
    (optional) -> Betrag = Σ(Anteil × Betrag) − Abzüge an vergüteten Abwesenheitstagen."""
    n_tage = monthrange(jahr, monat)[1]
    monatsende = date(jahr, monat, n_tage)
    abwesenheiten = list(belegung.abwesenheiten.select_related("art")
                         .filter(von__lte=monatsende))
    # Kalenderjahr-Kontingente EINMAL je Art vorberechnen (kein Query pro Tag)
    jahres_mengen = {}
    for a in abwesenheiten:
        if (a.art.max_tage is not None and a.art.basis == AbwesenheitsBasis.KALENDERJAHR
                and a.art_id not in jahres_mengen):
            jahres_mengen[a.art_id] = _jahres_tagesmenge(belegung.klient, a.art, monatsende)
    tage, summen = [], {"belegt": 0, "anwesend": 0, "abwesend": 0,
                        "verguetet_aequiv": Decimal("0"), "abzug": Decimal("0")}
    for t in range(1, n_tage + 1):
        tag = date(jahr, monat, t)
        if not belegung.belegt_am(tag):
            tage.append({"datum": tag, "status": "", "kuerzel": "", "anteil": None})
            continue
        summen["belegt"] += 1
        abw = _abwesenheit_am(abwesenheiten, tag)
        if abw is None:
            summen["anwesend"] += 1
            summen["verguetet_aequiv"] += 1
            tage.append({"datum": tag, "status": "anwesend", "kuerzel": "A", "anteil": Decimal("1")})
        else:
            summen["abwesend"] += 1
            anteil = tages_verguetung(abw, tag, jahres_menge=jahres_mengen.get(abw.art_id))
            summen["verguetet_aequiv"] += anteil
            if anteil > 0:
                summen["abzug"] += abw.art.abzug_je_tag or Decimal("0")
            tage.append({"datum": tag, "status": "abwesend",
                         "kuerzel": abw.art.kuerzel, "anteil": anteil})
    betrag = None
    if satz is not None:
        betrag = (summen["verguetet_aequiv"] * satz.betrag - summen["abzug"]).quantize(E2, ROUND_HALF_UP)
    return {"tage": tage, "summen": summen, "betrag": betrag, "satz": satz}


def satz_fuer_belegung(belegung, stichtag):
    """Entgeltsatz der Belegung: Katalog aus der aktiven Bewilligung der Klient*in,
    sonst Standard-Leistungstyp des Angebots; Kostenträger aus der Bewilligung.
    Stichtag wird auf den letzten BELEGTEN Tag geclippt — endet die Bewilligung mit
    dem Auszug im Monat, wird trotzdem der zutreffende Satz aufgelöst."""
    if belegung.auszug and belegung.auszug < stichtag:
        stichtag = belegung.auszug
    bew = belegung.klient.aktive_bewilligung(stichtag)
    katalog = (bew.katalog if bew and bew.katalog_id else None) or belegung.angebot.katalog
    if katalog is None:
        return None
    kt = bew.kostentraeger if bew and bew.kostentraeger_id else None
    return services.entgeltsatz_fuer(katalog, kostentraeger=kt, stichtag=stichtag)


def melde_warnungen(belegungen, stichtag=None):
    """Abwesenheiten, deren Meldefrist überschritten und die nicht gemeldet sind
    (BRV Jug: Meldung ans Jugendamt ab dem 4. Abwesenheitstag; BAO: sofort)."""
    stichtag = stichtag or date.today()
    warnungen = []
    for a in (KlientAbwesenheit.objects
              .filter(belegung__in=belegungen, gemeldet_am__isnull=True,
                      art__meldefrist_tage__isnull=False)
              .select_related("art", "belegung__klient")):
        ende = a.bis or stichtag
        dauer = (min(ende, stichtag) - a.von).days + 1
        if dauer > a.art.meldefrist_tage:
            warnungen.append({"abwesenheit": a, "dauer": dauer,
                              "frist": a.art.meldefrist_tage})
    return warnungen

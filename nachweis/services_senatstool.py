"""Senats-Umrechnungstool (Beschluss 3/2026) – exakte Nachbildung der Excel-Logik.

Bildet das offizielle Tool „Umrechnung Maßnahmepauschale → FLS/kLE" (V 8.0) des
Berliner Senats (SenASGIVA) formelgetreu nach. Quelle: Blätter „Input 1/2",
„Umrechnung", „Output", „Gegenprobe". Die Tests (tests_senatstool.py) prüfen
gegen die Referenzwerte eines echten Träger-Tools auf 6 Nachkommastellen.

Systematik:
  Alt:  Tagessatz (Maßnahmepauschale) je HBG 1–12.
  Neu:  * FLS-Satz  (€ je Fachleistungsstunde, ein Satz für alles)
        * individuelle FLS je HBG PRO WOCHE  (fallspezifische Zeiten,
          verteilt über die Personalschlüssel-Gewichtung)
        * kLE je Leistungsberechtigte*m und KALENDERTAG (einheitlich für alle
          HBG; deckt fallunspezifische Zeiten, Erreichbarkeit, Wegezeiten,
          Sonstige Kosten). Abgerechnet zum selben FLS-Satz.
  Die Umrechnung ist erlösneutral (Gegenprobe: Budget alt == Budget neu).
"""
from decimal import Decimal, getcontext

getcontext().prec = 28

D = Decimal

# Personalschlüssel je HBG (VK je Leistungsberechtigte*m bei 38,5 h/Woche) –
# landesweite Konstanten aus dem Tool (Umrechnung G7:G18).
PERSONALSCHLUESSEL = {
    1: D("0.136"), 2: D("0.192"), 3: D("0.248"), 4: D("0.305"),
    5: D("0.361"), 6: D("0.417"), 7: D("0.473"), 8: D("0.529"),
    9: D("0.586"), 10: D("0.642"), 11: D("0.699"), 12: D("0.755"),
}

# Netto-Jahresarbeitsstunden je VK bei 38,5 h/Woche (Beschluss 3/2017, KO75):
# 95689 Minuten/Woche-Logik des Tools: Input 1 G59 = 95689/60.
NETTO_JAS_385 = D(95689) / D(60)          # 1594.81666…

JAHR_TAGE = D("365.25")                    # Kalenderjahr inkl. Schaltjahre
WOCHEN_JE_JAHR = JAHR_TAGE / D(7)          # 52.1785…
WOCHEN_JE_MONAT = WOCHEN_JE_JAHR / D(12)   # 4.34821…  (Woche → Monat: ×)

# Tage-Aufteilung für die Erreichbarkeit (Input 1, Zeilen 78/79):
# Sa/So = 2/7 des Jahres, plus 8,29 Feiertage auf Werktagen (Berliner Schnitt).
WE_FT_TAGE = JAHR_TAGE * 2 / 7 + D("8.29")  # 112.6471…
WERKTAGE = JAHR_TAGE - WE_FT_TAGE           # 252.6028…


def erreichbarkeit_pa(mo_fr_std_je_tag, we_ft_std_je_tag=0) -> Decimal:
    """Erreichbarkeits-/Bereitschaftsstunden pro Jahr aus Stunden je Tag
    (Anzahl Mitarbeitende × Dauer), getrennt nach Mo–Fr und Sa/So/Feiertag –
    exakt wie das Tool (Input 1, I80)."""
    return D(str(mo_fr_std_je_tag)) * WERKTAGE + D(str(we_ft_std_je_tag)) * WE_FT_TAGE


def durchschnitts_personalkosten(pauschalen: dict, auslastung: Decimal) -> Decimal:
    """Ø-Personalkosten nach der Differenzmethode (Input 1 F98):
    (Pauschale HBG12 − Pauschale HBG1) × Tage p.a. / (Schlüssel HBG12 − Schlüssel HBG1).
    Unabhängig von der Wochenarbeitszeit (Normierung kürzt sich)."""
    tage = JAHR_TAGE * auslastung
    return ((D(str(pauschalen[12])) - D(str(pauschalen[1]))) * tage
            / (PERSONALSCHLUESSEL[12] - PERSONALSCHLUESSEL[1]))


def umrechnung(pauschalen: dict, belegung_ist: dict, kapazitaet: int,
               erreichbarkeit_std_pa, wegezeit_std_vk_woche=D(6),
               auslastung=D("0.959"), wochenarbeitszeit=D("38.5"),
               fallunspez_anteil=D("0.2"), personalkosten=None):
    """Vollständige Umrechnung wie das Senats-Tool (Blatt „Umrechnung").

    pauschalen:            {hbg: alter Tagessatz €}  (Input 1, 3. Vergütung)
    belegung_ist:          {hbg: Anzahl LB am Stichtag}  (Input 2)
    kapazitaet:            vereinbarte Platzzahl (Soll)
    erreichbarkeit_std_pa: Stunden Erreichbarkeit/Bereitschaft pro Jahr (Input 1, 5.)
    wegezeit_std_vk_woche: Ø Wegezeit je VK und Woche (Input 1, 6.)
    auslastung:            vereinbarte Auslastung (Input 1, 7. – landesweit 0,959)
    fallunspez_anteil:     Abschlag fallunspezifische Zeiten (Umrechnung J32 = 20 %)
    personalkosten:        Ø-PK überschreiben (sonst Differenzmethode)

    Rückgabe: dict mit fls_satz, kle_je_tag, fls_woche {hbg: Std}, sowie den
    Zwischengrößen (budget_gesamt, fallspez_std, …) für Gegenprobe/Anzeige.
    """
    pausch = {h: D(str(v)) for h, v in pauschalen.items()}
    ist = {h: D(str(v)) for h, v in belegung_ist.items()}
    kap = D(str(kapazitaet))
    ausl = D(str(auslastung))
    woz = D(str(wochenarbeitszeit))
    erreich = D(str(erreichbarkeit_std_pa))
    weg = D(str(wegezeit_std_vk_woche))

    tage = JAHR_TAGE * ausl                                   # K7 = 350.27475
    ist_gesamt = sum(ist.values())                            # E21
    jas = NETTO_JAS_385 * woz / D("38.5")                     # G63 / H31

    pk = D(str(personalkosten)) if personalkosten else \
        durchschnitts_personalkosten(pauschalen, ausl)        # F100

    # 1. Maßnahmebudgets: Ist auf Soll-Kapazität skalieren, VK & Budget je HBG.
    budget_gesamt = D(0)
    vk_gesamt = D(0)
    soll = {}
    for h in PERSONALSCHLUESSEL:
        e = ist.get(h, D(0))
        f = e * kap / ist_gesamt if ist_gesamt else D(0)      # F7:F18 (Soll-LB)
        soll[h] = f
        schluessel_norm = PERSONALSCHLUESSEL[h] * D("38.5") / woz   # H7:H18
        vk_gesamt += f * schluessel_norm                      # I7:I18
        budget_gesamt += f * pausch.get(h, D(0)) * tage       # L7:L18
    # (Nachtdienst/PTL A/B hier 0 – bei Bedarf analog ergänzen.)

    # 2. Aufteilung Assistenzpersonal → fallspezifische Zeiten (Std p.a.).
    std_gesamt = vk_gesamt * jas                              # I31
    fallunspez_std = -D(str(fallunspez_anteil)) * std_gesamt  # I32
    zwischensumme = std_gesamt + fallunspez_std - erreich     # I36
    wegezeit_anteil = weg / woz                               # G85
    wegezeit_std = -zwischensumme * wegezeit_anteil           # I38
    fallspez_std = zwischensumme + wegezeit_std               # I40

    # 3. FLS-Satz: Ø-PK je (Jahresarbeitsstunden × Auslastung).      (L45)
    fls_satz = pk / (jas * ausl)

    # 4. kLE je LB und Tag: Restbudget (gesamt − fallspezifisch) auf
    #    LB-Tage verteilt, in FLS-Äquivalent umgerechnet.            (L56)
    teilbudget_fallspez = fallspez_std / jas * pk             # L40
    budget_kle = budget_gesamt - teilbudget_fallspez          # I56
    lb_tage = tage * kap                                      # J56
    kle_je_tag = (budget_kle / lb_tage) / fls_satz            # K56 / L45

    # 5. Individuelle FLS je HBG pro Woche über die Gewichtung.      (L67:L78)
    gewicht = {h: PERSONALSCHLUESSEL[h] / PERSONALSCHLUESSEL[1] for h in PERSONALSCHLUESSEL}
    lb_gewichtet = sum(soll[h] * gewicht[h] for h in PERSONALSCHLUESSEL)   # J80
    fls_pa_hbg1 = fallspez_std / lb_gewichtet if lb_gewichtet else D(0)    # K67
    fls_woche = {h: fls_pa_hbg1 * gewicht[h] / WOCHEN_JE_JAHR for h in PERSONALSCHLUESSEL}

    return {
        "personalkosten": pk, "tage": tage, "jas": jas,
        "budget_gesamt": budget_gesamt, "vk_gesamt": vk_gesamt,
        "std_gesamt": std_gesamt, "fallspez_std": fallspez_std,
        "fls_satz": fls_satz, "kle_je_tag": kle_je_tag,
        "fls_woche": fls_woche, "soll": soll,
    }


def gegenprobe(ergebnis, pauschalen: dict, belegung_ist: dict):
    """Erlösneutralität wie Blatt „Gegenprobe": Budget alt == Budget neu
    (auf Basis der Ist-Belegung, volle 365,25 Tage). Rückgabe (alt, neu)."""
    ist = {h: D(str(v)) for h, v in belegung_ist.items()}
    alt = sum(ist.get(h, D(0)) * JAHR_TAGE * D(str(pauschalen.get(h, 0)))
              for h in PERSONALSCHLUESSEL)
    fls = ergebnis["fls_woche"]
    satz = ergebnis["fls_satz"]
    neu = sum(ist.get(h, D(0)) * (fls[h] / D(7)) * JAHR_TAGE * satz
              for h in PERSONALSCHLUESSEL)
    neu += sum(ist.values()) * ergebnis["kle_je_tag"] * JAHR_TAGE * satz
    return alt, neu

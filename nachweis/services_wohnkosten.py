"""Selbstzahler / Wohnkosten (WBVG): Zugriff, Nummernkreis, monatlicher Rechnungslauf.

Zweiter Debitor neben dem Kostenträger: die Bewohner*in zahlt Miete/Verpflegung selbst.
Aus der Wohnkostenvereinbarung (wiederkehrende Monatspositionen) entsteht je Monat eine
Selbstzahler-Rechnung. Eigener Nummernkreis WK-JAHR-NNNN (getrennt vom Kostenträger).
"""
from datetime import date
from decimal import Decimal

from django.db import transaction, IntegrityError
from django.utils import timezone

from . import services
from .models import (Klient, Angebot, Rechnungsstatus, Wohnkostenvereinbarung,
                     SelbstzahlerRechnung, SelbstzahlerPosition, _monatstage)

_AKTIVE_STATUS = [Rechnungsstatus.ENTWURF, Rechnungsstatus.GESTELLT, Rechnungsstatus.BEZAHLT]


def darf_wohnkosten(user) -> bool:
    """Leitung (eigenes Team) und Verwaltung/Break-Glass (alle) dürfen Wohnkosten pflegen."""
    return services.ist_leitung(user) or services.darf_abrechnen(user)


def klienten_im_zugriff(user):
    """Bewohner*innen, deren Wohnkosten der/die Nutzer*in sehen darf. Leitung: eigenes
    Team; Verwaltung: alle (Finanzfunktion, wie bei den Kostenträger-Rechnungen)."""
    if services.ist_leitung(user):
        return services.klienten_fuer(user)
    if services.darf_abrechnen(user):
        return Klient.objects.all()
    return Klient.objects.none()


def angebote_im_zugriff(user):
    """Wohnform-Angebote, die der/die Nutzer*in wählen darf – analog klienten_im_zugriff:
    Leitung nur die eigenen Team-Angebote (kein Fremd-Team-Objekt/Namensleak), Verwaltung alle."""
    if services.ist_leitung(user):
        return Angebot.objects.filter(team__in=services.teams_fuer(user))
    if services.darf_abrechnen(user):
        return Angebot.objects.all()
    return Angebot.objects.none()


def naechste_wohnkosten_nummer(jahr: int) -> str:
    """Fortlaufende Selbstzahler-Rechnungsnummer WK-JAHR-NNNN (lückenlos je Jahr)."""
    prefix = f"WK-{jahr}-"
    seqs = [int(n[len(prefix):]) for n in
            SelbstzahlerRechnung.objects.filter(nummer__startswith=prefix)
            .values_list("nummer", flat=True)
            if n[len(prefix):].isdigit()]
    return f"{prefix}{(max(seqs) + 1 if seqs else 1):04d}"


def rechnungen_erzeugen(jahr, monat, ersteller, klienten_qs) -> dict:
    """Erzeugt für alle im Monat gültigen, aktiven Vereinbarungen im Zugriff je eine
    Selbstzahler-Rechnung (überspringt bereits berechnete). Positionen werden
    festgeschrieben (Snapshot).

    Bewusst NICHT ein großer atomic-Block: jede Rechnung wird in einem eigenen
    Savepoint angelegt, damit eine Nummernkreis-Kollision (paralleler Lauf/Doppelklick)
    nur die eine Zeile verwirft statt des ganzen Laufs. Bei mehreren gleichzeitig
    gültigen Vereinbarungen einer Bewohner*in wird NICHT stumm ein Betrag geraten,
    sondern der Fall als 'mehrdeutig' gemeldet und übersprungen.
    Rückgabe: {erstellt, uebersprungen, ohne_positionen, mehrdeutig: [namen]}."""
    heute = date.today()
    faellig_tag_max = _monatstage(jahr, monat)
    erstellt, uebersprungen, ohne_pos, mehrdeutig = [], 0, 0, []

    # gültige Vereinbarungen je Klient sammeln (Mehrdeutigkeit erkennen)
    je_klient = {}
    for v in (Wohnkostenvereinbarung.objects
              .filter(klient__in=klienten_qs, aktiv=True)
              .select_related("klient").prefetch_related("positionen")):
        if v.gilt_im_monat(jahr, monat):
            je_klient.setdefault(v.klient_id, []).append(v)

    for kid, vs in je_klient.items():
        k = vs[0].klient
        if len(vs) > 1:                       # mehrere gültige Vereinbarungen -> nicht raten
            mehrdeutig.append(k.name)
            continue
        v = vs[0]
        if SelbstzahlerRechnung.objects.filter(
                klient=k, jahr=jahr, monat=monat, status__in=_AKTIVE_STATUS).exists():
            uebersprungen += 1
            continue
        positionen = list(v.positionen.all())
        if not positionen:
            ohne_pos += 1
            continue
        r = _rechnung_anlegen(k, v, jahr, monat, heute, faellig_tag_max, positionen, ersteller)
        if r is None:
            uebersprungen += 1        # Kollision/schon berechnet (paralleler Lauf)
        else:
            erstellt.append(r)
    return {"erstellt": erstellt, "uebersprungen": uebersprungen,
            "ohne_positionen": ohne_pos, "mehrdeutig": mehrdeutig}


def _rechnung_anlegen(k, v, jahr, monat, heute, faellig_tag_max, positionen, ersteller):
    """Legt eine Rechnung in einem eigenen Savepoint an; vergibt die Nummer neu bei
    Kollision (Retry). Gibt None zurück, wenn dauerhaft blockiert (z. B. paralleler
    Lauf hat die Rechnung des Monats bereits erstellt = (klient,jahr,monat)-Constraint)."""
    betrag = sum((p.monatsbetrag for p in positionen), Decimal("0"))
    faellig = date(jahr, monat, min(v.faelligkeit_tag, faellig_tag_max))
    for _ in range(5):
        try:
            with transaction.atomic():
                r = SelbstzahlerRechnung.objects.create(
                    nummer=naechste_wohnkosten_nummer(jahr), klient=k,
                    empfaenger=k.name, jahr=jahr, monat=monat, datum=heute,
                    faellig_am=faellig, betrag=betrag, status=Rechnungsstatus.GESTELLT,
                    erstellt_von=ersteller)
                SelbstzahlerPosition.objects.bulk_create([
                    SelbstzahlerPosition(rechnung=r, bezeichnung=p.bezeichnung,
                                         betrag=p.monatsbetrag) for p in positionen])
                return r
        except IntegrityError:
            # Nummernkollision -> neue Nummer im nächsten Versuch; ist bereits eine
            # Rechnung für (klient,jahr,monat) da, scheitern alle Versuche -> None.
            if SelbstzahlerRechnung.objects.filter(
                    klient=k, jahr=jahr, monat=monat, status__in=_AKTIVE_STATUS).exists():
                return None
    return None

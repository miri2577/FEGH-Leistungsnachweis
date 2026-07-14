"""Phase 3 / Slice 3a: Controlling — Kennzahlen-Cockpit für Leitung und Verwaltung.

Bewusst OHNE Klientenbezug (nur Aggregate): Erlöse/Zahlungseingänge je Monat,
Offene-Posten-Stand, FLS-Erbringungsquote je Team, Freigabe-Funnel des Monats,
Fristen-Compliance. Damit dürfen es beide Rollen sehen — die Verwaltung sieht
weiterhin keine Klientendaten, die Leitung bekommt die Geld-Sicht dazu.
(Pendant zu Vivendi Controlling Center — eingebaut statt Metabase-Fremdsystem.)
"""
import csv
from datetime import date
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render, redirect

from . import services
from .models import (Team, Teamtyp, Klient, Status, Rechnung, Rechnungsstatus,
                     Rechnungstyp, Zahlung, Monatsfreigabe, Freigabestatus,
                     Bericht, BerichtsStatus)

MONATSNAMEN_KURZ = ["", "Jan", "Feb", "Mär", "Apr", "Mai", "Jun",
                    "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]


def _darf_controlling(user) -> bool:
    return services.ist_leitung(user) or services.ist_verwaltung(user)


def _int(val, default):
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _erloese_je_monat(jahr: int):
    """Je Monat: fakturiert (gestellte/bezahlte Rechnungen inkl. saldierter Gutschriften,
    nach Rechnungsdatum) und Zahlungseingang (nach Zahldatum)."""
    fakturiert = [Decimal("0")] * 13
    for r in Rechnung.objects.filter(datum__year=jahr,
                                     status__in=[Rechnungsstatus.GESTELLT,
                                                 Rechnungsstatus.BEZAHLT]):
        fakturiert[r.datum.month] += r.betrag or Decimal("0")
    eingang = [Decimal("0")] * 13
    for z in Zahlung.objects.filter(datum__year=jahr).select_related("rechnung"):
        eingang[z.datum.month] += z.betrag
    return fakturiert, eingang


def _op_stand():
    offene = [r for r in Rechnung.objects.filter(status=Rechnungsstatus.GESTELLT)
              .prefetch_related("zahlungen") if r.offener_betrag > 0]
    heute = date.today()
    return {
        "anzahl": len(offene),
        "summe": sum((r.offener_betrag for r in offene), Decimal("0")),
        "ueberfaellig": sum((r.offener_betrag for r in offene
                             if r.tage_ueberfaellig(heute) > 0), Decimal("0")),
        "n_ueberfaellig": sum(1 for r in offene if r.tage_ueberfaellig(heute) > 0),
    }


def _team_quoten(jahr: int):
    """FLS-Erbringungsquote je Betreuungs-Team (Ist vs. Kontingent, nur Aggregate)."""
    zeilen = []
    for t in Team.objects.exclude(typ=Teamtyp.VERWALTUNG).order_by("name"):
        klienten = Klient.objects.filter(team=t)
        if not klienten.exists():
            continue
        _z, summe = services.fachleistungsstunden(jahr, klienten=klienten)
        kontingent = summe.get("kontingent_jahr") or Decimal("0")
        ist = summe.get("ist") or Decimal("0")
        quote = (ist / kontingent * 100) if kontingent else Decimal("0")
        zeilen.append({"team": t.name, "n_klienten": klienten.count(),
                       "kontingent": kontingent, "ist": ist,
                       "quote": quote.quantize(Decimal("0.1"))})
    return zeilen


def _freigabe_funnel(jahr: int, monat: int):
    """Abrechnungs-Funnel des Monats: wie viele Nachweise stehen in welchem Status?"""
    counts = {s: 0 for s, _ in Freigabestatus.choices}
    for mf in Monatsfreigabe.objects.filter(jahr=jahr, monat=monat):
        counts[mf.status] = counts.get(mf.status, 0) + 1
    in_betreuung = Klient.objects.filter(status=Status.BETREUUNG).count()
    ohne = max(0, in_betreuung - sum(counts.values()))
    return [{"label": "ohne Nachweis", "n": ohne, "warn": ohne > 0}] + \
           [{"label": label, "n": counts[s], "warn": False}
            for s, label in Freigabestatus.choices]


def _fristen_stand():
    heute = date.today()
    bfr = services.bewilligung_fristen(Klient.objects.filter(status=Status.BETREUUNG))
    berichte_ueberfaellig = sum(
        1 for b in Bericht.objects.exclude(status=BerichtsStatus.VERSENDET)
        .filter(faellig_am__isnull=False) if b.faellig_am < heute)
    return {
        "bew_fehlt": sum(1 for f in bfr if f["fehlt"]),
        "bew_auslaufend": sum(1 for f in bfr if not f["fehlt"]),
        "berichte_faellig": len(services.berichte_faellig(Klient.objects.all())),
        "berichte_ueberfaellig": berichte_ueberfaellig,
    }


@login_required
def controlling(request):
    if not _darf_controlling(request.user):
        return redirect("nachweis:start")
    jahr = _int(request.GET.get("jahr"), date.today().year)
    monat = min(12, max(1, _int(request.GET.get("monat"), date.today().month)))
    fakturiert, eingang = _erloese_je_monat(jahr)
    return render(request, "nachweis/controlling.html", {
        "aktiv": "controlling", "jahr": jahr, "monat": monat,
        "monate": list(range(1, 13)),
        "chart": {
            "labels": MONATSNAMEN_KURZ[1:],
            "fakturiert": [float(x) for x in fakturiert[1:]],
            "eingang": [float(x) for x in eingang[1:]],
        },
        "summe_fakturiert": sum(fakturiert, Decimal("0")),
        "summe_eingang": sum(eingang, Decimal("0")),
        "op": _op_stand(),
        "teams": _team_quoten(jahr),
        "funnel": _freigabe_funnel(jahr, monat),
        "fristen": _fristen_stand(),
    })


@login_required
def controlling_csv(request):
    """Monats-Kennzahlen als CSV (für Träger/Steuerberatung/eigene Auswertungen)."""
    if not _darf_controlling(request.user):
        return redirect("nachweis:start")
    jahr = _int(request.GET.get("jahr"), date.today().year)
    fakturiert, eingang = _erloese_je_monat(jahr)
    resp = HttpResponse(content_type="text/csv; charset=utf-8-sig")
    resp["Content-Disposition"] = f'attachment; filename="Controlling_{jahr}.csv"'
    w = csv.writer(resp, delimiter=";")
    w.writerow(["Monat", "Fakturiert_EUR", "Zahlungseingang_EUR"])
    for m in range(1, 13):
        w.writerow([f"{m:02d}.{jahr}", f"{fakturiert[m]}", f"{eingang[m]}"])
    w.writerow(["SUMME", f"{sum(fakturiert, Decimal('0'))}", f"{sum(eingang, Decimal('0'))}"])
    return resp

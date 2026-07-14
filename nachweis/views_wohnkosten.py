"""Selbstzahler / Wohnkosten (WBVG): Vereinbarungen pflegen, monatlich abrechnen,
Rechnungen einsehen/drucken, Zahlung/Storno. Zugriff: Leitung (eigenes Team) und
Verwaltung/Break-Glass (alle). Zweiter Debitor neben dem Kostenträger.
"""
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_POST

from . import services, services_wohnkosten as wk
from .models import (Klient, Angebot, Rechnungsstatus, WohnkostenKategorie,
                     Wohnkostenvereinbarung, Wohnkostenposition, SelbstzahlerRechnung)

MONATSNAMEN = ["", "Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
               "August", "September", "Oktober", "November", "Dezember"]


def _int0(val):
    try:
        return int(val)
    except (TypeError, ValueError):
        return 0


def _dec(val):
    """Deutschen Betrag robust parsen. Leer -> 0. Nicht parsebar oder negativ -> None
    (die aufrufende View meldet dann einen Fehler, statt still 0,00 zu speichern)."""
    from decimal import Decimal, InvalidOperation
    s = (val or "").strip().replace(" ", "").replace("€", "")
    if not s:
        return Decimal("0")
    if "," in s:                    # deutsch: Punkt = Tausender, Komma = Dezimal
        s = s.replace(".", "").replace(",", ".")
    try:
        d = Decimal(s)
    except InvalidOperation:
        return None
    return d if d >= 0 else None


def _datum(s):
    try:
        return date.fromisoformat(s)
    except (TypeError, ValueError):
        return None


@login_required
def wohnkosten(request):
    """Übersicht: Vereinbarungen im Zugriff, Monatslauf, letzte Selbstzahler-Rechnungen."""
    if not wk.darf_wohnkosten(request.user):
        return HttpResponseForbidden()
    im_zugriff = wk.klienten_im_zugriff(request.user)
    vereinbarungen = (Wohnkostenvereinbarung.objects.filter(klient__in=im_zugriff)
                      .select_related("klient", "angebot").prefetch_related("positionen"))
    rechnungen = (SelbstzahlerRechnung.objects.filter(klient__in=im_zugriff)
                  .select_related("klient").order_by("-datum", "-nummer")[:50])
    heute = date.today()
    return render(request, "nachweis/wohnkosten.html", {
        "aktiv": "wohnkosten",
        "vereinbarungen": list(vereinbarungen),
        "rechnungen": list(rechnungen),
        "klienten": im_zugriff.order_by("nachname", "vorname"),
        "monate": [(m, MONATSNAMEN[m]) for m in range(1, 13)],
        "jahr_default": heute.year, "monat_default": heute.month,
    })


@require_POST
@login_required
def vereinbarung_anlegen(request):
    if not wk.darf_wohnkosten(request.user):
        return HttpResponseForbidden()
    klient = get_object_or_404(wk.klienten_im_zugriff(request.user),
                               pk=_int0(request.POST.get("klient")))
    ang = wk.angebote_im_zugriff(request.user).filter(
        pk=_int0(request.POST.get("angebot"))).first()
    v = Wohnkostenvereinbarung.objects.create(
        klient=klient, angebot=ang,
        gueltig_von=_datum(request.POST.get("gueltig_von")))
    messages.success(request, f"Wohnkostenvereinbarung für {klient.name} angelegt – Positionen ergänzen.")
    return redirect("nachweis:wohnkosten_vereinbarung", pk=v.pk)


@login_required
def wohnkosten_vereinbarung(request, pk):
    """Eine Vereinbarung bearbeiten: Positionen, Gültigkeit, Fälligkeitstag, aktiv."""
    if not wk.darf_wohnkosten(request.user):
        return HttpResponseForbidden()
    v = get_object_or_404(Wohnkostenvereinbarung.objects.filter(
        klient__in=wk.klienten_im_zugriff(request.user)).select_related("klient", "angebot"), pk=pk)
    return render(request, "nachweis/wohnkosten_vereinbarung.html", {
        "aktiv": "wohnkosten", "v": v, "klient": v.klient,
        "positionen": list(v.positionen.all()),
        "kategorien": WohnkostenKategorie.choices,
        "angebote": wk.angebote_im_zugriff(request.user).filter(aktiv=True),
    })


@require_POST
@login_required
def vereinbarung_speichern(request):
    """Kopfdaten der Vereinbarung (Gültigkeit/Fälligkeit/Angebot/aktiv) speichern."""
    if not wk.darf_wohnkosten(request.user):
        return HttpResponseForbidden()
    v = get_object_or_404(Wohnkostenvereinbarung.objects.filter(
        klient__in=wk.klienten_im_zugriff(request.user)), pk=_int0(request.POST.get("id")))
    v.gueltig_von = _datum(request.POST.get("gueltig_von"))
    v.gueltig_bis = _datum(request.POST.get("gueltig_bis"))
    v.faelligkeit_tag = min(28, max(1, _int0(request.POST.get("faelligkeit_tag")) or 1))
    v.angebot = wk.angebote_im_zugriff(request.user).filter(
        pk=_int0(request.POST.get("angebot"))).first()
    v.aktiv = request.POST.get("aktiv") == "on"
    v.notiz = (request.POST.get("notiz") or "").strip()[:200]
    v.save()
    messages.success(request, "Vereinbarung gespeichert.")
    return redirect("nachweis:wohnkosten_vereinbarung", pk=v.pk)


@require_POST
@login_required
def position_speichern(request):
    if not wk.darf_wohnkosten(request.user):
        return HttpResponseForbidden()
    v = get_object_or_404(Wohnkostenvereinbarung.objects.filter(
        klient__in=wk.klienten_im_zugriff(request.user)), pk=_int0(request.POST.get("vereinbarung")))
    pid = request.POST.get("id")
    p = get_object_or_404(Wohnkostenposition, pk=_int0(pid), vereinbarung=v) if pid else \
        Wohnkostenposition(vereinbarung=v)
    bez = (request.POST.get("bezeichnung") or "").strip()
    if not bez:
        messages.error(request, "Bitte eine Bezeichnung angeben.")
        return redirect("nachweis:wohnkosten_vereinbarung", pk=v.pk)
    betrag = _dec(request.POST.get("monatsbetrag"))
    if betrag is None:
        messages.error(request, "Bitte einen gültigen Betrag eingeben (z. B. 1234,56).")
        return redirect("nachweis:wohnkosten_vereinbarung", pk=v.pk)
    kat = request.POST.get("kategorie")
    p.kategorie = kat if kat in WohnkostenKategorie.values else WohnkostenKategorie.SONSTIGES
    p.bezeichnung = bez[:120]
    p.monatsbetrag = betrag
    p.save()
    messages.success(request, f"Position „{p.bezeichnung}“ gespeichert.")
    return redirect("nachweis:wohnkosten_vereinbarung", pk=v.pk)


@require_POST
@login_required
def position_loeschen(request):
    if not wk.darf_wohnkosten(request.user):
        return HttpResponseForbidden()
    p = get_object_or_404(Wohnkostenposition.objects.filter(
        vereinbarung__klient__in=wk.klienten_im_zugriff(request.user)),
        pk=_int0(request.POST.get("id")))
    vid = p.vereinbarung_id
    p.delete()
    messages.success(request, "Position gelöscht.")
    return redirect("nachweis:wohnkosten_vereinbarung", pk=vid)


@require_POST
@login_required
def wohnkosten_erzeugen(request):
    """Monatslauf: Selbstzahler-Rechnungen für alle gültigen Vereinbarungen im Zugriff."""
    if not wk.darf_wohnkosten(request.user):
        return HttpResponseForbidden()
    jahr = min(2100, max(2000, _int0(request.POST.get("jahr")) or date.today().year))
    monat = min(12, max(1, _int0(request.POST.get("monat")) or date.today().month))
    ergebnis = wk.rechnungen_erzeugen(jahr, monat, services.mitarbeiter_fuer(request.user),
                                      wk.klienten_im_zugriff(request.user))
    n = len(ergebnis["erstellt"])
    teile = [f"{n} Rechnung(en) erstellt"]
    if ergebnis["uebersprungen"]:
        teile.append(f"{ergebnis['uebersprungen']} bereits vorhanden")
    if ergebnis["ohne_positionen"]:
        teile.append(f"{ergebnis['ohne_positionen']} ohne Positionen übersprungen")
    (messages.success if n else messages.info)(
        request, f"{MONATSNAMEN[monat]} {jahr}: " + ", ".join(teile) + ".")
    if ergebnis["mehrdeutig"]:
        messages.error(request, "Nicht abgerechnet – mehrere gültige Vereinbarungen: "
                                + ", ".join(ergebnis["mehrdeutig"])
                                + ". Bitte Zeitraum/aktiv-Status bereinigen (nur eine gültig).")
    return redirect("nachweis:wohnkosten")


@login_required
def selbstzahler_rechnung(request, pk):
    if not wk.darf_wohnkosten(request.user):
        return HttpResponseForbidden()
    r = get_object_or_404(SelbstzahlerRechnung.objects.filter(
        klient__in=wk.klienten_im_zugriff(request.user)).select_related("klient"), pk=pk)
    return render(request, "nachweis/selbstzahler_rechnung.html", {
        "aktiv": "wohnkosten", "r": r, "positionen": list(r.positionen.all()),
        "monatsname": MONATSNAMEN[r.monat],
    })


@login_required
def selbstzahler_pdf(request, pk):
    if not wk.darf_wohnkosten(request.user):
        return HttpResponseForbidden()
    r = get_object_or_404(SelbstzahlerRechnung.objects.filter(
        klient__in=wk.klienten_im_zugriff(request.user)).select_related("klient"), pk=pk)
    from .models import Rechnungssteller
    return render(request, "nachweis/selbstzahler_pdf.html", {
        "r": r, "positionen": list(r.positionen.all()), "monatsname": MONATSNAMEN[r.monat],
        "steller": Rechnungssteller.objects.first(),
    })


@require_POST
@login_required
def selbstzahler_aktion(request):
    """Zahlungseingang markieren oder stornieren."""
    if not wk.darf_wohnkosten(request.user):
        return HttpResponseForbidden()
    r = get_object_or_404(SelbstzahlerRechnung.objects.filter(
        klient__in=wk.klienten_im_zugriff(request.user)), pk=_int0(request.POST.get("id")))
    aktion = request.POST.get("aktion")
    if aktion == "bezahlt" and r.status == Rechnungsstatus.GESTELLT:
        eingang = _datum(request.POST.get("bezahlt_am")) or date.today()
        if eingang > date.today() or eingang < r.datum:
            messages.error(request, "Zahlungsdatum unplausibel (in der Zukunft oder vor "
                                    "dem Rechnungsdatum).")
            return redirect("nachweis:selbstzahler_rechnung", pk=r.pk)
        r.status = Rechnungsstatus.BEZAHLT
        r.bezahlt_am = eingang
        r.save(update_fields=["status", "bezahlt_am"])
        messages.success(request, f"{r.nummer} als bezahlt markiert.")
    elif aktion == "offen" and r.status == Rechnungsstatus.BEZAHLT:
        r.status = Rechnungsstatus.GESTELLT
        r.bezahlt_am = None
        r.save(update_fields=["status", "bezahlt_am"])
        messages.success(request, f"{r.nummer} wieder als offen markiert.")
    elif aktion == "storno" and r.status != Rechnungsstatus.STORNIERT:
        r.status = Rechnungsstatus.STORNIERT
        r.save(update_fields=["status"])
        messages.success(request, f"{r.nummer} storniert.")
    else:
        messages.error(request, "Aktion nicht möglich.")
    return redirect("nachweis:selbstzahler_rechnung", pk=r.pk)

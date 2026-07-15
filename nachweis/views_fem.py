"""Dokumentation freiheitsentziehender Maßnahmen (§ 1831 BGB, WTG Berlin) je Klient*in
in stationären Wohnformen: richterliche Genehmigung, Befristung, Meldeverfahren.

Rechtlich sensibel/Art-9 → streng team-gescopt über klienten_fuer; bei der
Voll-Anonymisierung mitgelöscht.
"""
from datetime import date, datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import services
from .models import FEM, FEMArt


def _klient(request, pk):
    return get_object_or_404(services.klienten_fuer(request.user), pk=pk)


def _dt(s):
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _datum(s):
    try:
        return date.fromisoformat((s or "").strip())
    except (ValueError, TypeError):
        return None


@login_required
def fem(request, pk):
    """Fallakten-Reiter: freiheitsentziehende Maßnahmen der Klient*in."""
    klient = _klient(request, pk)
    heute = date.today()
    massnahmen = list(klient.fem_massnahmen.all())
    for m in massnahmen:
        m.genehmigung_faellig = bool(
            m.laeuft and m.genehmigt_bis and (m.genehmigt_bis - heute).days <= 30)
    bearbeiten = None
    bid = request.GET.get("edit")
    if bid and bid.isdigit():
        bearbeiten = klient.fem_massnahmen.filter(pk=bid).first()
    return render(request, "nachweis/fem.html", {
        "aktiv": "belegungsliste" if services.ist_leitung(request.user) else "start",
        "klient": klient, "massnahmen": massnahmen, "arten": FEMArt.choices,
        "bearbeiten": bearbeiten,
        "jetzt": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
    })


@require_POST
@login_required
def fem_speichern(request, pk):
    klient = _klient(request, pk)
    beginn = _dt(request.POST.get("beginn"))
    grund = (request.POST.get("grund") or "").strip()
    if not (beginn and grund):
        messages.error(request, "Bitte Beginn (Datum/Zeit) und Grund angeben.")
        return redirect("nachweis:fem", pk=klient.id)
    mid = request.POST.get("id")
    if mid and mid.isdigit():
        m = klient.fem_massnahmen.filter(pk=mid).first()
        if m is None:
            return HttpResponseForbidden()
    else:
        m = FEM(klient=klient, erfasst_von=services.mitarbeiter_fuer(request.user))
    art = request.POST.get("art")
    m.art = art if art in FEMArt.values else FEMArt.FIXIERUNG
    m.beginn = beginn
    m.ende = _dt(request.POST.get("ende"))
    m.grund = grund[:200]
    m.angeordnet_von = (request.POST.get("angeordnet_von") or "").strip()[:140]
    m.genehmigung_az = (request.POST.get("genehmigung_az") or "").strip()[:80]
    m.genehmigt_bis = _datum(request.POST.get("genehmigt_bis"))
    m.einwilligung = request.POST.get("einwilligung") == "on"
    m.gemeldet_am = _datum(request.POST.get("gemeldet_am"))
    m.notiz = (request.POST.get("notiz") or "").strip()[:200]
    m.save()
    messages.success(request, "Maßnahme gespeichert.")
    return redirect("nachweis:fem", pk=klient.id)


@require_POST
@login_required
def fem_beenden(request, pk):
    klient = _klient(request, pk)
    m = get_object_or_404(klient.fem_massnahmen, pk=request.POST.get("id"))
    if m.laeuft:
        m.ende = timezone.now()
        m.save(update_fields=["ende"])
        messages.success(request, "Maßnahme als beendet dokumentiert.")
    return redirect("nachweis:fem", pk=klient.id)


@require_POST
@login_required
def fem_loeschen(request, pk):
    klient = _klient(request, pk)
    m = get_object_or_404(klient.fem_massnahmen, pk=request.POST.get("id"))
    m.delete()
    messages.success(request, "Maßnahme gelöscht.")
    return redirect("nachweis:fem", pk=klient.id)

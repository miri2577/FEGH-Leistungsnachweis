"""Fortbildungs-/Qualifikationsverwaltung je Mitarbeiter*in mit Ablauf-/Auffrischungs-
fristen. Leitung sieht die eigenen Teams, Admin/Superuser alle. Grundlage für den
Fachkraftnachweis gegenüber dem Kostenträger.
"""
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_POST

from . import services
from .models import Mitarbeiter, Qualifikation, QualifikationArt

HORIZONT = 60      # Tage Vorlauf für „läuft ab"


def _darf(user):
    return services.ist_leitung(user) or services.ist_admin(user) or user.is_superuser


def _sichtbare_ma(user):
    if services.ist_admin(user) or user.is_superuser:
        return Mitarbeiter.objects.filter(aktiv=True)
    return Mitarbeiter.objects.filter(aktiv=True, team__in=services.teams_fuer(user))


def _status(q, heute):
    if not q.gueltig_bis:
        return ("dauerhaft", 999)
    tage = (q.gueltig_bis - heute).days
    if tage < 0:
        return ("abgelaufen", tage)
    if tage <= HORIZONT:
        return ("laeuft_ab", tage)
    return ("gueltig", tage)


@login_required
def qualifikationen(request):
    if not _darf(request.user):
        return redirect("nachweis:start")
    heute = date.today()
    sichtbar = _sichtbare_ma(request.user).order_by("name", "vorname")
    quals = Qualifikation.objects.filter(mitarbeiter__in=sichtbar).select_related("mitarbeiter")
    mid = request.GET.get("ma")
    if mid and mid.isdigit():
        quals = quals.filter(mitarbeiter_id=mid)
    quals = list(quals)
    for q in quals:
        q.status, q.tage = _status(q, heute)
    faellig = [q for q in quals if q.status in ("abgelaufen", "laeuft_ab")]
    bearbeiten = None
    bid = request.GET.get("edit")
    if bid and bid.isdigit():
        bearbeiten = Qualifikation.objects.filter(pk=bid, mitarbeiter__in=sichtbar).first()
    return render(request, "nachweis/qualifikationen.html", {
        "aktiv": "qualifikationen", "quals": quals, "faellig": faellig,
        "mitarbeitende": sichtbar, "arten": QualifikationArt.choices,
        "bearbeiten": bearbeiten, "ma_filter": mid,
    })


@require_POST
@login_required
def qualifikation_speichern(request):
    if not _darf(request.user):
        return HttpResponseForbidden()
    sichtbar = _sichtbare_ma(request.user)
    ma = sichtbar.filter(pk=request.POST.get("mitarbeiter")).first()
    bezeichnung = (request.POST.get("bezeichnung") or "").strip()
    if not (ma and bezeichnung):
        messages.error(request, "Bitte Mitarbeiter*in und Bezeichnung angeben.")
        return redirect("nachweis:qualifikationen")
    qid = request.POST.get("id")
    if qid and qid.isdigit():
        q = Qualifikation.objects.filter(pk=qid, mitarbeiter__in=sichtbar).first()
        if q is None:
            return HttpResponseForbidden()
    else:
        q = Qualifikation()
    q.mitarbeiter = ma
    art = request.POST.get("art")
    q.art = art if art in QualifikationArt.values else QualifikationArt.FORTBILDUNG
    q.bezeichnung = bezeichnung
    q.erworben_am = _datum(request.POST.get("erworben_am"))
    q.gueltig_bis = _datum(request.POST.get("gueltig_bis"))
    q.pflicht = request.POST.get("pflicht") == "on"
    q.notiz = (request.POST.get("notiz") or "").strip()
    q.save()
    messages.success(request, f"Qualifikation „{q.bezeichnung}“ gespeichert.")
    return redirect("nachweis:qualifikationen")


@require_POST
@login_required
def qualifikation_loeschen(request):
    if not _darf(request.user):
        return HttpResponseForbidden()
    q = Qualifikation.objects.filter(
        pk=request.POST.get("id"), mitarbeiter__in=_sichtbare_ma(request.user)).first()
    if q:
        q.delete()
        messages.success(request, "Qualifikation gelöscht.")
    return redirect("nachweis:qualifikationen")


def _datum(s):
    try:
        return date.fromisoformat((s or "").strip())
    except ValueError:
        return None

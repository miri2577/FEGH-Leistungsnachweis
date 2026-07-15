"""Kontaktpersonen je Klient*in (Angehörige, Ärzte, gesetzliche Betreuung, Notfall).

Zugriff exakt wie Dokumente/Ziele über services.klienten_fuer (Team/Vertretung,
Leitung); Verwaltung/Admin haben keinen Klientenbezug. Personenbeziehbare Daten →
werden beim Löschkonzept mit anonymisiert/gelöscht.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_POST

from . import services
from .models import Kontaktperson, KontaktRolle


@login_required
def kontakte(request, pk):
    """Kontakte-Seite je Klient*in: Liste + Anlegen/Bearbeiten."""
    klient = get_object_or_404(services.klienten_fuer(request.user), pk=pk)
    bearbeiten = None
    bid = request.GET.get("edit")
    if bid and bid.isdigit():
        bearbeiten = klient.kontakte.filter(pk=bid).first()
    return render(request, "nachweis/kontakte.html", {
        "aktiv": "belegungsliste" if services.ist_leitung(request.user) else "start",
        "klient": klient, "kontakte": list(klient.kontakte.all()),
        "rollen": KontaktRolle.choices, "bearbeiten": bearbeiten,
    })


@require_POST
@login_required
def kontakt_speichern(request, pk):
    klient = get_object_or_404(services.klienten_fuer(request.user), pk=pk)
    name = (request.POST.get("name") or "").strip()
    if not name:
        messages.error(request, "Bitte einen Namen angeben.")
        return redirect("nachweis:kontakte", pk=klient.id)
    kid = request.POST.get("id")
    if kid and kid.isdigit():
        k = klient.kontakte.filter(pk=kid).first()   # streng auf DIESE Klient*in gescopt
        if k is None:
            return HttpResponseForbidden()
    else:
        k = Kontaktperson(klient=klient)
    rolle = request.POST.get("rolle")
    k.rolle = rolle if rolle in KontaktRolle.values else KontaktRolle.ANGEHOERIGE
    k.name = name
    k.funktion = (request.POST.get("funktion") or "").strip()
    k.telefon = (request.POST.get("telefon") or "").strip()
    k.email = (request.POST.get("email") or "").strip()
    k.adresse = (request.POST.get("adresse") or "").strip()
    k.notiz = (request.POST.get("notiz") or "").strip()
    k.notfall = request.POST.get("notfall") == "on"
    k.save()
    messages.success(request, f"Kontakt „{k.name}“ gespeichert.")
    return redirect("nachweis:kontakte", pk=klient.id)


@require_POST
@login_required
def kontakt_loeschen(request, pk):
    klient = get_object_or_404(services.klienten_fuer(request.user), pk=pk)
    k = klient.kontakte.filter(pk=request.POST.get("id")).first()
    if k:
        k.delete()
        messages.success(request, "Kontakt gelöscht.")
    return redirect("nachweis:kontakte", pk=klient.id)

"""Phase 2 / Slice 2a: Ziele der Ziel- und Leistungsplanung (ZLP) je Klient*in.

Zugriff wie Verlaufsdoku: alle mit Klient-Zugriff (Team/Vertretung, Leitung) pflegen
Ziele; Verwaltung/Admin haben keinen Klientenbezug (klienten_fuer ist dort leer).
Löschen ist der Leitung vorbehalten – fachlich korrekt ist das Setzen eines Status
(erreicht/angepasst/nicht weiterverfolgt), damit die Historie erhalten bleibt.
"""
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Max, Q
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_POST

from . import services
from .models import Klient, Ziel, ZielArt, ZielStatus, Leistung


def _datum(s):
    try:
        return date.fromisoformat(s)
    except (TypeError, ValueError):
        return None


@login_required
def ziele(request, pk):
    """Ziele-Seite je Klient*in: Richtungsziele mit Handlungszielen, Status, Zielverlauf."""
    klient = get_object_or_404(services.klienten_fuer(request.user), pk=pk)
    # Zielverlauf: je Ziel Anzahl Doku-Einträge + letztes Doku-Datum (deckt „vergessene" Ziele auf)
    alle = list(klient.ziele.annotate(
        doku_anzahl=Count("leistungen", filter=Q(leistungen__dokumentation__gt="")),
        doku_zuletzt=Max("leistungen__datum",
                         filter=Q(leistungen__dokumentation__gt=""))))
    richtungsziele = [z for z in alle if z.art == ZielArt.RICHTUNGSZIEL]
    frei = [z for z in alle if z.art == ZielArt.HANDLUNGSZIEL and not z.uebergeordnet_id]
    for r in richtungsziele:
        r.kinder = [z for z in alle if z.uebergeordnet_id == r.id]
    bearbeiten = next((z for z in alle if str(z.id) == request.GET.get("edit", "")), None)
    return render(request, "nachweis/ziele.html", {
        "aktiv": "belegungsliste" if services.ist_leitung(request.user) else "start",
        "klient": klient, "richtungsziele": richtungsziele, "freie_ziele": frei,
        "n_aktiv": sum(1 for z in alle if z.status == ZielStatus.AKTIV),
        "bearbeiten": bearbeiten,
        "art_wahl": ZielArt.choices, "status_wahl": ZielStatus.choices,
        "ist_leitung": services.ist_leitung(request.user),
        "heute": date.today().isoformat(),
    })


@require_POST
@login_required
def ziel_speichern(request):
    klient = get_object_or_404(services.klienten_fuer(request.user),
                               pk=request.POST.get("klient"))
    zid = request.POST.get("id")
    if zid:
        z = get_object_or_404(Ziel, pk=zid, klient=klient)
    else:
        z = Ziel(klient=klient)
    titel = (request.POST.get("titel") or "").strip()
    if not titel:
        messages.error(request, "Bitte einen Ziel-Titel angeben.")
        return redirect("nachweis:ziele", pk=klient.pk)
    z.titel = titel[:200]
    art = request.POST.get("art")
    z.art = art if art in ZielArt.values else ZielArt.HANDLUNGSZIEL
    ueber = request.POST.get("uebergeordnet")
    z.uebergeordnet = (Ziel.objects.filter(pk=ueber, klient=klient,
                                           art=ZielArt.RICHTUNGSZIEL).first()
                       if (ueber or "").isdigit() and z.art == ZielArt.HANDLUNGSZIEL else None)
    z.beschreibung = (request.POST.get("beschreibung") or "").strip()
    z.indikator = (request.POST.get("indikator") or "").strip()
    st = request.POST.get("status")
    if st in ZielStatus.values:
        z.status = st
    z.gueltig_von = _datum(request.POST.get("gueltig_von"))
    z.gueltig_bis = _datum(request.POST.get("gueltig_bis"))
    try:
        z.reihenfolge = max(0, min(int(request.POST.get("reihenfolge") or 0), 999))
    except ValueError:
        z.reihenfolge = 0
    z.save()
    messages.success(request, f"Ziel „{z.titel}“ gespeichert.")
    return redirect("nachweis:ziele", pk=klient.pk)


@require_POST
@login_required
def ziel_status(request):
    """Schneller Status-Wechsel (erreicht / nicht weiterverfolgt / wieder aktiv)."""
    z = get_object_or_404(Ziel.objects.filter(
        klient__in=services.klienten_fuer(request.user)), pk=request.POST.get("id"))
    st = request.POST.get("status")
    if st in ZielStatus.values:
        z.status = st
        z.save(update_fields=["status", "geaendert"])
        messages.success(request, f"Ziel „{z.titel}“: {z.get_status_display()}.")
    return redirect("nachweis:ziele", pk=z.klient_id)


@require_POST
@login_required
def ziel_loeschen(request):
    """Nur Leitung – fachlich ist Status setzen der Normalweg (Historie bleibt)."""
    if not services.ist_leitung(request.user):
        return HttpResponseForbidden()
    z = get_object_or_404(Ziel.objects.filter(
        klient__in=services.klienten_fuer(request.user)), pk=request.POST.get("id"))
    kpk = z.klient_id
    name = z.titel
    z.delete()
    messages.success(request, f"Ziel „{name}“ gelöscht.")
    return redirect("nachweis:ziele", pk=kpk)


@login_required
def api_ziele(request):
    """Aktive Ziele eines Klienten fürs Doku-Modal (id, titel, art)."""
    klient = services.klienten_fuer(request.user).filter(
        pk=request.GET.get("klient") or 0).first()
    if not klient:
        return JsonResponse({"ziele": []})
    return JsonResponse({"ziele": [
        {"id": z.id, "titel": z.titel, "art": z.get_art_display()}
        for z in klient.ziele.filter(status=ZielStatus.AKTIV)]})

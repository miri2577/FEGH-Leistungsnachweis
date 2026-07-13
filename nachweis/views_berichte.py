"""Phase 2 / Slice 2b: Berichts-Engine — Berichte je Klient*in mit Vorlagen und Workflow.

Workflow (örV/AV Hilfeplanung): offen → in Arbeit → mit Klient*in besprochen → versendet.
'Versendet' pflegt Klient.versendet_am automatisch nach (bestehende Fälligkeits-Anzeige).
Zugriff wie Ziele/Doku: alle mit Klient-Zugriff; Löschen nur Leitung.
"""
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_POST

from . import services
from .models import (Klient, Bericht, BerichtsStatus, Berichtsvorlage,
                     Ziel, ZielStatus)


def _datum(s):
    try:
        return date.fromisoformat(s)
    except (TypeError, ValueError):
        return None


@login_required
def berichte(request, pk):
    """Berichte-Seite je Klient*in: Liste + Anlegen/Bearbeiten."""
    klient = get_object_or_404(services.klienten_fuer(request.user), pk=pk)
    liste = list(klient.berichte.select_related("vorlage"))
    bearbeiten = next((b for b in liste if str(b.id) == request.GET.get("edit", "")), None)
    # sinnvolle Vorbelegung: fällig = KÜ-Ende, Zeitraum = letzte 12 Monate bzw. seit letztem Bericht
    letzter = next((b for b in liste if b.zeitraum_bis), None)
    von_default = (letzter.zeitraum_bis + timedelta(days=1)) if letzter \
        else date.today() - timedelta(days=365)
    return render(request, "nachweis/berichte.html", {
        "aktiv": "belegungsliste" if services.ist_leitung(request.user) else "start",
        "klient": klient, "berichte": liste, "bearbeiten": bearbeiten,
        "vorlagen": Berichtsvorlage.objects.filter(aktiv=True),
        "status_wahl": BerichtsStatus.choices,
        "ist_leitung": services.ist_leitung(request.user),
        "faellig_default": (klient.kue_bis or date.today() + timedelta(days=70)).isoformat(),
        "von_default": von_default.isoformat(),
        "bis_default": date.today().isoformat(),
    })


@require_POST
@login_required
def bericht_speichern(request):
    klient = get_object_or_404(services.klienten_fuer(request.user),
                               pk=request.POST.get("klient"))
    bid = request.POST.get("id")
    if bid:
        b = get_object_or_404(Bericht, pk=bid, klient=klient)
    else:
        b = Bericht(klient=klient, erstellt_von=services.mitarbeiter_fuer(request.user))
    v = request.POST.get("vorlage")
    b.vorlage = Berichtsvorlage.objects.filter(pk=v, aktiv=True).first() if (v or "").isdigit() else b.vorlage
    b.zeitraum_von = _datum(request.POST.get("zeitraum_von"))
    b.zeitraum_bis = _datum(request.POST.get("zeitraum_bis"))
    b.faellig_am = _datum(request.POST.get("faellig_am"))
    b.notiz = (request.POST.get("notiz") or "").strip()[:200]
    if "inhalt" in request.POST:
        b.inhalt = (request.POST.get("inhalt") or "").strip()
        if b.inhalt and b.status == BerichtsStatus.OFFEN:
            b.status = BerichtsStatus.IN_ARBEIT       # Text da -> automatisch „in Arbeit"
    b.save()
    messages.success(request, "Bericht gespeichert.")
    return redirect("nachweis:berichte", pk=klient.pk)


@require_POST
@login_required
def bericht_status(request):
    """Workflow-Schritte: in Arbeit / besprochen (Pflicht-Schritt!) / versendet / zurück."""
    b = get_object_or_404(Bericht.objects.filter(
        klient__in=services.klienten_fuer(request.user)), pk=request.POST.get("id"))
    st = request.POST.get("status")
    if st not in BerichtsStatus.values:
        return redirect("nachweis:berichte", pk=b.klient_id)
    if st == BerichtsStatus.VERSENDET and b.status != BerichtsStatus.BESPROCHEN:
        # örV/AV Hilfeplanung: der Bericht ist VOR dem Versand mit der/dem
        # Leistungsberechtigten zu besprechen – Reihenfolge wird erzwungen.
        messages.error(request, "Bitte zuerst „mit Klient*in besprochen“ bestätigen – "
                                "der Bericht ist vor dem Versand zu besprechen.")
        return redirect("nachweis:berichte", pk=b.klient_id)
    b.status = st
    heute = date.today()
    if st == BerichtsStatus.BESPROCHEN and not b.besprochen_am:
        b.besprochen_am = heute
    if st == BerichtsStatus.VERSENDET:
        b.versendet_am = b.versendet_am or heute
        # bestehendes Fälligkeits-Feld am Klienten nachpflegen („…versendet am")
        type(b.klient).objects.filter(pk=b.klient_id).update(versendet_am=b.versendet_am)
    b.save()
    messages.success(request, f"Bericht: {b.get_status_display()}.")
    return redirect("nachweis:berichte", pk=b.klient_id)


@require_POST
@login_required
def bericht_loeschen(request):
    if not services.ist_leitung(request.user):
        return HttpResponseForbidden()
    b = get_object_or_404(Bericht.objects.filter(
        klient__in=services.klienten_fuer(request.user)), pk=request.POST.get("id"))
    kpk = b.klient_id
    b.delete()
    messages.success(request, "Bericht gelöscht.")
    return redirect("nachweis:berichte", pk=kpk)


@login_required
def bericht_druck(request, pk):
    """Druckansicht: Kopf + Gliederung der Vorlage + Berichtstext + Zielerreichung."""
    b = get_object_or_404(Bericht.objects.filter(
        klient__in=services.klienten_fuer(request.user)).select_related("vorlage", "klient"), pk=pk)
    ziele = list(b.klient.ziele.filter(art="handlungsziel")
                 .exclude(status=ZielStatus.AUFGEGEBEN).select_related("uebergeordnet"))
    return render(request, "nachweis/bericht_druck.html", {
        "b": b, "klient": b.klient, "ziele": ziele,
        "abschnitte": (b.vorlage.abschnitte if b.vorlage else []),
    })

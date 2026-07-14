"""P5: Dienstplanung (Vivendi-PEP-Kern). Leitung plant SOLL-Dienste je Team/Monat;
das IST bleibt die Arbeitszeit-Erfassung. Nachtbesetzungs-Check für Angebote mit
Nacht-Erreichbarkeit (M2). Kein eAU – Krankmeldung läuft über Abwesenheit + Lohnbüro.
"""
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.http import HttpResponseForbidden
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from . import services
from .models import (Dienst, Schichtart, Mitarbeiter, Angebot, Erreichbarkeit)

WOCHENTAGE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def _int0(val):
    try:
        return int(val)
    except (TypeError, ValueError):
        return 0


@login_required
def dienstplan(request):
    """Der separate Dienstplan ist in die Kalender-Monatsmatrix aufgegangen —
    Kalender und Dienstplan sind dasselbe Planungsbrett (ambulant plant Termine,
    stationär Schichtdienste). Alte URL/Lesezeichen leiten dorthin um."""
    params = "&".join(f"{k}={request.GET.get(k)}" for k in ("team", "jahr", "monat")
                      if request.GET.get(k))
    return redirect(f"{reverse('nachweis:kalender')}?ansicht=monat"
                    + (f"&{params}" if params else ""))


def _nacht_luecken(team, jahr, monat, n_tage, dienste):
    nacht_angebote = list(Angebot.objects.filter(
        team=team, aktiv=True,
        erreichbarkeit__in=[Erreichbarkeit.NACHT, Erreichbarkeit.TAG_NACHT]))
    if not nacht_angebote:
        return []
    besetzt = {(d.angebot_id, d.datum.day) for d in dienste
               if d.schichtart.ist_nachtdienst and d.angebot_id}
    luecken = []
    for a in nacht_angebote:
        fehl = [t for t in range(1, n_tage + 1) if (a.id, t) not in besetzt]
        if fehl:
            luecken.append({"angebot": a, "anzahl": len(fehl), "tage": fehl[:10]})
    return luecken


@require_POST
@login_required
def dienst_setzen(request):
    """Dienst anlegen/ändern/entfernen (ein Feld im Raster). schichtart leer = löschen."""
    if not services.ist_leitung(request.user):
        return HttpResponseForbidden()
    teams = services.teams_fuer(request.user)
    m = get_object_or_404(Mitarbeiter.objects.filter(team__in=teams),
                          pk=_int0(request.POST.get("mitarbeiter")))
    try:
        d = date.fromisoformat(request.POST.get("datum"))
    except (TypeError, ValueError):
        messages.error(request, "Ungültiges Datum.")
        return redirect("nachweis:kalender")
    zurueck = f"{request.POST.get('back') or ''}"
    sa_pk = _int0(request.POST.get("schichtart"))
    ang = Angebot.objects.filter(pk=_int0(request.POST.get("angebot")), team=m.team).first()
    if not sa_pk:
        Dienst.objects.filter(mitarbeiter=m, datum=d).delete()
    else:
        sa = get_object_or_404(Schichtart, pk=sa_pk, aktiv=True)
        # ein Dienst je MA/Tag im Raster -> vorhandene desselben Tags ersetzen
        Dienst.objects.filter(mitarbeiter=m, datum=d).exclude(schichtart=sa).delete()
        try:
            obj, _ = Dienst.objects.update_or_create(
                mitarbeiter=m, datum=d, schichtart=sa,
                defaults={"angebot": ang, "notiz": (request.POST.get("notiz") or "").strip()[:120]})
        except IntegrityError:
            pass
    return redirect(zurueck or "nachweis:kalender")


@login_required
def schichtarten(request):
    """Schichtarten pflegen (Leitung)."""
    if not services.ist_leitung(request.user):
        return HttpResponseForbidden()
    if request.method == "POST":
        from datetime import datetime
        def _t(s):
            try:
                return datetime.strptime((s or "").strip(), "%H:%M").time()
            except ValueError:
                return None
        pk = request.POST.get("id")
        sa = get_object_or_404(Schichtart, pk=_int0(pk)) if pk else Schichtart()
        name = (request.POST.get("name") or "").strip()
        beginn, ende = _t(request.POST.get("beginn")), _t(request.POST.get("ende"))
        if not (name and beginn and ende):
            messages.error(request, "Bitte Name, Beginn und Ende angeben.")
            return redirect("nachweis:schichtarten")
        sa.name = name[:60]
        sa.kuerzel = (request.POST.get("kuerzel") or name[:2]).strip()[:3]
        sa.beginn, sa.ende = beginn, ende
        sa.farbe = (request.POST.get("farbe") or "#0e7490").strip()[:7]
        sa.ist_nachtdienst = request.POST.get("ist_nachtdienst") == "on"
        sa.aktiv = request.POST.get("aktiv") == "on"
        sa.save()
        messages.success(request, f"Schichtart „{sa.name}“ gespeichert.")
        return redirect("nachweis:schichtarten")
    bearbeiten = Schichtart.objects.filter(pk=_int0(request.GET.get("edit"))).first() \
        if request.GET.get("edit") else None
    return render(request, "nachweis/schichtarten.html", {
        "aktiv": "kalender", "schichtarten": Schichtart.objects.all(),
        "bearbeiten": bearbeiten,
    })

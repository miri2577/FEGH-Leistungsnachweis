"""ICF-Bedarfsermittlung (Teilhabeinstrument Berlin, TIB — § 118 SGB IX).

Narrativ-dialogisch, KEINE numerische Skala: je Lebensbereich vier Freitext-
Leitfragen + kategoriale Teilhabe-Einschätzung. Erhebungen sind versioniert
(Erst-/Folge-Bedarfsermittlung). Zugriff wie Ziele/Wirkung (Team, Leitung).
"""
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from . import services
from .models import (Klient, TibLebensbereich, Bedarfsermittlung, BedarfsEinschaetzung,
                     TibAnlass, TeilhabeStatus)


def _int0(val):
    try:
        return int(val)
    except (TypeError, ValueError):
        return 0


def _datum(s):
    try:
        return date.fromisoformat(s)
    except (TypeError, ValueError):
        return None


@login_required
def bedarf(request, pk):
    """Bedarfsermittlung je Klient*in: gewählte (oder jüngste) Erhebung mit den 12
    Lebensbereichen; Historie der Erhebungen zur Auswahl."""
    klient = get_object_or_404(services.klienten_fuer(request.user), pk=pk)
    if request.method == "GET":
        services.protokolliere_zugriff(request, klient, "bedarf")
    erhebungen = list(klient.bedarfsermittlungen.select_related("erhoben_von"))
    aktuell = next((b for b in erhebungen if str(b.id) == request.GET.get("erhebung", "")),
                   erhebungen[0] if erhebungen else None)
    zeilen = []
    if aktuell:
        vorhanden = {e.lebensbereich_id: e for e in aktuell.einschaetzungen.select_related("lebensbereich")}
        for lb in TibLebensbereich.objects.filter(aktiv=True):
            zeilen.append({"lb": lb, "e": vorhanden.get(lb.id)})
    return render(request, "nachweis/bedarf.html", {
        "aktiv": "belegungsliste" if services.ist_leitung(request.user) else "start",
        "klient": klient, "erhebungen": erhebungen, "aktuell": aktuell, "zeilen": zeilen,
        "status_wahl": TeilhabeStatus.choices, "anlass_wahl": TibAnlass.choices,
        "heute": date.today().isoformat(), "ist_leitung": services.ist_leitung(request.user),
    })


@require_POST
@login_required
def bedarf_neu(request):
    """Neue Erhebung anlegen (Erst-/Folgeerhebung); Folgeerhebung übernimmt die
    Einschätzungen der jüngsten Erhebung als Ausgangspunkt (Fortschreibung)."""
    klient = get_object_or_404(services.klienten_fuer(request.user),
                               pk=_int0(request.POST.get("klient")))
    anlass = request.POST.get("anlass")
    b = Bedarfsermittlung.objects.create(
        klient=klient,
        anlass=anlass if anlass in TibAnlass.values else TibAnlass.ERST,
        datum=_datum(request.POST.get("datum")) or date.today(),
        erhoben_von=services.mitarbeiter_fuer(request.user))
    if b.anlass == TibAnlass.FORTSCHREIBUNG:
        vorlage = klient.bedarfsermittlungen.exclude(pk=b.pk).order_by("-datum", "-id").first()
        if vorlage:
            BedarfsEinschaetzung.objects.bulk_create([
                BedarfsEinschaetzung(
                    bedarfsermittlung=b, lebensbereich_id=e.lebensbereich_id,
                    relevant=e.relevant, gelingt=e.gelingt, barrieren=e.barrieren,
                    personfaktoren=e.personfaktoren, teilhabe_status=e.teilhabe_status,
                    unterstuetzung=e.unterstuetzung)
                for e in vorlage.einschaetzungen.all()])
    messages.success(request, "Bedarfsermittlung angelegt.")
    return redirect(f"{reverse('nachweis:bedarf', args=[klient.pk])}?erhebung={b.pk}")


@require_POST
@login_required
def bedarf_speichern(request):
    """Alle Lebensbereich-Einschätzungen einer Erhebung in einem Rutsch speichern."""
    b = get_object_or_404(Bedarfsermittlung.objects.filter(
        klient__in=services.klienten_fuer(request.user)), pk=_int0(request.POST.get("erhebung")))
    vorhanden = {e.lebensbereich_id: e for e in b.einschaetzungen.all()}
    for lb in TibLebensbereich.objects.filter(aktiv=True):
        p = f"lb_{lb.id}_"
        relevant = request.POST.get(p + "relevant") == "on"
        gelingt = (request.POST.get(p + "gelingt") or "").strip()
        barrieren = (request.POST.get(p + "barrieren") or "").strip()
        person = (request.POST.get(p + "person") or "").strip()
        status = request.POST.get(p + "status")
        unterst = (request.POST.get(p + "unterst") or "").strip()[:255]
        status = status if status in TeilhabeStatus.values else TeilhabeStatus.OFFEN
        leer = not (relevant or gelingt or barrieren or person or unterst
                    or status != TeilhabeStatus.OFFEN)
        e = vorhanden.get(lb.id)
        if leer and not e:
            continue                      # nichts eingetragen, kein Datensatz nötig
        if not e:
            e = BedarfsEinschaetzung(bedarfsermittlung=b, lebensbereich=lb)
        e.relevant, e.gelingt, e.barrieren = relevant, gelingt, barrieren
        e.personfaktoren, e.teilhabe_status, e.unterstuetzung = person, status, unterst
        e.save()
    messages.success(request, "Bedarfsermittlung gespeichert.")
    return redirect(f"{reverse('nachweis:bedarf', args=[b.klient_id])}?erhebung={b.pk}")


@require_POST
@login_required
def bedarf_loeschen(request):
    """Ganze Erhebung löschen (nur Leitung)."""
    if not services.ist_leitung(request.user):
        return HttpResponseForbidden()
    b = get_object_or_404(Bedarfsermittlung.objects.filter(
        klient__in=services.klienten_fuer(request.user)), pk=_int0(request.POST.get("erhebung")))
    kpk = b.klient_id
    b.delete()
    messages.success(request, "Bedarfsermittlung gelöscht.")
    return redirect("nachweis:bedarf", pk=kpk)

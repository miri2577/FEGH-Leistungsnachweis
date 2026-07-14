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
from .models import (Klient, Ziel, ZielArt, ZielStatus, Leistung,
                     Wirkungsdimension, Wirkungseinschaetzung,
                     WirkungsAnlass, WirkungsPerspektive)


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
                               pk=_int0(request.POST.get("klient")))
    zid = request.POST.get("id")
    if zid:
        z = get_object_or_404(Ziel, pk=_int0(zid), klient=klient)
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
    # .exclude(pk=z.pk): ein Ziel darf nie sein eigenes Übergeordnetes werden (beim
    # Art-Wechsel trägt die DB-Zeile noch die alte Art -> ohne Exclude wäre ein
    # Selbstzyklus möglich, das Ziel verschwände aus der Seite).
    z.uebergeordnet = (Ziel.objects.filter(pk=ueber, klient=klient,
                                           art=ZielArt.RICHTUNGSZIEL)
                       .exclude(pk=z.pk).first()
                       if (ueber or "").isdigit() and z.art == ZielArt.HANDLUNGSZIEL else None)
    if z.pk and z.art == ZielArt.HANDLUNGSZIEL:
        # Art-Wechsel Richtungsziel -> Handlungsziel: vorhandene Unterziele freistellen,
        # sonst hängen sie an einem Nicht-Richtungsziel und verschwinden aus der Anzeige.
        geloest = Ziel.objects.filter(uebergeordnet=z).update(uebergeordnet=None)
        if geloest:
            messages.info(request, f"{geloest} Handlungsziel(e) wurden vom bisherigen "
                                   f"Richtungsziel gelöst und stehen jetzt unter „ohne Richtungsziel“.")
    z.beschreibung = (request.POST.get("beschreibung") or "").strip()
    z.indikator = (request.POST.get("indikator") or "").strip()
    st = request.POST.get("status")
    if st in ZielStatus.values:
        z.status = st
    grad = (request.POST.get("erreicht_grad") or "").strip()
    z.erreicht_grad = min(100, max(0, _int0(grad))) if grad else None
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
        klient__in=services.klienten_fuer(request.user)), pk=_int0(request.POST.get("id")))
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
        klient__in=services.klienten_fuer(request.user)), pk=_int0(request.POST.get("id")))
    kpk = z.klient_id
    name = z.titel
    z.delete()
    messages.success(request, f"Ziel „{name}“ gelöscht.")
    return redirect("nachweis:ziele", pk=kpk)


# ---------------------------------------------------------------- Wirkungsmessung
@login_required
def wirkung(request, pk):
    """Wirkungsdimensionen je Klient*in (Berliner Systematik): Ist/Soll auf 7er-Skala
    zu Beginn/Fortschreibung/Ende, partizipativ je Perspektive. Verlaufs-Matrix
    zeigt die Entwicklung (niedriger = besser)."""
    klient = get_object_or_404(services.klienten_fuer(request.user), pk=pk)
    einschaetzungen = list(klient.wirkungseinschaetzungen
                           .select_related("dimension", "erstellt_von"))
    # Verlaufs-Matrix: je Dimension die Fachkraft-Werte nach Anlass (Beginn/letzte/Ende)
    matrix = []
    for d in Wirkungsdimension.objects.filter(aktiv=True):
        werte = [e for e in einschaetzungen if e.dimension_id == d.id
                 and e.perspektive == WirkungsPerspektive.FACHKRAFT]
        if not werte and not d.aktiv:
            continue
        beginn = next((e for e in sorted(werte, key=lambda e: e.datum)
                       if e.anlass == WirkungsAnlass.BEGINN), None)
        letzte = max(werte, key=lambda e: e.datum, default=None)
        delta = (beginn.ist - letzte.ist) if beginn and letzte and letzte != beginn else None
        matrix.append({"dimension": d, "beginn": beginn, "letzte": letzte,
                       "delta": delta, "hat_werte": bool(werte)})
    return render(request, "nachweis/wirkung.html", {
        "aktiv": "belegungsliste" if services.ist_leitung(request.user) else "start",
        "klient": klient, "matrix": matrix, "einschaetzungen": einschaetzungen,
        "dimensionen": Wirkungsdimension.objects.filter(aktiv=True),
        "anlaesse": WirkungsAnlass.choices, "perspektiven": WirkungsPerspektive.choices,
        "skala": range(1, 8), "heute": date.today().isoformat(),
        "ist_leitung": services.ist_leitung(request.user),
    })


@require_POST
@login_required
def wirkung_speichern(request):
    klient = get_object_or_404(services.klienten_fuer(request.user),
                               pk=_int0(request.POST.get("klient")))
    dimension = get_object_or_404(Wirkungsdimension, pk=_int0(request.POST.get("dimension")),
                                  aktiv=True)
    ist, soll = _int0(request.POST.get("ist")), _int0(request.POST.get("soll"))
    if not (1 <= ist <= 7 and 1 <= soll <= 7):
        messages.error(request, "Ist und Soll bitte auf der 7er-Skala (1–7) einstufen.")
        return redirect("nachweis:wirkung", pk=klient.pk)
    anlass = request.POST.get("anlass")
    perspektive = request.POST.get("perspektive")
    Wirkungseinschaetzung.objects.create(
        klient=klient, dimension=dimension,
        datum=_datum(request.POST.get("datum")) or date.today(),
        anlass=anlass if anlass in WirkungsAnlass.values else WirkungsAnlass.FORTSCHREIBUNG,
        perspektive=(perspektive if perspektive in WirkungsPerspektive.values
                     else WirkungsPerspektive.FACHKRAFT),
        ist=ist, soll=soll,
        kommentar=(request.POST.get("kommentar") or "").strip()[:200],
        erstellt_von=services.mitarbeiter_fuer(request.user))
    messages.success(request, f"Einschätzung „{dimension.name}“ erfasst (Ist {ist} → Soll {soll}).")
    return redirect("nachweis:wirkung", pk=klient.pk)


@require_POST
@login_required
def wirkung_loeschen(request):
    if not services.ist_leitung(request.user):
        return HttpResponseForbidden()
    e = get_object_or_404(Wirkungseinschaetzung.objects.filter(
        klient__in=services.klienten_fuer(request.user)), pk=_int0(request.POST.get("id")))
    kpk = e.klient_id
    e.delete()
    messages.success(request, "Einschätzung gelöscht.")
    return redirect("nachweis:wirkung", pk=kpk)


@login_required
def api_ziele(request):
    """Aktive Ziele eines Klienten fürs Doku-Modal (id, titel, art)."""
    klient = services.klienten_fuer(request.user).filter(
        pk=_int0(request.GET.get("klient"))).first()
    if not klient:
        return JsonResponse({"ziele": []})
    return JsonResponse({"ziele": [
        {"id": z.id, "titel": z.titel, "art": z.get_art_display()}
        for z in klient.ziele.filter(status=ZielStatus.AKTIV)]})

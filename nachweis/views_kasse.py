"""Kasse: Kassenblatt (laufendes Kassenbuch je Team/Monat) + Zählprotokoll (Monatsabschluss).
Vorlage: Abrechnung*.xlsx (Blätter „Kassenblatt" und „Zählprotokoll").
Verwaltung = Finanz-Hub: sieht alle Kassen und pflegt die BuHa-Felder.
"""
from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import services
from .models import Kasse, Kassenbuchung, Zaehlprotokoll, Team, GELDSTUECKELUNG

MONATSNAMEN = ["", "Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
               "August", "September", "Oktober", "November", "Dezember"]


def _dec(s):
    try:
        return Decimal((str(s) or "0").replace(",", ".").strip() or "0")
    except (InvalidOperation, AttributeError):
        return Decimal("0")


def _datum(s):
    try:
        return date.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def _int(s, d=0):
    try:
        return int(s)
    except (TypeError, ValueError):
        return d


def _kasse_or_403(request, pk):
    kasse = services.kassen_fuer(request.user).filter(pk=pk).first()
    if not kasse:
        return None
    return kasse


# ---------------------------------------------------------------- Kassenblatt
@login_required
def kasse(request):
    kassen = services.kassen_fuer(request.user)
    if not kassen.exists():
        return render(request, "nachweis/kasse.html", {"aktiv": "kasse", "keine": True,
                      "darf_anlegen": services.kann_buha(request.user),
                      "teams_ohne_kasse": Team.objects.filter(kasse__isnull=True)
                      if services.kann_buha(request.user) else Team.objects.none()})

    kasse_id = _int(request.GET.get("kasse"), 0)
    aktuelle = kassen.filter(pk=kasse_id).first() or kassen.first()
    jahr = _int(request.GET.get("jahr"), date.today().year)
    monat = min(12, max(1, _int(request.GET.get("monat"), date.today().month)))
    km = services.kassenmonat(aktuelle, jahr, monat)
    bearbeiten = km.buchungen.filter(pk=request.GET.get("edit")).first() if request.GET.get("edit") else None

    return render(request, "nachweis/kasse.html", {
        "aktiv": "kasse",
        "kassen": kassen,
        "kasse": aktuelle,
        "km": km,
        "jahr": jahr, "monat": monat, "monat_name": MONATSNAMEN[monat],
        "zeilen": services.kassenblatt_zeilen(km),
        "bearbeiten": bearbeiten,
        "naechste_bel": km.naechste_bel_nr(),
        "kann_buha": services.kann_buha(request.user),
        "monate": [(m, MONATSNAMEN[m]) for m in range(1, 13)],
        "teams_ohne_kasse": Team.objects.filter(kasse__isnull=True)
        if services.kann_buha(request.user) else Team.objects.none(),
        "darf_anlegen": services.kann_buha(request.user),
    })


@require_POST
@login_required
def buchung_save(request):
    km = None
    kasse = _kasse_or_403(request, request.POST.get("kasse"))
    if not kasse:
        return HttpResponseForbidden()
    jahr = _int(request.POST.get("jahr"), date.today().year)
    monat = _int(request.POST.get("monat"), date.today().month)
    km = services.kassenmonat(kasse, jahr, monat)

    pk = request.POST.get("id")
    if pk:
        b = get_object_or_404(Kassenbuchung, pk=pk, monat=km)
    else:
        b = Kassenbuchung(monat=km, bel_nr=_int(request.POST.get("bel_nr"), km.naechste_bel_nr()))

    datum = _datum(request.POST.get("datum"))
    text = (request.POST.get("text") or "").strip()
    if not (datum and text):
        messages.error(request, "Bitte Datum und Text angeben.")
        return redirect(f"{request.path.replace('/buchung/','/')}")
    b.datum = datum
    b.text = text
    b.einnahme = _dec(request.POST.get("einnahme"))
    b.ausgabe = _dec(request.POST.get("ausgabe"))
    if pk:
        b.bel_nr = _int(request.POST.get("bel_nr"), b.bel_nr)
    # BuHa-Felder nur durch Verwaltung
    if services.kann_buha(request.user):
        b.buchungsdatum = _datum(request.POST.get("buchungsdatum"))
        b.kontonr = (request.POST.get("kontonr") or "").strip()
        b.kostenstelle = (request.POST.get("kostenstelle") or "").strip()
    b.save()
    messages.success(request, f"Beleg {b.bel_nr} gespeichert.")
    return redirect(f"/kasse/?kasse={kasse.id}&jahr={jahr}&monat={monat}")


@require_POST
@login_required
def buchung_delete(request):
    kasse = _kasse_or_403(request, request.POST.get("kasse"))
    if not kasse:
        return HttpResponseForbidden()
    b = get_object_or_404(Kassenbuchung, pk=request.POST.get("id"), monat__kasse=kasse)
    jahr, monat = b.monat.jahr, b.monat.monat
    b.delete()
    messages.success(request, "Beleg gelöscht.")
    return redirect(f"/kasse/?kasse={kasse.id}&jahr={jahr}&monat={monat}")


@require_POST
@login_required
def vortrag_save(request):
    kasse = _kasse_or_403(request, request.POST.get("kasse"))
    if not kasse or not services.kann_buha(request.user):
        return HttpResponseForbidden()
    jahr = _int(request.POST.get("jahr"), date.today().year)
    monat = _int(request.POST.get("monat"), date.today().month)
    km = services.kassenmonat(kasse, jahr, monat)
    km.vortrag = _dec(request.POST.get("vortrag"))
    km.save(update_fields=["vortrag"])
    messages.success(request, "Kassenvortrag gespeichert.")
    return redirect(f"/kasse/?kasse={kasse.id}&jahr={jahr}&monat={monat}")


@require_POST
@login_required
def kasse_anlegen(request):
    if not services.kann_buha(request.user):
        return HttpResponseForbidden()
    team = get_object_or_404(Team, pk=request.POST.get("team"))
    Kasse.objects.get_or_create(team=team, defaults={
        "bezeichnung": f"Kassenbuch {team.name}",
        "kostenstelle": (request.POST.get("kostenstelle") or "").strip()})
    messages.success(request, f"Kasse für {team.name} angelegt.")
    return redirect("nachweis:kasse")


# ---------------------------------------------------------------- Zählprotokoll
@login_required
def zaehlprotokoll(request):
    kasse = _kasse_or_403(request, request.GET.get("kasse") or request.POST.get("kasse"))
    if not kasse:
        return HttpResponseForbidden()
    jahr = _int(request.GET.get("jahr") or request.POST.get("jahr"), date.today().year)
    monat = _int(request.GET.get("monat") or request.POST.get("monat"), date.today().month)
    km = services.kassenmonat(kasse, jahr, monat)
    z, _ = Zaehlprotokoll.objects.get_or_create(monat=km)

    if request.method == "POST":
        for _wert, feld in GELDSTUECKELUNG:
            setattr(z, feld, max(0, _int(request.POST.get(feld), 0)))
        z.datum = _datum(request.POST.get("datum"))
        z.nicht_eingetragene = _dec(request.POST.get("nicht_eingetragene"))
        z.vermerke = (request.POST.get("vermerke") or "").strip()
        z.save()
        messages.success(request, "Zählprotokoll gespeichert.")
        return redirect(f"/kasse/zaehlprotokoll/?kasse={kasse.id}&jahr={jahr}&monat={monat}")

    # Stückelung fürs Template (Noten oben, Münzen unten)
    noten = [(w, f, getattr(z, f)) for w, f in GELDSTUECKELUNG if w >= 5]
    muenzen = [(w, f, getattr(z, f)) for w, f in GELDSTUECKELUNG if w < 5]
    return render(request, "nachweis/zaehlprotokoll.html", {
        "aktiv": "kasse", "kasse": kasse, "km": km, "z": z,
        "jahr": jahr, "monat": monat, "monat_name": MONATSNAMEN[monat],
        "noten": noten, "muenzen": muenzen,
    })


# ---------------------------------------------------------------- Druck: Kassenblatt + Zählprotokoll
@login_required
def kasse_druck(request):
    kasse = _kasse_or_403(request, request.GET.get("kasse"))
    if not kasse:
        return HttpResponseForbidden()
    if request.GET.get("monat"):
        jahr = _int(request.GET.get("jahr"), date.today().year)
        monat = min(12, max(1, _int(request.GET.get("monat"), date.today().month)))
    else:
        # Ohne expliziten Monat: den zuletzt abgeschlossenen Monat vorbelegen.
        jahr, monat = services.letzter_kassenabschluss(kasse)
    km = services.kassenmonat(kasse, jahr, monat)
    z = Zaehlprotokoll.objects.filter(monat=km).first()
    # Zählprotokoll gehört als Monatsabschluss immer auf den Druck. Ist noch keins
    # erfasst, drucken wir ein leeres Formular (transiente, nicht gespeicherte Instanz).
    z_erfasst = bool(z and (z.datum or z.bargeld_gesamt))
    if z is None:
        z = Zaehlprotokoll(monat=km)
    noten = [(w, getattr(z, f), w * getattr(z, f)) for w, f in GELDSTUECKELUNG if w >= 5]
    muenzen = [(w, getattr(z, f), w * getattr(z, f)) for w, f in GELDSTUECKELUNG if w < 5]
    return render(request, "nachweis/kasse_druck.html", {
        "kasse": kasse, "km": km, "z": z, "z_erfasst": z_erfasst,
        "jahr": jahr, "monat": monat, "monat_name": MONATSNAMEN[monat],
        "zeilen": services.kassenblatt_zeilen(km),
        "noten": noten, "muenzen": muenzen,
        "kann_buha": services.kann_buha(request.user),
    })

"""Löschkonzept-UI (DSGVO Art. 5/17, § 84 SGB X): Übersicht der Aufbewahrungs-
fristen + fälligen Klient*innen, review-gestützte Anonymisierung.

Zugriff: nur Leitung (verwaltet die Belegungsliste). Die Anonymisierung ist
IRREVERSIBEL – daher zweistufig (Trockenlauf-Vorschau + ausdrückliche Bestätigung)
und streng team-gescopt. Nichts läuft automatisch.
"""
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_POST

from . import services, services_loeschfristen as lf
from .models import Klient, Status, Aufbewahrungsregel


def _int0(val):
    try:
        return int(val)
    except (TypeError, ValueError):
        return 0


@login_required
def loeschfristen(request):
    """Übersicht: Aufbewahrungsregeln + beendete Klient*innen mit Fristen-Status."""
    if not services.ist_leitung(request.user):
        return HttpResponseForbidden()
    beendet = (services.klienten_fuer(request.user)
               .filter(status=Status.BEENDIGUNG)
               .prefetch_related("leistungen", "belegungen", "freigaben"))
    zeilen = [lf.loeschstatus(k) for k in beendet]
    # Fällige zuerst, dann nach Frei-ab-Datum
    zeilen.sort(key=lambda s: (not s["fach_faellig"],
                               s["fach_frei_ab"] or date.max))
    n_fach = sum(1 for z in zeilen if z["fach_faellig"])
    n_voll = sum(1 for z in zeilen if z["voll_faellig"])
    return render(request, "nachweis/loeschfristen.html", {
        "aktiv": "loeschfristen",
        "regeln": Aufbewahrungsregel.objects.all(),
        "zeilen": zeilen, "n_fach": n_fach, "n_voll": n_voll,
        "n_beendet": len(zeilen),
    })


@login_required
def loeschfristen_klient(request, pk):
    """Detail-/Bestätigungsseite für eine*n Klient*in: zeigt den Trockenlauf
    (was würde gelöscht/anonymisiert) vor der eigentlichen Anwendung."""
    if not services.ist_leitung(request.user):
        return HttpResponseForbidden()
    klient = get_object_or_404(services.klienten_fuer(request.user), pk=pk)
    status = lf.loeschstatus(klient)
    stufe = "voll" if status["voll_faellig"] else "fachdaten"
    vorschau = lf.anonymisieren(klient, stufe=stufe, apply=False)
    return render(request, "nachweis/loeschfristen_klient.html", {
        "aktiv": "loeschfristen", "klient": klient, "status": status,
        "stufe": stufe, "vorschau": vorschau,
    })


@login_required
@require_POST
def loeschfristen_anonymisieren(request):
    """Führt die Anonymisierung aus – nur wenn fällig, mit Bestätigungstext."""
    if not services.ist_leitung(request.user):
        return HttpResponseForbidden()
    klient = get_object_or_404(services.klienten_fuer(request.user),
                               pk=_int0(request.POST.get("klient")))
    status = lf.loeschstatus(klient)
    if not status["fach_faellig"]:
        messages.error(request, "Die Aufbewahrungsfrist ist noch nicht abgelaufen – "
                                "keine Anonymisierung möglich.")
        return redirect("nachweis:loeschfristen_klient", pk=klient.pk)
    # Tippschutz: der Name muss zur Bestätigung eingegeben werden. Beide Seiten
    # normalisieren; ein leerer Soll-Name lehnt IMMER ab (sonst "" == "" -> Bypass).
    eingabe = (request.POST.get("bestaetigung") or "").strip()
    soll = (klient.nachname or "").strip()
    if not soll or eingabe != soll:
        messages.error(request, "Bestätigung fehlgeschlagen: Nachname stimmt nicht.")
        return redirect("nachweis:loeschfristen_klient", pk=klient.pk)
    stufe = "voll" if status["voll_faellig"] else "fachdaten"
    report = lf.anonymisieren(klient, stufe=stufe, apply=True)
    messages.success(request, f"Anonymisierung ausgeführt ({len(report['aktionen'])} "
                              f"Aktion(en), Stufe: {stufe}).")
    return redirect("nachweis:loeschfristen")

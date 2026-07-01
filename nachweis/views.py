import json
from datetime import date, datetime

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden
from django.shortcuts import render, get_object_or_404, redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from . import services
from .models import Mitarbeiter, Leistung, Klient, Leistungsart


def _jahr(request):
    return int(request.GET.get("jahr") or date.today().year)


def _parse_time(s):
    s = (s or "").strip()
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).time()
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------- Dashboard
@login_required
def dashboard(request):
    jahr = _jahr(request)
    betreuer_id = request.GET.get("betreuer") or ""
    sichtbar = services.klienten_fuer(request.user)

    zeilen, summe = services.fachleistungsstunden(jahr, klienten=sichtbar)
    if betreuer_id and services.darf_alles(request.user):
        zeilen = [z for z in zeilen if str(z["betreuer"].id) == betreuer_id]
        summe = summe | {
            "kontingent_jahr": sum((z["kontingent_jahr"] for z in zeilen), 0),
            "ist": sum((z["ist"] for z in zeilen), 0),
            "rest": sum((z["rest"] for z in zeilen), 0),
        }

    context = {
        "aktiv": "dashboard",
        "jahr": jahr,
        "zeilen": zeilen,
        "summe": summe,
        "darf_alles": services.darf_alles(request.user),
        "betreuer_liste": Mitarbeiter.objects.filter(aktiv=True),
        "betreuer_id": betreuer_id,
        "kennzahlen": {
            "klienten": sichtbar.count(),
            "leistungen": Leistung.objects.filter(datum__year=jahr, klient__in=sichtbar).count(),
            "n_donnerstage": summe["n_donnerstage"],
        },
    }
    return render(request, "nachweis/dashboard.html", context)


# ---------------------------------------------------------------- Erfassung (Grid)
@ensure_csrf_cookie
@login_required
def erfassung(request):
    klienten = services.klienten_fuer(request.user).order_by("nachname", "vorname")
    context = {
        "aktiv": "erfassung",
        "jahr": _jahr(request),
        "klienten": klienten,
        "klienten_json": [{"id": k.id, "name": k.name} for k in klienten],
        "leistungsarten_json": [{"v": a.value, "l": a.label} for a in Leistungsart],
        "monate": [f"{m:02d}" for m in range(1, 13)],
    }
    return render(request, "nachweis/erfassung.html", context)


def _row(l: Leistung):
    return {
        "id": l.id,
        "datum": l.datum.isoformat(),
        "klient": l.klient_id,
        "klient_name": l.klient.name,
        "leistungsart": l.leistungsart,
        "taetigkeit": l.taetigkeit,
        "beginn": l.beginn.strftime("%H:%M") if l.beginn else "",
        "ende": l.ende.strftime("%H:%M") if l.ende else "",
        "dauer": float(l.dauer_stunden),
        "betreuer": str(l.betreuer),
    }


@login_required
def api_leistungen(request):
    jahr = _jahr(request)
    qs = Leistung.objects.filter(
        datum__year=jahr, klient__in=services.klienten_fuer(request.user)
    ).select_related("klient", "betreuer")
    if request.GET.get("monat"):
        qs = qs.filter(datum__month=int(request.GET["monat"]))
    if request.GET.get("klient"):
        qs = qs.filter(klient_id=request.GET["klient"])
    data = [_row(l) for l in qs.order_by("-datum", "beginn")]
    return JsonResponse({"data": data})


@require_POST
@login_required
def api_leistung_save(request):
    try:
        p = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return HttpResponse(status=400)

    sichtbar = services.klienten_fuer(request.user)
    klient = sichtbar.filter(pk=p.get("klient")).first()
    if not klient:
        return HttpResponseForbidden("Klient*in nicht wählbar.")
    if p.get("leistungsart") not in Leistungsart.values:
        return HttpResponse("Ungültige Leistungsart.", status=400)
    try:
        datum = date.fromisoformat(p["datum"])
    except (KeyError, ValueError):
        return HttpResponse("Datum fehlt/ungültig.", status=400)

    if p.get("id"):
        l = Leistung.objects.filter(pk=p["id"]).first()
        if not l or l.klient not in sichtbar:
            return HttpResponseForbidden()
    else:
        l = Leistung()

    l.datum = datum
    l.klient = klient
    l.leistungsart = p["leistungsart"]
    l.taetigkeit = (p.get("taetigkeit") or "").strip()
    l.beginn = _parse_time(p.get("beginn"))
    l.ende = _parse_time(p.get("ende"))
    l.notiz = (p.get("notiz") or "").strip()
    l.betreuer = services.mitarbeiter_fuer(request.user) or klient.bezugsbetreuer
    l.save()
    return JsonResponse(_row(l))


@require_POST
@login_required
def api_leistung_delete(request):
    try:
        p = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return HttpResponse(status=400)
    l = Leistung.objects.filter(pk=p.get("id")).first()
    if not l or l.klient not in services.klienten_fuer(request.user):
        return HttpResponseForbidden()
    l.delete()
    return JsonResponse({"ok": True})


# ---------------------------------------------------------------- Druck-Nachweis
@login_required
def druck(request):
    jahr = _jahr(request)
    monat = int(request.GET.get("monat") or date.today().month)
    sichtbar = services.klienten_fuer(request.user).order_by("nachname", "vorname")
    klient = None
    daten = None
    if request.GET.get("klient"):
        klient = get_object_or_404(sichtbar, pk=request.GET["klient"])
        daten = services.druck_nachweis(klient, jahr, monat)
    return render(request, "nachweis/druck.html", {
        "aktiv": "druck", "jahr": jahr, "monat": monat, "klient": klient, "daten": daten,
        "klienten": sichtbar, "monate": list(range(1, 13)),
    })


@login_required
def druck_pdf(request):
    jahr = _jahr(request)
    monat = int(request.GET.get("monat") or date.today().month)
    sichtbar = services.klienten_fuer(request.user)
    klient = get_object_or_404(sichtbar, pk=request.GET.get("klient"))
    daten = services.druck_nachweis(klient, jahr, monat)
    html = render_to_string("nachweis/druck_pdf.html", {"daten": daten, "klient": klient}, request)
    try:
        from weasyprint import HTML  # nur wenn native Libs vorhanden (Linux/Server)
    except Exception:
        # Prototyp/Windows ohne WeasyPrint: zurück zur Druckansicht (Browser: Strg+P)
        return redirect(f"{reverse('nachweis:druck')}?klient={klient.id}&monat={monat}&jahr={jahr}")
    pdf = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()
    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = (
        f'inline; filename="Leistungsnachweis_{klient.nachname}_{monat:02d}_{jahr}.pdf"')
    return resp

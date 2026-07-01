import json
from datetime import date, datetime
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden
from django.shortcuts import render, get_object_or_404, redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from . import services
from .models import Mitarbeiter, Leistung, Gruppe, Klient, Leistungsart


def _int(val, default):
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _jahr(request):
    return _int(request.GET.get("jahr"), date.today().year)


def _monat(request):
    return min(12, max(1, _int(request.GET.get("monat"), date.today().month)))


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
    gefiltert = sichtbar.filter(bezugsbetreuer_id=int(betreuer_id)) if betreuer_id.isdigit() else sichtbar

    zeilen, summe = services.fachleistungsstunden(jahr, klienten=gefiltert)
    zeitreihe = services.auslastung_zeitreihe(jahr, gefiltert)

    context = {
        "aktiv": "dashboard",
        "jahr": jahr,
        "zeilen": zeilen,
        "summe": summe,
        "zeitreihe_json": zeitreihe,
        "betreuer_liste": Mitarbeiter.objects.filter(aktiv=True),
        "betreuer_id": betreuer_id,
        "kennzahlen": {
            "klienten": gefiltert.count(),
            "leistungen": Leistung.objects.filter(datum__year=jahr, klient__in=gefiltert).count(),
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
    monat = _int(request.GET.get("monat"), 0)
    if 1 <= monat <= 12:
        qs = qs.filter(datum__month=monat)
    klient = _int(request.GET.get("klient"), 0)
    if klient:
        qs = qs.filter(klient_id=klient)
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
    monat = _monat(request)
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


# ---------------------------------------------------------------- Gruppennachweise (Stammdaten, für alle)
@login_required
def gruppen(request):
    return render(request, "nachweis/gruppen.html", {
        "aktiv": "gruppen",
        "gruppen": Gruppe.objects.prefetch_related("teilnehmer").order_by("-datum"),
        "klienten": Klient.objects.order_by("nachname", "vorname"),
        "leistungsarten": [{"v": a.value, "l": a.label} for a in Leistungsart],
    })


@require_POST
@login_required
def gruppe_save(request):
    thema = (request.POST.get("thema") or "").strip()
    try:
        datum = date.fromisoformat(request.POST.get("datum"))
    except (TypeError, ValueError):
        datum = None
    art = request.POST.get("leistungsart")
    if not (thema and datum and art in Leistungsart.values):
        messages.error(request, "Bitte Datum, Thema und Leistungsart angeben.")
        return redirect("nachweis:gruppen")

    g = Gruppe.objects.create(
        datum=datum, thema=thema, leistungsart=art,
        beginn=_parse_time(request.POST.get("beginn")),
        ende=_parse_time(request.POST.get("ende")),
        anz_ma=max(1, _int(request.POST.get("anz_ma"), 1)))
    ids = [i for i in request.POST.getlist("teilnehmer") if i.isdigit()]
    g.teilnehmer.set(Klient.objects.filter(pk__in=ids))
    messages.success(request, f"Gruppe {thema} gespeichert ({g.teilnehmer.count()} Teilnehmer*innen).")
    return redirect("nachweis:gruppen")


@require_POST
@login_required
def gruppe_delete(request):
    g = get_object_or_404(Gruppe, pk=request.POST.get("id"))
    g.delete()
    messages.success(request, "Gruppe gelöscht.")
    return redirect("nachweis:gruppen")


@login_required
def druck_pdf(request):
    jahr = _jahr(request)
    monat = _monat(request)
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

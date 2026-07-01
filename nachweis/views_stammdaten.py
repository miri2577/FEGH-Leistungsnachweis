"""Stammdaten der Leitung im App-Design: Belegungsliste (Klient*innen) + Team-Parameter.
Ersetzt die entsprechenden Django-Admin-Seiten. Alles auf die geleiteten Team(s) gescopt.
"""
from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import services
from .models import Klient, Mitarbeiter, Parameter, Status


def _nur_leitung(request):
    return services.ist_leitung(request.user)


def _dec(s):
    try:
        return Decimal((s or "0").replace(",", ".").strip() or "0")
    except (InvalidOperation, AttributeError):
        return Decimal("0")


def _datum(s):
    try:
        return date.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def _int_or_none(s):
    try:
        return int(s)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- Belegungsliste
@login_required
def belegungsliste(request):
    if not _nur_leitung(request):
        return HttpResponseForbidden()
    klienten = services.klienten_fuer(request.user).select_related("team", "bezugsbetreuer").order_by("nachname", "vorname")
    return render(request, "nachweis/belegungsliste.html", {
        "aktiv": "belegungsliste", "klienten": klienten,
    })


def _form_kontext(request, klient=None):
    teams = services.teams_fuer(request.user)
    return {
        "aktiv": "belegungsliste",
        "klient": klient,
        "teams": teams,
        "mitarbeiter": Mitarbeiter.objects.filter(aktiv=True, team__in=teams).order_by("name", "vorname"),
        "status_wahl": Status.choices,
    }


@login_required
def klient_form(request, pk=None):
    if not _nur_leitung(request):
        return HttpResponseForbidden()
    klient = None
    if pk:
        klient = get_object_or_404(services.klienten_fuer(request.user), pk=pk)
    return render(request, "nachweis/klient_form.html", _form_kontext(request, klient))


@require_POST
@login_required
def klient_speichern(request):
    if not _nur_leitung(request):
        return HttpResponseForbidden()
    teams = services.teams_fuer(request.user)
    pk = request.POST.get("id")
    if pk:
        k = get_object_or_404(services.klienten_fuer(request.user), pk=pk)
    else:
        k = Klient()

    nachname = (request.POST.get("nachname") or "").strip()
    team = teams.filter(pk=request.POST.get("team")).first()
    bez = Mitarbeiter.objects.filter(pk=request.POST.get("bezugsbetreuer"), team__in=teams).first()
    if not (nachname and team and bez):
        messages.error(request, "Bitte Nachname, Team und Bezugsbetreuer*in (aus dem Team) angeben.")
        return redirect(request.META.get("HTTP_REFERER", "nachweis:belegungsliste"))

    k.nachname = nachname
    k.vorname = (request.POST.get("vorname") or "").strip()
    k.geburtsdatum = _datum(request.POST.get("geburtsdatum"))
    k.team = team
    k.bezugsbetreuer = bez
    k.vertretung1 = Mitarbeiter.objects.filter(pk=request.POST.get("vertretung1")).first()
    k.vertretung2 = Mitarbeiter.objects.filter(pk=request.POST.get("vertretung2")).first()
    k.al = _dec(request.POST.get("al"))
    k.kle = _dec(request.POST.get("kle"))
    k.hbg = _int_or_none(request.POST.get("hbg"))
    k.kue_bis = _datum(request.POST.get("kue_bis"))
    k.brp_bis = _datum(request.POST.get("brp_bis"))
    k.versendet_am = _datum(request.POST.get("versendet_am"))
    status = request.POST.get("status")
    k.status = status if status in Status.values else Status.BETREUUNG
    k.person_id = (request.POST.get("person_id") or "").strip()
    k.thfd = (request.POST.get("thfd") or "").strip()
    k.kommentar = (request.POST.get("kommentar") or "").strip()
    k.save()
    messages.success(request, f"{k.name} gespeichert.")
    return redirect("nachweis:belegungsliste")


# ---------------------------------------------------------------- Team-Parameter
@login_required
def parameter(request):
    if not _nur_leitung(request):
        return HttpResponseForbidden()
    jahr = int(request.GET.get("jahr") or date.today().year)
    p = services.get_parameter(jahr)
    if request.method == "POST":
        p.teamsitzung_dauer_std = _dec(request.POST.get("teamsitzung_dauer_std"))
        p.teamsitzung_wochentag = _int_or_none(request.POST.get("teamsitzung_wochentag")) or 3
        p.fls_preis = _dec(request.POST.get("fls_preis"))
        p.save()
        messages.success(request, "Parameter gespeichert.")
        return redirect(f"{request.path}?jahr={jahr}")
    wochentage = [(0, "Montag"), (1, "Dienstag"), (2, "Mittwoch"), (3, "Donnerstag"),
                  (4, "Freitag")]
    ts_pro, n_do = services.teamsitzung_pro_klient(jahr)
    return render(request, "nachweis/parameter.html", {
        "aktiv": "parameter", "p": p, "jahr": jahr, "wochentage": wochentage,
        "n_donnerstage": n_do, "ts_pro_klient": ts_pro,
    })

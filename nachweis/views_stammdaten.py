"""Stammdaten der Leitung im App-Design: Belegungsliste (Klient*innen) + Team-Parameter.
Ersetzt die entsprechenden Django-Admin-Seiten. Alles auf die geleiteten Team(s) gescopt.
"""
from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from . import services
from .models import (Klient, Mitarbeiter, Parameter, Status, Team, Leistungsart,
                     WiederkehrendeLeistung, Rhythmus, Anrechnung)


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


def _ma(pk):
    """Mitarbeiter zum PK (oder None) – leere Auswahl robust behandeln."""
    return Mitarbeiter.objects.filter(pk=pk).first() if (pk or "").strip().isdigit() else None


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
    _tid = request.POST.get("team")
    team = teams.filter(pk=_tid).first() if (_tid or "").strip().isdigit() else None
    _bid = request.POST.get("bezugsbetreuer")
    bez = Mitarbeiter.objects.filter(pk=_bid, team__in=teams).first() if (_bid or "").strip().isdigit() else None
    if not (nachname and team and bez):
        messages.error(request, "Bitte Nachname, Team und Bezugsbetreuer*in (aus dem Team) angeben.")
        return redirect("nachweis:belegungsliste")

    k.nachname = nachname
    k.vorname = (request.POST.get("vorname") or "").strip()
    k.geburtsdatum = _datum(request.POST.get("geburtsdatum"))
    k.team = team
    k.bezugsbetreuer = bez
    k.vertretung1 = _ma(request.POST.get("vertretung1"))
    k.vertretung2 = _ma(request.POST.get("vertretung2"))
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
    k.kostentraeger = (request.POST.get("kostentraeger") or "").strip()
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
                  (4, "Freitag"), (5, "Samstag"), (6, "Sonntag")]
    ts_pro, n_do = services.teamsitzung_pro_klient(jahr)
    teams = services.teams_fuer(request.user)
    serien = list(WiederkehrendeLeistung.objects
                  .filter(Q(team__isnull=True) | Q(team__in=teams)).select_related("team"))
    edit_serie = next((s for s in serien if str(s.id) == request.GET.get("serie", "")), None)
    return render(request, "nachweis/parameter.html", {
        "aktiv": "parameter", "p": p, "jahr": jahr, "wochentage": wochentage,
        "n_donnerstage": n_do, "ts_pro_klient": ts_pro,
        "serien": serien, "edit_serie": edit_serie, "teams": teams,
        "rhythmus_choices": Rhythmus.choices, "anrechnung_choices": Anrechnung.choices,
        "leistungsart_choices": Leistungsart.choices,
        "wochen_optionen": [(0, "— (Wochen-Rhythmus)"), (1, "1."), (2, "2."),
                            (3, "3."), (4, "4."), (-1, "letzte")],
    })


def _meine_team_ids(request):
    return set(services.teams_fuer(request.user).values_list("id", flat=True))


@require_POST
@login_required
def serie_save(request):
    """Wiederkehrende Leistung anlegen/bearbeiten (Leitung, für eigene Teams oder global)."""
    if not _nur_leitung(request):
        return HttpResponseForbidden()
    jahr = request.POST.get("jahr") or date.today().year
    meine = _meine_team_ids(request)
    sid = request.POST.get("id")
    if sid:
        wl = get_object_or_404(WiederkehrendeLeistung, pk=sid)
        if wl.team_id and wl.team_id not in meine:
            return HttpResponseForbidden()
    else:
        wl = WiederkehrendeLeistung()
    team_id = _int_or_none(request.POST.get("team"))
    if team_id and team_id not in meine:
        return HttpResponseForbidden()
    wl.bezeichnung = (request.POST.get("bezeichnung") or "").strip() or "Termin"
    wl.leistungsart = request.POST.get("leistungsart") or Leistungsart.KLE
    wl.team_id = team_id
    wl.rhythmus = request.POST.get("rhythmus") or Rhythmus.WOECHENTLICH
    wl.wochentag = _int_or_none(request.POST.get("wochentag")) or 0
    wl.woche_im_monat = _int_or_none(request.POST.get("woche_im_monat")) or 0
    wl.tag_im_monat = _int_or_none(request.POST.get("tag_im_monat"))
    wl.monat_im_jahr = _int_or_none(request.POST.get("monat_im_jahr"))
    wl.dauer_std = _dec(request.POST.get("dauer_std"))
    wl.anrechnung = request.POST.get("anrechnung") or Anrechnung.TEILER
    wl.wert_pro_klient = _dec(request.POST.get("wert_pro_klient"))
    wl.feiertage_aussparen = bool(request.POST.get("feiertage_aussparen"))
    wl.im_kalender = bool(request.POST.get("im_kalender"))
    wl.gilt_ab = _datum(request.POST.get("gilt_ab"))
    wl.gilt_bis = _datum(request.POST.get("gilt_bis"))
    wl.aktiv = bool(request.POST.get("aktiv"))
    wl.save()
    messages.success(request, f"„{wl.bezeichnung}“ gespeichert.")
    return redirect(f"{reverse('nachweis:parameter')}?jahr={jahr}")


@require_POST
@login_required
def serie_delete(request):
    if not _nur_leitung(request):
        return HttpResponseForbidden()
    jahr = request.POST.get("jahr") or date.today().year
    wl = get_object_or_404(WiederkehrendeLeistung, pk=request.POST.get("id"))
    if wl.team_id and wl.team_id not in _meine_team_ids(request):
        return HttpResponseForbidden()
    name = wl.bezeichnung
    wl.delete()
    messages.success(request, f"„{name}“ gelöscht.")
    return redirect(f"{reverse('nachweis:parameter')}?jahr={jahr}")

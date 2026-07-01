import json
from datetime import date, datetime
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden
from django.shortcuts import render, get_object_or_404, redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from . import services
from .models import (Mitarbeiter, Team, Leistung, Gruppe, Klient, Leistungsart,
                     Arbeitszeit, Abwesenheit, AbwesenheitArt, AbwesenheitStatus,
                     Genehmigungsstatus)

MONATSNAMEN = ["", "Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
               "August", "September", "Oktober", "November", "Dezember"]


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


# ---------------------------------------------------------------- Mein Überblick (Startseite)
def _wochentage(feiertage_set):
    """Mo–Fr der aktuellen Woche als Tages-Kacheln (mit Heute- und Frei-Markierung)."""
    from datetime import timedelta as _td
    heute = date.today()
    montag = heute - _td(days=heute.weekday())
    wd = ["Mo", "Di", "Mi", "Do", "Fr"]
    tage = []
    for i in range(5):
        d = montag + _td(days=i)
        tage.append({"wd": wd[i], "tag": d.day, "heute": d == heute,
                     "frei": d in feiertage_set})
    return tage


@login_required
def mein_ueberblick(request):
    jahr = _jahr(request)
    monat = _monat(request)
    me = services.mitarbeiter_fuer(request.user)
    eigene = services.eigene_klienten(request.user)
    zeilen, summe = services.fachleistungsstunden(jahr, klienten=eigene)
    # Berichte: eigene zuerst, sonst alle im Team-Zugriff (Vertretung)
    berichte = services.berichte_faellig(eigene) or services.berichte_faellig(services.klienten_fuer(request.user))
    feier = services._feiertage_set(jahr)
    return render(request, "nachweis/mein_ueberblick.html", {
        "aktiv": "start",
        "jahr": jahr, "monat": monat, "monat_name": MONATSNAMEN[monat],
        "me": me,
        "eigene_zeilen": zeilen,
        "summe": summe,
        "az": services.arbeitszeit_monat(me, jahr, monat) if me else None,
        "urlaub": services.urlaub_uebersicht(me, jahr) if me else None,
        "berichte": berichte,
        "wochentage": _wochentage(feier),
        "ist_leitung": services.ist_leitung(request.user),
        "ist_verwaltung": bool(me and me.ist_verwaltung),
        "stempel": services.stempel_status(me) if (me and me.ist_verwaltung) else None,
        "offene_antraege": me.abwesenheiten.filter(status=AbwesenheitStatus.BEANTRAGT).count() if me else 0,
    })


@require_POST
@login_required
def versendet_setzen(request):
    """Mitarbeiter*in setzt das '…versendet am'-Datum für eine*n eigene*n/Team-Klient*in.
    Die Leitung sieht es anschließend in der Belegungsliste."""
    k = services.klienten_fuer(request.user).filter(pk=request.POST.get("klient")).first()
    if not k:
        return HttpResponseForbidden()
    d = (request.POST.get("datum") or "").strip()
    try:
        k.versendet_am = date.fromisoformat(d) if d else None
    except ValueError:
        return HttpResponse("Ungültiges Datum.", status=400)
    k.save(update_fields=["versendet_am"])
    messages.success(request, f"„…versendet am“ für {k.name} gespeichert.")
    return redirect("nachweis:start")


@require_POST
@login_required
def stempeln(request):
    me = services.mitarbeiter_fuer(request.user)
    if not (me and me.ist_verwaltung):
        # Stempeluhr nur für Verwaltung (fester Arbeitsplatz)
        return HttpResponseForbidden()
    try:
        aktion = services.stempeln(me)
    except IntegrityError:
        messages.info(request, "Du bist bereits eingestempelt.")
        return redirect("nachweis:start")
    messages.success(request, "Eingestempelt. Guten Start!" if aktion == "kommen"
                     else "Ausgestempelt. Feierabend!")
    return redirect("nachweis:start")


# ---------------------------------------------------------------- Fachleistungsstunden (Leitungs-Übersicht)
@login_required
def dashboard(request):
    # Nur Leitung/Superuser: differenzierte Auslastung aller Klient*innen mit Filter.
    if not services.ist_leitung(request.user):
        messages.info(request, "Die Team-Auswertung ist der Leitung vorbehalten.")
        return redirect("nachweis:start")

    jahr = _jahr(request)
    betreuer_id = request.GET.get("betreuer") or ""
    team_id = request.GET.get("team") or ""
    sichtbar = services.klienten_fuer(request.user)
    teams = services.teams_fuer(request.user)

    gefiltert = sichtbar
    if team_id.isdigit():
        gefiltert = gefiltert.filter(team_id=int(team_id))
    if betreuer_id.isdigit():
        gefiltert = gefiltert.filter(bezugsbetreuer_id=int(betreuer_id))

    zeilen, summe = services.fachleistungsstunden(jahr, klienten=gefiltert)
    zeitreihe = services.auslastung_zeitreihe(jahr, gefiltert)

    context = {
        "aktiv": "dashboard",
        "jahr": jahr,
        "zeilen": zeilen,
        "summe": summe,
        "zeitreihe_json": zeitreihe,
        "team_liste": teams,
        "team_id": team_id,
        "betreuer_liste": Mitarbeiter.objects.filter(aktiv=True, team__in=teams).distinct(),
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
    if services.ohne_klientenarbeit(request.user):
        return redirect("nachweis:start")
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
    if services.ohne_klientenarbeit(request.user):
        return redirect("nachweis:start")
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


# ---------------------------------------------------------------- Gruppennachweise (team-gescopt)
@login_required
def gruppen(request):
    # Admin (kein Klientenzugriff) und Verwaltung (keine Klientenarbeit) ausgeschlossen.
    if services.ohne_klientenarbeit(request.user):
        return redirect("nachweis:start")
    sichtbar = services.klienten_fuer(request.user)
    # Nur Gruppen mit mind. einer/einem sichtbaren Teilnehmer*in (Team-Scoping).
    gruppen_qs = (Gruppe.objects.filter(teilnehmer__in=sichtbar).distinct()
                  .prefetch_related("teilnehmer").order_by("-datum"))
    return render(request, "nachweis/gruppen.html", {
        "aktiv": "gruppen",
        "gruppen": gruppen_qs,
        "klienten": sichtbar.order_by("nachname", "vorname"),
        "leistungsarten": [{"v": a.value, "l": a.label} for a in Leistungsart],
    })


@require_POST
@login_required
def gruppe_save(request):
    if services.ohne_klientenarbeit(request.user):
        return HttpResponseForbidden()
    sichtbar = services.klienten_fuer(request.user)
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
    # nur sichtbare (eigene Team-)Klient*innen zuweisbar
    g.teilnehmer.set(sichtbar.filter(pk__in=ids))
    messages.success(request, f"Gruppe {thema} gespeichert ({g.teilnehmer.count()} Teilnehmer*innen).")
    return redirect("nachweis:gruppen")


@require_POST
@login_required
def gruppe_delete(request):
    sichtbar = services.klienten_fuer(request.user)
    # nur Gruppen löschbar, die auch sichtbar sind (mind. ein*e sichtbare*r Teilnehmer*in)
    g = get_object_or_404(
        Gruppe.objects.filter(teilnehmer__in=sichtbar).distinct(), pk=request.POST.get("id"))
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


# ---------------------------------------------------------------- Druck-Center (Sammelseite, unten in der Sidebar)
def _druck_mitarbeiter(request):
    """Für den Druck auswählbare Mitarbeiter*innen: Leitung → ganzes Team, sonst nur selbst."""
    me = services.mitarbeiter_fuer(request.user)
    if services.ist_leitung(request.user):
        return Mitarbeiter.objects.filter(
            aktiv=True, team__in=services.teams_fuer(request.user)).order_by("name", "vorname")
    if me:
        return Mitarbeiter.objects.filter(pk=me.pk)
    return Mitarbeiter.objects.none()


@login_required
def druck_center(request):
    """Sammelseite: bündelt alle druckbaren Nachweise (Klient · Arbeitszeit · Kasse · Gruppe)."""
    me = services.mitarbeiter_fuer(request.user)
    ohne_klienten = services.ohne_klientenarbeit(request.user)
    sichtbar = services.klienten_fuer(request.user)
    gruppen_qs = (Gruppe.objects.filter(teilnehmer__in=sichtbar).distinct()
                  .order_by("-datum")[:60] if not ohne_klienten else Gruppe.objects.none())
    kassen = services.kassen_fuer(request.user)
    # Kassen-Karte auf den zuletzt abgeschlossenen Monat vorbelegen (statt aktueller Monat).
    if kassen.exists():
        kasse_jahr, kasse_monat = services.letzter_kassenabschluss(kassen.first())
    else:
        kasse_jahr, kasse_monat = _jahr(request), _monat(request)
    return render(request, "nachweis/druck_center.html", {
        "aktiv": "druck",
        "jahr": _jahr(request), "monat": _monat(request),
        "kasse_jahr": kasse_jahr, "kasse_monat": kasse_monat,
        "monate": [(m, MONATSNAMEN[m]) for m in range(1, 13)],
        "jahre": range(date.today().year, date.today().year - 3, -1),
        "ohne_klienten": ohne_klienten,
        "klienten": sichtbar.order_by("nachname", "vorname"),
        "mitarbeiter": _druck_mitarbeiter(request),
        "kassen": kassen,
        "gruppen": gruppen_qs,
        "me": me,
    })


@login_required
def arbeitszeit_druck(request):
    """Monats-Arbeitszeitnachweis (druckbar). Leitung darf ?mitarbeiter= des eigenen Teams drucken."""
    ziel = services.mitarbeiter_fuer(request.user)
    mid = request.GET.get("mitarbeiter")
    if mid and services.ist_leitung(request.user):
        cand = Mitarbeiter.objects.filter(
            pk=mid, team__in=services.teams_fuer(request.user)).first()
        if cand:
            ziel = cand
    if not ziel:
        return HttpResponseForbidden()
    jahr, monat = _jahr(request), _monat(request)
    eintraege = list(ziel.arbeitszeiten.filter(datum__year=jahr, datum__month=monat)
                     .order_by("datum", "beginn"))
    return render(request, "nachweis/arbeitszeit_druck.html", {
        "ziel": ziel, "jahr": jahr, "monat": monat, "monat_name": MONATSNAMEN[monat],
        "eintraege": eintraege, "az": services.arbeitszeit_monat(ziel, jahr, monat),
    })


@login_required
def gruppe_druck(request, pk):
    """Einzelner Gruppennachweis (druckbar) – nur bei sichtbaren Teilnehmer*innen (Team-Scoping)."""
    if services.ohne_klientenarbeit(request.user):
        return HttpResponseForbidden()
    sichtbar = services.klienten_fuer(request.user)
    g = get_object_or_404(
        Gruppe.objects.filter(teilnehmer__in=sichtbar).distinct().prefetch_related("teilnehmer"),
        pk=pk)
    return render(request, "nachweis/gruppe_druck.html", {
        "g": g, "teilnehmer": g.teilnehmer.order_by("nachname", "vorname"),
    })


# ---------------------------------------------------------------- Arbeitszeiterfassung (Selfservice)
@ensure_csrf_cookie
@login_required
def arbeitszeit(request):
    me = services.mitarbeiter_fuer(request.user)
    jahr = _jahr(request); monat = _monat(request)
    return render(request, "nachweis/arbeitszeit.html", {
        "aktiv": "arbeitszeit", "jahr": jahr, "monat": monat, "monat_name": MONATSNAMEN[monat],
        "me": me,
        "az": services.arbeitszeit_monat(me, jahr, monat) if me else None,
        "monate": [f"{m:02d}" for m in range(1, 13)],
    })


def _az_row(a):
    return {
        "id": a.id, "datum": a.datum.isoformat(),
        "beginn": a.beginn.strftime("%H:%M") if a.beginn else "",
        "ende": a.ende.strftime("%H:%M") if a.ende else "",
        "pause_min": a.pause_min, "dauer": float(a.dauer_stunden), "notiz": a.notiz,
        "status": a.status, "status_label": a.get_status_display(),
    }


@login_required
def api_arbeitszeit(request):
    me = services.mitarbeiter_fuer(request.user)
    if not me:
        return JsonResponse({"data": []})
    qs = me.arbeitszeiten.filter(datum__year=_jahr(request))
    monat = _int(request.GET.get("monat"), 0)
    if 1 <= monat <= 12:
        qs = qs.filter(datum__month=monat)
    return JsonResponse({"data": [_az_row(a) for a in qs.order_by("-datum", "beginn")]})


@require_POST
@login_required
def api_arbeitszeit_save(request):
    me = services.mitarbeiter_fuer(request.user)
    if not me:
        return HttpResponseForbidden("Kein Mitarbeiterprofil.")
    try:
        p = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return HttpResponse(status=400)
    try:
        datum = date.fromisoformat(p["datum"])
    except (KeyError, ValueError):
        return HttpResponse("Datum fehlt/ungueltig.", status=400)
    if p.get("id"):
        a = Arbeitszeit.objects.filter(pk=p["id"], mitarbeiter=me).first()
        if not a:
            return HttpResponseForbidden()
    else:
        a = Arbeitszeit(mitarbeiter=me)
    a.datum = datum
    a.beginn = _parse_time(p.get("beginn"))
    a.ende = _parse_time(p.get("ende"))
    a.pause_min = max(0, _int(p.get("pause_min"), 0))
    a.notiz = (p.get("notiz") or "").strip()
    # jede Eingabe/Änderung geht (erneut) zur Genehmigung an die Leitung
    a.status = Genehmigungsstatus.BEANTRAGT
    a.save()
    return JsonResponse(_az_row(a))


@require_POST
@login_required
def api_arbeitszeit_delete(request):
    me = services.mitarbeiter_fuer(request.user)
    try:
        p = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return HttpResponse(status=400)
    a = Arbeitszeit.objects.filter(pk=p.get("id"), mitarbeiter=me).first()
    if not a:
        return HttpResponseForbidden()
    a.delete()
    return JsonResponse({"ok": True})


# ---------------------------------------------------------------- Arbeitszeit-Freigaben (Leitung)
@login_required
def arbeitszeit_freigaben(request):
    if not services.ist_leitung(request.user):
        return HttpResponseForbidden()
    teams = services.teams_fuer(request.user)
    offen = (Arbeitszeit.objects.filter(status=Genehmigungsstatus.BEANTRAGT,
                                        mitarbeiter__team__in=teams)
             .select_related("mitarbeiter").order_by("mitarbeiter__name", "-datum", "beginn"))
    # nach Mitarbeiter*in gruppieren
    gruppen = {}
    for a in offen:
        gruppen.setdefault(a.mitarbeiter, []).append(a)
    gruppiert = [{"ma": ma, "eintraege": eintr, "summe": sum((x.dauer_stunden for x in eintr), 0)}
                 for ma, eintr in gruppen.items()]
    return render(request, "nachweis/arbeitszeit_freigaben.html", {
        "aktiv": "az_freigaben", "gruppiert": gruppiert, "anzahl": offen.count(),
    })


@require_POST
@login_required
def arbeitszeit_status(request):
    if not services.ist_leitung(request.user):
        return HttpResponseForbidden()
    teams = services.teams_fuer(request.user)
    scope = Arbeitszeit.objects.filter(mitarbeiter__team__in=teams)
    aktion = request.POST.get("aktion")
    if aktion in ("alle_genehmigen", "alle_ablehnen"):
        ma_id = request.POST.get("mitarbeiter")
        neu = Genehmigungsstatus.GENEHMIGT if aktion == "alle_genehmigen" else Genehmigungsstatus.ABGELEHNT
        n = scope.filter(mitarbeiter_id=ma_id, status=Genehmigungsstatus.BEANTRAGT).update(status=neu)
        messages.success(request, f"{n} Arbeitszeit-Einträge {neu}.")
    else:
        a = get_object_or_404(scope, pk=request.POST.get("id"))
        st = request.POST.get("status")
        if st in Genehmigungsstatus.values:
            a.status = st
            a.save(update_fields=["status"])
            messages.success(request, f"Eintrag {a.get_status_display()}.")
    return redirect("nachweis:arbeitszeit_freigaben")


# ---------------------------------------------------------------- Abwesenheiten (Urlaub / Freizeitausgleich)
@login_required
def abwesenheit(request):
    me = services.mitarbeiter_fuer(request.user)
    jahr = _jahr(request)
    alle_offen = None
    if services.ist_leitung(request.user):
        # nur Anträge von Mitarbeiter*innen der geleiteten Team(s)
        alle_offen = Abwesenheit.objects.filter(
            status=AbwesenheitStatus.BEANTRAGT,
            mitarbeiter__team__in=services.teams_fuer(request.user)).select_related("mitarbeiter")
    return render(request, "nachweis/abwesenheit.html", {
        "aktiv": "abwesenheit", "jahr": jahr, "me": me,
        "meine": list(me.abwesenheiten.all()) if me else [],
        "alle_offen": alle_offen,
        "arten": AbwesenheitArt.choices,
        "urlaub": services.urlaub_uebersicht(me, jahr) if me else None,
        "ist_leitung": services.ist_leitung(request.user),
    })


@require_POST
@login_required
def abwesenheit_save(request):
    me = services.mitarbeiter_fuer(request.user)
    if not me:
        messages.error(request, "Kein Mitarbeiterprofil hinterlegt.")
        return redirect("nachweis:abwesenheit")
    try:
        von = date.fromisoformat(request.POST.get("von"))
        bis = date.fromisoformat(request.POST.get("bis"))
    except (TypeError, ValueError):
        messages.error(request, "Bitte gueltige Daten (von/bis) angeben.")
        return redirect("nachweis:abwesenheit")
    if bis < von:
        messages.error(request, "Das End-Datum liegt vor dem Start-Datum.")
        return redirect("nachweis:abwesenheit")
    art = request.POST.get("art")
    Abwesenheit.objects.create(
        mitarbeiter=me, von=von, bis=bis,
        art=art if art in AbwesenheitArt.values else AbwesenheitArt.SONSTIGE,
        kommentar=(request.POST.get("kommentar") or "").strip())
    messages.success(request, "Antrag eingereicht.")
    return redirect("nachweis:abwesenheit")


@require_POST
@login_required
def abwesenheit_status(request):
    if not services.ist_leitung(request.user):
        return HttpResponseForbidden()
    # nur Anträge aus den geleiteten Team(s) genehmigen/ablehnen
    a = get_object_or_404(
        Abwesenheit.objects.filter(mitarbeiter__team__in=services.teams_fuer(request.user)),
        pk=request.POST.get("id"))
    st = request.POST.get("status")
    if st in AbwesenheitStatus.values:
        a.status = st
        a.save()
        messages.success(request, f"Antrag {a.get_status_display()}.")
    return redirect("nachweis:abwesenheit")

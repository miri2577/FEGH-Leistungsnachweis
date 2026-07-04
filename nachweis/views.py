import json
from datetime import date, datetime, timedelta
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
                     Genehmigungsstatus, Termin)

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
    # Wochensicht (laufende KW): verbrauchtes Wochenkontingent + FL/KLE-Verteilung
    woche = services.wochenauslastung(eigene, jahr)
    for z in zeilen:
        z["woche"] = woche["zeilen"].get(z["klient"].id)
    # Berichte: eigene zuerst, sonst alle im Team-Zugriff (Vertretung)
    berichte = services.berichte_faellig(eigene) or services.berichte_faellig(services.klienten_fuer(request.user))
    feier = services._feiertage_set(jahr)
    return render(request, "nachweis/mein_ueberblick.html", {
        "aktiv": "start",
        "jahr": jahr, "monat": monat, "monat_name": MONATSNAMEN[monat],
        "me": me,
        "eigene_zeilen": zeilen,
        "summe": summe,
        "woche_total": woche["total"], "kw": woche["kw"],
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
    woche = services.wochenauslastung(gefiltert, jahr)
    for z in zeilen:
        z["woche"] = woche["zeilen"].get(z["klient"].id)

    context = {
        "aktiv": "dashboard",
        "jahr": jahr,
        "zeilen": zeilen,
        "summe": summe,
        "woche_total": woche["total"], "kw": woche["kw"],
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


def _volltext_q(felder, q):
    """Multi-Wort-Volltext, DB-unabhängig (SQLite/PostgreSQL): jedes Token muss in
    mindestens einem der Felder vorkommen (AND über Tokens, OR über Felder)."""
    from django.db.models import Q
    ausdruck = Q()
    for token in q.split():
        oder = Q()
        for f in felder:
            oder |= Q(**{f"{f}__icontains": token})
        ausdruck &= oder
    return ausdruck


def _suche_kategorien(request, q, limit=7):
    """Rollen-gescopte Trefferliste (dieselben Zugriffsgrenzen wie überall, DSGVO).
    Rückgabe: Liste von {key, label, items:[{titel, sub, url}]}."""
    user = request.user
    kats = []

    def add(key, label, items):
        items = [i for i in items if i]
        if items:
            kats.append({"key": key, "label": label, "items": items})

    # Klient*innen / Leistungen / Gruppen – nur mit Klientenarbeit (Admin/Verwaltung sehen nichts)
    if not services.ohne_klientenarbeit(user):
        kl = services.klienten_fuer(user)
        leitung = services.ist_leitung(user)
        klq = kl.filter(_volltext_q(["nachname", "vorname", "person_id", "thfd", "kommentar"], q)) \
                .select_related("team", "bezugsbetreuer")[:limit]
        add("klienten", "Klient*innen", [{
            "titel": k.name,
            "sub": " · ".join(filter(None, [k.team.name if k.team else "", str(k.bezugsbetreuer) if k.bezugsbetreuer_id else ""])),
            "url": reverse("nachweis:klient_bearbeiten", args=[k.id]) if leitung
                   else f"{reverse('nachweis:druck')}?klient={k.id}",
        } for k in klq])

        lq = (Leistung.objects.filter(klient__in=kl)
              .filter(_volltext_q(["taetigkeit", "notiz", "klient__nachname", "klient__vorname"], q))
              .select_related("klient").order_by("-datum")[:limit])
        add("leistungen", "Leistungen", [{
            "titel": l.taetigkeit or l.get_leistungsart_display(),
            "sub": f"{l.datum:%d.%m.%Y} · {l.klient.name} · {l.leistungsart}",
            "url": f"{reverse('nachweis:druck')}?klient={l.klient_id}&monat={l.datum.month}&jahr={l.datum.year}",
        } for l in lq])

        gq = (Gruppe.objects.filter(teilnehmer__in=kl)
              .filter(_volltext_q(["thema", "teilnehmer__nachname", "teilnehmer__vorname"], q))
              .distinct().order_by("-datum")[:limit])
        add("gruppen", "Gruppen", [{
            "titel": g.thema, "sub": f"{g.datum:%d.%m.%Y} · {g.get_leistungsart_display()}",
            "url": reverse("nachweis:gruppe_druck", args=[g.id]),
        } for g in gq])

    # Kolleg*innen – team-gescopt (kein org-weites Personenverzeichnis für normale User);
    # Admin/Superuser (Personalverwaltung) sehen alle.
    if services.ist_admin(user) or user.is_superuser:
        ma_basis = Mitarbeiter.objects.all()
    else:
        ma_basis = Mitarbeiter.objects.filter(team__in=services.teams_fuer(user))
    mq = ma_basis.filter(_volltext_q(["name", "vorname", "kuerzel"], q)) \
                 .select_related("team").order_by("name")[:limit]

    def m_url(m):
        if services.ist_admin(user) or user.is_superuser:
            return reverse("nachweis:mitarbeiter_liste")
        if services.ist_leitung(user):
            return f"{reverse('nachweis:dashboard')}?betreuer={m.id}"
        return ""
    add("mitarbeiter", "Kolleg*innen", [{
        "titel": f"{m.vorname} {m.name}".strip(),
        "sub": " · ".join(filter(None, [m.get_rolle_display(), m.team.name if m.team else ""])),
        "url": m_url(m),
    } for m in mq])

    # Teams – ebenfalls team-gescopt; Admin/Superuser sehen alle.
    if services.ist_admin(user) or user.is_superuser:
        team_basis = Team.objects.all()
    else:
        team_basis = services.teams_fuer(user)
    tq = team_basis.filter(_volltext_q(["name"], q)).order_by("name")[:limit]

    def t_url(t):
        if services.ist_admin(user) or user.is_superuser:
            return reverse("nachweis:teams_liste")
        if services.ist_leitung(user):
            return f"{reverse('nachweis:dashboard')}?team={t.id}"
        return ""
    add("teams", "Teams", [{"titel": t.name, "sub": t.get_typ_display(), "url": t_url(t)} for t in tq])

    # Kasse (Buchungen) – nur mit Kassenzugriff
    kassen = services.kassen_fuer(user)
    if kassen.exists():
        from .models import Kassenbuchung
        bq = (Kassenbuchung.objects.filter(monat__kasse__in=kassen)
              .filter(_volltext_q(["text", "kontonr", "kostenstelle"], q))
              .select_related("monat", "monat__kasse").order_by("-datum")[:limit])
        add("kasse", "Kasse", [{
            "titel": f"Beleg {b.bel_nr}: {b.text}",
            "sub": f"{b.datum:%d.%m.%Y} · {b.monat.kasse.bezeichnung} · {(b.einnahme or 0) - (b.ausgabe or 0):+.2f} €",
            "url": f"{reverse('nachweis:kasse')}?kasse={b.monat.kasse_id}&jahr={b.monat.jahr}&monat={b.monat.monat}",
        } for b in bq])

    return kats


@login_required
def api_ping(request):
    """Leichter Keepalive: hält die Session bei echter Interaktion frisch (der Idle-Timer
    im Client ruft ihn gedrosselt auf). Jede Anfrage wertet die Middleware als Aktivität."""
    return HttpResponse(status=204)


@login_required
def api_suche(request):
    """Globale, rollen-gescopte Suche für das Spotlight-Overlay (Live-JSON)."""
    q = (request.GET.get("q") or "").strip()
    kategorien = _suche_kategorien(request, q) if len(q) >= 2 else []
    total = sum(len(k["items"]) for k in kategorien)
    return JsonResponse({"q": q, "total": total, "kategorien": kategorien})


@login_required
def api_wochen_fls(request):
    """FL/KLE-Wochensicht (laufende KW) für die Zusammenfassungsleiste im Erfassungs-Grid.
    Optional per ?klient= gefiltert; sonst alle sichtbaren Klient*innen."""
    jahr = _jahr(request)
    kl = services.klienten_fuer(request.user)
    kid = _int(request.GET.get("klient"), 0)
    if kid:
        kl = kl.filter(pk=kid)
    w = services.wochenauslastung(kl, jahr)
    t = w["total"]

    def f(x):
        return round(float(x), 2)
    klienten = [{
        "name": z["klient"].name,
        "soll": f(z["soll"]), "ist": f(z["ist"]),
        "al": f(z["al"]), "soll_al": f(z["soll_al"]),
        "kle": f(z["kle"]), "soll_kle": f(z["soll_kle"]),
    } for z in sorted(w["zeilen"].values(), key=lambda z: z["klient"].name)]
    return JsonResponse({
        "kw": w["kw"],
        "soll": f(t["soll"]), "ist": f(t["ist"]),
        "al": f(t["al"]), "soll_al": f(t["soll_al"]),
        "kle": f(t["kle"]), "soll_kle": f(t["soll_kle"]),
        "klienten": klienten,
    })


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


# ---------------------------------------------------------------- Wochenkalender (Team-Matrix, Mo–So)
def _kalender_kontext(request):
    """Gemeinsame Daten für Kalender-Ansicht und -Druck: Woche (Mo–So), Team-Filter,
    Matrix Mitarbeiter*in × Tag, Legende (Klient*innen mit Farbe/Kürzel)."""
    from collections import defaultdict
    me = services.mitarbeiter_fuer(request.user)
    teams = services.teams_fuer(request.user)
    jahr = _jahr(request)
    kw = min(53, max(1, _int(request.GET.get("kw"), 0) or services.aktuelle_kw(jahr)))
    mo, so = services.iso_wochenbereich(jahr, kw)

    team_id = request.GET.get("team") or ""
    team_qs = teams.filter(id=int(team_id)) if team_id.isdigit() else teams
    _namen = list(team_qs.values_list("name", flat=True))
    team_name = _namen[0] if len(_namen) == 1 else "Alle Teams"
    mitarbeiter = Mitarbeiter.objects.filter(aktiv=True, team__in=team_qs).order_by("name", "vorname")

    termine = (Termin.objects.filter(mitarbeiter__in=mitarbeiter, datum__range=(mo, so))
               .select_related("klient", "mitarbeiter"))
    matrix = defaultdict(lambda: defaultdict(list))
    klienten_used = {}
    for t in termine:
        matrix[t.mitarbeiter_id][(t.datum - mo).days].append(t)
        if t.klient_id:
            klienten_used[t.klient_id] = t.klient

    wd = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
    tage = [{"datum": mo + timedelta(days=i), "wd": wd[i], "we": i >= 5} for i in range(7)]
    rows = []
    for m in mitarbeiter:
        zellen = [{"datum": tage[i]["datum"], "we": tage[i]["we"],
                   "termine": matrix[m.id].get(i, [])} for i in range(7)]
        rows.append({"m": m, "ich": bool(me and m.id == me.id), "zellen": zellen})
    legende = sorted(klienten_used.values(), key=lambda k: k.nachname.lower())

    n_weeks = date(jahr, 12, 28).isocalendar()[1]
    prev = (jahr, kw - 1) if kw > 1 else (jahr - 1, date(jahr - 1, 12, 28).isocalendar()[1])
    nxt = (jahr, kw + 1) if kw < n_weeks else (jahr + 1, 1)

    return {
        "me": me, "jahr": jahr, "kw": kw, "mo": mo, "so": so,
        "tage": tage, "rows": rows, "legende": legende,
        "teams": teams, "team_id": team_id, "team_name": team_name,
        "prev_jahr": prev[0], "prev_kw": prev[1], "next_jahr": nxt[0], "next_kw": nxt[1],
    }


@login_required
def kalender(request):
    if services.ohne_klientenarbeit(request.user):
        return redirect("nachweis:start")
    ctx = _kalender_kontext(request)
    ctx["aktiv"] = "kalender"
    me = ctx["me"]
    ctx["bearbeiten"] = (Termin.objects.filter(pk=request.GET.get("edit"), mitarbeiter=me).first()
                         if (request.GET.get("edit") and me) else None)
    ctx["tag_prefill"] = request.GET.get("tag") or ""
    ctx["klienten"] = services.klienten_fuer(request.user).order_by("nachname", "vorname")
    return render(request, "nachweis/kalender.html", ctx)


@require_POST
@login_required
def termin_save(request):
    me = services.mitarbeiter_fuer(request.user)
    if not me or services.ohne_klientenarbeit(request.user):
        return HttpResponseForbidden()
    jahr = _int(request.POST.get("jahr"), date.today().year)
    kw = _int(request.POST.get("kw"), 1)
    ziel = f"{reverse('nachweis:kalender')}?jahr={jahr}&kw={kw}"

    pk = request.POST.get("id")
    t = get_object_or_404(Termin, pk=pk, mitarbeiter=me) if pk else Termin(mitarbeiter=me)
    try:
        t.datum = date.fromisoformat(request.POST.get("datum"))
    except (TypeError, ValueError):
        messages.error(request, "Bitte ein gültiges Datum angeben.")
        return redirect(ziel)
    t.beginn = _parse_time(request.POST.get("beginn"))
    if not t.beginn:
        messages.error(request, "Bitte eine Beginn-Uhrzeit angeben.")
        return redirect(ziel)
    t.ende = _parse_time(request.POST.get("ende"))
    kid = request.POST.get("klient") or ""
    t.klient = services.klienten_fuer(request.user).filter(pk=kid).first() if kid.isdigit() else None
    t.titel = (request.POST.get("titel") or "").strip()
    t.ort = (request.POST.get("ort") or "").strip()
    t.notiz = (request.POST.get("notiz") or "").strip()
    if not t.klient and not t.titel:
        messages.error(request, "Bitte eine*n Klient*in wählen oder einen Titel angeben.")
        return redirect(ziel)
    t.save()
    messages.success(request, "Termin gespeichert.")
    return redirect(ziel)


@require_POST
@login_required
def termin_delete(request):
    me = services.mitarbeiter_fuer(request.user)
    jahr = _int(request.POST.get("jahr"), date.today().year)
    kw = _int(request.POST.get("kw"), 1)
    if me:
        t = Termin.objects.filter(pk=request.POST.get("id"), mitarbeiter=me).first()
        if t:
            t.delete()
            messages.success(request, "Termin gelöscht.")
    return redirect(f"{reverse('nachweis:kalender')}?jahr={jahr}&kw={kw}")


@login_required
def kalender_druck(request):
    if services.ohne_klientenarbeit(request.user):
        return redirect("nachweis:start")
    return render(request, "nachweis/kalender_druck.html", _kalender_kontext(request))


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

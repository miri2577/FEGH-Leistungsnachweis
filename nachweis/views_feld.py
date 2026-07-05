"""Unterwegs-Modus (mobile PWA): Vor-Ort-Dokumentation je Klientenbesuch.

Manuelle Von-bis-Erfassung, meist im Anschluss an den Termin. Aus den heutigen
Terminen lässt sich Klient*in + geplante Zeit vorausfüllen (der Termin trägt sie
bereits). Erzeugt direkt eine Leistung, die sofort im Leistungsnachweis erscheint.
Keine Klientendaten werden auf dem Gerät gespeichert (reiner Online-Modus).
"""
from datetime import date, datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import services
from .models import Leistung, Termin, Leistungsart


def _time(s):
    try:
        return datetime.strptime((s or "").strip(), "%H:%M").time()
    except ValueError:
        return None


def _date(s):
    try:
        return date.fromisoformat((s or "").strip())
    except (TypeError, ValueError):
        return None


def _int(s, default=0):
    try:
        return int(s)
    except (TypeError, ValueError):
        return default


@login_required
def feld_heute(request):
    if services.ohne_klientenarbeit(request.user):
        return redirect("nachweis:start")
    me = services.mitarbeiter_fuer(request.user)
    if not me:
        return redirect("nachweis:start")
    heute = timezone.localdate()
    termine = list(Termin.objects.filter(mitarbeiter=me, datum=heute, klient__isnull=False)
                   .select_related("klient").order_by("beginn"))
    for t in termine:                       # schon dokumentiert? (verknüpfte Leistung)
        t.dok = t.dokumentationen.exists()
    # Nachzuholen: vergangene, noch nicht dokumentierte Klienten-Termine.
    nachhol = [t for t in services.undokumentierte_termine(me) if t.datum < heute]
    erfasst = (Leistung.objects.filter(betreuer=me, datum=heute).exclude(auto=True)
               .select_related("klient").order_by("-beginn", "-id"))
    klienten = services.klienten_fuer(request.user).order_by("nachname", "vorname")
    return render(request, "nachweis/feld.html", {
        "aktiv": "feld", "heute": heute, "termine": termine, "nachhol": nachhol,
        "erfasst": erfasst, "klienten": klienten,
        "arten": [{"v": a.value, "l": a.label} for a in Leistungsart],
    })


@require_POST
@login_required
def feld_speichern(request):
    if services.ohne_klientenarbeit(request.user):
        return HttpResponseForbidden()
    me = services.mitarbeiter_fuer(request.user)
    if not me:
        return HttpResponseForbidden()
    # nur eigene/geleitete Team-Klient*innen zuweisbar. pk-Guard: leerer String
    # wuerde auf PostgreSQL einen Integer-Cast-Fehler ausloesen (SQLite schluckt ihn).
    kid = request.POST.get("klient")
    klient = (services.klienten_fuer(request.user).filter(pk=kid).first()
              if kid and kid.isdigit() else None)
    datum = _date(request.POST.get("datum")) or timezone.localdate()
    beginn = _time(request.POST.get("beginn"))
    ende = _time(request.POST.get("ende"))
    art = request.POST.get("leistungsart")
    art = art if art in Leistungsart.values else Leistungsart.FS
    if not (klient and beginn and ende):
        messages.error(request, "Bitte Klient*in, Von- und Bis-Zeit angeben.")
        return redirect("nachweis:feld_heute")
    # Bezug zum Kalender-Termin (falls aus einem Termin heraus dokumentiert) –
    # nur eigener Termin desselben/derselben Klient*in; markiert ihn als dokumentiert.
    tid = request.POST.get("termin")
    termin = (Termin.objects.filter(pk=tid, mitarbeiter=me, klient=klient).first()
              if tid and tid.isdigit() else None)
    # 1) Der Besuch selbst (Standard FS), mit der Verlaufs-Doku.
    leistung = Leistung.objects.create(
        datum=datum, klient=klient, leistungsart=art, betreuer=me,
        beginn=beginn, ende=ende, termin=termin,
        taetigkeit=(request.POST.get("taetigkeit") or "").strip()[:120],
        dokumentation=(request.POST.get("dokumentation") or "").strip())
    # 2) Die Doku-Zeit als SEPARATER WFS-Eintrag, direkt im Anschluss (Default 15 Min).
    doku_min = max(0, _int(request.POST.get("doku_minuten"), 15))
    extra = ""
    if doku_min:
        d_ende = (datetime.combine(date.min, ende) + timedelta(minutes=doku_min)).time()
        Leistung.objects.create(
            datum=datum, klient=klient, leistungsart=Leistungsart.WFS, betreuer=me,
            beginn=ende, ende=d_ende, taetigkeit="Dokumentation")
        extra = f" + {doku_min} Min Doku (WFS)"
    messages.success(
        request, f"{klient.name}: {leistung.dauer_stunden} h ({art}){extra} gespeichert – "
                 f"im Leistungsnachweis sichtbar.")
    return redirect("nachweis:feld_heute")

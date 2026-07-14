"""P4a: Vorkommnis-Meldewesen (QM-Pflichtkern § 37a SGB IX / WTG § 19 f. / § 8a SGB VIII).

Zugriff: Mitarbeitende mit Klientenarbeit ERFASSEN Vorkommnisse (Vorfälle passieren
im Dienst) und sehen ihre eigenen; die Leitung sieht und bearbeitet alle des Teams
und schließt ab (Auswertung/Maßnahmen sind Pflicht vor dem Abschluss).
Verwaltung/Admin haben keinen Zugriff (Art-9-Freitexte).
"""
from datetime import date, datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_POST

from . import services
from .models import (Vorkommnis, VorkommnisKategorie, VorkommnisStatus,
                     Team, Angebot, Klient)


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


def _sichtbare(request):
    """Leitung: alle Vorkommnisse der geleiteten Teams; sonst nur selbst erstellte."""
    me = services.mitarbeiter_fuer(request.user)
    if me is None or services.ohne_klientenarbeit(request.user):
        return Vorkommnis.objects.none(), None
    if services.ist_leitung(request.user):
        return (Vorkommnis.objects.filter(team__in=services.teams_fuer(request.user)),
                me)
    return Vorkommnis.objects.filter(erstellt_von=me), me


@login_required
def vorkommnisse(request):
    qs, me = _sichtbare(request)
    if me is None:
        return redirect("nachweis:start")
    status = request.GET.get("status") or ""
    if status in VorkommnisStatus.values:
        qs = qs.filter(status=status)
    kat = request.GET.get("kategorie") or ""
    if kat in VorkommnisKategorie.values:
        qs = qs.filter(kategorie=kat)
    liste = list(qs.select_related("klient", "team", "angebot", "erstellt_von"))
    bearbeiten = next((v for v in liste if str(v.id) == request.GET.get("edit", "")), None)
    ist_leitung = services.ist_leitung(request.user)
    teams = services.teams_fuer(request.user) if ist_leitung else \
        Team.objects.filter(pk=me.team_id)
    return render(request, "nachweis/vorkommnisse.html", {
        "aktiv": "vorkommnisse", "liste": liste, "bearbeiten": bearbeiten,
        "n_meldung_faellig": sum(1 for v in liste if v.meldung_faellig),
        "kategorien": VorkommnisKategorie.choices, "status_wahl": VorkommnisStatus.choices,
        "f_status": status, "f_kategorie": kat,
        "teams": teams, "angebote": Angebot.objects.filter(team__in=teams, aktiv=True),
        "klienten": services.klienten_fuer(request.user).order_by("nachname"),
        "ist_leitung": ist_leitung, "heute": date.today().isoformat(),
    })


@require_POST
@login_required
def vorkommnis_speichern(request):
    me = services.mitarbeiter_fuer(request.user)
    if me is None or services.ohne_klientenarbeit(request.user):
        return HttpResponseForbidden()
    pk = request.POST.get("id")
    if pk:
        qs, _me = _sichtbare(request)
        v = get_object_or_404(qs, pk=_int0(pk))
        if v.status == VorkommnisStatus.ABGESCHLOSSEN and not services.ist_leitung(request.user):
            return HttpResponseForbidden()
    else:
        v = Vorkommnis(erstellt_von=me)
    datum = _datum(request.POST.get("datum"))
    beschreibung = (request.POST.get("beschreibung") or "").strip()
    kat = request.POST.get("kategorie")
    if not (datum and beschreibung and kat in VorkommnisKategorie.values):
        messages.error(request, "Bitte Datum, Kategorie und Beschreibung angeben.")
        return redirect("nachweis:vorkommnisse")
    teams = services.teams_fuer(request.user)
    team = teams.filter(pk=_int0(request.POST.get("team"))).first() or me.team
    if team is None:
        messages.error(request, "Kein Team zuordenbar.")
        return redirect("nachweis:vorkommnisse")
    v.datum = datum
    try:
        v.uhrzeit = datetime.strptime((request.POST.get("uhrzeit") or "").strip(),
                                      "%H:%M").time()
    except ValueError:
        v.uhrzeit = None
    v.kategorie = kat
    v.team = team
    v.angebot = Angebot.objects.filter(pk=_int0(request.POST.get("angebot")),
                                       team__in=teams | Team.objects.filter(pk=me.team_id)).first()
    v.klient = services.klienten_fuer(request.user).filter(
        pk=_int0(request.POST.get("klient"))).first()
    v.beschreibung = beschreibung
    v.sofortmassnahmen = (request.POST.get("sofortmassnahmen") or "").strip()
    if "massnahmen" in request.POST:
        v.massnahmen = (request.POST.get("massnahmen") or "").strip()
    v.gemeldet_an = (request.POST.get("gemeldet_an") or "").strip()[:160]
    v.gemeldet_am = _datum(request.POST.get("gemeldet_am"))
    if v.status == VorkommnisStatus.OFFEN and (v.sofortmassnahmen or v.gemeldet_am):
        v.status = VorkommnisStatus.IN_BEARBEITUNG
    v.save()
    if v.meldung_faellig:
        messages.warning(request, "Meldepflichtige Kategorie – bitte unverzüglich an die "
                                  "zuständige Stelle melden und die Meldung hier dokumentieren.")
    messages.success(request, "Vorkommnis gespeichert.")
    return redirect("nachweis:vorkommnisse")


@require_POST
@login_required
def vorkommnis_status(request):
    """Abschließen (nur Leitung, Maßnahmen Pflicht) bzw. wieder öffnen."""
    if not services.ist_leitung(request.user):
        return HttpResponseForbidden()
    v = get_object_or_404(Vorkommnis.objects.filter(
        team__in=services.teams_fuer(request.user)), pk=_int0(request.POST.get("id")))
    aktion = request.POST.get("aktion")
    if aktion == "abschliessen":
        if not v.massnahmen.strip():
            messages.error(request, "Bitte zuerst die Auswertung/Maßnahmen dokumentieren – "
                                    "erst dann kann abgeschlossen werden (QM-Kreislauf).")
            return redirect("nachweis:vorkommnisse")
        if v.meldung_faellig:
            messages.error(request, "Meldepflichtiges Vorkommnis ohne dokumentierte Meldung – "
                                    "bitte zuerst die Meldung nachtragen.")
            return redirect("nachweis:vorkommnisse")
        v.status = VorkommnisStatus.ABGESCHLOSSEN
        v.abgeschlossen_am = date.today()
        v.abgeschlossen_von = services.mitarbeiter_fuer(request.user)
        v.save()
        messages.success(request, "Vorkommnis abgeschlossen.")
    elif aktion == "oeffnen":
        v.status = VorkommnisStatus.IN_BEARBEITUNG
        v.abgeschlossen_am = None
        v.abgeschlossen_von = None
        v.save()
        messages.success(request, "Vorkommnis wieder geöffnet.")
    return redirect("nachweis:vorkommnisse")

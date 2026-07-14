"""M2: Angebote + Belegungsverwaltung mit Anwesenheitskalender (Leitung, team-gescopt)."""
from calendar import monthrange
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_POST

from . import services, services_belegung
from .models import (Angebot, AngebotsTyp, Erreichbarkeit, Belegung,
                     KlientAbwesenheit, AbwesenheitsartKlient, Leistungskatalog,
                     Klient, Status)


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


def _meine_angebote(request):
    return Angebot.objects.filter(team__in=services.teams_fuer(request.user))


def _ueberlappt(klient, einzug, auszug, ausser_pk=None):
    """True, wenn der Zeitraum [einzug, auszug/∞] eine andere Belegung der Klient*in
    schneidet — verhindert Doppel-Belegungen auch mit künftigen/offenen Zeiträumen."""
    for b in klient.belegungen.exclude(pk=ausser_pk):
        b_ende = b.auszug           # None = offen
        # Schnitt zweier Intervalle mit offenen Enden
        if (auszug is None or b.einzug <= auszug) and (b_ende is None or b_ende >= einzug):
            return True
    return False


@login_required
def angebote(request):
    """Angebots-Verwaltung: Standorte/Wohnformen mit Plätzen und Auslastung."""
    if not services.ist_leitung(request.user):
        return HttpResponseForbidden()
    if request.method == "POST":
        teams = services.teams_fuer(request.user)
        team = teams.filter(pk=_int0(request.POST.get("team"))).first()
        name = (request.POST.get("name") or "").strip()
        if not (team and name):
            messages.error(request, "Bitte Name und (eigenes) Team angeben.")
            return redirect("nachweis:angebote")
        pk = request.POST.get("id")
        a = get_object_or_404(_meine_angebote(request), pk=_int0(pk)) if pk else Angebot()
        a.name = name[:120]
        a.team = team
        typ = request.POST.get("typ")
        a.typ = typ if typ in AngebotsTyp.values else AngebotsTyp.WG_VERBUND
        err = request.POST.get("erreichbarkeit")
        a.erreichbarkeit = err if err in Erreichbarkeit.values else Erreichbarkeit.OHNE
        kat_pk = _int0(request.POST.get("katalog"))
        # aktiv=True für NEUE Zuordnungen; den bereits zugeordneten (ggf. inzwischen
        # inaktiven) Katalog darf man behalten – er verschwindet nicht still.
        a.katalog = (a.katalog if a.pk and a.katalog_id == kat_pk
                     else Leistungskatalog.objects.filter(pk=kat_pk, aktiv=True).first())
        a.plaetze = max(0, min(_int0(request.POST.get("plaetze")), 500))
        a.betriebserlaubnis = (request.POST.get("betriebserlaubnis") or "").strip()[:80]
        a.adresse = (request.POST.get("adresse") or "").strip()[:160]
        a.aktiv = request.POST.get("aktiv") == "on"
        a.save()
        messages.success(request, f"Angebot „{a.name}“ gespeichert.")
        return redirect("nachweis:angebote")
    heute = date.today()
    liste = list(_meine_angebote(request).select_related("team", "katalog"))
    for a in liste:
        a.belegt = sum(1 for b in a.belegungen.all() if b.belegt_am(heute))
    bearbeiten = next((a for a in liste if str(a.id) == request.GET.get("edit", "")), None)
    return render(request, "nachweis/angebote.html", {
        "aktiv": "belegungsliste", "angebote": liste, "bearbeiten": bearbeiten,
        "teams": services.teams_fuer(request.user),
        "typen": AngebotsTyp.choices, "erreichbarkeiten": Erreichbarkeit.choices,
        "kataloge": Leistungskatalog.objects.filter(aktiv=True),
    })


@login_required
def belegungskalender(request, pk):
    """Anwesenheits-Matrix eines Angebots (Bewohner × Tage) mit Summen, Betrag
    (bei Tagessatz-Katalog) und Meldefrist-Warnungen."""
    if not services.ist_leitung(request.user):
        return HttpResponseForbidden()
    angebot = get_object_or_404(_meine_angebote(request), pk=pk)
    jahr = min(2100, max(2000, _int0(request.GET.get("jahr")) or date.today().year))
    monat = min(12, max(1, _int0(request.GET.get("monat")) or date.today().month))
    n_tage = monthrange(jahr, monat)[1]
    monatsende = date(jahr, monat, n_tage)
    monatsanfang = date(jahr, monat, 1)

    belegungen = list(angebot.belegungen.select_related("klient")
                      .filter(einzug__lte=monatsende)
                      .exclude(auszug__lt=monatsanfang))
    zeilen, gesamt = [], {"belegt": 0, "anwesend": 0, "abwesend": 0}
    for b in belegungen:
        satz = services_belegung.satz_fuer_belegung(b, monatsende)
        kal = services_belegung.monatskalender(b, jahr, monat, satz=satz)
        zeilen.append({"belegung": b, "kal": kal})
        for k in ("belegt", "anwesend", "abwesend"):
            gesamt[k] += kal["summen"][k]
    warnungen = services_belegung.melde_warnungen(belegungen)
    # Klient*innen des Teams, die noch nicht (aktuell) hier wohnen – für den Einzug
    bewohner_ids = [b.klient_id for b in belegungen if b.belegt_am(date.today())]
    kandidaten = (services.klienten_fuer(request.user)
                  .filter(status=Status.BETREUUNG).exclude(pk__in=bewohner_ids)
                  .order_by("nachname"))
    return render(request, "nachweis/belegungskalender.html", {
        "aktiv": "belegungsliste", "angebot": angebot, "jahr": jahr, "monat": monat,
        "monate": list(range(1, 13)), "tage_range": list(range(1, n_tage + 1)),
        "zeilen": zeilen, "gesamt": gesamt, "warnungen": warnungen,
        "arten": AbwesenheitsartKlient.objects.filter(aktiv=True),
        "kandidaten": kandidaten, "heute": date.today().isoformat(),
        "auslastung": (round(gesamt["belegt"] / (angebot.plaetze * n_tage) * 100, 1)
                       if angebot.plaetze else None),
    })


@require_POST
@login_required
def belegung_speichern(request):
    """Einzug anlegen bzw. Auszug/Platz setzen."""
    if not services.ist_leitung(request.user):
        return HttpResponseForbidden()
    pk = request.POST.get("id")
    if pk:
        b = get_object_or_404(Belegung.objects.filter(
            angebot__in=_meine_angebote(request)), pk=_int0(pk))
        auszug = _datum(request.POST.get("auszug"))
        if auszug and auszug < b.einzug:
            messages.error(request, "Auszug liegt vor dem Einzug.")
            return redirect("nachweis:belegungskalender", pk=b.angebot_id)
        # Overlap-Schutz auch beim Bearbeiten: Auszug leeren/verschieben darf keine
        # andere Belegung schneiden (sonst „still wieder geöffnete" Doppelbelegung).
        if _ueberlappt(b.klient, b.einzug, auszug, ausser_pk=b.pk):
            messages.error(request, f"Zeitraum überschneidet eine andere Belegung von {b.klient.name}.")
            return redirect("nachweis:belegungskalender", pk=b.angebot_id)
        b.auszug = auszug
        b.platz = (request.POST.get("platz") or b.platz or "").strip()[:40]
        b.save()
        if auszug:
            # Offene Abwesenheiten enden spätestens mit dem Auszug – sonst verbrauchen
            # sie Kontingent/erzeugen Warnungen für Tage nach der Belegung.
            geschlossen = b.abwesenheiten.filter(bis__isnull=True, von__lte=auszug).update(bis=auszug)
            b.abwesenheiten.filter(bis__gt=auszug).update(bis=auszug)
            if geschlossen:
                messages.info(request, f"{geschlossen} offene Abwesenheit(en) zum Auszug beendet.")
        messages.success(request, f"Belegung von {b.klient.name} aktualisiert.")
        return redirect("nachweis:belegungskalender", pk=b.angebot_id)
    angebot = get_object_or_404(_meine_angebote(request), pk=_int0(request.POST.get("angebot")))
    klient = get_object_or_404(services.klienten_fuer(request.user),
                               pk=_int0(request.POST.get("klient")))
    if klient.team_id != angebot.team_id:
        # Belegungs-Sichtbarkeit hängt am Angebots-Team – ein Cross-Team-Einzug würde
        # die Klient*in für fremde Leitungen sichtbar machen. Erst Team wechseln.
        messages.error(request, f"{klient.name} gehört zu einem anderen Team als das Angebot – "
                                f"bitte zuerst das Team in der Belegungsliste anpassen.")
        return redirect("nachweis:belegungskalender", pk=angebot.pk)
    einzug = _datum(request.POST.get("einzug"))
    if not einzug:
        messages.error(request, "Bitte ein Einzugsdatum angeben.")
        return redirect("nachweis:belegungskalender", pk=angebot.pk)
    if _ueberlappt(klient, einzug, None):
        messages.error(request, f"{klient.name} hat eine Belegung, die sich mit dem "
                                f"Einzug am {einzug:%d.%m.%Y} überschneidet.")
        return redirect("nachweis:belegungskalender", pk=angebot.pk)
    Belegung.objects.create(klient=klient, angebot=angebot, einzug=einzug,
                            platz=(request.POST.get("platz") or "").strip()[:40])
    messages.success(request, f"{klient.name} eingezogen zum {einzug:%d.%m.%Y}.")
    return redirect("nachweis:belegungskalender", pk=angebot.pk)


@require_POST
@login_required
def klient_abwesenheit_speichern(request):
    if not services.ist_leitung(request.user):
        return HttpResponseForbidden()
    b = get_object_or_404(Belegung.objects.filter(
        angebot__in=_meine_angebote(request)), pk=_int0(request.POST.get("belegung")))
    art = get_object_or_404(AbwesenheitsartKlient, pk=_int0(request.POST.get("art")),
                            aktiv=True)
    von = _datum(request.POST.get("von"))
    bis = _datum(request.POST.get("bis"))
    if not von or (bis and bis < von):
        messages.error(request, "Bitte gültigen Zeitraum angeben (bis ≥ von).")
        return redirect("nachweis:belegungskalender", pk=b.angebot_id)
    # Abwesenheit muss im Belegungszeitraum liegen (sonst Kontingent-/Anzeige-Geister)
    if von < b.einzug or (b.auszug and von > b.auszug) or (b.auszug and bis and bis > b.auszug):
        messages.error(request, "Die Abwesenheit liegt (teilweise) außerhalb des Belegungszeitraums.")
        return redirect("nachweis:belegungskalender", pk=b.angebot_id)
    if art.max_tage and art.basis == "ereignis" and bis and (bis - von).days + 1 > art.max_tage \
            and art.kuerzel == "KB":
        messages.error(request, f"„{art.name}“ ist auf {art.max_tage} Tage begrenzt – "
                                f"für längere Abwesenheiten bitte die Freihaltegeld-Art (FRH) erfassen.")
        return redirect("nachweis:belegungskalender", pk=b.angebot_id)
    KlientAbwesenheit.objects.create(
        belegung=b, art=art, von=von, bis=bis,
        gemeldet_am=_datum(request.POST.get("gemeldet_am")),
        kommentar=(request.POST.get("kommentar") or "").strip()[:200])
    messages.success(request, f"{b.klient.name}: {art.name} ab {von:%d.%m.%Y} erfasst.")
    return redirect("nachweis:belegungskalender", pk=b.angebot_id)


@require_POST
@login_required
def klient_abwesenheit_aktion(request):
    """gemeldet-Datum setzen oder Abwesenheit löschen."""
    if not services.ist_leitung(request.user):
        return HttpResponseForbidden()
    a = get_object_or_404(KlientAbwesenheit.objects.filter(
        belegung__angebot__in=_meine_angebote(request)), pk=_int0(request.POST.get("id")))
    apk = a.belegung.angebot_id
    if request.POST.get("aktion") == "loeschen":
        a.delete()
        messages.success(request, "Abwesenheit gelöscht.")
    else:
        a.gemeldet_am = _datum(request.POST.get("gemeldet_am")) or date.today()
        a.save(update_fields=["gemeldet_am"])
        messages.success(request, f"Meldung an den Kostenträger dokumentiert ({a.gemeldet_am:%d.%m.%Y}).")
    return redirect("nachweis:belegungskalender", pk=apk)

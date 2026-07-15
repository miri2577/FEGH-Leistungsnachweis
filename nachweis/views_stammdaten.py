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
                     WiederkehrendeLeistung, Rhythmus, Anrechnung, HBGSatz, Umrechnung,
                     Kostentraeger, KostentraegerTyp, Bewilligung, BewilligungStatus, Leistungstyp)


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
    klienten = list(services.klienten_fuer(request.user)
                    .select_related("team", "bezugsbetreuer")
                    .prefetch_related("bewilligungen")
                    .order_by("nachname", "vorname"))
    heute = date.today()
    for k in klienten:                          # Status-Badges (Bewilligung/Bericht)
        k.hinweise = services.klient_hinweise(k, heute)
    return render(request, "nachweis/belegungsliste.html", {
        "aktiv": "belegungsliste", "klienten": klienten,
        "kein_team": not services.teams_fuer(request.user).exists(),
    })


def _form_kontext(request, klient=None):
    teams = services.teams_fuer(request.user)
    import json
    vorschlag = {str(h): {"al": str(v["al"]), "kle": str(v["kle"]), "woche": str(v["fls_woche"])}
                 for h, v in services.bewilligung_vorschlag(date.today().year).items()}
    return {
        "aktiv": "belegungsliste",
        "klient": klient,
        "teams": teams,
        "mitarbeiter": Mitarbeiter.objects.filter(aktiv=True, team__in=teams).order_by("name", "vorname"),
        "status_wahl": Status.choices,
        "hbg_vorschlag_json": json.dumps(vorschlag),
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
    # Bewilligungsdaten (al/kle/hbg/kue_bis/kostentraeger) werden aus dem Klient-Formular
    # nur noch gepflegt, solange es KEINE aktive Bewilligung gibt. Sobald eine Bewilligung
    # existiert, ist sie die führende Quelle und synchronisiert diese Cache-Felder selbst –
    # das Formular überschreibt sie dann nicht (keine Divergenz).
    hat_bewilligung = bool(k.pk) and k.aktive_bewilligung() is not None
    if not hat_bewilligung:
        k.al = _dec(request.POST.get("al"))
        k.kle = _dec(request.POST.get("kle"))
        k.hbg = _int_or_none(request.POST.get("hbg"))
        # HBG gewählt, aber AL/kLE leer -> aus der HBG-Tabelle der Parameter ableiten.
        if k.hbg and not k.al and not k.kle:
            v = services.bewilligung_vorschlag(date.today().year).get(k.hbg)
            if v:
                k.al, k.kle = v["al"], v["kle"]
        k.kue_bis = _datum(request.POST.get("kue_bis"))
        k.kostentraeger = (request.POST.get("kostentraeger") or "").strip()
    k.brp_bis = _datum(request.POST.get("brp_bis"))
    k.versendet_am = _datum(request.POST.get("versendet_am"))
    status = request.POST.get("status")
    k.status = status if status in Status.values else Status.BETREUUNG
    k.person_id = (request.POST.get("person_id") or "").strip()
    k.thfd = (request.POST.get("thfd") or "").strip()
    k.kommentar = (request.POST.get("kommentar") or "").strip()
    k.strasse = (request.POST.get("strasse") or "").strip()
    k.plz = (request.POST.get("plz") or "").strip()
    k.ort = (request.POST.get("ort") or "").strip()
    k.betreuung_name = (request.POST.get("betreuung_name") or "").strip()
    k.betreuung_telefon = (request.POST.get("betreuung_telefon") or "").strip()
    k.betreuung_umfang = (request.POST.get("betreuung_umfang") or "").strip()
    k.betreuung_bis = _datum(request.POST.get("betreuung_bis"))
    k.save()
    messages.success(request, f"{k.name} gespeichert.")
    return redirect("nachweis:belegungsliste")


# ---------------------------------------------------------------- Kostenträger
@login_required
def kostentraeger_liste(request):
    if not _nur_leitung(request):
        return HttpResponseForbidden()
    bearbeiten = Kostentraeger.objects.filter(pk=request.GET.get("edit")).first() if request.GET.get("edit") else None
    return render(request, "nachweis/kostentraeger_liste.html", {
        "aktiv": "belegungsliste",
        "kostentraeger": Kostentraeger.objects.all(),
        "typen": KostentraegerTyp.choices,
        "bearbeiten": bearbeiten,
    })


@require_POST
@login_required
def kostentraeger_speichern(request):
    if not _nur_leitung(request):
        return HttpResponseForbidden()
    name = (request.POST.get("name") or "").strip()
    if not name:
        messages.error(request, "Bitte einen Namen angeben.")
        return redirect("nachweis:kostentraeger_liste")
    pk = request.POST.get("id")
    kt = get_object_or_404(Kostentraeger, pk=pk) if pk else Kostentraeger()
    kt.name = name
    typ = request.POST.get("typ")
    kt.typ = typ if typ in KostentraegerTyp.values else KostentraegerTyp.BEZIRKSAMT
    kt.amt = (request.POST.get("amt") or "").strip()
    kt.adresse = (request.POST.get("adresse") or "").strip()
    kt.ansprechpartner = (request.POST.get("ansprechpartner") or "").strip()
    kt.leitweg_id = (request.POST.get("leitweg_id") or "").strip()
    kt.email = (request.POST.get("email") or "").strip()
    kt.debitorenkonto = (request.POST.get("debitorenkonto") or "").strip()[:9]
    kt.zahlungsziel_tage = _int_or_none(request.POST.get("zahlungsziel_tage")) or 30
    kt.aktiv = request.POST.get("aktiv") == "on"
    kt.save()
    messages.success(request, f'Kostenträger „{kt.name}“ gespeichert.')
    return redirect("nachweis:kostentraeger_liste")


@login_required
def leistungskatalog(request):
    """M1: Leistungskatalog + Entgeltsatz-Zeitscheiben pflegen (Leitung).
    Fortschreibungen = neuer Satz ab Stichtag; laufende Fälle preisen automatisch um."""
    from .models import Leistungskatalog, Entgeltsatz, Abrechnungseinheit
    if not _nur_leitung(request):
        return HttpResponseForbidden()
    if request.method == "POST":
        aktion = request.POST.get("aktion")
        if aktion == "eintrag":
            name = (request.POST.get("name") or "").strip()
            einheit = request.POST.get("einheit")
            if name and einheit in Abrechnungseinheit.values:
                Leistungskatalog.objects.get_or_create(name=name[:120], defaults={
                    "einheit": einheit,
                    "rechtsgrundlage": (request.POST.get("rechtsgrundlage") or "").strip()[:80],
                    "beschreibung": (request.POST.get("beschreibung") or "").strip()[:255]})
                messages.success(request, f"Katalogeintrag „{name}“ angelegt.")
            else:
                messages.error(request, "Bitte Name und Abrechnungseinheit angeben.")
        elif aktion == "satz":
            k = Leistungskatalog.objects.filter(pk=_int_or_none(request.POST.get("katalog"))).first()
            von = _datum(request.POST.get("gueltig_von"))
            betrag = _dec(request.POST.get("betrag"))
            if k and von and betrag > 0:
                Entgeltsatz.objects.create(
                    katalog=k, gueltig_von=von, betrag=betrag,
                    gueltig_bis=_datum(request.POST.get("gueltig_bis")),
                    kostentraeger=Kostentraeger.objects.filter(
                        pk=_int_or_none(request.POST.get("kostentraeger"))).first(),
                    variante=(request.POST.get("variante") or "").strip()[:60],
                    betrag_nebenkosten=_dec(request.POST.get("betrag_nebenkosten")),
                    betrag_investition=_dec(request.POST.get("betrag_investition")),
                    kommentar=(request.POST.get("kommentar") or "").strip()[:200])
                messages.success(request, f"Entgeltsatz {betrag} € ab {von:%d.%m.%Y} angelegt.")
            else:
                messages.error(request, "Bitte Katalogeintrag, Gültig-ab und Betrag > 0 angeben.")
        elif aktion == "satz_loeschen":
            s = Entgeltsatz.objects.filter(pk=_int_or_none(request.POST.get("id"))).first()
            if s:
                s.delete()
                messages.success(request, "Entgeltsatz gelöscht.")
        return redirect("nachweis:leistungskatalog")
    eintraege = list(Leistungskatalog.objects.prefetch_related("saetze__kostentraeger"))
    heute = date.today()
    for e in eintraege:
        e.satz_liste = list(e.saetze.all())
        for s in e.satz_liste:
            s.aktuell = s.gilt_am(heute)
    return render(request, "nachweis/leistungskatalog.html", {
        "aktiv": "parameter", "eintraege": eintraege,
        "einheiten": Abrechnungseinheit.choices,
        "kostentraeger": Kostentraeger.objects.filter(aktiv=True),
        "heute": heute.isoformat(),
    })


@require_POST
@login_required
def kostentraeger_bezirke(request):
    """Legt die 12 Berliner Bezirksämter als Kostenträger an (idempotent)."""
    if not _nur_leitung(request):
        return HttpResponseForbidden()
    from .berlin import ensure_berliner_bezirke
    neu, gesamt = ensure_berliner_bezirke()
    if neu:
        messages.success(request, f"{neu} Berliner Bezirksamt/-ämter angelegt "
                                  f"({gesamt}/12 vorhanden). Leitweg-IDs für die XRechnung bitte je Bezirk ergänzen.")
    else:
        messages.info(request, f"Alle 12 Berliner Bezirksämter waren bereits angelegt ({gesamt}/12).")
    return redirect("nachweis:kostentraeger_liste")


# ---------------------------------------------------------------- Bewilligungen (je Klient*in)
@login_required
def bewilligungen(request, pk):
    if not _nur_leitung(request):
        return HttpResponseForbidden()
    klient = get_object_or_404(services.klienten_fuer(request.user), pk=pk)
    liste = list(klient.bewilligungen.select_related("kostentraeger").all())
    bearbeiten = next((b for b in liste if str(b.id) == request.GET.get("edit", "")), None)
    # Fortschreibung: neue Fassung, vorbefüllt aus einer bestehenden Bewilligung
    fortschreibung = next((b for b in liste if str(b.id) == request.GET.get("fort", "")), None)
    hbg_map = services.hbg_tabelle(date.today().year)
    import json
    hbg_json = {str(h): {"fls_woche": str(w),
                         "kle_tag": str(services.get_parameter(date.today().year).kle_je_tag or 0)}
                for h, w in hbg_map.items()}
    from .models import Leistungskatalog
    return render(request, "nachweis/bewilligungen.html", {
        "aktiv": "belegungsliste", "klient": klient, "bewilligungen": liste,
        "aktive": klient.aktive_bewilligung(),
        "kostentraeger": Kostentraeger.objects.filter(aktiv=True),
        "katalog_liste": Leistungskatalog.objects.filter(aktiv=True),
        "status_wahl": BewilligungStatus.choices, "typ_wahl": Leistungstyp.choices,
        "bearbeiten": bearbeiten, "fortschreibung": fortschreibung,
        "hbg_json": json.dumps(hbg_json),
    })


@require_POST
@login_required
def bewilligung_speichern(request):
    if not _nur_leitung(request):
        return HttpResponseForbidden()
    klient = get_object_or_404(services.klienten_fuer(request.user), pk=request.POST.get("klient"))
    pk = request.POST.get("id")
    if pk:
        b = get_object_or_404(Bewilligung, pk=pk, klient=klient)
    else:
        b = Bewilligung(klient=klient)
    _kt = request.POST.get("kostentraeger")
    b.kostentraeger = Kostentraeger.objects.filter(pk=_kt).first() if (_kt or "").isdigit() else None
    b.aktenzeichen = (request.POST.get("aktenzeichen") or "").strip()
    typ = request.POST.get("leistungstyp")
    b.leistungstyp = typ if typ in Leistungstyp.values else Leistungstyp.FLS_KLE
    # M1: optionaler Katalog-Bezug (leer = klassisches Berliner BEW-Verhalten)
    from .models import Leistungskatalog
    _kat = request.POST.get("katalog")
    b.katalog = (Leistungskatalog.objects.filter(pk=_kat, aktiv=True).first()
                 if (_kat or "").isdigit() else None)
    b.gueltig_von = _datum(request.POST.get("gueltig_von"))
    b.gueltig_bis = _datum(request.POST.get("gueltig_bis"))
    b.fls_woche = _dec(request.POST.get("fls_woche"))
    b.kle_tag = _dec(request.POST.get("kle_tag"))
    b.hbg = _int_or_none(request.POST.get("hbg"))
    _ptl = request.POST.get("ptl") or ""
    b.ptl = _ptl if _ptl in ("A", "B") else ""
    st = request.POST.get("status")
    b.status = st if st in BewilligungStatus.values else BewilligungStatus.AKTIV
    _vg = request.POST.get("vorgaenger")
    b.vorgaenger = Bewilligung.objects.filter(pk=_vg, klient=klient).first() if (_vg or "").isdigit() else None
    b.kommentar = (request.POST.get("kommentar") or "").strip()
    b.save()   # synchronisiert den Klient-Cache automatisch
    messages.success(request, "Bewilligung gespeichert.")
    return redirect("nachweis:bewilligungen", pk=klient.pk)


@require_POST
@login_required
def bewilligung_loeschen(request):
    if not _nur_leitung(request):
        return HttpResponseForbidden()
    b = get_object_or_404(Bewilligung.objects.filter(
        klient__in=services.klienten_fuer(request.user)), pk=request.POST.get("id"))
    kpk = b.klient_id
    b.delete()
    messages.success(request, "Bewilligung gelöscht.")
    return redirect("nachweis:bewilligungen", pk=kpk)


# ---------------------------------------------------------------- Team-Parameter
@login_required
def parameter(request):
    if not _nur_leitung(request):
        return HttpResponseForbidden()
    jahr = int(request.GET.get("jahr") or date.today().year)
    p = services.get_parameter(jahr)
    if request.method == "POST":
        aktion = request.POST.get("aktion") or "parameter"
        if aktion == "parameter":
            p.teamsitzung_dauer_std = _dec(request.POST.get("teamsitzung_dauer_std"))
            p.teamsitzung_wochentag = _int_or_none(request.POST.get("teamsitzung_wochentag")) or 3
            p.fls_preis = _dec(request.POST.get("fls_preis"))
            p.kle_je_tag = _dec(request.POST.get("kle_je_tag"))
            p.ptl_preis = _dec(request.POST.get("ptl_preis"))
            p.erbringungsfiktion = request.POST.get("erbringungsfiktion") == "on"
            p.save()
            # HBG-Tabelle (FLS/Woche je HBG 1–12, aus dem Senats-Tool Output 5.)
            for hbg in range(1, 13):
                wert = _dec(request.POST.get(f"hbg_{hbg}"))
                if wert:
                    HBGSatz.objects.update_or_create(parameter=p, hbg=hbg,
                                                     defaults={"fls_woche": wert})
                else:
                    HBGSatz.objects.filter(parameter=p, hbg=hbg,
                                           pauschale_alt=0, belegung_stichtag=0).delete()
            messages.success(request, "Parameter gespeichert.")
        elif aktion == "rechner":
            # Eingaben des Umrechnungsrechners speichern (Kostensätze/Platzzahl
            # sind individuell verhandelt und hier frei anpassbar).
            u, _ = Umrechnung.objects.get_or_create(parameter=p)
            u.kapazitaet = _int_or_none(request.POST.get("kapazitaet")) or 0
            u.wochenarbeitszeit = _dec(request.POST.get("wochenarbeitszeit")) or Decimal("38.5")
            u.auslastung = _dec(request.POST.get("auslastung")) or Decimal("0.959")
            u.fallunspez_anteil = _dec(request.POST.get("fallunspez_anteil"))
            u.erreichbarkeit_mo_fr_std = _dec(request.POST.get("erreichbarkeit_mo_fr_std"))
            u.erreichbarkeit_we_ft_std = _dec(request.POST.get("erreichbarkeit_we_ft_std"))
            u.wegezeit_std_vk_woche = _dec(request.POST.get("wegezeit_std_vk_woche"))
            u.pk_alternativ = _dec(request.POST.get("pk_alternativ"))
            u.save()
            for hbg in range(1, 13):
                HBGSatz.objects.update_or_create(
                    parameter=p, hbg=hbg,
                    defaults={"pauschale_alt": _dec(request.POST.get(f"pausch_{hbg}")),
                              "belegung_stichtag": _int_or_none(request.POST.get(f"beleg_{hbg}")) or 0})
            messages.success(request, "Umrechnungs-Eingaben gespeichert – Ergebnis unten geprüft (Gegenprobe).")
        elif aktion == "uebernehmen":
            # Rechner-Ergebnisse in die Abrechnungsparameter übernehmen.
            erg, _alt, _neu = services.umrechnung_fuer_jahr(jahr)
            if not erg:
                messages.error(request, "Berechnung unvollständig – bitte Kapazität, Belegung und Pauschalen (mind. HBG 1 und 12) eintragen.")
            else:
                p.fls_preis = erg["fls_satz"].quantize(Decimal("0.0001"))
                p.kle_je_tag = erg["kle_je_tag"].quantize(Decimal("0.000001"))
                p.save()
                for hbg, woche in erg["fls_woche"].items():
                    HBGSatz.objects.update_or_create(
                        parameter=p, hbg=hbg,
                        defaults={"fls_woche": woche.quantize(Decimal("0.0001"))})
                messages.success(request, f"Übernommen: FLS-Satz {p.fls_preis} € · kLE/Tag {p.kle_je_tag} · FLS/Woche je HBG aktualisiert.")
        return redirect(f"{request.path}?jahr={jahr}")
    wochentage = [(0, "Montag"), (1, "Dienstag"), (2, "Mittwoch"), (3, "Donnerstag"),
                  (4, "Freitag"), (5, "Samstag"), (6, "Sonntag")]
    ts_pro, n_do = services.teamsitzung_pro_klient(jahr)
    hbg_map = services.hbg_tabelle(jahr)
    hbg_zeilen = [{"hbg": h, "fls_woche": hbg_map.get(h, ""),
                   "al_monat": (hbg_map[h] * services.WOCHEN_JE_MONAT).quantize(Decimal("0.001"))
                   if h in hbg_map else ""} for h in range(1, 13)]
    kle_monat = ((p.kle_je_tag or Decimal("0")) * (Decimal("365.25") / 12)).quantize(Decimal("0.001"))
    # Umrechnungsrechner: Eingaben + (falls vollständig) Ergebnis inkl. Gegenprobe
    rechner = Umrechnung.objects.filter(parameter=p).first()
    saetze = {s.hbg: s for s in p.hbg_saetze.all()}
    rechner_zeilen = [{"hbg": h,
                       "pauschale": saetze[h].pauschale_alt if h in saetze and saetze[h].pauschale_alt else "",
                       "belegung": saetze[h].belegung_stichtag if h in saetze and saetze[h].belegung_stichtag else ""}
                      for h in range(1, 13)]
    erg, gp_alt, gp_neu = services.umrechnung_fuer_jahr(jahr)
    ergebnis = None
    if erg:
        ergebnis = {
            "fls_satz": erg["fls_satz"].quantize(Decimal("0.0001")),
            "kle_je_tag": erg["kle_je_tag"].quantize(Decimal("0.000001")),
            "fallspez_std": erg["fallspez_std"].quantize(Decimal("0.01")),
            "vk": erg["vk_gesamt"].quantize(Decimal("0.001")),
            "budget": erg["budget_gesamt"].quantize(Decimal("0.01")),
            "fls_woche": [{"hbg": h, "woche": w.quantize(Decimal("0.0001"))}
                          for h, w in erg["fls_woche"].items()],
            "gp_alt": gp_alt.quantize(Decimal("0.01")),
            "gp_neu": gp_neu.quantize(Decimal("0.01")),
            "gp_diff": (gp_neu - gp_alt).quantize(Decimal("0.01")),
        }
    teams = services.teams_fuer(request.user)
    serien = list(WiederkehrendeLeistung.objects
                  .filter(Q(team__isnull=True) | Q(team__in=teams)).select_related("team"))
    edit_serie = next((s for s in serien if str(s.id) == request.GET.get("serie", "")), None)
    return render(request, "nachweis/parameter.html", {
        "aktiv": "parameter", "p": p, "jahr": jahr, "wochentage": wochentage,
        "n_donnerstage": n_do, "ts_pro_klient": ts_pro,
        "hbg_zeilen": hbg_zeilen, "kle_monat": kle_monat,
        "rechner": rechner, "rechner_zeilen": rechner_zeilen, "ergebnis": ergebnis,
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

"""Phase 2 / Slice 2b: Berichts-Engine — Berichte je Klient*in mit Vorlagen und Workflow.

Workflow (örV/AV Hilfeplanung): offen → in Arbeit → mit Klient*in besprochen → versendet.
'Versendet' pflegt Klient.versendet_am automatisch nach (bestehende Fälligkeits-Anzeige).
Zugriff wie Ziele/Doku: alle mit Klient-Zugriff; Löschen nur Leitung.
"""
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_POST

from . import services
from .models import (Klient, Bericht, BerichtsStatus, Berichtsvorlage,
                     Ziel, ZielStatus)


def _datum(s):
    try:
        return date.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def _int0(val):
    try:
        return int(val)
    except (TypeError, ValueError):
        return 0


@login_required
def berichte(request, pk):
    """Berichte-Seite je Klient*in: Liste + Anlegen/Bearbeiten."""
    klient = get_object_or_404(services.klienten_fuer(request.user), pk=pk)
    liste = list(klient.berichte.select_related("vorlage"))
    bearbeiten = next((b for b in liste if str(b.id) == request.GET.get("edit", "")), None)
    # Vorbelegung: fällig = 10 Wochen VOR KÜ-Ende (Fristlogik von Klient.bericht_faellig_am),
    # Zeitraum = Anschluss an den spätesten bisherigen Berichtszeitraum bzw. letzte 12 Monate
    letztes_bis = max((b.zeitraum_bis for b in liste if b.zeitraum_bis), default=None)
    von_default = (letztes_bis + timedelta(days=1)) if letztes_bis \
        else date.today() - timedelta(days=365)
    faellig_default = klient.bericht_faellig_am or (date.today() + timedelta(days=70))
    return render(request, "nachweis/berichte.html", {
        "aktiv": "belegungsliste" if services.ist_leitung(request.user) else "start",
        "klient": klient, "berichte": liste, "bearbeiten": bearbeiten,
        "vorlagen": Berichtsvorlage.objects.filter(aktiv=True),
        "status_wahl": BerichtsStatus.choices,
        "ist_leitung": services.ist_leitung(request.user),
        "faellig_default": faellig_default.isoformat(),
        "von_default": von_default.isoformat(),
        "bis_default": date.today().isoformat(),
    })


@require_POST
@login_required
def bericht_speichern(request):
    klient = get_object_or_404(services.klienten_fuer(request.user),
                               pk=_int0(request.POST.get("klient")))
    bid = request.POST.get("id")
    if bid:
        b = get_object_or_404(Bericht, pk=_int0(bid), klient=klient)
    else:
        b = Bericht(klient=klient, erstellt_von=services.mitarbeiter_fuer(request.user))
    if b.pk and b.status == BerichtsStatus.VERSENDET:
        # Festschreibung: ein versendeter Bericht ging an den Kostenträger und wird
        # nicht mehr verändert – Korrekturen laufen über einen neuen Bericht.
        messages.error(request, "Dieser Bericht wurde bereits versendet und ist festgeschrieben – "
                                "für Korrekturen bitte einen neuen Bericht anlegen.")
        return redirect("nachweis:berichte", pk=klient.pk)
    v = request.POST.get("vorlage")
    b.vorlage = Berichtsvorlage.objects.filter(pk=v, aktiv=True).first() if (v or "").isdigit() else b.vorlage
    b.zeitraum_von = _datum(request.POST.get("zeitraum_von"))
    b.zeitraum_bis = _datum(request.POST.get("zeitraum_bis"))
    b.faellig_am = _datum(request.POST.get("faellig_am"))
    b.notiz = (request.POST.get("notiz") or "").strip()[:200]
    if "inhalt" in request.POST:
        neuer_inhalt = (request.POST.get("inhalt") or "").strip()
        if neuer_inhalt != b.inhalt and b.status == BerichtsStatus.BESPROCHEN:
            # Textänderung NACH dem Besprechen: das Besprochene gilt nicht mehr –
            # der geänderte Bericht muss erneut besprochen werden (örV/AV Hilfeplanung).
            b.status = BerichtsStatus.IN_ARBEIT
            b.besprochen_am = None
            messages.info(request, "Der Text wurde nach dem Besprechen geändert – "
                                   "bitte erneut mit der/dem Klient*in besprechen.")
        b.inhalt = neuer_inhalt
        if b.inhalt and b.status == BerichtsStatus.OFFEN:
            b.status = BerichtsStatus.IN_ARBEIT       # Text da -> automatisch „in Arbeit"
    b.save()
    messages.success(request, "Bericht gespeichert.")
    return redirect("nachweis:berichte", pk=klient.pk)


@require_POST
@login_required
def bericht_status(request):
    """Workflow-Schritte: in Arbeit / besprochen (Pflicht-Schritt!) / versendet / zurück."""
    b = get_object_or_404(Bericht.objects.filter(
        klient__in=services.klienten_fuer(request.user)), pk=_int0(request.POST.get("id")))
    st = request.POST.get("status")
    if st not in BerichtsStatus.values:
        return redirect("nachweis:berichte", pk=b.klient_id)
    if st == BerichtsStatus.VERSENDET and b.status != BerichtsStatus.BESPROCHEN:
        # örV/AV Hilfeplanung: der Bericht ist VOR dem Versand mit der/dem
        # Leistungsberechtigten zu besprechen – Reihenfolge wird erzwungen.
        messages.error(request, "Bitte zuerst „mit Klient*in besprochen“ bestätigen – "
                                "der Bericht ist vor dem Versand zu besprechen.")
        return redirect("nachweis:berichte", pk=b.klient_id)
    war_versendet = (b.status == BerichtsStatus.VERSENDET)
    b.status = st
    heute = date.today()
    if st == BerichtsStatus.BESPROCHEN and not b.besprochen_am:
        b.besprochen_am = heute
    if st == BerichtsStatus.VERSENDET:
        b.versendet_am = heute        # beim (Re-)Versand zählt das aktuelle Datum
        # bestehendes Fälligkeits-Feld am Klienten nachpflegen („…versendet am")
        type(b.klient).objects.filter(pk=b.klient_id).update(versendet_am=b.versendet_am)
    elif war_versendet:
        b.versendet_am = None         # Rücksprung: altes Versanddatum gilt nicht mehr
    b.save()
    messages.success(request, f"Bericht: {b.get_status_display()}.")
    return redirect("nachweis:berichte", pk=b.klient_id)


@require_POST
@login_required
def bericht_loeschen(request):
    if not services.ist_leitung(request.user):
        return HttpResponseForbidden()
    b = get_object_or_404(Bericht.objects.filter(
        klient__in=services.klienten_fuer(request.user)), pk=_int0(request.POST.get("id")))
    kpk = b.klient_id
    b.delete()
    messages.success(request, "Bericht gelöscht.")
    return redirect("nachweis:berichte", pk=kpk)


def _rohpaket_daten(b):
    """Berichts-Rohpaket für FEGH-Bericht (TeilhabeAssist): alles, was die KI-gestützte
    Berichtserstellung braucht — Rahmendaten, Ziele (ZLP) und die chronologische
    Verlaufsdoku des Berichtszeitraums. Die Pseudonymisierung passiert BEWUSST erst
    lokal in der Desktop-App (deren Datenschutzmodell) — dieses Paket ist Klartext
    und nur für Berechtigte mit Klient-Zugriff abrufbar."""
    k = b.klient
    bis = b.zeitraum_bis or date.today()
    von = b.zeitraum_von or bis - timedelta(days=365)   # Fallback relativ zum Zeitraum-Ende
    bew = k.aktive_bewilligung(bis)                     # Bewilligung zum BERICHTSzeitraum
    dokus = list(k.leistungen.exclude(dokumentation="")
                 .filter(datum__gte=von, datum__lte=bis)
                 .select_related("betreuer").prefetch_related("ziele")
                 .order_by("datum", "beginn"))
    ziele = list(k.ziele.select_related("uebergeordnet").order_by("reihenfolge", "id"))
    kontakte = k.leistungen.filter(datum__gte=von, datum__lte=bis,
                                   leistungsart__in=["FS", "BAO"]).count()
    return {
        "format": "fegh-berichtspaket",
        "version": 1,
        "vorlage": {
            "name": b.vorlage.name if b.vorlage else "",
            "abschnitte": (b.vorlage.abschnitte if b.vorlage else []),
        },
        "klient": {
            "name": k.name, "vorname": k.vorname, "nachname": k.nachname,
            "geburtsdatum": k.geburtsdatum.isoformat() if k.geburtsdatum else None,
            "person_id": k.person_id,
            "bezugsbetreuer": str(k.bezugsbetreuer or ""),
        },
        "zeitraum": {"von": von.isoformat(), "bis": bis.isoformat(),
                     "faellig_am": b.faellig_am.isoformat() if b.faellig_am else None},
        "bewilligung": {
            "hbg": bew.hbg if bew else k.hbg,
            "fls_woche": str(bew.fls_woche) if bew else None,
            "gueltig_von": bew.gueltig_von.isoformat() if bew and bew.gueltig_von else None,
            "gueltig_bis": bew.gueltig_bis.isoformat() if bew and bew.gueltig_bis else None,
            "kostentraeger": bew.kostentraeger.name if bew and bew.kostentraeger else k.kostentraeger,
            "aktenzeichen": bew.aktenzeichen if bew else "",
        } if (bew or k.hbg or k.kostentraeger) else None,
        "ziele": [{
            "art": z.get_art_display(), "titel": z.titel,
            "richtungsziel": z.uebergeordnet.titel if z.uebergeordnet else None,
            "indikator": z.indikator, "beschreibung": z.beschreibung,
            "status": z.get_status_display(),
            "erreicht_grad": z.erreicht_grad,
        } for z in ziele],
        "wirkung": [{
            "dimension": e.dimension.name, "bereich": e.dimension.get_bereich_display(),
            "datum": e.datum.isoformat(), "anlass": e.get_anlass_display(),
            "perspektive": e.get_perspektive_display(),
            "ist": e.ist, "soll": e.soll,
        } for e in k.wirkungseinschaetzungen.select_related("dimension")
            .order_by("datum")],
        "statistik": {"kontakte_im_zeitraum": kontakte, "doku_eintraege": len(dokus)},
        "verlaufsdokumentation": [{
            "datum": l.datum.isoformat(), "leistungsart": l.leistungsart,
            "taetigkeit": l.taetigkeit, "betreuer": str(l.betreuer or ""),
            "text": l.dokumentation,
            "zielbezug": [z.titel for z in l.ziele.all()],
        } for l in dokus],
    }


def _rohpaket_markdown(d) -> str:
    """Markdown-Fassung: direkt als Vorbericht/Stichpunkte in FEGH-Bericht einfügbar."""
    z = d["zeitraum"]
    out = [f"# Berichts-Rohpaket — {d['vorlage']['name'] or 'Bericht'}",
           f"Klient*in: {d['klient']['name']} · Zeitraum {z['von']} bis {z['bis']}", ""]
    if d["bewilligung"]:
        b = d["bewilligung"]
        out += ["## Rahmendaten",
                f"- HBG: {b['hbg'] or '—'} · FLS/Woche: {b['fls_woche'] or '—'}",
                f"- Bewilligung: {b['gueltig_von'] or '—'} bis {b['gueltig_bis'] or 'offen'}"
                f" · Kostenträger: {b['kostentraeger'] or '—'}", ""]
    if d["vorlage"]["abschnitte"]:
        out += ["## Gliederung der Vorlage"] + \
               [f"{i}. {a}" for i, a in enumerate(d["vorlage"]["abschnitte"], 1)] + [""]
    if d["ziele"]:
        out.append("## Ziele (ZLP)")
        for zi in d["ziele"]:
            praefix = f"{zi['richtungsziel']} → " if zi["richtungsziel"] else ""
            grad = (f" — Zielerreichung {zi['erreicht_grad']} %"
                    if zi.get("erreicht_grad") is not None else "")
            out.append(f"- [{zi['status']}] {praefix}{zi['titel']}"
                       + (f" — Indikator: {zi['indikator']}" if zi["indikator"] else "")
                       + grad)
        out.append("")
    if d.get("wirkung"):
        out.append("## Wirkungsdimensionen (Ist→Soll, 7er-Skala, niedriger = besser)")
        for w in d["wirkung"]:
            out.append(f"- {w['datum']} · {w['dimension']} ({w['anlass']}, "
                       f"{w['perspektive']}): Ist {w['ist']} → Soll {w['soll']}")
        out.append("")
    st = d["statistik"]
    out.append(f"## Verlaufsdokumentation ({st['doku_eintraege']} Einträge, "
               f"{st['kontakte_im_zeitraum']} Kontakte im Zeitraum)")
    for e in d["verlaufsdokumentation"]:
        kopf = f"### {e['datum']} · {e['leistungsart']}"
        if e["taetigkeit"]:
            kopf += f" · {e['taetigkeit']}"
        out += [kopf, e["text"]]
        if e["zielbezug"]:
            out.append(f"*Zielbezug: {', '.join(e['zielbezug'])}*")
        out.append("")
    return "\n".join(out)


@login_required
def bericht_rohpaket(request, pk):
    """Rohpaket-Download für FEGH-Bericht (TeilhabeAssist): ?format=json (Import) oder
    ?format=md (direkt einfügbar). Export wird protokolliert (exportiert_am -> Auditlog)."""
    from django.http import HttpResponse
    from django.utils import timezone
    b = get_object_or_404(Bericht.objects.filter(
        klient__in=services.klienten_fuer(request.user)).select_related("vorlage", "klient"), pk=pk)
    daten = _rohpaket_daten(b)
    b.exportiert_am = timezone.now()
    b.save(update_fields=["exportiert_am", "geaendert"])
    # Dateiname bewusst OHNE Klientenname (PII nicht in Download-Logs/Dateisystem)
    if request.GET.get("format") == "md":
        resp = HttpResponse(_rohpaket_markdown(daten),
                            content_type="text/markdown; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="FEGH-Bericht_Rohpaket_{b.id}.md"'
    else:
        import json as _json
        resp = HttpResponse(_json.dumps(daten, ensure_ascii=False, indent=2),
                            content_type="application/json; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="FEGH-Bericht_Rohpaket_{b.id}.json"'
    resp["Cache-Control"] = "no-store"      # Art-9-Klartext nie in Caches
    return resp


@login_required
def bericht_druck(request, pk):
    """Druckansicht: Kopf + Gliederung der Vorlage + Berichtstext + Zielerreichung."""
    b = get_object_or_404(Bericht.objects.filter(
        klient__in=services.klienten_fuer(request.user)).select_related("vorlage", "klient"), pk=pk)
    ziele = list(b.klient.ziele.filter(art="handlungsziel")
                 .exclude(status=ZielStatus.AUFGEGEBEN).select_related("uebergeordnet"))
    return render(request, "nachweis/bericht_druck.html", {
        "b": b, "klient": b.klient, "ziele": ziele,
        "wirkung": list(b.klient.wirkungseinschaetzungen
                        .select_related("dimension").order_by("datum")),
        "abschnitte": (b.vorlage.abschnitte if b.vorlage else []),
    })

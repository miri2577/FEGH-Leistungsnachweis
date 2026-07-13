"""Abrechnung: Freigabe-Workflow (MA → Leitung → Verwaltung) und Rechnungen.

Ablauf je Monatsnachweis (Klient*in × Monat):
  OFFEN → (MA: „fertig")  EINGEREICHT → (Leitung: „freigeben")  FREIGEGEBEN
        → (Verwaltung: Rechnung erstellen)  ABGERECHNET

DSGVO: Die Verwaltung sieht ausschließlich Abrechnungsdaten (Name/Aktenzeichen,
Kostenträger, FLS, Betrag, Monat, Status) – KEINE Tätigkeits-Dokumentation.
Deshalb baut jede Verwaltungs-Ansicht bewusst eine reduzierte Projektion und
gibt NICHT das vollständige Klient-Objekt an das Template.
"""
import csv
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import render, get_object_or_404, redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import services
from .models import (Monatsfreigabe, Rechnung, Freigabestatus, Rechnungsstatus,
                     Rechnungssteller, Zahlung, Mahnung, Mahnstufe, Rechnungstyp)

MONATSNAMEN = ["", "Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
               "August", "September", "Oktober", "November", "Dezember"]


def _csv_safe(v):
    """Neutralisiert CSV-/Formel-Injection (Excel/LibreOffice werten =,+,-,@ am
    Zellanfang als Formel). Nur für Freitextfelder (Name/Aktenzeichen/Empfänger) –
    NICHT für formatierte Zahlen, deren führendes '-' erhalten bleiben muss."""
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def _int(val, default):
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _eur(betrag) -> str:
    """Betrag deutsch formatiert (Komma) für Meldungstexte – Templates machen das via floatformat."""
    return f"{Decimal(betrag):.2f}".replace(".", ",")


def _jahr(request):
    return _int(request.GET.get("jahr") or request.POST.get("jahr"), date.today().year)


def _monat(request):
    return min(12, max(1, _int(request.GET.get("monat") or request.POST.get("monat"),
                              date.today().month)))


# --------------------------------------------------------------------------
#  Freigabe-Übersicht (Mitarbeiter*in / Leitung)
# --------------------------------------------------------------------------
@login_required
def abrechnung(request):
    """Monatsübersicht mit Freigabe-Status je Klient*in. Verwaltung → Rechnungen."""
    if services.darf_abrechnen(request.user):
        return redirect("nachweis:rechnungen")
    if services.ohne_klientenarbeit(request.user):      # Admin: kein Klientenbezug
        return redirect("nachweis:start")
    jahr, monat = _jahr(request), _monat(request)
    sichtbar = services.klienten_fuer(request.user).order_by("nachname", "vorname")
    zeilen = services.abrechnungsuebersicht(sichtbar, jahr, monat)
    me = services.mitarbeiter_fuer(request.user)
    summe = sum((z["betrag"] for z in zeilen), Decimal("0"))
    return render(request, "nachweis/abrechnung.html", {
        "aktiv": "abrechnung", "jahr": jahr, "monat": monat, "monatsname": MONATSNAMEN[monat],
        "monate": list(range(1, 13)), "jahre": list(range(date.today().year, 2025, -1)),
        "zeilen": zeilen, "summe": summe,
        "kann_freigeben": services.darf_freigeben(request.user),
        "me_id": me.id if me else None,
        "S": Freigabestatus,
    })


@require_POST
@login_required
def freigabe_aktion(request):
    """Statuswechsel eines Monatsnachweises. Rechte je Aktion streng geprüft."""
    if services.ohne_klientenarbeit(request.user):
        return HttpResponseForbidden()
    aktion = request.POST.get("aktion")
    jahr, monat = _jahr(request), _monat(request)
    sichtbar = services.klienten_fuer(request.user)          # nur eigenes/geleitetes Team
    klient = get_object_or_404(sichtbar, pk=request.POST.get("klient"))
    mf = services.freigabe_holen(klient, jahr, monat, erzeugen=True)
    me = services.mitarbeiter_fuer(request.user)
    jetzt = timezone.now()

    if aktion == "fertig":
        if mf.status == Freigabestatus.OFFEN:
            services.freigabe_snapshot(mf)
            mf.status = Freigabestatus.EINGEREICHT
            mf.eingereicht_am, mf.eingereicht_von, mf.hinweis = jetzt, me, ""
            mf.save()
            messages.success(request, f"{klient.name}: als fertig gemeldet.")
    elif aktion == "zurueckholen":
        if mf.status == Freigabestatus.EINGEREICHT:
            mf.status = Freigabestatus.OFFEN
            mf.save()
            messages.success(request, f"{klient.name}: zurückgeholt (wieder in Bearbeitung).")
    elif aktion in ("freigeben", "zurueckweisen", "freigabe_zuruecknehmen"):
        if not services.darf_freigeben(request.user):
            return HttpResponseForbidden()
        if aktion == "freigeben" and mf.status == Freigabestatus.EINGEREICHT:
            services.freigabe_snapshot(mf)                   # ggf. zwischenzeitliche Änderungen
            mf.status = Freigabestatus.FREIGEGEBEN
            mf.freigegeben_am, mf.freigegeben_von = jetzt, me
            mf.save()
            messages.success(request, f"{klient.name}: freigegeben ({mf.betrag} €).")
        elif aktion == "zurueckweisen" and mf.status == Freigabestatus.EINGEREICHT:
            mf.status = Freigabestatus.OFFEN
            mf.hinweis = (request.POST.get("hinweis") or "").strip()[:255]
            mf.save()
            messages.success(request, f"{klient.name}: an die/den Mitarbeiter*in zurückgewiesen.")
        elif aktion == "freigabe_zuruecknehmen" and mf.status == Freigabestatus.FREIGEGEBEN:
            mf.status = Freigabestatus.EINGEREICHT
            mf.freigegeben_am, mf.freigegeben_von = None, None
            mf.save()
            messages.success(request, f"{klient.name}: Freigabe zurückgenommen.")
    return redirect(f"{reverse('nachweis:abrechnung')}?jahr={jahr}&monat={monat}")


# --------------------------------------------------------------------------
#  Rechnungen (Verwaltung) – nur Abrechnungsdaten
# --------------------------------------------------------------------------
@login_required
def rechnungen(request):
    """Verwaltungs-Hub: freigegebene Nachweise (nach Kostenträger) → Rechnung + Rechnungsliste."""
    if not services.darf_abrechnen(request.user):
        return redirect("nachweis:start")
    jahr, monat = _jahr(request), _monat(request)
    offen = services.offene_abrechnung(jahr, monat)
    gruppen = {}
    for mf in offen:
        kt = mf.klient.kostentraeger or "— ohne Kostenträger —"
        gruppen.setdefault(kt, []).append({
            "id": mf.id, "name": mf.klient.name, "az": mf.klient.person_id,
            "betreuer": mf.klient.bezugsbetreuer.name if mf.klient.bezugsbetreuer_id else "",
            "fls": mf.fls_summe, "kle": mf.kle_summe, "betrag": mf.betrag,
        })
    gruppen_list = [{
        "kostentraeger": kt, "zeilen": z,
        "summe": sum((x["betrag"] for x in z), Decimal("0")),
        "ids": ",".join(str(x["id"]) for x in z),
    } for kt, z in sorted(gruppen.items())]
    liste = Rechnung.objects.all()[:100]
    return render(request, "nachweis/rechnungen.html", {
        "aktiv": "abrechnung", "jahr": jahr, "monat": monat, "monatsname": MONATSNAMEN[monat],
        "monate": list(range(1, 13)), "jahre": list(range(date.today().year, 2025, -1)),
        "gruppen": gruppen_list,
        "offen_summe": sum((g["summe"] for g in gruppen_list), Decimal("0")),
        "rechnungen": liste, "heute": date.today().isoformat(),
    })


@require_POST
@login_required
def rechnung_neu(request):
    """Sammelrechnung aus ausgewählten freigegebenen Nachweisen erstellen."""
    if not services.darf_abrechnen(request.user):
        return HttpResponseForbidden()
    ids = [i for i in (request.POST.get("ids") or "").split(",") if i.isdigit()]
    freigaben = list(Monatsfreigabe.objects
                     .filter(id__in=ids, status=Freigabestatus.FREIGEGEBEN)
                     .select_related("klient"))
    if not freigaben:
        messages.error(request, "Keine freigegebenen Nachweise ausgewählt.")
        return redirect("nachweis:rechnungen")
    empfaenger = ((request.POST.get("empfaenger") or "").strip()
                  or freigaben[0].klient.kostentraeger or "Kostenträger")
    try:
        datum = date.fromisoformat(request.POST.get("datum"))
    except (TypeError, ValueError):
        datum = date.today()
    me = services.mitarbeiter_fuer(request.user)
    r = services.rechnung_erstellen(
        freigaben, empfaenger, freigaben[0].jahr, freigaben[0].monat, datum, me,
        anschrift=(request.POST.get("anschrift") or "").strip(),
        notiz=(request.POST.get("notiz") or "").strip())
    messages.success(request, f"Rechnung {r.nummer} über {r.betrag} € erstellt "
                              f"({len(freigaben)} Positionen).")
    return redirect(reverse("nachweis:rechnung_detail", args=[r.id]))


def _positionen(r):
    """Reduzierte Positions-Projektion (nur Abrechnungsdaten, § 18-Struktur)."""
    return [{"name": p.klient.name, "az": p.klient.person_id,
             "soll": p.soll_fls, "einzeln": p.fls_einzeln, "gruppe": p.fls_gruppe,
             "fls": p.fls_summe, "kle": p.kle_summe, "vorschuss": p.vorschuss,
             "betrag": p.betrag}
            for p in r.positionen.select_related("klient")]


@login_required
def rechnung_detail(request, pk):
    if not services.darf_abrechnen(request.user):
        return redirect("nachweis:start")
    r = get_object_or_404(Rechnung, pk=pk)
    # Änderungshistorie (simple-history): kompakte Wer/Wann/Was-Zeilen für die Detailseite
    historie = []
    for h in r.history.select_related("history_user")[:10]:
        prev = h.prev_record
        felder = []
        if prev:
            delta = h.diff_against(prev)
            felder = [c.field for c in delta.changes]
        historie.append({
            "zeit": h.history_date, "nutzer": h.history_user,
            "art": {"+": "angelegt", "~": "geändert", "-": "gelöscht"}.get(h.history_type, "?"),
            "felder": ", ".join(felder),
        })
    return render(request, "nachweis/rechnung_detail.html", {
        "aktiv": "abrechnung", "r": r, "positionen": _positionen(r),
        "monatsname": MONATSNAMEN[r.monat], "RS": Rechnungsstatus,
        "absender": getattr(settings, "RECHNUNG_ABSENDER", ""),
        "zahlungen": r.zahlungen.all(), "mahnungen": r.mahnungen.all(),
        "offen": r.offener_betrag, "heute": date.today().isoformat(),
        "naechste_stufe": min(r.mahnstufe + 1, 3),
        "stufen": dict(Mahnstufe.choices),
        "historie": historie,
        "gutschrift": r.gutschriften.exclude(status=Rechnungsstatus.STORNIERT).first(),
    })


@login_required
def rechnung_pdf(request, pk):
    if not services.darf_abrechnen(request.user):
        return redirect("nachweis:start")
    r = get_object_or_404(Rechnung, pk=pk)
    html = render_to_string("nachweis/rechnung_pdf.html", {
        "r": r, "positionen": _positionen(r), "monatsname": MONATSNAMEN[r.monat],
        "absender": getattr(settings, "RECHNUNG_ABSENDER", "")}, request)
    try:
        from weasyprint import HTML
    except Exception:
        return redirect(reverse("nachweis:rechnung_detail", args=[r.id]))
    pdf = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()
    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="Rechnung_{r.nummer}.pdf"'
    return resp


@login_required
def rechnung_csv(request, pk):
    if not services.darf_abrechnen(request.user):
        return redirect("nachweis:start")
    r = get_object_or_404(Rechnung, pk=pk)
    resp = HttpResponse(content_type="text/csv; charset=utf-8-sig")
    resp["Content-Disposition"] = f'attachment; filename="Rechnung_{r.nummer}.csv"'
    w = csv.writer(resp, delimiter=";")
    w.writerow(["Rechnungsnummer", "Empfänger", "Zeitraum", "Klient*in", "Aktenzeichen",
                "FLS_Soll", "FLS_Ist_einzeln", "FLS_Ist_Gruppe", "FLS_Ist", "kLE",
                "Vorschuss_EUR", "Betrag_EUR"])
    for p in _positionen(r):
        w.writerow([r.nummer, _csv_safe(r.empfaenger), r.monat_text, _csv_safe(p["name"]), _csv_safe(p["az"]),
                    f'{p["soll"]}', f'{p["einzeln"]}', f'{p["gruppe"]}', f'{p["fls"]}',
                    f'{p["kle"]}', f'{p["vorschuss"]}', f'{p["betrag"]}'])
    w.writerow([r.nummer, _csv_safe(r.empfaenger), r.monat_text, "SUMME", "", "", "", "", "", "", "",
                f"{r.betrag}"])
    return resp


@login_required
def rechnung_eabrechnung(request, pk):
    """Strukturierter Export nach § 18 Abs. 3 Anlage 4 örV (Pflichtinhalte der
    Monatsrechnung a–k) – vorbereitet für die eAbrechnung über OPEN/PROSOZ
    (Abs. 6). Das finale Übergabeformat liefert der Kostenträger beim Opt-in;
    dieser Export enthält bereits alle Felder für das Mapping."""
    if not services.darf_abrechnen(request.user):
        return redirect("nachweis:start")
    r = get_object_or_404(Rechnung, pk=pk)
    satz = services.fls_preis(r.jahr)
    resp = HttpResponse(content_type="text/csv; charset=utf-8-sig")
    resp["Content-Disposition"] = f'attachment; filename="eAbrechnung_{r.nummer}.csv"'
    w = csv.writer(resp, delimiter=";")
    w.writerow(["a_Zeitraum", "Kennzeichen", "b_EUR_je_Std_kLE", "c_Vorschuss_EUR",
                "d_FLS_Soll_Monat", "e_FLS_Ist", "e1_einzeln_erbracht", "e2_Gruppe_erbracht",
                "f_Anzahl_kLE", "g_Zwischensumme_Std", "h_Zwischenbetrag_EUR",
                "k_Rechnungsbetrag_EUR"])
    for p in _positionen(r):
        zwsumme = p["fls"] + p["kle"]
        w.writerow([r.monat_text, _csv_safe(p["az"] or p["name"]), f"{satz}", f'{p["vorschuss"]}',
                    f'{p["soll"]}', f'{p["fls"]}', f'{p["einzeln"]}', f'{p["gruppe"]}',
                    f'{p["kle"]}', f"{zwsumme}", f'{p["betrag"]}', f'{p["betrag"]}'])
    w.writerow([r.monat_text, "GESAMT", f"{satz}", "", "", "", "", "", "", "", "",
                f"{r.betrag}"])
    return resp


@require_POST
@login_required
def rechnung_status(request, pk):
    """Rechnung als gestellt/bezahlt markieren oder stornieren (gibt Positionen frei)."""
    if not services.darf_abrechnen(request.user):
        return HttpResponseForbidden()
    r = get_object_or_404(Rechnung, pk=pk)
    neu = request.POST.get("status")
    if neu in Rechnungsstatus.values:
        if neu == Rechnungsstatus.STORNIERT and r.status != Rechnungsstatus.ENTWURF:
            # Beleg-Disziplin: eine bereits GESTELLTE Rechnung war beim Kostenträger –
            # sie wird nur beleghaft per Gutschrift storniert (rechnung_gutschrift).
            messages.error(request, f"Rechnung {r.nummer} wurde bereits gestellt – bitte über "
                                    f"„Stornieren (Gutschrift)“ beleghaft stornieren.")
            return redirect(reverse("nachweis:rechnung_detail", args=[r.id]))
        if neu == Rechnungsstatus.STORNIERT and r.zahlungen.exists():
            # Geld-Schutz: Storno gäbe die Positionen zur ERNEUTEN Voll-Fakturierung frei,
            # während die gebuchten Zahlungen unsichtbar an der stornierten Rechnung hingen.
            messages.error(request, f"Rechnung {r.nummer} hat gebuchte Zahlungen "
                                    f"({r.bezahlt_summe} €) – bitte zuerst die Zahlungen löschen "
                                    f"(bzw. umbuchen), dann stornieren.")
            return redirect(reverse("nachweis:rechnung_detail", args=[r.id]))
        if neu == Rechnungsstatus.STORNIERT:
            for p in r.positionen.all():
                p.status = Freigabestatus.FREIGEGEBEN
                p.rechnung = None
                p.abgerechnet_am = None
                p.save(update_fields=["status", "rechnung", "abgerechnet_am", "geaendert"])
            messages.success(request, f"Rechnung {r.nummer} storniert – Nachweise wieder freigegeben.")
        else:
            messages.success(request, f"Rechnung {r.nummer}: {dict(Rechnungsstatus.choices)[neu]}.")
        r.status = neu
        r.save(update_fields=["status"])
    return redirect(reverse("nachweis:rechnung_detail", args=[r.id]))


@require_POST
@login_required
def rechnung_gutschrift(request, pk):
    """Gestellte Rechnung beleghaft stornieren: Gutschrift erzeugen (services.gutschrift_erstellen)."""
    if not services.darf_abrechnen(request.user):
        return HttpResponseForbidden()
    r = get_object_or_404(Rechnung, pk=pk)
    g, fehler = services.gutschrift_erstellen(r, services.mitarbeiter_fuer(request.user))
    if fehler:
        messages.error(request, fehler)
        return redirect(reverse("nachweis:rechnung_detail", args=[r.id]))
    messages.success(request, f"Gutschrift {g.nummer} über {_eur(g.betrag)} € erstellt – "
                              f"Rechnung {r.nummer} ist storniert, die Nachweise sind wieder freigegeben.")
    return redirect(reverse("nachweis:rechnung_detail", args=[g.id]))


@login_required
def rechnung_xrechnung(request, pk):
    """XRechnung 3.0 (UBL-XML) einer Rechnung herunterladen – für OZG-RE (Berlin)."""
    if not services.darf_abrechnen(request.user):
        return redirect("nachweis:start")
    from . import xrechnung
    r = get_object_or_404(Rechnung, pk=pk)
    if r.typ == Rechnungstyp.GUTSCHRIFT:
        # XRechnung-Gutschrift ist ein eigenes UBL-Dokument (CreditNote) – noch nicht gebaut.
        messages.info(request, "Gutschriften werden aktuell als PDF/Druck übermittelt – "
                               "die XRechnung-Gutschrift (UBL CreditNote) folgt bei Bedarf.")
        return redirect(reverse("nachweis:rechnung_detail", args=[r.id]))
    probleme = xrechnung.pruefe_voraussetzungen(r)
    if probleme:
        for p in probleme:
            messages.error(request, p)
        messages.info(request, "Bitte Stammdaten/Leitweg-ID ergänzen, dann erneut exportieren.")
        return redirect(reverse("nachweis:rechnung_detail", args=[r.id]))
    xml = xrechnung.build_ubl(r)
    resp = HttpResponse(xml, content_type="application/xml; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="XRechnung_{r.nummer}.xml"'
    return resp


@login_required
def rechnungssteller(request):
    """Stammdaten des Rechnungsstellers (Verkäufer) für die E-Rechnung pflegen."""
    if not services.darf_abrechnen(request.user):
        return redirect("nachweis:start")
    s = Rechnungssteller.load()
    if request.method == "POST":
        for f in ("name", "strasse", "plz", "ort", "land", "ust_id", "steuernummer",
                  "iban", "bic", "bank", "kontakt_name", "kontakt_tel", "kontakt_mail",
                  "befreiungsgrund"):
            setattr(s, f, (request.POST.get(f) or "").strip())
        s.land = s.land or "DE"
        s.zahlungsziel_tage = int(request.POST.get("zahlungsziel_tage") or 30)
        s.ust_befreit = request.POST.get("ust_befreit") == "on"
        s.befreiungsgrund = s.befreiungsgrund or "Steuerfrei nach § 4 Nr. 16 UStG"
        s.save()
        messages.success(request, "Rechnungssteller-Stammdaten gespeichert.")
        return redirect("nachweis:rechnungssteller")
    return render(request, "nachweis/rechnungssteller.html", {
        "aktiv": "abrechnung", "s": s, "vollstaendig": s.vollstaendig})


# ---------------------------------------------------------------- Offene Posten / Mahnwesen
@login_required
def offene_posten(request):
    """OP-Liste (Verwaltung): gestellte, unbezahlte Rechnungen mit Fälligkeit,
    Überfälligkeit und Mahnstand. Grundlage des Mahnwesens."""
    if not services.darf_abrechnen(request.user):
        return redirect("nachweis:start")
    heute = date.today()
    offene = [r for r in Rechnung.objects.filter(status=Rechnungsstatus.GESTELLT)
              .prefetch_related("zahlungen", "mahnungen") if r.offener_betrag > 0]
    zeilen = []
    for r in offene:
        tage = r.tage_ueberfaellig(heute)
        zeilen.append({"r": r, "offen": r.offener_betrag, "faellig": r.faelligkeit,
                       "tage": tage, "ueberfaellig": tage > 0, "stufe": r.mahnstufe})
    zeilen.sort(key=lambda z: -z["tage"])
    return render(request, "nachweis/offene_posten.html", {
        "aktiv": "abrechnung", "zeilen": zeilen,
        "summe_offen": sum((z["offen"] for z in zeilen), Decimal("0")),
        "summe_ueberfaellig": sum((z["offen"] for z in zeilen if z["ueberfaellig"]), Decimal("0")),
        "n_ueberfaellig": sum(1 for z in zeilen if z["ueberfaellig"]),
    })


@require_POST
@login_required
def zahlung_erfassen(request, pk):
    """Zahlungseingang zu einer Rechnung buchen (Teilzahlung möglich)."""
    if not services.darf_abrechnen(request.user):
        return HttpResponseForbidden()
    r = get_object_or_404(Rechnung, pk=pk)
    if r.status != Rechnungsstatus.GESTELLT:
        # Nur gestellte Rechnungen erhalten Zahlungen: ein Entwurf war nie beim Kostenträger,
        # eine bezahlte/stornierte darf ihren Status hier nicht ändern.
        messages.error(request, "Zahlungen können nur auf gestellte Rechnungen gebucht werden.")
        return redirect(reverse("nachweis:rechnung_detail", args=[r.id]))
    try:
        betrag = Decimal((request.POST.get("betrag") or "").replace(",", ".").strip())
        if not betrag.is_finite():
            betrag = Decimal("0")
    except Exception:
        betrag = Decimal("0")
    if betrag <= 0:
        messages.error(request, "Bitte einen Zahlbetrag > 0 angeben.")
        return redirect(reverse("nachweis:rechnung_detail", args=[r.id]))
    if betrag > r.offener_betrag:
        messages.error(request, f"Zahlbetrag {_eur(betrag)} € übersteigt den offenen Betrag "
                                f"{_eur(r.offener_betrag)} € – bitte prüfen (Überzahlung wird nicht gebucht).")
        return redirect(reverse("nachweis:rechnung_detail", args=[r.id]))
    try:
        datum = date.fromisoformat(request.POST.get("datum"))
    except (TypeError, ValueError):
        datum = date.today()
    Zahlung.objects.create(rechnung=r, datum=datum, betrag=betrag,
                           notiz=(request.POST.get("notiz") or "").strip()[:200],
                           erfasst_von=services.mitarbeiter_fuer(request.user))
    r.refresh_from_db()
    rest = r.offener_betrag
    if rest <= 0:
        messages.success(request, f"Zahlung über {_eur(betrag)} € gebucht – Rechnung {r.nummer} ist bezahlt.")
    else:
        messages.success(request, f"Teilzahlung über {_eur(betrag)} € gebucht – offen bleiben {_eur(rest)} €.")
    return redirect(reverse("nachweis:rechnung_detail", args=[r.id]))


@require_POST
@login_required
def zahlung_loeschen(request):
    if not services.darf_abrechnen(request.user):
        return HttpResponseForbidden()
    z = get_object_or_404(Zahlung, pk=_int(request.POST.get("id"), 0))
    rid = z.rechnung_id
    z.delete()
    messages.success(request, "Zahlung gelöscht – Zahlungsstand aktualisiert.")
    return redirect(reverse("nachweis:rechnung_detail", args=[rid]))


@require_POST
@login_required
def mahnung_erstellen(request, pk):
    """Nächste Mahnstufe (Zahlungserinnerung → 1. → 2. Mahnung) anlegen."""
    if not services.darf_abrechnen(request.user):
        return HttpResponseForbidden()
    from django.db import IntegrityError, transaction
    frist = max(1, min(_int(request.POST.get("frist_tage"), 14), 60))
    heute = date.today()
    try:
        with transaction.atomic():
            # Lock gegen Doppelklick/Race: sonst entstehen zwei Stufen am selben Tag
            # oder ein IntegrityError-500 (UniqueConstraint je Stufe).
            r = get_object_or_404(Rechnung.objects.select_for_update(), pk=pk)
            if not r.ist_offen:
                messages.error(request, "Nur offene (gestellte, unbezahlte) Rechnungen können gemahnt werden.")
                return redirect(reverse("nachweis:rechnung_detail", args=[r.id]))
            letzte = r.mahnungen.order_by("-stufe").first()
            stufe = (letzte.stufe if letzte else 0) + 1
            if stufe > 3:
                messages.error(request, "Höchste Mahnstufe bereits erreicht (2. Mahnung).")
                return redirect(reverse("nachweis:rechnung_detail", args=[r.id]))
            if letzte is None and r.tage_ueberfaellig(heute) <= 0:
                messages.error(request, f"Die Rechnung ist erst am {r.faelligkeit:%d.%m.%Y} fällig – "
                                        f"eine Zahlungserinnerung vor Fälligkeit ist nicht üblich.")
                return redirect(reverse("nachweis:rechnung_detail", args=[r.id]))
            if letzte is not None and heute <= letzte.zahlbar_bis:
                messages.error(request, f"Die Frist der letzten Mahnstufe läuft noch "
                                        f"(zahlbar bis {letzte.zahlbar_bis:%d.%m.%Y}) – nächste Stufe erst danach.")
                return redirect(reverse("nachweis:rechnung_detail", args=[r.id]))
            m = Mahnung.objects.create(rechnung=r, stufe=stufe, datum=heute, frist_tage=frist,
                                       notiz=(request.POST.get("notiz") or "").strip()[:200],
                                       erstellt_von=services.mitarbeiter_fuer(request.user))
    except IntegrityError:
        messages.error(request, "Diese Mahnstufe wurde soeben bereits erstellt (Doppelklick?).")
        return redirect(reverse("nachweis:rechnung_detail", args=[pk]))
    messages.success(request, f"{m.get_stufe_display()} erstellt – Schreiben kann jetzt gedruckt werden.")
    return redirect(reverse("nachweis:mahnung_druck", args=[m.id]))


@login_required
def mahnung_druck(request, pk):
    """Mahnschreiben als druckfertige Seite (Browser-Druck/PDF)."""
    if not services.darf_abrechnen(request.user):
        return redirect("nachweis:start")
    m = get_object_or_404(Mahnung.objects.select_related("rechnung"), pk=pk)
    r = m.rechnung
    return render(request, "nachweis/mahnung_druck.html", {
        "m": m, "r": r, "offen": r.offener_betrag, "bezahlt": r.bezahlt_summe,
        "monatsname": MONATSNAMEN[r.monat],
        "steller": Rechnungssteller.load(),
    })

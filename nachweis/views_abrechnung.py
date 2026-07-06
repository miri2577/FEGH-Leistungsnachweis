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
from .models import Monatsfreigabe, Rechnung, Freigabestatus, Rechnungsstatus

MONATSNAMEN = ["", "Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
               "August", "September", "Oktober", "November", "Dezember"]


def _int(val, default):
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


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
    return render(request, "nachweis/rechnung_detail.html", {
        "aktiv": "abrechnung", "r": r, "positionen": _positionen(r),
        "monatsname": MONATSNAMEN[r.monat], "RS": Rechnungsstatus,
        "absender": getattr(settings, "RECHNUNG_ABSENDER", ""),
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
        w.writerow([r.nummer, r.empfaenger, r.monat_text, p["name"], p["az"],
                    f'{p["soll"]}', f'{p["einzeln"]}', f'{p["gruppe"]}', f'{p["fls"]}',
                    f'{p["kle"]}', f'{p["vorschuss"]}', f'{p["betrag"]}'])
    w.writerow([r.nummer, r.empfaenger, r.monat_text, "SUMME", "", "", "", "", "", "", "",
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
        w.writerow([r.monat_text, p["az"] or p["name"], f"{satz}", f'{p["vorschuss"]}',
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

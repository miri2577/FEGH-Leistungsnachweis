"""Barbetrags-/Verwahrgeldverwaltung: treuhänderische Klientenkonten je Klient*in
(besondere Wohnformen). Personenbeziehbar → streng team-gescopt über klienten_fuer
(Verwaltung/Admin haben KEINEN Klientenbezug). Prüfungsrelevant.
"""
from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponseForbidden
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_POST

from . import services
from .models import Klientenkonto, Kontobuchung, KlientenkontoTyp


def _klient(request, pk):
    return get_object_or_404(services.klienten_fuer(request.user), pk=pk)


def _dec(s):
    try:
        return Decimal((s or "").replace(",", ".").strip())
    except (InvalidOperation, AttributeError):
        return None


def _datum(s):
    try:
        return date.fromisoformat((s or "").strip())
    except (ValueError, TypeError):
        return None


@login_required
def klientenkonto(request, pk):
    """Fallakten-Reiter: Barbetrags-/Verwahrgeldkonten der Klient*in mit Buchungen."""
    klient = _klient(request, pk)
    konten = list(klient.konten.prefetch_related("buchungen"))
    for k in konten:
        k.saldo_wert = k.saldo
        k.buchungsliste = list(k.buchungen.all()[:25])
    return render(request, "nachweis/klientenkonto.html", {
        "aktiv": "belegungsliste" if services.ist_leitung(request.user) else "start",
        "klient": klient, "konten": konten, "typen": KlientenkontoTyp.choices,
        "heute": date.today().isoformat(),
    })


@require_POST
@login_required
def konto_anlegen(request, pk):
    klient = _klient(request, pk)
    typ = request.POST.get("typ")
    Klientenkonto.objects.create(
        klient=klient,
        typ=typ if typ in KlientenkontoTyp.values else KlientenkontoTyp.BARBETRAG,
        bezeichnung=(request.POST.get("bezeichnung") or "").strip()[:80])
    messages.success(request, "Konto angelegt.")
    return redirect("nachweis:klientenkonto", pk=klient.id)


@require_POST
@login_required
def kontobuchung_speichern(request, pk):
    klient = _klient(request, pk)
    betrag = _dec(request.POST.get("betrag"))
    zweck = (request.POST.get("zweck") or "").strip()
    datum = _datum(request.POST.get("datum")) or date.today()
    if betrag is None or betrag == 0 or not zweck:
        messages.error(request, "Bitte Betrag (≠ 0) und Zweck angeben.")
        return redirect("nachweis:klientenkonto", pk=klient.id)
    with transaction.atomic():
        konto = get_object_or_404(
            Klientenkonto.objects.select_for_update().filter(klient=klient),
            pk=request.POST.get("konto"))
        # Treuhänderisches Konto darf nicht ins Minus (Auszahlung > Kontostand).
        if betrag < 0 and konto.saldo + betrag < 0:
            messages.error(request, f"Auszahlung übersteigt den Kontostand ({konto.saldo} €) – "
                                    f"das treuhänderische Konto darf nicht ins Minus gehen.")
            return redirect("nachweis:klientenkonto", pk=klient.id)
        Kontobuchung.objects.create(
            konto=konto, datum=datum, betrag=betrag, zweck=zweck[:160],
            beleg_nr=(request.POST.get("beleg_nr") or "").strip()[:40],
            erfasst_von=services.mitarbeiter_fuer(request.user))
    messages.success(request, "Buchung erfasst.")
    return redirect("nachweis:klientenkonto", pk=klient.id)


@require_POST
@login_required
def kontobuchung_loeschen(request, pk):
    klient = _klient(request, pk)
    b = get_object_or_404(Kontobuchung.objects.filter(konto__klient=klient),
                          pk=request.POST.get("id"))
    b.delete()
    messages.success(request, "Buchung gelöscht.")
    return redirect("nachweis:klientenkonto", pk=klient.id)


@require_POST
@login_required
def konto_loeschen(request, pk):
    klient = _klient(request, pk)
    konto = get_object_or_404(klient.konten, pk=request.POST.get("id"))
    if konto.buchungen.exists():
        messages.error(request, "Konto mit Buchungen kann nicht gelöscht werden "
                                "(Prüfhistorie) – bitte stattdessen deaktivieren.")
    else:
        konto.delete()
        messages.success(request, "Konto gelöscht.")
    return redirect("nachweis:klientenkonto", pk=klient.id)

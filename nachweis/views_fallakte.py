"""Klient-Fallakte: zentrale Detailseite je Klient*in mit Reiter-Navigation.

Die Fallakte ist der Einstieg von der Belegungsliste („Öffnen"). Der Kopf +
die Reiter-Leiste (_fallakte_kopf.html) sind auf allen fallbezogenen Unterseiten
gleich (Übersicht/Kostenzusage/Teilhabe/Berichte/Dokumente/Verlauf), sodass die
Navigation einheitlich ist. Zugriff wie die übrigen Klient-Seiten (team-gescopt).
"""
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Max, Q
from django.shortcuts import render, get_object_or_404

from . import services
from .models import ZielStatus, Leistungsart


@login_required
def klient_detail(request, pk):
    """Übersichts-Reiter: Kennzahlen, Fälligkeiten, Bestände auf einen Blick."""
    klient = get_object_or_404(
        services.klienten_fuer(request.user).select_related("team", "bezugsbetreuer"),
        pk=pk)
    hinweise = services.klient_hinweise(klient)
    letzte_doku = list(klient.leistungen.exclude(dokumentation="")
                       .select_related("betreuer").order_by("-datum", "-id")[:5])
    zaehler = {
        "ziele_aktiv": klient.ziele.filter(status=ZielStatus.AKTIV).count(),
        "berichte": klient.berichte.count(),
        "dokumente": klient.dokumente.count(),
        "wirkung": klient.wirkungseinschaetzungen.count(),
        "bewilligungen": klient.bewilligungen.count(),
    }
    return render(request, "nachweis/klient_detail.html", {
        "aktiv": "belegungsliste" if services.ist_leitung(request.user) else "start",
        "klient": klient, "hinweise": hinweise, "zaehler": zaehler,
        "letzte_doku": letzte_doku,
        "aktive_bewilligung": klient.aktive_bewilligung(),
    })


@login_required
def klient_verlauf(request, pk):
    """Verlaufs-Reiter: chronologische Verlaufsdokumentation (nur dokumentierte
    Leistungen), read-only. Zielbezüge werden mit ausgewiesen."""
    klient = get_object_or_404(services.klienten_fuer(request.user), pk=pk)
    eintraege = list(klient.leistungen.exclude(dokumentation="")
                     .select_related("betreuer").prefetch_related("ziele")
                     .order_by("-datum", "-beginn", "-id"))
    return render(request, "nachweis/klient_verlauf.html", {
        "aktiv": "belegungsliste" if services.ist_leitung(request.user) else "start",
        "klient": klient, "eintraege": eintraege,
    })

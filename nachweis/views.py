from datetime import date

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from . import services
from .models import Mitarbeiter, Leistung, Gruppe, Klient


def _summe(zeilen, n_do, ts_pro):
    return {
        "kontingent_jahr": sum((z["kontingent_jahr"] for z in zeilen), 0),
        "ist": sum((z["ist"] for z in zeilen), 0),
        "rest": sum((z["rest"] for z in zeilen), 0),
        "n_donnerstage": n_do,
        "ts_pro_klient_jahr": ts_pro,
    }


@login_required
def dashboard(request):
    """Fachleistungsstunden-Übersicht (wie Excel-Tab), optional nach Betreuer*in gefiltert."""
    jahr = int(request.GET.get("jahr") or date.today().year)
    betreuer_id = request.GET.get("betreuer") or ""

    zeilen, summe = services.fachleistungsstunden(jahr)
    if betreuer_id:
        zeilen = [z for z in zeilen if str(z["betreuer"].id) == betreuer_id]
        summe = _summe(zeilen, summe["n_donnerstage"], summe["ts_pro_klient_jahr"])

    context = {
        "aktiv": "dashboard",
        "jahr": jahr,
        "zeilen": zeilen,
        "summe": summe,
        "betreuer_liste": Mitarbeiter.objects.filter(aktiv=True),
        "betreuer_id": betreuer_id,
        "kennzahlen": {
            "klienten": Klient.objects.count(),
            "mitarbeiter": Mitarbeiter.objects.filter(aktiv=True).count(),
            "leistungen": Leistung.objects.filter(datum__year=jahr).count(),
            "gruppen": Gruppe.objects.filter(datum__year=jahr).count(),
        },
    }
    return render(request, "nachweis/dashboard.html", context)

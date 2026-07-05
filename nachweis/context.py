from django.conf import settings

from . import services


def globale(request):
    """Stellt globale Werte (Wiki-URL, Rollen-Flags, offene Freigaben) allen Templates bereit."""
    if not request.user.is_authenticated:
        return {"WIKI_URL": getattr(settings, "WIKI_URL", "")}
    me = services.mitarbeiter_fuer(request.user)
    ist_leitung = services.ist_leitung(request.user)
    az_offen = 0
    if ist_leitung:
        from .models import Arbeitszeit, Genehmigungsstatus
        az_offen = Arbeitszeit.objects.filter(
            status=Genehmigungsstatus.BEANTRAGT,
            mitarbeiter__team__in=services.teams_fuer(request.user)).count()
    # Offene Abrechnungsschritte: Verwaltung = freigegebene (zu berechnen),
    # Leitung = eingereichte (zu prüfen).
    abr_offen = 0
    from .models import Monatsfreigabe, Freigabestatus
    if services.darf_abrechnen(request.user):
        abr_offen = Monatsfreigabe.objects.filter(status=Freigabestatus.FREIGEGEBEN).count()
    elif ist_leitung:
        abr_offen = Monatsfreigabe.objects.filter(
            status=Freigabestatus.EINGEREICHT,
            klient__team__in=services.teams_fuer(request.user)).count()
    return {
        "WIKI_URL": getattr(settings, "WIKI_URL", ""),
        "nav_me": me,
        "nav_ist_leitung": ist_leitung,
        "nav_ist_admin": services.ist_admin(request.user),
        "nav_ist_verwaltung": bool(me and me.ist_verwaltung),
        "nav_az_offen": az_offen,
        "nav_abr_offen": abr_offen,
        "nav_hat_kasse": services.kassen_fuer(request.user).exists(),
        "IDLE_TIMEOUT_SEC": getattr(settings, "SESSION_IDLE_TIMEOUT", 0),
    }

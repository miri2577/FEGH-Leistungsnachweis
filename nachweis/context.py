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
    # Offene meldepflichtige Vorkommnisse (Meldung noch nicht dokumentiert) – rotes
    # Signal im Nav (WTG: unverzüglich melden). Scoping wie die Vorkommnis-Seite:
    # Leitung = Team, sonst selbst erfasste; Verwaltung/Admin sehen keine.
    vork_meldung = 0
    if me and not services.ohne_klientenarbeit(request.user):
        from .models import Vorkommnis, VorkommnisStatus
        q = (Vorkommnis.objects
             .filter(kategorie__in=Vorkommnis.MELDEPFLICHTIG, gemeldet_am__isnull=True)
             .exclude(status=VorkommnisStatus.ABGESCHLOSSEN))
        q = (q.filter(team__in=services.teams_fuer(request.user)) if ist_leitung
             else q.filter(erstellt_von=me))
        vork_meldung = q.count()
    return {
        "WIKI_URL": getattr(settings, "WIKI_URL", ""),
        "nav_me": me,
        "nav_ist_leitung": ist_leitung,
        "nav_ist_admin": services.ist_admin(request.user),
        "nav_ist_verwaltung": bool(me and me.ist_verwaltung),
        "nav_az_offen": az_offen,
        "nav_abr_offen": abr_offen,
        "nav_vork_meldung": vork_meldung,
        "nav_hat_kasse": services.kassen_fuer(request.user).exists(),
        "IDLE_TIMEOUT_SEC": getattr(settings, "SESSION_IDLE_TIMEOUT", 0),
    }

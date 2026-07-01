from django.conf import settings

from . import services


def globale(request):
    """Stellt globale Werte (Wiki-URL, Rollen-Flags) allen Templates bereit."""
    me = services.mitarbeiter_fuer(request.user) if request.user.is_authenticated else None
    return {
        "WIKI_URL": getattr(settings, "WIKI_URL", ""),
        "nav_me": me,
        "nav_ist_leitung": services.ist_leitung(request.user) if request.user.is_authenticated else False,
        "nav_ist_admin": services.ist_admin(request.user) if request.user.is_authenticated else False,
        "nav_ist_verwaltung": bool(me and me.ist_verwaltung),
    }

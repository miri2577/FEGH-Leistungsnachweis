from django.conf import settings


def globale(request):
    """Stellt globale Werte (z. B. die externe Wiki-URL) allen Templates bereit."""
    return {"WIKI_URL": getattr(settings, "WIKI_URL", "")}

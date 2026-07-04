from django.contrib import admin
from django.db import connection
from django.http import HttpResponse
from django.urls import include, path


def healthz(request):
    """Leichtgewichtiger Health-Check für externes Uptime-Monitoring (ohne Login).
    Prüft die DB-Verbindung und liefert 200 'ok' bzw. 503 – keine sensiblen Infos.
    Ziel für einen externen Uptime-Monitor: https://<domain>/healthz"""
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
    except Exception:
        return HttpResponse("db-fehler", status=503, content_type="text/plain")
    return HttpResponse("ok", content_type="text/plain")


urlpatterns = [
    path("healthz", healthz),
    path("admin/", admin.site.urls),
    path("", include("nachweis.urls")),
]

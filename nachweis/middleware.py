"""Erzwingt Zwei-Faktor (TOTP) für eingeloggte, aber nicht OTP-verifizierte Nutzer.

Greift, wenn OTP_REQUIRED gesetzt ist ODER der Nutzer bereits ein bestätigtes Gerät hat
(=> Opt-in im Prototyp funktioniert, "für alle verpflichtend" per Setting umschaltbar).
Ausgenommen sind nur Login/Logout, die 2FA-Seiten selbst und statische Dateien.
Auch der Break-Glass-Superuser unterliegt der 2FA-Pflicht (TOTP + Recovery-Codes) –
die letzte Rückfallebene im Notfall ist der Server-Shell-Zugang (manage.py), nicht
der Web-Login. So ist nicht ausgerechnet das mächtigste Konto nur passwortgeschützt.
"""
import secrets
import time as _time

from django.conf import settings
from django.contrib.auth import logout as _logout
from django.db import connection
from django.shortcuts import redirect
from django.urls import reverse

from .services import _superuser_ohne_profil


class RLSKontext:
    """Setzt pro Request die PostgreSQL-Session-Variablen für Row-Level-Security:
    app.team_ids = die sichtbaren Team-IDs, app.bypass = 'on' für den Break-Glass-
    Superuser. Ist HARMLOS, solange keine RLS-Policies aktiv sind – scharf schaltet
    sie ausschließlich 'manage.py rls_setup --enable' (opt-in). Nur PostgreSQL;
    auf SQLite (lokal) ein No-Op. Migrationen/Management laufen ohne gesetzte
    Variablen und haben damit vollen Zugriff (Policy erlaubt NULL-Kontext)."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if connection.vendor != "postgresql":
            return self.get_response(request)
        u = getattr(request, "user", None)
        teams, bypass = "", "off"
        if u is not None and u.is_authenticated:
            from . import services
            if u.is_superuser or _superuser_ohne_profil(u):
                bypass = "on"
            else:
                teams = ",".join(str(i) for i in services.teams_fuer(u).values_list("id", flat=True))
        try:
            with connection.cursor() as cur:
                cur.execute("SELECT set_config('app.team_ids', %s, false)", [teams])
                cur.execute("SELECT set_config('app.bypass', %s, false)", [bypass])
            return self.get_response(request)
        finally:
            try:
                with connection.cursor() as cur:
                    cur.execute("SELECT set_config('app.team_ids', '', false)")
                    cur.execute("SELECT set_config('app.bypass', 'off', false)")
            except Exception:
                pass


class InaktivitaetsAbmeldung:
    """Meldet eingeloggte Nutzer*innen nach SESSION_IDLE_TIMEOUT Sekunden ohne Aktivität
    automatisch ab (serverseitig erzwungen, auch ohne JavaScript). Jede Anfrage gilt als
    Aktivität und setzt den Timer zurück (gleitendes Fenster). Bei sensiblen Daten Pflicht."""
    def __init__(self, get_response):
        self.get_response = get_response
        self.timeout = getattr(settings, "SESSION_IDLE_TIMEOUT", 0)

    def __call__(self, request):
        u = request.user
        if self.timeout and u.is_authenticated and not request.path.startswith(settings.STATIC_URL):
            jetzt = int(_time.time())
            letzte = request.session.get("last_activity")
            if letzte and (jetzt - letzte) > self.timeout:
                _logout(request)
                login = reverse("nachweis:login")
                if request.path != login:
                    return redirect(f"{login}?timeout=1")
            else:
                request.session["last_activity"] = jetzt
        return self.get_response(request)


class OTPErzwingenMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def _exempt(self, request):
        pfad = request.path
        # Statische Dateien und die Admin-LOGIN-Seite ausnehmen – aber NICHT den
        # ganzen /admin/-Bereich (sonst wäre 2FA auf der sensibelsten Oberfläche umgehbar).
        if pfad.startswith(settings.STATIC_URL) or pfad == "/admin/login/":
            return True
        return pfad in {
            reverse("nachweis:login"),
            reverse("nachweis:logout"),
            reverse("nachweis:2fa_verify"),
            reverse("nachweis:2fa_setup"),
        }

    def __call__(self, request):
        u = request.user
        if (u.is_authenticated and not u.is_verified()
                and not self._exempt(request)):
            hat_device = u.totpdevice_set.filter(confirmed=True).exists()
            if settings.OTP_REQUIRED or hat_device:
                ziel = "nachweis:2fa_verify" if hat_device else "nachweis:2fa_setup"
                return redirect(f"{reverse(ziel)}?next={request.get_full_path()}")
        return self.get_response(request)


# Content-Security-Policy: script-src OHNE 'unsafe-inline' – stattdessen ein pro Request
# frisch gewürfeltes nonce (an request.csp_nonce; die Inline-<script> tragen es, die früheren
# Inline-Handler wurden nach aktionen.js ausgelagert). Damit führt der Browser eingeschleustes
# Inline-JS NICHT mehr aus (zweite XSS-Verteidigung hinter Djangos Auto-Escaping). style-src
# behält 'unsafe-inline' bewusst: 858 Inline-style-Attribute wären unverhältnismäßig, und
# CSS-Injection ist ein weit geringeres Risiko. {nonce} wird pro Request ersetzt.
DEFAULT_CSP = (
    "default-src 'self'; "
    "img-src 'self' data:; "
    "style-src 'self' 'unsafe-inline'; "
    "script-src 'self' 'nonce-{nonce}'; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "object-src 'none'"
)


class CSPMiddleware:
    """Setzt eine Content-Security-Policy (Defense-in-Depth gegen XSS/Datenabfluss).
    Standard: Report-Only (bricht nichts). settings.CSP_ENFORCE=True schaltet scharf;
    optionales settings.CSP_REPORT_URI hängt eine report-uri an. Pro Request wird ein
    nonce erzeugt und – VOR dem View-Rendering – an request.csp_nonce gelegt, damit die
    Templates es in ihre <script>-Tags schreiben können."""
    def __init__(self, get_response):
        self.get_response = get_response
        self.base = getattr(settings, "CSP_POLICY", DEFAULT_CSP)
        self.report_uri = getattr(settings, "CSP_REPORT_URI", "")
        self.enforce = getattr(settings, "CSP_ENFORCE", False)

    def __call__(self, request):
        nonce = secrets.token_urlsafe(16)
        request.csp_nonce = nonce
        resp = self.get_response(request)
        policy = self.base.replace("{nonce}", nonce)
        if self.report_uri:
            policy = f"{policy}; report-uri {self.report_uri}"
        header = "Content-Security-Policy" if self.enforce else "Content-Security-Policy-Report-Only"
        # Nicht überschreiben, falls schon gesetzt (z. B. durch einen Reverse-Proxy).
        if ("Content-Security-Policy" not in resp
                and "Content-Security-Policy-Report-Only" not in resp):
            resp[header] = policy
        return resp

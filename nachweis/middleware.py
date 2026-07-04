"""Erzwingt Zwei-Faktor (TOTP) für eingeloggte, aber nicht OTP-verifizierte Nutzer.

Greift, wenn OTP_REQUIRED gesetzt ist ODER der Nutzer bereits ein bestätigtes Gerät hat
(=> Opt-in im Prototyp funktioniert, "für alle verpflichtend" per Setting umschaltbar).
Ausgenommen: Login/Logout, die 2FA-Seiten selbst, statische Dateien und der
Break-Glass-Superuser ohne Mitarbeiter-Profil.
"""
import time as _time

from django.conf import settings
from django.contrib.auth import logout as _logout
from django.shortcuts import redirect
from django.urls import reverse

from .services import _superuser_ohne_profil


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
                and not _superuser_ohne_profil(u)
                and not self._exempt(request)):
            hat_device = u.totpdevice_set.filter(confirmed=True).exists()
            if settings.OTP_REQUIRED or hat_device:
                ziel = "nachweis:2fa_verify" if hat_device else "nachweis:2fa_setup"
                return redirect(f"{reverse(ziel)}?next={request.get_full_path()}")
        return self.get_response(request)

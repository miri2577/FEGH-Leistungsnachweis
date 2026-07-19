"""Zwei-Faktor (TOTP) – Enrollment, Verifikation, Recovery-Codes.
QR-Code wird lokal als SVG gerendert (kein CDN). Auf django-otp aufgesetzt.
"""
import io

import qrcode
import qrcode.image.svg
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods
from django_otp import login as otp_login, match_token
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice


def _svg_qr(config_url: str) -> str:
    """otpauth://-URI als Inline-SVG-QR (lokal, ohne Pillow, ohne CDN)."""
    img = qrcode.make(config_url, image_factory=qrcode.image.svg.SvgPathImage)
    buf = io.BytesIO()
    img.save(buf)
    return buf.getvalue().decode()


def _recovery_codes_neu(user):
    sd, _ = StaticDevice.objects.get_or_create(user=user, name="backup")
    sd.token_set.all().delete()
    codes = [StaticToken.random_token() for _ in range(10)]
    for c in codes:
        sd.token_set.create(token=c)
    return codes


@login_required
@require_http_methods(["GET", "POST"])
def zwei_faktor_setup(request):
    # Ist bereits ein bestätigtes Gerät vorhanden, ist das Enrollment abgeschlossen:
    #  - verifizierte Session      -> Statusseite (Neu-Einrichtung dort nur mit Step-up-Passwort)
    #  - NICHT verifizierte Session -> NICHT erneut enrollen! Sonst könnte jemand, der nur das
    #    Passwort kennt (Phishing/Reuse), ein EIGENES Gerät registrieren und so den zweiten Faktor
    #    umgehen. Stattdessen zwingend erst mit dem vorhandenen Faktor verifizieren.
    if request.user.totpdevice_set.filter(confirmed=True).exists():
        if request.user.is_verified():
            return redirect("nachweis:2fa_status")
        return redirect("nachweis:2fa_verify")
    # Ab hier: KEIN bestätigtes Gerät -> Erst-Einrichtung ist erlaubt.
    # Genau EIN unbestätigtes Gerät verwenden (Race-sicher: Duplikate bereinigen)
    unbestaetigt = list(request.user.totpdevice_set.filter(confirmed=False).order_by("id"))
    if unbestaetigt:
        device = unbestaetigt[0]
        for extra in unbestaetigt[1:]:
            extra.delete()
    else:
        device = TOTPDevice.objects.create(user=request.user, confirmed=False, name="default")
    if request.method == "POST":
        if device.verify_token(request.POST.get("token", "").strip()):
            device.confirmed = True
            device.save()
            request.user.totpdevice_set.filter(confirmed=False).exclude(pk=device.pk).delete()
            codes = _recovery_codes_neu(request.user)
            otp_login(request, device)  # Session sofort verifizieren
            return render(request, "nachweis/2fa_codes.html", {"codes": codes})
        messages.error(request, "Code ungültig – bitte den aktuellen 6-stelligen Code eingeben.")
    return render(request, "nachweis/2fa_setup.html", {
        "svg": _svg_qr(device.config_url),
        "secret": device.bin_key.hex(),
    })


@login_required
@require_http_methods(["GET", "POST"])
def zwei_faktor_verify(request):
    if request.user.is_verified():
        return redirect("nachweis:start")
    # Kein bestätigtes Gerät -> zuerst einrichten
    if not request.user.totpdevice_set.filter(confirmed=True).exists():
        return redirect("nachweis:2fa_setup")
    if request.method == "POST":
        device = match_token(request.user, request.POST.get("token", "").strip())
        if device:
            otp_login(request, device)
            nxt = request.GET.get("next") or reverse("nachweis:start")
            if url_has_allowed_host_and_scheme(nxt, {request.get_host()}, require_https=request.is_secure()):
                return redirect(nxt)
            return redirect("nachweis:start")
        messages.error(request, "Code ungültig. Bitte erneut versuchen (auch Recovery-Code möglich).")
    return render(request, "nachweis/2fa_verify.html")


@login_required
def zwei_faktor_status(request):
    aktiv = request.user.totpdevice_set.filter(confirmed=True).exists()
    sd = StaticDevice.objects.filter(user=request.user, name="backup").first()
    rest = sd.token_set.count() if sd else 0
    return render(request, "nachweis/2fa_status.html", {"aktiv": aktiv, "rest_codes": rest})


@login_required
@require_http_methods(["POST"])
def zwei_faktor_deaktivieren(request):
    # Step-up (ISO A.8.5): sicherheitskritische Aktion erfordert erneute Passwort-Eingabe,
    # damit eine übernommene/offen gelassene Session 2FA nicht einfach abschalten kann.
    if not request.user.check_password(request.POST.get("password", "")):
        messages.error(request, "Passwort falsch – Zwei-Faktor wurde NICHT deaktiviert.")
        return redirect("nachweis:2fa_status")
    request.user.totpdevice_set.all().delete()
    StaticDevice.objects.filter(user=request.user).delete()
    messages.success(request, "Zwei-Faktor wurde deaktiviert.")
    return redirect("nachweis:2fa_status")

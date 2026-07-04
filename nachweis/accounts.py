"""Onboarding-Helfer: Konten anlegen, Rollen-Rechte setzen, Aktivierungslinks.

Der Aktivierungs-/Reset-Link nutzt Djangos zustandslosen PasswordResetTokenGenerator:
Der Token hängt am Passwort-Hash + last_login + Zeitstempel und wird damit
automatisch **einmalig** (ungültig, sobald das Passwort gesetzt/geändert wurde)
und **zeitlich begrenzt** (SETTINGS.PASSWORD_RESET_TIMEOUT).
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.tokens import default_token_generator
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .models import Rolle

User = get_user_model()

# Django-Gruppen: Modell-Rechte je Rolle (DSGVO: Admin verwaltet Teams/MA, NICHT Klienten)
GRUPPEN_RECHTE = {
    "Administration": ["team", "mitarbeiter"],
    "Leitung": ["klient", "gruppe", "parameter", "leistung", "abwesenheit"],
}


def ensure_gruppen():
    """Legt die Rechte-Gruppen an bzw. aktualisiert ihre Berechtigungen (idempotent)."""
    for name, modelle in GRUPPEN_RECHTE.items():
        g, _ = Group.objects.get_or_create(name=name)
        g.permissions.set(Permission.objects.filter(
            content_type__app_label="nachweis", content_type__model__in=modelle))


def eindeutiger_benutzername(nachname, vorname=""):
    """Erzeugt einen freien Benutzernamen aus dem Nachnamen (bei Kollision …2, …3)."""
    import re
    basis = re.sub(r"[^a-z0-9]", "", (nachname or "user").lower()) or "user"
    name, i = basis, 1
    while User.objects.filter(username=name).exists():
        i += 1
        name = f"{basis}{i}"
    return name


def konto_rechte_setzen(user, rolle):
    """Setzt is_staff/is_superuser und Gruppen passend zur App-Rolle.

    WICHTIG (Sicherheits-/DSGVO-Härtung): KEINE App-Rolle bekommt Django-Admin-Zugang
    (is_staff=False). Der Django-Admin umgeht das objektbezogene Team-Scoping
    (klienten_fuer/teams_fuer) komplett – eine Leitung könnte dort teamübergreifend
    ALLE Klient*innen sehen/ändern, ein Admin sich per rolle-Feld selbst zur Leitung
    machen (Rechte-Eskalation). Team-/Mitarbeiter-/Klienten-Pflege läuft ausschließlich
    über die app-nativen, rollen- und team-gescopten Seiten. Django-Admin bleibt dem
    technischen Break-Glass-Superuser vorbehalten."""
    ensure_gruppen()
    user.is_staff = False
    user.is_superuser = False
    user.save(update_fields=["is_staff", "is_superuser"])
    # Gruppen historisch/dokumentarisch weiter zuordnen (ohne is_staff wirkungslos im Admin)
    user.groups.clear()
    if rolle == Rolle.ADMIN:
        user.groups.add(Group.objects.get(name="Administration"))
    elif rolle == Rolle.LEITUNG:
        user.groups.add(Group.objects.get(name="Leitung"))


def konto_anlegen(nachname, vorname, rolle, email=""):
    """Legt einen Login OHNE brauchbares Passwort an (Nutzer vergibt es selbst per Link)."""
    username = eindeutiger_benutzername(nachname, vorname)
    user = User.objects.create(username=username, email=email or "",
                               first_name=vorname or "", last_name=nachname or "",
                               is_active=True)
    user.set_unusable_password()
    user.save()
    konto_rechte_setzen(user, rolle)
    return user


def aktivierungs_link(request, user):
    """Absoluter, signierter Einmal-Link zum Setzen/Zurücksetzen des Passworts."""
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    pfad = reverse("nachweis:aktivieren", args=[uid, token])
    return request.build_absolute_uri(pfad)

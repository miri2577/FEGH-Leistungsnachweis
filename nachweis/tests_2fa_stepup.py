"""Test #11: 2FA-Deaktivierung erfordert erneute Passwort-Eingabe (Step-up)."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django_otp import DEVICE_ID_SESSION_KEY
from django_otp.plugins.otp_totp.models import TOTPDevice

from .models import Mitarbeiter, Team, Teamtyp, Rolle

User = get_user_model()


class ZweiFaktorStepUpTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="TBEW", typ=Teamtyp.values[0])
        self.u = User.objects.create_user(username="mirko", password="Sicher-Passwort-123")
        Mitarbeiter.objects.create(user=self.u, name="Richter", rolle=Rolle.LEITUNG, kuerzel="ri")
        self.device = TOTPDevice.objects.create(user=self.u, confirmed=True, name="default")
        self.client.force_login(self.u)
        # Session als OTP-verifiziert markieren (sonst fängt die OTP-Middleware den POST ab)
        session = self.client.session
        session[DEVICE_ID_SESSION_KEY] = self.device.persistent_id
        session.save()

    def test_falsches_passwort_deaktiviert_nicht(self):
        resp = self.client.post(reverse("nachweis:2fa_deaktivieren"), {"password": "falsch"})
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(self.u.totpdevice_set.filter(confirmed=True).exists())  # noch aktiv

    def test_fehlendes_passwort_deaktiviert_nicht(self):
        self.client.post(reverse("nachweis:2fa_deaktivieren"), {})
        self.assertTrue(self.u.totpdevice_set.filter(confirmed=True).exists())

    def test_richtiges_passwort_deaktiviert(self):
        self.client.post(reverse("nachweis:2fa_deaktivieren"), {"password": "Sicher-Passwort-123"})
        self.assertFalse(self.u.totpdevice_set.filter(confirmed=True).exists())  # weg

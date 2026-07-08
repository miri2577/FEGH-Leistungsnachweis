"""Tests für CSP-Enforce-Schalter (#12) und Rate-Limiting am Aktivierungslink (#14)."""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.contrib.auth.tokens import default_token_generator

from . import accounts
from .models import Mitarbeiter, Rolle

User = get_user_model()


class CSPHeaderTests(TestCase):
    def test_report_only_default(self):
        resp = self.client.get(reverse("nachweis:login"))
        self.assertIn("Content-Security-Policy-Report-Only", resp)
        self.assertNotIn("Content-Security-Policy", [h for h in resp.headers if h == "Content-Security-Policy"])

    @override_settings(CSP_ENFORCE=True)
    def test_enforce_setzt_scharfen_header(self):
        resp = self.client.get(reverse("nachweis:login"))
        self.assertIn("Content-Security-Policy", resp)
        self.assertIn("default-src 'self'", resp["Content-Security-Policy"])


class AktivierungRateLimitTests(TestCase):
    def setUp(self):
        cache.clear()
        self.u = accounts.konto_anlegen("Weber", "Anna", Rolle.USER)
        Mitarbeiter.objects.create(user=self.u, name="Weber", rolle=Rolle.USER, kuerzel="web")

    def _url(self):
        uid = urlsafe_base64_encode(force_bytes(self.u.pk))
        return reverse("nachweis:aktivieren", args=[uid, default_token_generator.make_token(self.u)])

    def test_zu_viele_versuche_werden_gebremst(self):
        url = self._url()
        codes = [self.client.get(url).status_code for _ in range(17)]
        self.assertNotIn(429, codes[:15])   # die ersten 15 gehen durch
        self.assertEqual(codes[-1], 429)     # danach 429

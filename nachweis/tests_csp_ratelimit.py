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

    def test_script_src_per_nonce_ohne_unsafe_inline(self):
        # Härtung: script-src trägt ein nonce statt 'unsafe-inline'; style-src behält es bewusst.
        header = self.client.get(reverse("nachweis:login"))["Content-Security-Policy-Report-Only"]
        self.assertRegex(header, r"script-src 'self' 'nonce-[^']+'")
        self.assertNotIn("script-src 'self' 'unsafe-inline'", header)
        self.assertIn("style-src 'self' 'unsafe-inline'", header)

    def test_nonce_wechselt_pro_request_und_matcht_html(self):
        import re
        # base.html-erbende (eingeloggte) Seite trägt den Header-nonce an ihren Inline-Scripts.
        u = accounts.konto_anlegen("Meier", "Tom", Rolle.USER)
        from .models import Team, Teamtyp
        team = Team.objects.create(name="TBEW", typ=Teamtyp.values[0])
        Mitarbeiter.objects.create(user=u, name="Meier", rolle=Rolle.USER, team=team, kuerzel="mei")
        u.set_password("x"); u.is_active = True; u.save()
        self.client.force_login(u)
        r1 = self.client.get(reverse("nachweis:erfassung"))
        n1 = re.search(r"'nonce-([^']+)'", r1["Content-Security-Policy-Report-Only"]).group(1)
        self.assertIn(f'nonce="{n1}"', r1.content.decode())        # nonce steht am Inline-<script>
        r2 = self.client.get(reverse("nachweis:erfassung"))
        n2 = re.search(r"'nonce-([^']+)'", r2["Content-Security-Policy-Report-Only"]).group(1)
        self.assertNotEqual(n1, n2)                                # pro Request frisch


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

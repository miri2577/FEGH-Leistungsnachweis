"""Härtungs-Tests: Content-Security-Policy-Header + rls_setup-Kommando.

RLS selbst ist PostgreSQL-only; auf der SQLite-Testdatenbank ist das Kommando ein
No-Op. Getestet wird daher nur, dass es fehlerfrei läuft – die Policies müssen auf
einer Postgres-Staging-DB verifiziert werden (siehe docs/sicherheit/rls.md)."""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase, Client


class CSPHeaderTests(TestCase):
    def test_report_only_header_gesetzt(self):
        r = Client().get("/login/")
        self.assertTrue(r.has_header("Content-Security-Policy-Report-Only"))
        pol = r["Content-Security-Policy-Report-Only"]
        self.assertIn("default-src 'self'", pol)
        self.assertIn("frame-ancestors 'none'", pol)
        self.assertIn("object-src 'none'", pol)
        # Standard ist Report-Only, nicht erzwingend:
        self.assertFalse(r.has_header("Content-Security-Policy"))


class RlsKommandoTests(TestCase):
    def test_rls_setup_laeuft_ohne_fehler(self):
        out = StringIO()
        call_command("rls_setup", stdout=out)          # SQLite: No-Op, darf nicht crashen
        self.assertIn("SQLite", out.getvalue())

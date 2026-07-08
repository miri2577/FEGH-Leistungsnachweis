"""Regressionstests für die Sicherheitsbehebungen aus dem ISO-27001-Audit."""
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from . import services, accounts
from .models import (Mitarbeiter, Team, Teamtyp, Rolle, Klient, Status,
                     Rechnung, Rechnungsstatus)

User = get_user_model()


def _mk(username, rolle, team=None, leitet=None, aktiv=True):
    u = User.objects.create_user(username=username, password="x")
    m = Mitarbeiter.objects.create(user=u, name=username.title(), rolle=rolle,
                                   team=team, kuerzel=username[:5], aktiv=aktiv)
    if leitet:
        m.leitet.set(leitet)
    return u, m


class SelfEscalationTests(TestCase):
    """Befund #1: Admin darf sich nicht selbst zur Leitung machen."""
    def setUp(self):
        self.team = Team.objects.create(name="TBEW", typ=Teamtyp.values[0])
        self.admin_u, self.admin_m = _mk("admin", Rolle.ADMIN)

    def test_admin_kann_eigene_rolle_nicht_eskalieren(self):
        self.client.force_login(self.admin_u)
        self.client.post(reverse("nachweis:mitarbeiter_bearbeiten", args=[self.admin_m.id]),
                         {"nachname": "Admin", "rolle": Rolle.LEITUNG,
                          "team": str(self.team.id), "leitet": [str(self.team.id)],
                          "wochenstunden": "39", "urlaubstage": "30"})
        self.admin_m.refresh_from_db()
        self.assertEqual(self.admin_m.rolle, Rolle.ADMIN)      # unverändert
        self.assertEqual(self.admin_m.leitet.count(), 0)
        self.assertIsNone(self.admin_m.team)
        self.assertFalse(services.ist_leitung(self.admin_u))
        self.assertEqual(services.klienten_fuer(self.admin_u).count(), 0)

    def test_admin_darf_fremdes_konto_weiter_verwalten(self):
        _u, fremd = _mk("kollege", Rolle.USER)
        self.client.force_login(self.admin_u)
        self.client.post(reverse("nachweis:mitarbeiter_bearbeiten", args=[fremd.id]),
                         {"nachname": "Kollege", "rolle": Rolle.LEITUNG,
                          "team": "", "leitet": [str(self.team.id)],
                          "wochenstunden": "39", "urlaubstage": "30"})
        fremd.refresh_from_db()
        self.assertEqual(fremd.rolle, Rolle.LEITUNG)           # fremdes Konto: erlaubt
        self.assertIn(self.team, fremd.leitet.all())

    def test_admin_kann_eigenen_namen_aendern(self):
        self.client.force_login(self.admin_u)
        self.client.post(reverse("nachweis:mitarbeiter_bearbeiten", args=[self.admin_m.id]),
                         {"nachname": "Neuname", "rolle": Rolle.ADMIN,
                          "wochenstunden": "39", "urlaubstage": "30"})
        self.admin_m.refresh_from_db()
        self.assertEqual(self.admin_m.name, "Neuname")


class ReaktivierungsSperreTests(TestCase):
    """Befund #2: Deaktiviertes Konto lässt sich nicht per Aktivierungslink reaktivieren."""
    def setUp(self):
        self.u = accounts.konto_anlegen("Weber", "Anna", Rolle.USER)
        self.m = Mitarbeiter.objects.create(user=self.u, name="Weber", rolle=Rolle.USER, kuerzel="web")

    def _link(self):
        from django.utils.http import urlsafe_base64_encode
        from django.utils.encoding import force_bytes
        from django.contrib.auth.tokens import default_token_generator
        uid = urlsafe_base64_encode(force_bytes(self.u.pk))
        return reverse("nachweis:aktivieren", args=[uid, default_token_generator.make_token(self.u)])

    def test_deaktiviertes_konto_link_ungueltig(self):
        self.m.aktiv = False
        self.m.save()
        resp = self.client.get(self._link())
        self.assertContains(resp, "", status_code=200)
        self.assertTrue(resp.context.get("ungueltig"))

    def test_aktives_konto_link_gueltig(self):
        resp = self.client.get(self._link())
        self.assertFalse(resp.context.get("ungueltig"))


class SucheProtectionTests(TestCase):
    """Befund #4: Suche nur per POST (kein PII im Query-String/Log)."""
    def setUp(self):
        self.team = Team.objects.create(name="TBEW", typ=Teamtyp.values[0])
        self.u, self.m = _mk("betr", Rolle.USER, team=self.team)

    def test_get_wird_abgelehnt(self):
        self.client.force_login(self.u)
        resp = self.client.get(reverse("nachweis:api_suche"), {"q": "Galow"})
        self.assertEqual(resp.status_code, 405)

    def test_post_funktioniert(self):
        Klient.objects.create(nachname="Galow", team=self.team, bezugsbetreuer=self.m,
                              status=Status.BETREUUNG)
        self.client.force_login(self.u)
        resp = self.client.post(reverse("nachweis:api_suche"), {"q": "Galow"})
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(resp.json()["total"], 1)


class CSVInjectionTests(TestCase):
    """Befund #6: Formel-Präfixe in CSV-Exporten werden neutralisiert."""
    def test_csv_safe(self):
        from .views_abrechnung import _csv_safe
        self.assertEqual(_csv_safe("=HYPERLINK(1)"), "'=HYPERLINK(1)")
        self.assertEqual(_csv_safe("+SUM(A1)"), "'+SUM(A1)")
        self.assertEqual(_csv_safe("@cmd"), "'@cmd")
        self.assertEqual(_csv_safe("Müller, Anna"), "Müller, Anna")   # harmlos bleibt
        self.assertEqual(_csv_safe("2026-0001"), "2026-0001")          # Ziffer-Start unverändert

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

    def test_admin_darf_fremdes_konto_verwalten_aber_nicht_zur_leitung(self):
        _u, fremd = _mk("kollege", Rolle.USER)
        self.client.force_login(self.admin_u)
        self.client.post(reverse("nachweis:mitarbeiter_bearbeiten", args=[fremd.id]),
                         {"nachname": "Kollege-Neu", "rolle": Rolle.LEITUNG,
                          "team": "", "leitet": [str(self.team.id)],
                          "wochenstunden": "39", "urlaubstage": "30"})
        fremd.refresh_from_db()
        self.assertEqual(fremd.name, "Kollege-Neu")            # Stammdaten pflegen: erlaubt
        self.assertEqual(fremd.rolle, Rolle.USER)              # Beförderung zur Leitung: blockiert
        self.assertEqual(fremd.leitet.count(), 0)

    def test_admin_kann_superuserkonto_nicht_bearbeiten(self):
        su_u, su_m = _mk("root_profil", Rolle.ADMIN)
        su_u.is_superuser = True
        su_u.save()
        self.client.force_login(self.admin_u)
        resp = self.client.post(reverse("nachweis:mitarbeiter_bearbeiten", args=[su_m.id]),
                                {"nachname": "Gehackt", "rolle": Rolle.ADMIN,
                                 "wochenstunden": "39", "urlaubstage": "30"})
        self.assertEqual(resp.status_code, 403)

    def test_admin_darf_leitung_verwalten_und_herabstufen(self):
        _u, chef = _mk("chefdrei", Rolle.LEITUNG, leitet=[self.team])
        self.client.force_login(self.admin_u)
        self.client.post(reverse("nachweis:mitarbeiter_bearbeiten", args=[chef.id]),
                         {"nachname": "Chef", "rolle": Rolle.USER,
                          "wochenstunden": "39", "urlaubstage": "30"})
        chef.refresh_from_db()
        self.assertEqual(chef.rolle, Rolle.USER)              # herabstufen: legitime Verwaltung
        self.assertEqual(chef.leitet.count(), 0)

    def test_admin_kann_leitungskonto_nicht_uebernehmen(self):
        u_chef, chef = _mk("chefzwei", Rolle.LEITUNG, leitet=[self.team])
        u_chef.set_password("altes-passwort"); u_chef.save()
        from django_otp.plugins.otp_totp.models import TOTPDevice
        TOTPDevice.objects.create(user=u_chef, confirmed=True, name="default")
        self.client.force_login(self.admin_u)
        # reset_link (Passwort-Übernahme) für ein Leitungskonto -> abgelehnt, kein Link-Screen
        resp = self.client.post(reverse("nachweis:mitarbeiter_aktion"),
                                {"id": str(chef.id), "aktion": "reset_link"})
        self.assertRedirects(resp, reverse("nachweis:mitarbeiter_liste"))
        # 2FA-Reset für ein Leitungskonto -> abgelehnt, Gerät bleibt
        self.client.post(reverse("nachweis:mitarbeiter_aktion"),
                         {"id": str(chef.id), "aktion": "twofa_reset"})
        self.assertTrue(u_chef.totpdevice_set.filter(confirmed=True).exists())

    def test_admin_darf_user_konto_weiter_zuruecksetzen(self):
        _u, user_m = _mk("betreuerx", Rolle.USER)
        self.client.force_login(self.admin_u)
        resp = self.client.post(reverse("nachweis:mitarbeiter_aktion"),
                                {"id": str(user_m.id), "aktion": "reset_link"})
        self.assertEqual(resp.status_code, 200)               # Link-Screen: Kontoführung erlaubt

    def test_admin_kann_kein_leitungskonto_anlegen(self):
        self.client.force_login(self.admin_u)
        self.client.post(reverse("nachweis:mitarbeiter_neu"),
                         {"nachname": "Neu", "vorname": "Chef", "rolle": Rolle.LEITUNG, "team": ""})
        self.assertFalse(Mitarbeiter.objects.filter(rolle=Rolle.LEITUNG).exists())

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
        from django.core.cache import cache
        cache.clear()   # Rate-Limit-Zähler (prozessweiter Cache) je Test zurücksetzen
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

"""Tests für den Leitungs-Team-Bugfix und die Vertretungs-Card."""
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from . import services
from .models import (Mitarbeiter, Team, Teamtyp, Rolle, Klient, Status,
                     Abwesenheit, AbwesenheitArt, AbwesenheitStatus)

User = get_user_model()


def _user(username, rolle, team=None, leitet=None, **kw):
    u = User.objects.create_user(username=username, password="x")
    m = Mitarbeiter.objects.create(user=u, name=username.title(), rolle=rolle,
                                   team=team, kuerzel=username[:5], **kw)
    if leitet:
        m.leitet.set(leitet)
    return u, m


class LeitungTeamTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="TBEW", typ=Teamtyp.BEW if hasattr(Teamtyp, "BEW") else Teamtyp.values[0])
        self.u_user, self.m_user = _user("mitarb", Rolle.USER, team=self.team)
        self.klient = Klient.objects.create(nachname="Galow", vorname="Andrea",
                                            team=self.team, bezugsbetreuer=self.m_user,
                                            status=Status.BETREUUNG)

    def test_leitung_ohne_team_sieht_nichts(self):
        """Reproduziert den Bug: Leitung ohne geleitetes/eigenes Team -> keine Klient*innen."""
        u, m = _user("chef", Rolle.LEITUNG)  # leitet nichts, kein Team
        self.assertFalse(services.teams_fuer(u).exists())
        self.assertEqual(services.klienten_fuer(u).count(), 0)

    def test_leitung_mit_leitet_sieht_klienten(self):
        """Fix: sobald das Team geleitet wird, sind die Klient*innen sichtbar."""
        u, m = _user("chef2", Rolle.LEITUNG, leitet=[self.team])
        self.assertEqual(services.klienten_fuer(u).count(), 1)
        self.assertIn(self.team, services.teams_fuer(u))

    def test_bearbeiten_setzt_leitet(self):
        """Die neue Bearbeiten-Seite ordnet die Leitung dem Team zu (M2M)."""
        admin_u, _ = _user("admin", Rolle.ADMIN)
        u, m = _user("chef3", Rolle.LEITUNG)
        self.client.force_login(admin_u)
        resp = self.client.post(
            reverse("nachweis:mitarbeiter_bearbeiten", args=[m.id]),
            {"nachname": "Chef3", "rolle": Rolle.LEITUNG, "team": "",
             "leitet": [str(self.team.id)], "wochenstunden": "38.5", "urlaubstage": "30"})
        self.assertEqual(resp.status_code, 302)
        m.refresh_from_db()
        self.assertIn(self.team, m.leitet.all())
        # und nun sieht die Leitung die Klient*innen
        self.assertEqual(services.klienten_fuer(u).count(), 1)

    def test_rollenwechsel_weg_von_leitung_leert_leitet(self):
        u, m = _user("chef4", Rolle.LEITUNG, leitet=[self.team])
        admin_u, _ = _user("admin2", Rolle.ADMIN)
        self.client.force_login(admin_u)
        self.client.post(reverse("nachweis:mitarbeiter_bearbeiten", args=[m.id]),
                         {"nachname": "Chef4", "rolle": Rolle.USER, "team": str(self.team.id),
                          "wochenstunden": "30", "urlaubstage": "30"})
        m.refresh_from_db()
        self.assertEqual(m.leitet.count(), 0)


class VertretungTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="TBEW", typ=Teamtyp.values[0])
        self.u_haupt, self.m_haupt = _user("haupt", Rolle.USER, team=self.team)
        self.u_vertr, self.m_vertr = _user("vertr", Rolle.USER, team=self.team)
        self.klient = Klient.objects.create(
            nachname="Galow", vorname="Andrea", team=self.team,
            bezugsbetreuer=self.m_haupt, vertretung1=self.m_vertr, status=Status.BETREUUNG)

    def test_vertretung_wird_gelistet(self):
        v = services.vertretungen_fuer(self.u_vertr)
        self.assertEqual(len(v), 1)
        self.assertEqual(v[0]["klient"], self.klient)
        self.assertFalse(v[0]["aktiv"])  # Betreuer nicht abwesend

    def test_vertretung_aktiv_bei_urlaub(self):
        heute = date.today()
        Abwesenheit.objects.create(
            mitarbeiter=self.m_haupt, art=AbwesenheitArt.URLAUB,
            von=heute - timedelta(days=1), bis=heute + timedelta(days=3),
            status=AbwesenheitStatus.GENEHMIGT)
        v = services.vertretungen_fuer(self.u_vertr)
        self.assertTrue(v[0]["aktiv"])
        self.assertEqual(v[0]["bis"], heute + timedelta(days=3))

    def test_beantragter_urlaub_macht_nicht_aktiv(self):
        heute = date.today()
        Abwesenheit.objects.create(
            mitarbeiter=self.m_haupt, art=AbwesenheitArt.URLAUB,
            von=heute, bis=heute, status=AbwesenheitStatus.BEANTRAGT)
        self.assertFalse(services.vertretungen_fuer(self.u_vertr)[0]["aktiv"])

    def test_eigene_klienten_nicht_als_vertretung(self):
        # Hauptbetreuer ist nicht Vertretung seiner eigenen Klient*innen
        self.assertEqual(services.vertretungen_fuer(self.u_haupt), [])

    def test_ueberblick_rendert_mit_vertretungskarte(self):
        """Smoke: die Startseite rendert mit der neuen Vertretungs-Card."""
        self.client.force_login(self.u_vertr)
        resp = self.client.get(reverse("nachweis:start"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Meine Vertretungen")
        self.assertContains(resp, self.klient.name)


class TemplateSmokeTests(TestCase):
    """Rendert die geänderten/neuen Seiten (GET), um Template-Fehler zu fangen."""
    def setUp(self):
        self.team = Team.objects.create(name="TBEW", typ=Teamtyp.values[0])
        self.admin_u, self.admin_m = _user("admin", Rolle.ADMIN)
        self.chef_u, self.chef_m = _user("chef", Rolle.LEITUNG, leitet=[self.team])

    def test_mitarbeiter_bearbeiten_get(self):
        self.client.force_login(self.admin_u)
        resp = self.client.get(reverse("nachweis:mitarbeiter_bearbeiten", args=[self.chef_m.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Leitet Team(s)")

    def test_mitarbeiter_liste_get(self):
        self.client.force_login(self.admin_u)
        resp = self.client.get(reverse("nachweis:mitarbeiter_liste"))
        self.assertEqual(resp.status_code, 200)

    def test_belegungsliste_get_ohne_team_zeigt_hinweis(self):
        u, m = _user("chef_leer", Rolle.LEITUNG)  # leitet nichts
        self.client.force_login(u)
        resp = self.client.get(reverse("nachweis:belegungsliste"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "noch keinem Team zugeordnet")

    def test_klient_form_get(self):
        self.client.force_login(self.chef_u)
        resp = self.client.get(reverse("nachweis:klient_neu"))
        self.assertEqual(resp.status_code, 200)

    def test_belegungsliste_hat_tabellensuche(self):
        # Client-Filter: Suchfeld verweist per data-tsuche auf die Tabelle; das JS wird geladen.
        self.client.force_login(self.chef_u)
        resp = self.client.get(reverse("nachweis:belegungsliste"))
        self.assertContains(resp, 'data-tsuche="#bl-tab"')
        self.assertContains(resp, 'id="bl-tab"')
        self.assertContains(resp, "tabellensuche.js")


class KlientHBGFallbackTests(TestCase):
    """HBG gewählt + AL/kLE leer -> Werte aus der Parameter-Tabelle ableiten."""
    def setUp(self):
        from decimal import Decimal
        from .models import Parameter, HBGSatz
        self.team = Team.objects.create(name="TBEW", typ=Teamtyp.values[0])
        self.chef_u, self.chef_m = _user("chef", Rolle.LEITUNG, leitet=[self.team])
        self.betreuer_u, self.betreuer_m = _user("betr", Rolle.USER, team=self.team)
        # Parameter für das laufende Jahr mit HBG-2-Satz + kLE/Tag befüllen
        p = services.get_parameter(date.today().year)
        p.kle_je_tag = Decimal("0.722167")
        p.save()
        HBGSatz.objects.update_or_create(parameter=p, hbg=2,
                                         defaults={"fls_woche": Decimal("2.95")})

    def _post(self, al="", kle="", hbg="2"):
        self.client.force_login(self.chef_u)
        return self.client.post(reverse("nachweis:klient_speichern"), {
            "nachname": "Muster", "vorname": "Max", "team": str(self.team.id),
            "bezugsbetreuer": str(self.betreuer_m.id), "status": "Betreuung",
            "al": al, "kle": kle, "hbg": hbg})

    def test_leere_al_kle_werden_aus_hbg_abgeleitet(self):
        from decimal import Decimal
        self._post(al="0", kle="0", hbg="2")
        k = Klient.objects.get(nachname="Muster")
        # AL/Monat = 2,95 × 4,3482 ≈ 12,827 ; kLE/Monat = 0,722167 × 30,4375 ≈ 21,981
        self.assertGreater(k.al, Decimal("12"))
        self.assertGreater(k.kle, Decimal("21"))

    def test_getippte_werte_werden_nicht_ueberschrieben(self):
        from decimal import Decimal
        self._post(al="9,5", kle="18", hbg="2")
        k = Klient.objects.get(nachname="Muster")
        self.assertEqual(k.al, Decimal("9.5"))
        self.assertEqual(k.kle, Decimal("18"))

    def test_ohne_hbg_bleibt_null(self):
        from decimal import Decimal
        self._post(al="0", kle="0", hbg="")
        k = Klient.objects.get(nachname="Muster")
        self.assertEqual(k.al, Decimal("0"))
        self.assertEqual(k.kle, Decimal("0"))

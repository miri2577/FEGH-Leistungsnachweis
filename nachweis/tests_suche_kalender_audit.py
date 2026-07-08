"""Tests: Doku-Suche (nur Klientenarbeit), Teamsitzung im Kalender, Auditlog-Maskierung."""
import json
from datetime import date, time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from . import services
from .models import (Mitarbeiter, Team, Teamtyp, Rolle, Klient, Status,
                     Leistung, Leistungsart)

User = get_user_model()


def _mk(username, rolle, team=None, leitet=None):
    u = User.objects.create_user(username=username, password="x")
    m = Mitarbeiter.objects.create(user=u, name=username.title(), rolle=rolle,
                                   team=team, kuerzel=username[:5])
    if leitet:
        m.leitet.set(leitet)
    return u, m


class DokuSucheTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="TBEW", typ=Teamtyp.values[0])
        self.u, self.m = _mk("betr", Rolle.USER, team=self.team)
        self.k = Klient.objects.create(nachname="Galow", team=self.team,
                                       bezugsbetreuer=self.m, status=Status.BETREUUNG)
        Leistung.objects.create(klient=self.k, betreuer=self.m, datum=date(2026, 6, 3),
                                leistungsart=Leistungsart.values[0],
                                dokumentation="Gespräch über das Zauberwort Sonnenblume.")

    def test_user_findet_doku(self):
        self.client.force_login(self.u)
        d = self.client.post(reverse("nachweis:api_suche"), {"q": "Sonnenblume"}).json()
        treffer = [i for k in d["kategorien"] if k["key"] == "leistungen" for i in k["items"]]
        self.assertTrue(treffer, "Doku-Treffer erwartet")
        self.assertIn("Sonnenblume", treffer[0]["sub"])

    def test_verwaltung_findet_keine_doku(self):
        vu, _ = _mk("verw", Rolle.USER, team=Team.objects.create(name="Verwaltung", typ=Teamtyp.values[0]))
        vm = vu.mitarbeiter_profil
        # als Verwaltung markieren (kein Klientenzugriff)
        vt = vm.team; vt.name = "Verwaltung"; vt.save()
        if hasattr(vm, "ist_verwaltung"):
            pass
        self.client.force_login(vu)
        d = self.client.post(reverse("nachweis:api_suche"), {"q": "Sonnenblume"}).json()
        self.assertNotIn("leistungen", [k["key"] for k in d["kategorien"]])


class KalenderTeamsitzungTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="TBEW", typ=Teamtyp.values[0])
        self.u, self.m = _mk("betr", Rolle.USER, team=self.team)

    def test_teamsitzung_erscheint_im_kalender(self):
        self.client.force_login(self.u)
        # Woche mit einem Nicht-Feiertags-Donnerstag: KW24/2026 (11.06.2026 = Do)
        resp = self.client.get(reverse("nachweis:kalender"), {"ansicht": "woche", "jahr": 2026, "kw": 24})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Teamsitzung")


class AuditlogMaskierungTests(TestCase):
    def test_dokumentation_nicht_im_auditlog(self):
        from auditlog.models import LogEntry
        team = Team.objects.create(name="TBEW", typ=Teamtyp.values[0])
        _u, m = _mk("betr", Rolle.USER, team=team)
        k = Klient.objects.create(nachname="Galow", team=team, bezugsbetreuer=m, status=Status.BETREUUNG)
        l = Leistung.objects.create(klient=k, betreuer=m, datum=date(2026, 6, 3),
                                    leistungsart=Leistungsart.values[0], dokumentation="")
        l.dokumentation = "Sensibler Verlaufstext mit Diagnose."
        l.notiz = "geheime Notiz"
        l.taetigkeit = "Hausbesuch"
        l.save()
        eintraege = LogEntry.objects.filter(object_pk=str(l.pk))
        blob = " ".join(json.dumps(e.changes) if isinstance(e.changes, (dict, list))
                        else str(e.changes) for e in eintraege)
        self.assertNotIn("Sensibler Verlaufstext", blob)
        self.assertNotIn("geheime Notiz", blob)
        # unkritische Felder dürfen weiter protokolliert werden
        self.assertIn("Hausbesuch", blob)

    def test_klient_kommentar_nicht_im_auditlog(self):
        from auditlog.models import LogEntry
        team = Team.objects.create(name="TBEW", typ=Teamtyp.values[0])
        _u, m = _mk("betr", Rolle.USER, team=team)
        k = Klient.objects.create(nachname="Galow", team=team, bezugsbetreuer=m, status=Status.BETREUUNG)
        k.kommentar = "vertraulicher Kommentar"
        k.save()
        blob = " ".join(json.dumps(e.changes) if isinstance(e.changes, (dict, list))
                        else str(e.changes) for e in LogEntry.objects.filter(object_pk=str(k.pk)))
        self.assertNotIn("vertraulicher Kommentar", blob)

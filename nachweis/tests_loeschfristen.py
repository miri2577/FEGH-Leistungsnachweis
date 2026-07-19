"""Tests Löschkonzept (DSGVO): Aufbewahrungsfristen, Fälligkeit, Anonymisierung."""
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from . import services_loeschfristen as lf
from .models import (Team, Teamtyp, Mitarbeiter, Rolle, Klient, Status,
                     Aufbewahrungsregel, AufbewahrungsKategorie, Leistung,
                     Leistungsart, Monatsfreigabe, Ziel, ZielArt, Bericht,
                     Berichtsvorlage, Wirkungsdimension, Wirkungseinschaetzung,
                     WirkungsAnlass)

User = get_user_model()


class RegelTests(TestCase):
    def test_defaults_aus_migration(self):
        self.assertEqual(Aufbewahrungsregel.objects.count(), 8)
        self.assertEqual(lf.frist_jahre(AufbewahrungsKategorie.ABRECHNUNG), 8)
        self.assertEqual(lf.frist_jahre(AufbewahrungsKategorie.FACHDOKU_EGH), 10)
        self.assertEqual(lf.frist_jahre(AufbewahrungsKategorie.FACHDOKU_JUG), 70)
        self.assertEqual(lf.frist_jahre(AufbewahrungsKategorie.WTG), 5)

    def test_frist_aus_db_ueberschreibt_fallback(self):
        r = Aufbewahrungsregel.objects.get(kategorie=AufbewahrungsKategorie.FACHDOKU_EGH)
        r.jahre = 12
        r.save()
        self.assertEqual(lf.frist_jahre(AufbewahrungsKategorie.FACHDOKU_EGH), 12)


class LoeschBasis(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="TBEW", typ=Teamtyp.BEW)
        self.u = User.objects.create_user("chef", password="x")
        m = Mitarbeiter.objects.create(user=self.u, name="Chef", rolle=Rolle.LEITUNG, kuerzel="c")
        m.leitet.set([self.team])
        self.betr = m
        self.client.force_login(self.u)

    def _klient(self, **kw):
        d = dict(nachname="Alt", team=self.team, bezugsbetreuer=self.betr,
                 status=Status.BEENDIGUNG)
        d.update(kw)
        return Klient.objects.create(**d)


class FristStatusTests(LoeschBasis):
    def test_laufende_betreuung_nie_faellig(self):
        k = self._klient(status=Status.BETREUUNG, kue_bis=date(2010, 1, 1))
        st = lf.loeschstatus(k, heute=date(2026, 7, 14))
        self.assertFalse(st["fach_faellig"])       # Status Betreuung -> nie fällig

    def test_alte_beendete_betreuung_voll_faellig(self):
        k = self._klient(kue_bis=date(2014, 1, 1))
        Leistung.objects.create(datum=date(2013, 6, 1), klient=k, leistungsart=Leistungsart.FS,
                                betreuer=self.betr, dokumentation="alt")
        st = lf.loeschstatus(k, heute=date(2026, 7, 14))
        self.assertEqual(st["betreuungsende"], date(2014, 1, 1))
        self.assertTrue(st["fach_faellig"])        # 2014 + 10 = 2024 < heute
        self.assertTrue(st["voll_faellig"])        # Abrechnung 2013+8 auch vorbei

    def test_fachdaten_faellig_aber_abrechnung_laeuft_noch(self):
        # altes Betreuungsende, aber jüngste Abrechnung 2024 -> Abrechnungsfrist bis 2032
        k = self._klient(kue_bis=date(2014, 1, 1))
        Monatsfreigabe.objects.create(klient=k, jahr=2024, monat=3)
        st = lf.loeschstatus(k, heute=date(2026, 7, 14))
        self.assertTrue(st["fach_faellig"])
        self.assertFalse(st["voll_faellig"])       # Abrechnung 2024+8 = 2032 > heute

    def test_offene_belegung_blockiert_frist(self):
        """Review HOCH: laufende (offene) Belegung = Person noch untergebracht ->
        Ende unklar, nie fällig (sonst verfrühte Löschung bei aktiver Betreuung)."""
        from .models import Angebot, AngebotsTyp, Belegung
        k = self._klient(kue_bis=date(2010, 1, 1))
        ang = Angebot.objects.create(name="WG", team=self.team, typ=AngebotsTyp.WG_VERBUND, plaetze=4)
        Belegung.objects.create(klient=k, angebot=ang, einzug=date(2009, 1, 1))  # kein Auszug
        st = lf.loeschstatus(k, heute=date(2026, 7, 14))
        self.assertIsNone(st["betreuungsende"])
        self.assertFalse(st["fach_faellig"])

    def test_anonymisierter_nicht_erneut_faellig(self):
        """Review MITTEL: einmal voll-anonymisiert -> nie wieder in der Fällig-Liste."""
        k = self._klient(kue_bis=date(2013, 1, 1))
        Leistung.objects.create(datum=date(2012, 6, 1), klient=k, leistungsart=Leistungsart.FS,
                                betreuer=self.betr)
        self.assertTrue(lf.loeschstatus(k, heute=date(2026, 7, 14))["fach_faellig"])
        lf.anonymisieren(k, stufe="voll", apply=True, heute=date(2026, 7, 14))
        k.refresh_from_db()
        self.assertIsNotNone(k.anonymisiert_am)
        self.assertFalse(lf.loeschstatus(k, heute=date(2026, 7, 14))["fach_faellig"])


class AnonymisierungTests(LoeschBasis):
    def _voll_klient(self):
        k = self._klient(kue_bis=date(2013, 1, 1), person_id="AZ-123", vorname="Anna",
                         geburtsdatum=date(1990, 5, 5), kommentar="privat")
        k.strasse = "Musterweg 3"; k.plz = "10115"; k.ort = "Berlin"
        k.betreuung_name = "Betreuungsverein e.V."; k.betreuung_telefon = "030-123"
        k.betreuung_umfang = "Vermögenssorge"; k.betreuung_bis = date(2027, 1, 1)
        k.save()
        Leistung.objects.create(datum=date(2012, 6, 1), klient=k, leistungsart=Leistungsart.FS,
                                betreuer=self.betr, dokumentation="Verlauf", notiz="Notiz")
        Monatsfreigabe.objects.create(klient=k, jahr=2012, monat=6, betrag=100)
        Ziel.objects.create(klient=k, art=ZielArt.HANDLUNGSZIEL, titel="Z")
        b = Bericht.objects.create(klient=k, vorlage=Berichtsvorlage.objects.first(),
                                   zeitraum_von=date(2012, 1, 1), zeitraum_bis=date(2012, 12, 31))
        dim = Wirkungsdimension.objects.first()
        Wirkungseinschaetzung.objects.create(klient=k, dimension=dim, datum=date(2012, 6, 1),
                                             anlass=WirkungsAnlass.BEGINN, ist=4, soll=3)
        return k

    def test_trockenlauf_aendert_nichts(self):
        k = self._voll_klient()
        report = lf.anonymisieren(k, stufe="voll", apply=False)
        self.assertTrue(report["aktionen"])
        k.refresh_from_db()
        self.assertEqual(k.nachname, "Alt")              # unverändert
        self.assertEqual(k.ziele.count(), 1)
        self.assertEqual(k.leistungen.first().dokumentation, "Verlauf")

    def test_voll_anonymisierung(self):
        from auditlog.models import LogEntry
        from django.contrib.contenttypes.models import ContentType
        k = self._voll_klient()
        k.gruppen.add(self._gruppe())               # Gruppen-Teilnahme
        alt_name = k.nachname
        lf.anonymisieren(k, stufe="voll", apply=True)
        k.refresh_from_db()
        # Fachdaten weg
        self.assertEqual(k.ziele.count(), 0)
        self.assertEqual(k.berichte.count(), 0)
        self.assertEqual(k.wirkungseinschaetzungen.count(), 0)
        self.assertEqual(k.gruppen.count(), 0)           # Gruppen-Teilnahme gelöst
        # Freitexte geleert, Abrechnungsgerüst bleibt
        self.assertEqual(k.leistungen.count(), 1)        # Leistung-Zeile bleibt (Beleg)
        self.assertEqual(k.leistungen.first().dokumentation, "")
        self.assertEqual(k.leistungen.first().taetigkeit, "")
        self.assertEqual(k.freigaben.count(), 1)         # Monatsfreigabe bleibt
        # Stammdaten pseudonymisiert + Marker
        self.assertEqual(k.nachname, f"Gelöscht #{k.pk}")
        self.assertEqual(k.vorname, "")
        self.assertIsNone(k.geburtsdatum)
        self.assertEqual(k.person_id, "")
        # Anschrift + gesetzliche Betreuung mit anonymisiert
        self.assertEqual(k.strasse, ""); self.assertEqual(k.plz, ""); self.assertEqual(k.ort, "")
        self.assertEqual(k.betreuung_name, ""); self.assertEqual(k.betreuung_telefon, "")
        self.assertEqual(k.betreuung_umfang, ""); self.assertIsNone(k.betreuung_bis)
        self.assertIsNotNone(k.anonymisiert_am)
        # Review HOCH: kein Klartext-Name mehr im Auditlog des Klienten
        ct = ContentType.objects.get_for_model(Klient)
        eintraege = LogEntry.objects.filter(content_type=ct, object_pk=str(k.pk))
        self.assertEqual(eintraege.count(), 0)
        self.assertFalse(any(alt_name in str(e.changes) for e in LogEntry.objects.all()))

    def _gruppe(self):
        from .models import Gruppe
        from datetime import time
        return Gruppe.objects.create(datum=date(2012, 5, 1), thema="Gruppe",
                                     beginn=time(10, 0), ende=time(11, 0))

    def test_fachdaten_stufe_behaelt_stammdaten(self):
        k = self._voll_klient()
        lf.anonymisieren(k, stufe="fachdaten", apply=True)
        k.refresh_from_db()
        self.assertEqual(k.ziele.count(), 0)             # Fachdaten weg
        self.assertEqual(k.leistungen.first().dokumentation, "")
        self.assertEqual(k.nachname, "Alt")              # Stammdaten bleiben
        self.assertEqual(k.person_id, "AZ-123")


class AnonymisierungVollstaendigkeitTests(LoeschBasis):
    """P0 (Audit): Voll-Anonymisierung erfasst auch Selbstzahler-Rechnung, ICF-
    Bedarfsermittlung, Wohnkosten und die simple_history-Snapshots (irreversibel)."""
    def _reicher_klient(self):
        from .models import (SelbstzahlerRechnung, Wohnkostenvereinbarung,
                             Bedarfsermittlung, BedarfsEinschaetzung, TibLebensbereich)
        k = self._klient(kue_bis=date(2013, 1, 1), vorname="Max", person_id="AZ-9")
        Leistung.objects.create(datum=date(2012, 6, 1), klient=k, leistungsart=Leistungsart.FS,
                                betreuer=self.betr)
        sz = SelbstzahlerRechnung.objects.create(
            nummer="WK-2012-0001", klient=k, empfaenger="Max Alt",
            empfaenger_anschrift="Musterweg 3, 10115 Berlin", jahr=2012, monat=6,
            datum=date(2012, 6, 1), betrag=500, notiz="privat")
        sz.betrag = 550
        sz.save()                                        # zweiter History-Snapshot
        Wohnkostenvereinbarung.objects.create(klient=k, notiz="Sondervereinbarung")
        be = Bedarfsermittlung.objects.create(klient=k, datum=date(2012, 3, 1))
        lb = TibLebensbereich.objects.first() or TibLebensbereich.objects.create(name="Wohnen")
        BedarfsEinschaetzung.objects.create(
            bedarfsermittlung=be, lebensbereich=lb, gelingt="Ressource X",
            barrieren="Barriere Y", personfaktoren="Faktor Z")
        return k, sz.pk

    def test_selbstzahler_bedarf_wohnkosten_werden_erfasst(self):
        k, _ = self._reicher_klient()
        lf.anonymisieren(k, stufe="voll", apply=True)
        k.refresh_from_db()
        sz = k.selbstzahler_rechnungen.first()
        self.assertIsNotNone(sz)                          # Beleg bleibt (PROTECT)
        self.assertNotIn("Max Alt", sz.empfaenger)        # Klarname weg
        self.assertEqual(sz.empfaenger_anschrift, "")
        self.assertEqual(sz.notiz, "")
        self.assertEqual(k.bedarfsermittlungen.count(), 0)   # Art-9 gelöscht
        self.assertEqual(k.wohnkosten.first().notiz, "")     # Notiz geleert

    def test_simple_history_wird_gescrubbt(self):
        from .models import SelbstzahlerRechnung
        k, sz_pk = self._reicher_klient()
        self.assertGreater(SelbstzahlerRechnung.history.filter(id=sz_pk).count(), 0)
        lf.anonymisieren(k, stufe="voll", apply=True)
        self.assertEqual(SelbstzahlerRechnung.history.filter(id=sz_pk).count(), 0)
        # kein Klarname mehr in IRGENDEINEM Selbstzahler-History-Snapshot
        self.assertFalse(any("Max Alt" in (h.empfaenger or "")
                             for h in SelbstzahlerRechnung.history.all()))

    def test_bedarfsermittlung_schon_in_fachdaten_stufe(self):
        k, _ = self._reicher_klient()
        lf.anonymisieren(k, stufe="fachdaten", apply=True)
        self.assertEqual(k.bedarfsermittlungen.count(), 0)
        k.refresh_from_db()
        self.assertEqual(k.nachname, "Alt")               # Stammdaten bleiben (nur Fachdaten)


class LoeschViewTests(LoeschBasis):
    def test_uebersicht_nur_leitung(self):
        u2 = User.objects.create_user("ma", password="x")
        Mitarbeiter.objects.create(user=u2, name="MA", rolle=Rolle.USER,
                                   team=self.team, kuerzel="m")
        self.client.force_login(u2)
        self.assertEqual(self.client.get(reverse("nachweis:loeschfristen")).status_code, 403)

    def test_uebersicht_zeigt_faellige(self):
        k = self._klient(kue_bis=date(2013, 1, 1))
        Leistung.objects.create(datum=date(2012, 6, 1), klient=k, leistungsart=Leistungsart.FS,
                                betreuer=self.betr)
        r = self.client.get(reverse("nachweis:loeschfristen"))
        self.assertContains(r, "Alt")
        self.assertContains(r, "fällig")

    def test_anonymisieren_braucht_richtigen_namen(self):
        k = self._klient(kue_bis=date(2013, 1, 1))
        Leistung.objects.create(datum=date(2012, 6, 1), klient=k, leistungsart=Leistungsart.FS,
                                betreuer=self.betr, dokumentation="x")
        # falscher Bestätigungsname -> keine Änderung
        self.client.post(reverse("nachweis:loeschfristen_anonymisieren"),
                         {"klient": k.id, "bestaetigung": "Falsch"})
        k.refresh_from_db()
        self.assertEqual(k.nachname, "Alt")
        # richtiger Name -> anonymisiert
        self.client.post(reverse("nachweis:loeschfristen_anonymisieren"),
                         {"klient": k.id, "bestaetigung": "Alt"})
        k.refresh_from_db()
        self.assertEqual(k.nachname, f"Gelöscht #{k.pk}")

    def test_nicht_faellig_wird_abgewiesen(self):
        k = self._klient(status=Status.BETREUUNG, kue_bis=date(2013, 1, 1))
        r = self.client.post(reverse("nachweis:loeschfristen_anonymisieren"),
                             {"klient": k.id, "bestaetigung": "Alt"})
        self.assertEqual(r.status_code, 302)
        k.refresh_from_db()
        self.assertEqual(k.nachname, "Alt")              # nicht fällig -> unverändert

    def test_fremdes_team_kein_zugriff(self):
        fremd = Klient.objects.create(nachname="Fremd",
                                      team=Team.objects.create(name="X", typ=Teamtyp.BEW),
                                      bezugsbetreuer=self.betr, status=Status.BEENDIGUNG,
                                      kue_bis=date(2010, 1, 1))
        r = self.client.get(reverse("nachweis:loeschfristen_klient", args=[fremd.id]))
        self.assertEqual(r.status_code, 404)

"""Tests Phase 2 / Slice 2a: Ziele (ZLP) + Zielbezug der Verlaufsdoku."""
import json
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import (Team, Teamtyp, Mitarbeiter, Rolle, Klient, Status,
                     Ziel, ZielArt, ZielStatus, Leistung, Leistungsart)

User = get_user_model()


class ZieleBasis(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="TBEW", typ=Teamtyp.values[0])
        self.u = User.objects.create_user("betr", password="x")
        self.betr = Mitarbeiter.objects.create(user=self.u, name="Betr", rolle=Rolle.USER,
                                               team=self.team, kuerzel="betr")
        self.k = Klient.objects.create(nachname="Galow", team=self.team,
                                       bezugsbetreuer=self.betr, status=Status.BETREUUNG)
        self.client.force_login(self.u)

    def _rz(self, titel="Selbstständig wohnen"):
        return Ziel.objects.create(klient=self.k, art=ZielArt.RICHTUNGSZIEL, titel=titel)

    def _hz(self, rz=None, titel="Wocheneinkauf selbst erledigen", **kw):
        return Ziel.objects.create(klient=self.k, art=ZielArt.HANDLUNGSZIEL,
                                   uebergeordnet=rz, titel=titel,
                                   indikator="erledigt Einkauf 4 Wochen ohne Begleitung", **kw)


class ZielModellTests(ZieleBasis):
    def test_hierarchie_und_status(self):
        rz = self._rz()
        hz = self._hz(rz)
        self.assertEqual(list(rz.unterziele.all()), [hz])
        self.assertTrue(hz.ist_aktiv)
        hz.status = ZielStatus.ERREICHT
        hz.save()
        self.assertFalse(hz.ist_aktiv)

    def test_ziel_versioniert(self):
        z = self._hz()
        z.titel = "Wocheneinkauf mit Begleitung"
        z.save()
        self.assertEqual(z.history.count(), 2)
        self.assertEqual(z.history.last().titel, "Wocheneinkauf selbst erledigen")

    def test_doku_zielbezug(self):
        z = self._hz()
        l = Leistung.objects.create(datum=date.today(), klient=self.k,
                                    leistungsart=Leistungsart.FS, taetigkeit="Hausbesuch",
                                    betreuer=self.betr, dokumentation="Einkauf begleitet.")
        l.ziele.add(z)
        self.assertEqual(list(z.leistungen.all()), [l])


class ZielViewTests(ZieleBasis):
    def test_ziele_seite(self):
        rz = self._rz(); self._hz(rz)
        resp = self.client.get(reverse("nachweis:ziele", args=[self.k.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Selbstständig wohnen")
        self.assertContains(resp, "Wocheneinkauf")
        self.assertContains(resp, "noch keine Doku")     # Zielverlauf-Warnung

    def test_ziel_speichern_und_zuordnung(self):
        rz = self._rz()
        resp = self.client.post(reverse("nachweis:ziel_speichern"), {
            "klient": self.k.id, "titel": "Neues Handlungsziel", "art": "handlungsziel",
            "uebergeordnet": rz.id, "indikator": "…", "gueltig_von": "2026-07-01"})
        self.assertEqual(resp.status_code, 302)
        z = Ziel.objects.get(titel="Neues Handlungsziel")
        self.assertEqual(z.uebergeordnet, rz)

    def test_status_schnellwechsel(self):
        z = self._hz()
        self.client.post(reverse("nachweis:ziel_status"), {"id": z.id, "status": "erreicht"})
        z.refresh_from_db()
        self.assertEqual(z.status, ZielStatus.ERREICHT)

    def test_loeschen_nur_leitung(self):
        z = self._hz()
        resp = self.client.post(reverse("nachweis:ziel_loeschen"), {"id": z.id})
        self.assertEqual(resp.status_code, 403)          # User darf nicht löschen
        self.assertTrue(Ziel.objects.filter(pk=z.pk).exists())

    def test_fremdes_team_kein_zugriff(self):
        fremd_team = Team.objects.create(name="WG", typ=Teamtyp.values[0])
        fu = User.objects.create_user("fremd", password="x")
        Mitarbeiter.objects.create(user=fu, name="F", rolle=Rolle.USER,
                                   team=fremd_team, kuerzel="f")
        self.client.force_login(fu)
        resp = self.client.get(reverse("nachweis:ziele", args=[self.k.id]))
        self.assertEqual(resp.status_code, 404)          # team-gescopt
        z = self._hz()
        resp = self.client.post(reverse("nachweis:ziel_status"),
                                {"id": z.id, "status": "erreicht"})
        self.assertEqual(resp.status_code, 404)

    def test_api_ziele_nur_aktive_und_gescopt(self):
        aktiv = self._hz()
        erledigt = self._hz(titel="Altes Ziel"); erledigt.status = ZielStatus.ERREICHT
        erledigt.save()
        resp = self.client.get(reverse("nachweis:api_ziele"), {"klient": self.k.id})
        ids = [z["id"] for z in resp.json()["ziele"]]
        self.assertIn(aktiv.id, ids)
        self.assertNotIn(erledigt.id, ids)


class DokuZielbezugAPITests(ZieleBasis):
    def _save(self, payload):
        return self.client.post(reverse("nachweis:api_leistung_save"),
                                json.dumps(payload), content_type="application/json")

    def test_save_mit_zielen(self):
        z = self._hz()
        resp = self._save({"klient": self.k.id, "datum": date.today().isoformat(),
                           "leistungsart": "FS", "taetigkeit": "Hausbesuch",
                           "beginn": "09:00", "ende": "10:00",
                           "dokumentation": "Einkauf begleitet.", "ziele": [z.id]})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["ziele"], [z.id])
        l = Leistung.objects.get()
        self.assertEqual(list(l.ziele.all()), [z])

    def test_fremde_ziele_werden_ignoriert(self):
        # Ziel eines ANDEREN Klienten darf nicht zuordenbar sein
        k2 = Klient.objects.create(nachname="Anders", team=self.team,
                                   bezugsbetreuer=self.betr, status=Status.BETREUUNG)
        fremdziel = Ziel.objects.create(klient=k2, titel="Fremdes Ziel")
        eigen = self._hz()
        resp = self._save({"klient": self.k.id, "datum": date.today().isoformat(),
                           "leistungsart": "FS", "taetigkeit": "x",
                           "ziele": [eigen.id, fremdziel.id]})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["ziele"], [eigen.id])   # fremdes gefiltert

    # ---- Regressionstests aus dem adversarialen Review ----

    def test_bezug_zu_inaktivem_ziel_bleibt_erhalten(self):
        """HOCH-Befund: Modal zeigt nur aktive Ziele – Bezug zu erreichten darf beim
        Speichern nicht still verschwinden (Verlaufsdoku würde rückwirkend verfälscht)."""
        from .models import ZielStatus
        erreicht = self._hz(titel="Altes erreichtes Ziel")
        erreicht.status = ZielStatus.ERREICHT
        erreicht.save()
        aktiv = self._hz(titel="Aktives Ziel")
        l = Leistung.objects.create(datum=date.today(), klient=self.k,
                                    leistungsart=Leistungsart.FS, taetigkeit="x",
                                    betreuer=self.betr, dokumentation="Text")
        l.ziele.add(erreicht)
        # Modal sendet nur die (aktiven) Checkbox-IDs -> erreichtes Ziel fehlt im Payload
        resp = self._save({"id": l.id, "klient": self.k.id,
                           "datum": date.today().isoformat(),
                           "leistungsart": "FS", "taetigkeit": "x",
                           "ziele": [aktiv.id]})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(set(l.ziele.all()), {erreicht, aktiv})   # Bestand geschützt
        # sogar bei leerer Liste (fetch-Fehler-Fall) bleibt der inaktive Bezug
        self._save({"id": l.id, "klient": self.k.id, "datum": date.today().isoformat(),
                    "leistungsart": "FS", "taetigkeit": "x", "ziele": []})
        self.assertEqual(set(l.ziele.all()), {erreicht})

    def test_kein_selbstzyklus_beim_art_wechsel(self):
        rz = self._rz()
        resp = self.client.post(reverse("nachweis:ziel_speichern"), {
            "klient": self.k.id, "id": rz.id, "titel": rz.titel,
            "art": "handlungsziel", "uebergeordnet": rz.id})   # sich selbst als Parent
        self.assertEqual(resp.status_code, 302)
        rz.refresh_from_db()
        self.assertIsNone(rz.uebergeordnet_id)                  # Selbstzyklus verhindert

    def test_art_wechsel_stellt_unterziele_frei(self):
        rz = self._rz()
        h1 = self._hz(rz, titel="Kind 1")
        self.client.post(reverse("nachweis:ziel_speichern"), {
            "klient": self.k.id, "id": rz.id, "titel": rz.titel, "art": "handlungsziel"})
        h1.refresh_from_db()
        self.assertIsNone(h1.uebergeordnet_id)                  # freigestellt, bleibt sichtbar
        resp = self.client.get(reverse("nachweis:ziele", args=[self.k.id]))
        self.assertContains(resp, "Kind 1")

    def test_kaputte_ids_kein_500(self):
        resp = self.client.post(reverse("nachweis:ziel_status"), {"id": "abc", "status": "erreicht"})
        self.assertEqual(resp.status_code, 404)
        resp = self.client.get(reverse("nachweis:api_ziele"), {"klient": "abc"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["ziele"], [])

    def test_save_ohne_ziele_laesst_bezug_unveraendert(self):
        z = self._hz()
        l = Leistung.objects.create(datum=date.today(), klient=self.k,
                                    leistungsart=Leistungsart.FS, taetigkeit="x",
                                    betreuer=self.betr)
        l.ziele.add(z)
        resp = self._save({"id": l.id, "klient": self.k.id,
                           "datum": date.today().isoformat(),
                           "leistungsart": "FS", "taetigkeit": "y"})   # kein "ziele"-Key
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(list(l.ziele.all()), [z])           # Bezug bleibt

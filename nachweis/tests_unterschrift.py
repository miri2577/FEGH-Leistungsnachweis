"""Tests Phase 3 / Slice 3b: mobile Unterschrift im Unterwegs-Modus."""
import base64
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Team, Teamtyp, Mitarbeiter, Rolle, Klient, Status, Leistung

User = get_user_model()

# 1x1-PNG als gültige Beispiel-Signatur
PNG = "data:image/png;base64," + base64.b64encode(
    bytes.fromhex("89504e470d0a1a0a0000000d494844520000000100000001080600000"
                  "01f15c4890000000d49444154789c626001000000ffff030000060005"
                  "57bfabd40000000049454e44ae426082")).decode()


class UnterschriftTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="TBEW", typ=Teamtyp.values[0])
        self.u = User.objects.create_user("betr", password="x")
        self.betr = Mitarbeiter.objects.create(user=self.u, name="B", rolle=Rolle.USER,
                                               team=self.team, kuerzel="b")
        self.k = Klient.objects.create(nachname="K", team=self.team,
                                       bezugsbetreuer=self.betr, status=Status.BETREUUNG)
        self.client.force_login(self.u)

    def _post(self, **extra):
        daten = {"klient": self.k.id, "datum": date.today().isoformat(),
                 "beginn": "09:00", "ende": "10:00", "leistungsart": "FS",
                 "taetigkeit": "Hausbesuch", "doku_minuten": "0"}
        daten.update(extra)
        return self.client.post(reverse("nachweis:feld_speichern"), daten)

    def test_besuch_mit_unterschrift(self):
        resp = self._post(unterschrift=PNG)
        self.assertEqual(resp.status_code, 302)
        l = Leistung.objects.get(taetigkeit="Hausbesuch")
        self.assertTrue(l.unterschrift.startswith("data:image/png;base64,"))
        self.assertIsNotNone(l.unterschrieben_am)

    def test_ohne_unterschrift_bleibt_leer(self):
        self._post()
        l = Leistung.objects.get()
        self.assertEqual(l.unterschrift, "")
        self.assertIsNone(l.unterschrieben_am)

    def test_ungueltige_daten_verworfen(self):
        # kein PNG-Data-URL-Präfix bzw. zu groß -> wird NICHT gespeichert
        self._post(unterschrift="javascript:alert(1)")
        l = Leistung.objects.get()
        self.assertEqual(l.unterschrift, "")
        l.delete()
        self._post(unterschrift="data:image/png;base64," + "A" * 250_000)
        l2 = Leistung.objects.get()
        self.assertEqual(l2.unterschrift, "")

    def test_erfolg_redirect_mit_ok_signal(self):
        # Erfolgreicher Speichervorgang signalisiert dem Client per ?ok=1, den lokalen
        # Entwurf zu verwerfen (Datenverlust-Schutz unterwegs).
        resp = self._post()
        self.assertEqual(resp.status_code, 302)
        self.assertIn("ok=1", resp.url)

    def test_fehler_ohne_ok_signal(self):
        # Fehlgeschlagener Speichervorgang -> KEIN ok=1 -> Entwurf bleibt erhalten.
        resp = self.client.post(reverse("nachweis:feld_speichern"),
                                {"datum": date.today().isoformat()})   # Pflichtfelder fehlen
        self.assertEqual(resp.status_code, 302)
        self.assertNotIn("ok=1", resp.url)

    def test_unterschrift_im_druck_nachweis(self):
        self._post(unterschrift=PNG)
        resp = self.client.get(reverse("nachweis:druck"),
                               {"klient": self.k.id, "monat": date.today().month,
                                "jahr": date.today().year})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "data:image/png;base64,")     # Bild eingebettet
        self.assertContains(resp, "Unterschrift")               # Spalte vorhanden

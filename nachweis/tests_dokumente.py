"""Tests Dokumentenablage (Upload-Whitelist, Scoping, Löschrechte, Datei-Cleanup)."""
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Team, Teamtyp, Mitarbeiter, Rolle, Klient, Status, Dokument

User = get_user_model()
_MEDIA = tempfile.mkdtemp(prefix="fegh_test_media_")

PDF = b"%PDF-1.4 fake\n%%EOF"


def _pdf(name="bescheid.pdf", inhalt=PDF):
    return SimpleUploadedFile(name, inhalt, content_type="application/pdf")


@override_settings(MEDIA_ROOT=_MEDIA)
class DokumenteTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(_MEDIA, ignore_errors=True)

    def setUp(self):
        self.team = Team.objects.create(name="TBEW", typ=Teamtyp.values[0])
        self.u = User.objects.create_user("betr", password="x")
        self.betr = Mitarbeiter.objects.create(user=self.u, name="B", rolle=Rolle.USER,
                                               team=self.team, kuerzel="b")
        self.k = Klient.objects.create(nachname="K", team=self.team,
                                       bezugsbetreuer=self.betr, status=Status.BETREUUNG)
        self.client.force_login(self.u)

    def _upload(self, datei, **extra):
        daten = {"klient": self.k.id, "datei": datei, "kategorie": "bescheid"}
        daten.update(extra)
        return self.client.post(reverse("nachweis:dokument_hochladen"), daten)

    def test_upload_und_liste(self):
        self._upload(_pdf(), name="Bescheid 2026")
        d = Dokument.objects.get()
        self.assertEqual(d.name, "Bescheid 2026")
        self.assertEqual(d.groesse, len(PDF))
        self.assertNotIn("bescheid.pdf", d.datei.name)   # Zufallsname auf der Platte
        resp = self.client.get(reverse("nachweis:dokumente", args=[self.k.id]))
        self.assertContains(resp, "Bescheid 2026")

    def test_endung_nicht_erlaubt(self):
        self._upload(SimpleUploadedFile("run.exe", b"MZ\x90\x00"))
        self.assertEqual(Dokument.objects.count(), 0)

    def test_magic_bytes_muessen_passen(self):
        self._upload(_pdf(inhalt=b"kein pdf inhalt"))    # .pdf ohne %PDF-Kopf
        self.assertEqual(Dokument.objects.count(), 0)

    def test_zu_gross(self):
        gross = b"%PDF" + b"0" * (Dokument.MAX_GROESSE + 1)
        self._upload(_pdf(inhalt=gross))
        self.assertEqual(Dokument.objects.count(), 0)

    def test_download(self):
        self._upload(_pdf())
        d = Dokument.objects.get()
        resp = self.client.get(reverse("nachweis:dokument_download", args=[d.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("attachment", resp["Content-Disposition"])
        self.assertEqual(b"".join(resp.streaming_content), PDF)

    def test_fremdes_team_kein_zugriff(self):
        self._upload(_pdf())
        d = Dokument.objects.get()
        fu = User.objects.create_user("fremd", password="x")
        Mitarbeiter.objects.create(user=fu, name="F", rolle=Rolle.USER,
                                   team=Team.objects.create(name="X", typ=Teamtyp.values[0]),
                                   kuerzel="f")
        self.client.force_login(fu)
        self.assertEqual(self.client.get(
            reverse("nachweis:dokumente", args=[self.k.id])).status_code, 404)
        self.assertEqual(self.client.get(
            reverse("nachweis:dokument_download", args=[d.id])).status_code, 404)

    def test_loeschen_nur_leitung_oder_uploader(self):
        self._upload(_pdf())
        d = Dokument.objects.get()
        # Teamkollege (weder Leitung noch Uploader) darf nicht löschen
        ku = User.objects.create_user("kollege", password="x")
        Mitarbeiter.objects.create(user=ku, name="C", rolle=Rolle.USER,
                                   team=self.team, kuerzel="c")
        self.client.force_login(ku)
        resp = self.client.post(reverse("nachweis:dokument_loeschen"), {"id": d.id})
        self.assertEqual(resp.status_code, 403)
        # Uploader darf — und die Datei verschwindet mit von der Platte
        self.client.force_login(self.u)
        pfad = d.datei.path
        self.client.post(reverse("nachweis:dokument_loeschen"), {"id": d.id})
        self.assertEqual(Dokument.objects.count(), 0)
        import os
        self.assertFalse(os.path.exists(pfad))

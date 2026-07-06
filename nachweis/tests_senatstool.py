"""Verifikation der Senats-Tool-Nachbildung gegen die Referenzwerte des echten
Umrechnungstools (V 8.0, „Tool ab März 2026", Blätter Umrechnung/Output/Gegenprobe).

Eingaben wie im Original: Maßnahmepauschalen 2025 (HBG 1–12), Belegung am
Stichtag (10/11/5/1 in HBG 1–4), Kapazität 25, Erreichbarkeit Mo–Fr 10–16 Uhr,
Wegezeit 6 h/VK/Woche, Auslastung 95,9 %, 38,5-h-Woche. Alle Erwartungswerte
sind die von Excel berechneten Zellwerte (auf ≥6 Stellen)."""
from decimal import Decimal

from django.test import SimpleTestCase, TestCase, Client
from django.contrib.auth import get_user_model

from .models import Team, Teamtyp, Mitarbeiter, Rolle, Parameter, HBGSatz
from .services_senatstool import (umrechnung, gegenprobe, durchschnitts_personalkosten,
                                  erreichbarkeit_pa, PERSONALSCHLUESSEL, WOCHEN_JE_MONAT)

PAUSCHALEN = {1: "41.45", 2: "52.60", 3: "63.75", 4: "75.00", 5: "86.15",
              6: "97.30", 7: "108.45", 8: "119.70", 9: "130.86", 10: "142.01",
              11: "153.16", 12: "164.31"}
BELEGUNG = {1: 10, 2: 11, 3: 5, 4: 1}
# Erreichbarkeit: 1 MA Mo–Fr 10–16 Uhr = 6 h × (365,25 − Wochenend-/Feiertage) → Zelle I80
ERREICHBARKEIT_PA = "1515.6171428571424"


class SenatstoolTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.erg = umrechnung(PAUSCHALEN, BELEGUNG, kapazitaet=25,
                             erreichbarkeit_std_pa=ERREICHBARKEIT_PA)

    def _fast(self, wert, referenz, stellen=6):
        self.assertAlmostEqual(float(wert), referenz, places=stellen)

    def test_personalkosten_differenzmethode(self):        # Input 1 F98
        pk = durchschnitts_personalkosten(PAUSCHALEN, Decimal("0.959"))
        self._fast(pk, 69523.03034733441)

    def test_budget_und_vk(self):                          # Umrechnung L21 / I21
        self._fast(self.erg["budget_gesamt"], 449794.941701389, 5)
        self._fast(self.erg["vk_gesamt"], 4.645370370370371)

    def test_fallspezifische_stunden(self):                # Umrechnung I40
        self._fast(self.erg["fallspez_std"], 3723.735303488399)

    def test_fls_satz(self):                               # Output F43
        self._fast(self.erg["fls_satz"], 45.4568482836267)

    def test_kle_je_tag(self):                             # Output F46
        self._fast(self.erg["kle_je_tag"], 0.722167413912657)

    def test_fls_woche_je_hbg(self):                       # Output D57, D58, D59, D60, D68
        fw = self.erg["fls_woche"]
        self._fast(fw[1], 2.0893210529154373)
        self._fast(fw[2], 2.9496297217629697)
        self._fast(fw[3], 3.809938390610503)
        self._fast(fw[4], 4.685609714258884)
        self._fast(fw[12], 11.598804374640846)

    def test_gegenprobe_erloesneutral(self):               # Gegenprobe I52 == I53
        alt, neu = gegenprobe(self.erg, PAUSCHALEN, BELEGUNG)
        self._fast(alt, 506546.9625, 4)
        self._fast(neu, 506546.9625, 4)

    def test_personalschluessel_vollstaendig(self):
        self.assertEqual(len(PERSONALSCHLUESSEL), 12)
        self.assertEqual(PERSONALSCHLUESSEL[1], Decimal("0.136"))
        self.assertEqual(PERSONALSCHLUESSEL[12], Decimal("0.755"))

    def test_wochen_je_monat(self):                        # 365,25 / 7 / 12
        self._fast(WOCHEN_JE_MONAT, 4.348214285714286)

    def test_erreichbarkeit_pa(self):                      # Input 1 I80 (1 MA Mo–Fr 10–16)
        self._fast(erreichbarkeit_pa(6, 0), 1515.6171428571424)


class RechnerEinstellungenTests(TestCase):
    """End-to-End: verhandelte Eingaben im Einstellungsbereich ändern → berechnen →
    übernehmen → die Abrechnungsparameter tragen exakt die Senats-Tool-Werte."""

    @classmethod
    def setUpTestData(cls):
        team = Team.objects.create(name="T", typ=Teamtyp.BEW)
        cls.uL = get_user_model().objects.create_user("lea", password="pw")
        m = Mitarbeiter.objects.create(user=cls.uL, name="Lea", rolle=Rolle.LEITUNG, team=team)
        m.leitet.set([team])

    def _cl(self):
        c = Client()
        c.force_login(self.uL)
        return c

    def test_eingaben_speichern_berechnen_uebernehmen(self):
        jahr = 2026
        daten = {"aktion": "rechner", "kapazitaet": "25", "wochenarbeitszeit": "38.5",
                 "auslastung": "0.959", "fallunspez_anteil": "0.2",
                 "erreichbarkeit_mo_fr_std": "6", "erreichbarkeit_we_ft_std": "0",
                 "wegezeit_std_vk_woche": "6", "pk_alternativ": "0"}
        for h, p in PAUSCHALEN.items():
            daten[f"pausch_{h}"] = p
        for h, b in BELEGUNG.items():
            daten[f"beleg_{h}"] = str(b)
        c = self._cl()
        r = c.post(f"/parameter/?jahr={jahr}", daten)
        self.assertEqual(r.status_code, 302)

        # Ergebnis wird auf der Seite angezeigt (deutsche Lokalisierung: Komma)
        r = c.get(f"/parameter/?jahr={jahr}")
        self.assertContains(r, "45,4568")                 # FLS-Satz
        self.assertContains(r, "0,722167")                # kLE je Tag
        self.assertContains(r, "Gegenprobe")

        # Übernehmen schreibt die Werte exakt in die Abrechnungsparameter
        c.post(f"/parameter/?jahr={jahr}", {"aktion": "uebernehmen"})
        p = Parameter.objects.get(jahr=jahr)
        self.assertEqual(p.fls_preis, Decimal("45.4568"))
        self.assertEqual(p.kle_je_tag, Decimal("0.722167"))
        s = {x.hbg: x.fls_woche for x in HBGSatz.objects.filter(parameter=p)}
        self.assertEqual(s[1], Decimal("2.0893"))
        self.assertEqual(s[4], Decimal("4.6856"))
        self.assertEqual(s[12], Decimal("11.5988"))

    def test_andere_platzzahl_bleibt_konsistent(self):
        """Kapazität ändern (verhandelt): FLS-Satz bleibt (unabhängig von Plätzen),
        kLE bleibt konstant (skaliert mit Budget UND Plätzen), Gegenprobe weiter 0."""
        erg25 = umrechnung(PAUSCHALEN, BELEGUNG, kapazitaet=25,
                           erreichbarkeit_std_pa=erreichbarkeit_pa(6, 0))
        erg30 = umrechnung(PAUSCHALEN, BELEGUNG, kapazitaet=30,
                           erreichbarkeit_std_pa=erreichbarkeit_pa(6, 0))
        self.assertAlmostEqual(float(erg25["fls_satz"]), float(erg30["fls_satz"]), places=9)
        alt, neu = gegenprobe(erg30, PAUSCHALEN, BELEGUNG)
        self.assertAlmostEqual(float(alt), float(neu), places=4)   # erlösneutral auch bei 30 Plätzen

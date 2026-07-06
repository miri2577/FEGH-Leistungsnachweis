"""Verifikation der Senats-Tool-Nachbildung gegen die Referenzwerte des echten
Umrechnungstools (V 8.0, „Tool ab März 2026", Blätter Umrechnung/Output/Gegenprobe).

Eingaben wie im Original: Maßnahmepauschalen 2025 (HBG 1–12), Belegung am
Stichtag (10/11/5/1 in HBG 1–4), Kapazität 25, Erreichbarkeit Mo–Fr 10–16 Uhr,
Wegezeit 6 h/VK/Woche, Auslastung 95,9 %, 38,5-h-Woche. Alle Erwartungswerte
sind die von Excel berechneten Zellwerte (auf ≥6 Stellen)."""
from decimal import Decimal

from django.test import SimpleTestCase

from .services_senatstool import (umrechnung, gegenprobe, durchschnitts_personalkosten,
                                  PERSONALSCHLUESSEL, WOCHEN_JE_MONAT)

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

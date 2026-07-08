"""Verifiziert: die realen Tool-Eingaben ergeben über den App-Pfad die korrekten
Ausgaben (FLS-Satz 45,4568 · kLE 0,722167 · Gegenprobe 0,00).
Zahlenwerte = generische Kalkulationsgrößen des Beispielangebots (keine Personen-/Trägerdaten)."""
from decimal import Decimal

from django.test import TestCase

from . import services
from .models import Umrechnung, HBGSatz

# Reale Eingaben aus dem Senats-Tool (Input 1 + Input 2):
PAUSCHALEN = {1: "41.45", 2: "52.60", 3: "63.75", 4: "75.00", 5: "86.15", 6: "97.30",
              7: "108.45", 8: "119.70", 9: "130.86", 10: "142.01", 11: "153.16", 12: "164.31"}
BELEGUNG = {1: 10, 2: 11, 3: 5, 4: 1}
SETTINGS = dict(kapazitaet=25, wochenarbeitszeit="38.5", auslastung="0.959",
                fallunspez_anteil="0.20", erreichbarkeit_mo_fr_std="6",
                erreichbarkeit_we_ft_std="0", wegezeit_std_vk_woche="6", pk_alternativ="0")


def _befuellen(jahr):
    """Legt Parameter + Umrechnung + HBGSätze wie im Parameter-Rechner an."""
    p = services.get_parameter(jahr)
    u, _ = Umrechnung.objects.get_or_create(parameter=p)
    u.kapazitaet = SETTINGS["kapazitaet"]
    u.wochenarbeitszeit = Decimal(SETTINGS["wochenarbeitszeit"])
    u.auslastung = Decimal(SETTINGS["auslastung"])
    u.fallunspez_anteil = Decimal(SETTINGS["fallunspez_anteil"])
    u.erreichbarkeit_mo_fr_std = Decimal(SETTINGS["erreichbarkeit_mo_fr_std"])
    u.erreichbarkeit_we_ft_std = Decimal(SETTINGS["erreichbarkeit_we_ft_std"])
    u.wegezeit_std_vk_woche = Decimal(SETTINGS["wegezeit_std_vk_woche"])
    u.pk_alternativ = Decimal(SETTINGS["pk_alternativ"])
    u.save()
    for h in range(1, 13):
        HBGSatz.objects.update_or_create(
            parameter=p, hbg=h,
            defaults={"pauschale_alt": Decimal(PAUSCHALEN[h]),
                      "belegung_stichtag": BELEGUNG.get(h, 0)})
    return p


class ToolInputTests(TestCase):
    def test_eingaben_ergeben_korrekte_ausgaben(self):
        _befuellen(2026)
        erg, alt, neu = services.umrechnung_fuer_jahr(2026)
        self.assertIsNotNone(erg)
        self.assertAlmostEqual(float(erg["fls_satz"]), 45.4568, places=3)
        self.assertAlmostEqual(float(erg["kle_je_tag"]), 0.722167, places=5)
        # Gegenprobe erlösneutral
        self.assertAlmostEqual(float(neu - alt), 0.0, places=1)
        self.assertAlmostEqual(float(alt), 506546.96, places=1)
        # FLS/Woche je HBG (Auswahl)
        self.assertAlmostEqual(float(erg["fls_woche"][1]), 2.089, places=2)
        self.assertAlmostEqual(float(erg["fls_woche"][2]), 2.950, places=2)
        self.assertAlmostEqual(float(erg["fls_woche"][12]), 11.599, places=2)

    def test_uebernahme_schreibt_parameter(self):
        p = _befuellen(2026)
        erg, _a, _n = services.umrechnung_fuer_jahr(2026)
        p.fls_preis = erg["fls_satz"].quantize(Decimal("0.0001"))
        p.kle_je_tag = erg["kle_je_tag"].quantize(Decimal("0.000001"))
        p.save()
        for hbg, woche in erg["fls_woche"].items():
            HBGSatz.objects.update_or_create(parameter=p, hbg=hbg,
                                             defaults={"fls_woche": woche.quantize(Decimal("0.0001"))})
        tab = services.hbg_tabelle(2026)
        self.assertEqual(len(tab), 12)
        self.assertAlmostEqual(float(p.fls_preis), 45.4568, places=3)

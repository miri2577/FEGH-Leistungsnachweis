"""Datenmodell FEGH-Leistungsnachweis (Team TBEW, Berlin).

Abgeleitet aus der Excel-Mappe TBEW_Leistungsnachweis_2026:
Belegungsliste (Klienten-Stammdaten) · Leistungsnachweis (Erfassung) ·
Gruppennachweise · Teamsitzung · Fachleistungsstunden-Auswertung.

Fachliche Grundlage: Berlin ab 01.01.2026, Beschluss 3/2026.
Alle Zeit-/Betragsgrößen als Decimal (keine Floats) – abrechnungsrelevant.
"""
from datetime import datetime, date
from decimal import Decimal, ROUND_HALF_UP

from django.db import models
from django.core.validators import MinValueValidator


Q3 = Decimal("0.001")  # Rundung auf 3 Nachkommastellen (Stunden)


def _stunden(beginn, ende) -> Decimal:
    """Dauer zwischen zwei Uhrzeiten in Dezimalstunden (0, falls unvollständig)."""
    if not beginn or not ende:
        return Decimal("0")
    delta = datetime.combine(date.min, ende) - datetime.combine(date.min, beginn)
    return (Decimal(delta.total_seconds()) / Decimal(3600)).quantize(Q3, ROUND_HALF_UP)


class Leistungsart(models.TextChoices):
    FS = "FS", "FS – fallspezifische Leistung"
    WFS = "WFS", "WFS – weitere fallspezifische Leistung"
    BAO = "BAO", "BAO – Betreuung am anderen Ort"
    FUS = "FUS", "FUS – fallunspezifische Leistung"
    FZ = "FZ", "FZ – Fahrtzeit"
    AL = "AL", "AL – Assistenzleistung"
    KLE = "KLE", "KLE – kalkulatorische Leistungseinheit"
    FH = "FH", "FH – Freihaltung/Abwesenheit (50 %)"


# Leistungsarten, die als Fachleistungsstunden (FLS) zählen:
FLS_ARTEN = {Leistungsart.FS, Leistungsart.WFS, Leistungsart.BAO}


class Rolle(models.TextChoices):
    BETREUER = "betreuer", "Betreuer*in"
    TEAMLEITUNG = "teamleitung", "Teamleitung"


class Status(models.TextChoices):
    BETREUUNG = "Betreuung", "Betreuung"
    BEENDIGUNG = "Beendigung", "Beendigung"


class Mitarbeiter(models.Model):
    """Teammitglied. Im Prototyp eigenständig; später an Django-User koppelbar."""
    name = models.CharField("Nachname", max_length=80)
    vorname = models.CharField("Vorname", max_length=80, blank=True)
    kuerzel = models.CharField("Kürzel", max_length=10, blank=True)
    rolle = models.CharField(max_length=20, choices=Rolle.choices, default=Rolle.BETREUER)
    aktiv = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Mitarbeiter*in"
        verbose_name_plural = "Mitarbeiter*innen"
        ordering = ["name", "vorname"]

    def __str__(self):
        return f"{self.name}{', ' + self.vorname if self.vorname else ''}"


class Klient(models.Model):
    """Stammdaten aus der Belegungsliste. AL + kLE = bewilligte FLS pro MONAT."""
    nachname = models.CharField(max_length=80)
    vorname = models.CharField(max_length=80, blank=True)
    geburtsdatum = models.DateField("geb. am", null=True, blank=True)
    bezugsbetreuer = models.ForeignKey(
        Mitarbeiter, on_delete=models.PROTECT, related_name="klienten",
        verbose_name="Bezugsbetreuer*in")
    al = models.DecimalField("bewilligt FLS/Monat (AL)", max_digits=7, decimal_places=3,
                             default=0, validators=[MinValueValidator(Decimal("0"))])
    kle = models.DecimalField("davon kLE/Monat", max_digits=7, decimal_places=3,
                              default=0, validators=[MinValueValidator(Decimal("0"))])
    hbg = models.PositiveSmallIntegerField("HBG", null=True, blank=True)
    vertretung1 = models.ForeignKey(Mitarbeiter, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name="vertretung1_klienten", verbose_name="Vertretung I")
    vertretung2 = models.ForeignKey(Mitarbeiter, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name="vertretung2_klienten", verbose_name="Vertretung II")
    kue_bis = models.DateField("KÜ bis", null=True, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.BETREUUNG)
    brp_bis = models.DateField("BRP zu Teamleitung bis", null=True, blank=True)
    versendet_am = models.DateField("… versendet am", null=True, blank=True)
    person_id = models.CharField("Person-ID", max_length=40, blank=True)
    thfd = models.CharField("Zuständigkeit THFD", max_length=120, blank=True)
    kommentar = models.TextField(blank=True)

    class Meta:
        verbose_name = "Klient*in"
        verbose_name_plural = "Belegungsliste (Klient*innen)"
        ordering = ["nachname", "vorname"]

    def __str__(self):
        return self.name

    @property
    def name(self) -> str:
        return f"{self.nachname}{', ' + self.vorname if self.vorname else ''}"

    @property
    def fls_gesamt(self) -> Decimal:
        """Bewilligte Gesamt-FLS pro Monat = AL + kLE."""
        return (self.al or Decimal("0")) + (self.kle or Decimal("0"))

    @property
    def fls_gesamt_jahr(self) -> Decimal:
        return self.fls_gesamt * 12

    @property
    def kle_anteil(self) -> Decimal:
        g = self.fls_gesamt
        return (self.kle / g).quantize(Decimal("0.001")) if g else Decimal("0")


class Leistung(models.Model):
    """Eine erfasste Leistung im Leistungsnachweis (manuelle 1:1-Zeile)."""
    datum = models.DateField()
    klient = models.ForeignKey(Klient, on_delete=models.PROTECT, related_name="leistungen")
    leistungsart = models.CharField(max_length=4, choices=Leistungsart.choices)
    taetigkeit = models.CharField("Tätigkeit", max_length=120, blank=True)
    betreuer = models.ForeignKey(Mitarbeiter, on_delete=models.PROTECT, related_name="leistungen")
    beginn = models.TimeField(null=True, blank=True)
    ende = models.TimeField(null=True, blank=True)
    notiz = models.CharField(max_length=255, blank=True)
    # Herkunft: manuell erfasst oder automatisch aus Gruppe/Teamsitzung erzeugt
    auto = models.BooleanField("automatisch", default=False)
    erstellt = models.DateTimeField(auto_now_add=True)
    geaendert = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Leistung"
        verbose_name_plural = "Leistungsnachweis"
        ordering = ["-datum", "beginn"]

    def __str__(self):
        return f"{self.datum} · {self.klient} · {self.leistungsart} · {self.dauer_stunden} h"

    @property
    def dauer_stunden(self) -> Decimal:
        return _stunden(self.beginn, self.ende)

    @property
    def monat(self) -> str:
        return self.datum.strftime("%m.%Y")

    @property
    def zaehlt_als_fls(self) -> bool:
        return self.leistungsart in FLS_ARTEN


class Gruppe(models.Model):
    """Gruppenangebot mit mehreren Teilnehmern.
    Zeit/Klient = Gesamtzeit ÷ Anzahl Teilnehmer ÷ Anzahl Mitarbeiter (die geleitet haben)."""
    datum = models.DateField()
    thema = models.CharField(max_length=120)
    leistungsart = models.CharField(max_length=4, choices=Leistungsart.choices, default=Leistungsart.FS)
    beginn = models.TimeField(null=True, blank=True)
    ende = models.TimeField(null=True, blank=True)
    anz_ma = models.PositiveSmallIntegerField("Anz. Mitarbeiter", default=1,
                                              validators=[MinValueValidator(1)])
    teilnehmer = models.ManyToManyField(Klient, related_name="gruppen", blank=True)

    class Meta:
        verbose_name = "Gruppe"
        verbose_name_plural = "Gruppennachweise"
        ordering = ["-datum"]

    def __str__(self):
        return f"{self.datum} · {self.thema}"

    @property
    def dauer_stunden(self) -> Decimal:
        return _stunden(self.beginn, self.ende)

    @property
    def anzahl_teilnehmer(self) -> int:
        return self.teilnehmer.count()

    @property
    def zeit_pro_klient(self) -> Decimal:
        n = self.anzahl_teilnehmer
        ma = max(self.anz_ma or 1, 1)
        if not n:
            return Decimal("0")
        return (self.dauer_stunden / (Decimal(n) * Decimal(ma))).quantize(Q3, ROUND_HALF_UP)


class Parameter(models.Model):
    """Team-Parameter (ein Datensatz je Jahr). Vergütungssätze NICHT hartkodieren."""
    jahr = models.PositiveIntegerField(default=2026, unique=True)
    teamsitzung_wochentag = models.PositiveSmallIntegerField(
        default=3, help_text="0=Mo … 3=Do … 6=So")
    teamsitzung_dauer_std = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal("3.0"))
    fls_preis = models.DecimalField("FLS-Preis €", max_digits=8, decimal_places=2, default=0)

    class Meta:
        verbose_name = "Team-Parameter"
        verbose_name_plural = "Team-Parameter"

    def __str__(self):
        return f"Parameter {self.jahr}"

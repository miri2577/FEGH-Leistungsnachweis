"""Datenmodell FEGH-Leistungsnachweis (Team TBEW, Berlin).

Abgeleitet aus der Excel-Mappe TBEW_Leistungsnachweis_2026:
Belegungsliste (Klienten-Stammdaten) · Leistungsnachweis (Erfassung) ·
Gruppennachweise · Teamsitzung · Fachleistungsstunden-Auswertung.

Fachliche Grundlage: Berlin ab 01.01.2026, Beschluss 3/2026.
Alle Zeit-/Betragsgrößen als Decimal (keine Floats) – abrechnungsrelevant.
"""
from datetime import datetime, date, timedelta as _td
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.db import models
from django.core.validators import MinValueValidator
from simple_history.models import HistoricalRecords


Q3 = Decimal("0.001")  # Rundung auf 3 Nachkommastellen (Stunden)


def _stunden(beginn, ende) -> Decimal:
    """Dauer zwischen zwei Uhrzeiten in Dezimalstunden. Ist das Ende zeitlich vor dem
    Beginn, wird ein Tageswechsel angenommen (Nacht-/Bereitschaftsdienst über
    Mitternacht, z.B. 22:00–06:00 = 8 h) – so gehen solche Zeiten nicht verloren."""
    if not beginn or not ende:
        return Decimal("0")
    delta = datetime.combine(date.min, ende) - datetime.combine(date.min, beginn)
    sekunden = int(delta.total_seconds())
    if sekunden < 0:
        sekunden += 24 * 3600      # Ende am Folgetag (über Mitternacht)
    return (Decimal(sekunden) / Decimal(3600)).quantize(Q3, ROUND_HALF_UP)


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

# Pastell-Palette für die Farbcodierung im Wochenkalender (heller Grund, dunkle Schrift).
FARBPALETTE = [
    "#dbeafe", "#dcfce7", "#fef9c3", "#fee2e2", "#f3e8ff", "#ffedd5",
    "#cffafe", "#fce7f3", "#e0e7ff", "#d9f99d", "#fed7aa", "#c7d2fe",
]


class Rolle(models.TextChoices):
    """Systemrolle. User = Betreuer*in (eigene Klient*innen), Leitung = Team(s),
    Admin = Teams/Mitarbeiter verwalten (KEIN Klientenzugriff, DSGVO-Trennung)."""
    USER = "user", "User (Betreuer*in)"
    LEITUNG = "leitung", "Leitung"
    ADMIN = "admin", "Administration"


class Teamtyp(models.TextChoices):
    BEW = "BEW", "Betreutes Einzelwohnen (BEW)"
    WG = "WG", "Wohngemeinschaft (WG)"
    VERWALTUNG = "Verwaltung", "Verwaltung"


class Status(models.TextChoices):
    BETREUUNG = "Betreuung", "Betreuung"
    BEENDIGUNG = "Beendigung", "Beendigung"


class Genehmigungsstatus(models.TextChoices):
    """Freigabe-Status für Arbeitszeiten und Abwesenheiten (Leitung genehmigt)."""
    BEANTRAGT = "beantragt", "beantragt"
    GENEHMIGT = "genehmigt", "genehmigt"
    ABGELEHNT = "abgelehnt", "abgelehnt"


class Team(models.Model):
    """Organisatorische Einheit. Mitarbeiter*innen und Klient*innen gehören zu einem Team.
    Der Typ steuert später u. a. die Stempeluhr (Verwaltung = fester Arbeitsplatz)."""
    name = models.CharField(max_length=80, unique=True)
    typ = models.CharField(max_length=20, choices=Teamtyp.choices, default=Teamtyp.BEW)
    aktiv = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Team"
        verbose_name_plural = "Teams"
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def ist_verwaltung(self):
        return self.typ == Teamtyp.VERWALTUNG


class Mitarbeiter(models.Model):
    """Teammitglied, verknüpft mit einem Login (Django-User)."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                null=True, blank=True, related_name="mitarbeiter_profil")
    name = models.CharField("Nachname", max_length=80)
    vorname = models.CharField("Vorname", max_length=80, blank=True)
    kuerzel = models.CharField("Kürzel", max_length=10, blank=True)
    rolle = models.CharField(max_length=20, choices=Rolle.choices, default=Rolle.USER)
    team = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, blank=True,
                             related_name="mitglieder", verbose_name="Team (Zugehörigkeit)")
    leitet = models.ManyToManyField(Team, blank=True, related_name="leitungen",
                                    verbose_name="leitet Team(s)",
                                    help_text="Nur für Rolle Leitung: welche Teams diese Person leitet.")
    aktiv = models.BooleanField(default=True)
    # Selfservice-Vorgaben (in der Verwaltung/Admin pflegbar)
    wochenstunden = models.DecimalField("Wochen-Soll (Std)", max_digits=4, decimal_places=1,
                                        default=Decimal("39.0"))
    urlaubstage = models.PositiveSmallIntegerField("Urlaubstage/Jahr", default=30)

    @property
    def ist_leitung(self):
        return self.rolle == Rolle.LEITUNG

    @property
    def ist_admin(self):
        return self.rolle == Rolle.ADMIN

    @property
    def ist_verwaltung(self):
        return bool(self.team and self.team.ist_verwaltung)

    @property
    def tagessoll(self):
        """Soll-Stunden je Arbeitstag = Wochen-Soll ÷ 5."""
        return (self.wochenstunden / Decimal(5)).quantize(Decimal("0.01"))

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
    kuerzel = models.CharField("Kürzel", max_length=6, blank=True,
                               help_text="Kurzzeichen für den Wochenkalender (leer = automatisch aus dem Namen)")
    geburtsdatum = models.DateField("geb. am", null=True, blank=True)
    team = models.ForeignKey(Team, on_delete=models.PROTECT, null=True, blank=True,
                             related_name="klienten", verbose_name="Team")
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
    person_id = models.CharField("Person-ID / Aktenzeichen", max_length=40, blank=True)
    thfd = models.CharField("Zuständigkeit THFD", max_length=120, blank=True)
    kostentraeger = models.CharField("Kostenträger", max_length=120, blank=True,
                                     help_text="Bezirksamt / überörtlicher Träger – Rechnungsempfänger für die Abrechnung")
    kommentar = models.TextField(blank=True)

    class Meta:
        verbose_name = "Klient*in"
        verbose_name_plural = "Belegungsliste (Klient*innen)"
        ordering = ["nachname", "vorname"]
        indexes = [models.Index(fields=["team", "status"])]

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

    @property
    def kuerzel_anzeige(self) -> str:
        """Kurzzeichen für den Wochenkalender: gepflegtes Kürzel oder aus dem Namen abgeleitet."""
        return self.kuerzel or (self.nachname or "?")[:3].title()

    @property
    def farbe(self) -> str:
        """Stabile Pastellfarbe (aus der ID) für die Farbcodierung im Kalender."""
        return FARBPALETTE[self.pk % len(FARBPALETTE)] if self.pk else "#e5e7eb"

    # Frist für den Entwicklungsbericht: 10 Wochen (70 Tage) vor Ende der
    # Kostenübernahme (KÜ) muss der Bericht an den Träger geschrieben sein.
    BERICHT_VORLAUF_TAGE = 70

    @property
    def bericht_faellig_am(self):
        """Datum, ab dem der Bericht geschrieben werden sollte (KÜ-Ende − 10 Wochen)."""
        if not self.kue_bis:
            return None
        return self.kue_bis - _td(self.BERICHT_VORLAUF_TAGE)

    def bericht_offen(self, stichtag=None):
        """True, wenn wir im 10-Wochen-Fenster vor KÜ-Ende sind und der Status Betreuung ist."""
        if not self.kue_bis or self.status != Status.BETREUUNG:
            return False
        stichtag = stichtag or date.today()
        start = self.kue_bis - _td(self.BERICHT_VORLAUF_TAGE)
        return start <= stichtag <= self.kue_bis

    def aktive_bewilligung(self, stichtag=None):
        """Die zum Stichtag gültige Bewilligung (offener Beginn/Ende zählt als gültig)."""
        stichtag = stichtag or date.today()
        return (self.bewilligungen
                .filter(status=BewilligungStatus.AKTIV)
                .filter(models.Q(gueltig_von__lte=stichtag) | models.Q(gueltig_von__isnull=True))
                .filter(models.Q(gueltig_bis__gte=stichtag) | models.Q(gueltig_bis__isnull=True))
                .select_related("kostentraeger")
                .order_by("-gueltig_von").first())

    def sync_cache_aus_bewilligung(self):
        """Hält die abwärtskompatiblen Cache-Felder (al/kle/kue_bis/kostentraeger) aus der
        aktiven Bewilligung aktuell – so bleiben Abrechnung, Wochenauslastung und Vorschuss
        unverändert, obwohl die Bewilligung jetzt die führende Quelle ist. Bewusst per
        .update() (kein save/Auditlog), da es ein abgeleiteter Cache ist."""
        b = self.aktive_bewilligung()
        if not b:
            return
        self.al = b.al_monat
        self.kle = b.kle_monat
        self.kue_bis = b.gueltig_bis
        if b.kostentraeger_id:
            self.kostentraeger = b.kostentraeger.name
        if b.hbg:
            self.hbg = b.hbg
        type(self).objects.filter(pk=self.pk).update(
            al=self.al, kle=self.kle, kue_bis=self.kue_bis,
            kostentraeger=self.kostentraeger, hbg=self.hbg)


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
    dokumentation = models.TextField("Dokumentation", blank=True,
                                     help_text="ausführlicher Verlaufstext bei Bedarf")
    # Zielbezug der Verlaufsdoku (Phase 2/ZLP): auf welche vereinbarten Ziele bezieht
    # sich dieser Eintrag? Optional – Doku ohne Zielbezug bleibt möglich.
    ziele = models.ManyToManyField("Ziel", blank=True, related_name="leistungen")
    # Mobile Unterschrift (Phase 3): Klient*in/Sorgeberechtigte quittieren den Besuch
    # direkt auf dem Gerät (Unterwegs-Modus). PNG als Data-URL; v. a. für Kostenträger,
    # die gegengezeichnete Stundennachweise verlangen (z. B. Jugendämter bezirksabhängig).
    unterschrift = models.TextField(blank=True, editable=False)
    unterschrieben_am = models.DateTimeField(null=True, blank=True)
    # Ursprungs-Termin (nur bei Doku über den Unterwegs-Modus) – macht sichtbar,
    # welche Kalender-Termine bereits dokumentiert sind (Erinnerung an offene).
    termin = models.ForeignKey("Termin", on_delete=models.SET_NULL, null=True, blank=True,
                               related_name="dokumentationen")
    # Herkunft: manuell erfasst oder automatisch aus Gruppe/Teamsitzung erzeugt
    auto = models.BooleanField("automatisch", default=False)
    erstellt = models.DateTimeField(auto_now_add=True)
    geaendert = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Leistung"
        verbose_name_plural = "Leistungsnachweis"
        ordering = ["-datum", "beginn"]
        indexes = [
            models.Index(fields=["klient", "datum"]),
            models.Index(fields=["betreuer", "datum"]),
        ]

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


class Termin(models.Model):
    """Termin im Wochenkalender – je Mitarbeiter*in, optional mit Klient*in.
    Farbe/Kürzel werden zur besseren Unterscheidung aus der/dem Klient*in abgeleitet."""
    mitarbeiter = models.ForeignKey(Mitarbeiter, on_delete=models.CASCADE, related_name="termine")
    klient = models.ForeignKey(Klient, on_delete=models.SET_NULL, null=True, blank=True,
                               related_name="termine", verbose_name="Klient*in")
    datum = models.DateField()
    beginn = models.TimeField()
    ende = models.TimeField(null=True, blank=True)
    titel = models.CharField("Titel", max_length=120, blank=True,
                             help_text="frei, z. B. für interne Termine ohne Klient*in")
    ort = models.CharField("Ort", max_length=120, blank=True)
    notiz = models.CharField(max_length=255, blank=True)
    erstellt = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Termin"
        verbose_name_plural = "Termine"
        ordering = ["datum", "beginn"]
        indexes = [
            models.Index(fields=["mitarbeiter", "datum"]),
            models.Index(fields=["datum"]),
        ]

    def __str__(self):
        return f"{self.datum} {self.beginn:%H:%M} · {self.anzeige}"

    @property
    def anzeige(self) -> str:
        return self.klient.kuerzel_anzeige if self.klient_id else (self.titel or "Termin")

    @property
    def farbe(self) -> str:
        return self.klient.farbe if self.klient_id else "#e5e7eb"

    @property
    def zeit(self) -> str:
        return f"{self.beginn:%H:%M}–{self.ende:%H:%M}" if self.ende else f"{self.beginn:%H:%M}"


class Arbeitszeit(models.Model):
    """Arbeitszeiterfassung je Mitarbeiter*in (Selfservice)."""
    mitarbeiter = models.ForeignKey(Mitarbeiter, on_delete=models.CASCADE, related_name="arbeitszeiten")
    datum = models.DateField()
    beginn = models.TimeField(null=True, blank=True)
    ende = models.TimeField(null=True, blank=True)
    pause_min = models.PositiveSmallIntegerField("Pause (Min)", default=0)
    notiz = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=12, choices=Genehmigungsstatus.choices,
                              default=Genehmigungsstatus.BEANTRAGT)

    class Meta:
        verbose_name = "Arbeitszeit"
        verbose_name_plural = "Arbeitszeiten"
        ordering = ["-datum", "beginn"]
        indexes = [models.Index(fields=["mitarbeiter", "datum"])]

    def __str__(self):
        return f"{self.mitarbeiter} · {self.datum} · {self.dauer_stunden} h"

    @property
    def dauer_stunden(self) -> Decimal:
        brutto = _stunden(self.beginn, self.ende)
        netto = brutto - (Decimal(self.pause_min or 0) / Decimal(60))
        return netto.quantize(Q3, ROUND_HALF_UP) if netto > 0 else Decimal("0")


class Stempelung(models.Model):
    """Kommen/Gehen-Stempelung (Verwaltung, fester Arbeitsplatz). Eine Zeile = eine Sitzung."""
    mitarbeiter = models.ForeignKey(Mitarbeiter, on_delete=models.CASCADE, related_name="stempelungen")
    beginn = models.DateTimeField()
    ende = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Stempelung"
        verbose_name_plural = "Stempelungen"
        ordering = ["-beginn"]
        constraints = [
            # höchstens EINE offene Sitzung je Mitarbeiter*in (verhindert Doppel-Kommen)
            models.UniqueConstraint(fields=["mitarbeiter"], condition=models.Q(ende__isnull=True),
                                    name="eine_offene_stempelung"),
        ]

    def __str__(self):
        return f"{self.mitarbeiter} · {self.beginn:%d.%m.%Y %H:%M}"

    @property
    def offen(self) -> bool:
        return self.ende is None

    def dauer_sekunden(self, jetzt=None) -> int:
        from django.utils import timezone
        ende = self.ende or (jetzt or timezone.now())
        return max(0, int((ende - self.beginn).total_seconds()))


class AbwesenheitArt(models.TextChoices):
    URLAUB = "Urlaub", "Urlaub"
    FREIZEITAUSGLEICH = "Freizeitausgleich", "Freizeitausgleich"
    KRANK = "Krank", "Krank"
    FORTBILDUNG = "Fortbildung", "Fortbildung"
    SONSTIGE = "Sonstige", "Sonstige"


# Rückwärtskompatibler Alias (gleiche Werte) – von Views importiert
AbwesenheitStatus = Genehmigungsstatus


class Abwesenheit(models.Model):
    """Urlaub / Freizeitausgleich / Krank etc. – Antrag & Genehmigung."""
    mitarbeiter = models.ForeignKey(Mitarbeiter, on_delete=models.CASCADE, related_name="abwesenheiten")
    art = models.CharField(max_length=20, choices=AbwesenheitArt.choices, default=AbwesenheitArt.URLAUB)
    von = models.DateField()
    bis = models.DateField()
    status = models.CharField(max_length=12, choices=AbwesenheitStatus.choices,
                              default=AbwesenheitStatus.BEANTRAGT)
    kommentar = models.CharField(max_length=200, blank=True)
    erstellt = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Abwesenheit"
        verbose_name_plural = "Abwesenheiten"
        ordering = ["-von"]

    def __str__(self):
        return f"{self.mitarbeiter} · {self.art} {self.von}–{self.bis}"

    @property
    def werktage(self) -> int:
        """Anzahl Arbeitstage (Mo–Fr ohne Berliner Feiertage) im Zeitraum."""
        from . import services
        return services.werktage(self.von, self.bis)


# Stückelung (Euro) fürs Zählprotokoll – Wert -> Feldname (Noten 100..5, Münzen 2..0,01)
GELDSTUECKELUNG = [
    (Decimal("100"), "n100"), (Decimal("50"), "n50"), (Decimal("20"), "n20"),
    (Decimal("10"), "n10"), (Decimal("5"), "n5"),
    (Decimal("2"), "m2"), (Decimal("1"), "m1"), (Decimal("0.50"), "m050"),
    (Decimal("0.20"), "m020"), (Decimal("0.10"), "m010"), (Decimal("0.05"), "m005"),
    (Decimal("0.02"), "m002"), (Decimal("0.01"), "m001"),
]


class Kasse(models.Model):
    """Kassenbuch eines Teams. Die Verwaltung ist Finanz-Hub (sieht/pflegt alle Kassen).
    Im Team sehen nur Kassenverantwortliche*r und Vertretung die Kasse (plus Leitung,
    die die Zuständigkeit festlegt)."""
    team = models.OneToOneField(Team, on_delete=models.PROTECT, related_name="kasse")
    bezeichnung = models.CharField(max_length=80, blank=True)
    kostenstelle = models.CharField("Kostenstellen-Code", max_length=20, blank=True)
    verantwortlich = models.ForeignKey("Mitarbeiter", on_delete=models.SET_NULL,
                                       null=True, blank=True, related_name="kassen_verantwortlich",
                                       verbose_name="Kassenverantwortliche*r")
    vertretung = models.ForeignKey("Mitarbeiter", on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name="kassen_vertretung",
                                   verbose_name="Vertretung")
    aktiv = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Kasse"
        verbose_name_plural = "Kassen"
        ordering = ["team__name"]

    def __str__(self):
        return self.bezeichnung or f"Kassenbuch {self.team}"


class Kassenmonat(models.Model):
    """Ein Abrechnungsmonat einer Kasse mit Kassenvortrag (Endbestand Vormonat)."""
    kasse = models.ForeignKey(Kasse, on_delete=models.CASCADE, related_name="monate")
    jahr = models.PositiveIntegerField()
    monat = models.PositiveSmallIntegerField()
    vortrag = models.DecimalField("Kassenvortrag", max_digits=10, decimal_places=2, default=0)

    class Meta:
        verbose_name = "Kassenmonat"
        verbose_name_plural = "Kassenmonate"
        ordering = ["-jahr", "-monat"]
        constraints = [models.UniqueConstraint(fields=["kasse", "jahr", "monat"],
                                               name="ein_kassenmonat")]

    def __str__(self):
        return f"{self.kasse} · {self.monat:02d}.{self.jahr}"

    @property
    def einnahmen(self) -> Decimal:
        return sum((b.einnahme for b in self.buchungen.all()), Decimal("0"))

    @property
    def ausgaben(self) -> Decimal:
        return sum((b.ausgabe for b in self.buchungen.all()), Decimal("0"))

    @property
    def endbestand(self) -> Decimal:
        return self.vortrag + self.einnahmen - self.ausgaben

    def naechste_bel_nr(self) -> int:
        letzte = self.buchungen.order_by("-bel_nr").first()
        return (letzte.bel_nr + 1) if letzte else 1


class Kassenbuchung(models.Model):
    """Eine Buchung im Kassenblatt. BuHa-Felder (Buchungsdatum/Kontonr/Kostenstelle)
    füllt die Verwaltung/Buchhaltung."""
    monat = models.ForeignKey(Kassenmonat, on_delete=models.CASCADE, related_name="buchungen")
    bel_nr = models.PositiveIntegerField("Beleg-Nr.")
    datum = models.DateField()
    text = models.CharField(max_length=200)
    einnahme = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    ausgabe = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    # BuHa (Buchhaltung, von der Verwaltung gepflegt)
    buchungsdatum = models.DateField(null=True, blank=True)
    kontonr = models.CharField("Kontonr.", max_length=20, blank=True)
    kostenstelle = models.CharField("Kostenstellen-Code", max_length=20, blank=True)

    class Meta:
        verbose_name = "Kassenbuchung"
        verbose_name_plural = "Kassenbuchungen"
        ordering = ["bel_nr", "id"]
        constraints = [models.UniqueConstraint(fields=["monat", "bel_nr"],
                                               name="eine_belegnr_pro_kassenmonat")]

    def __str__(self):
        return f"{self.bel_nr} · {self.datum} · {self.text}"


class Zaehlprotokoll(models.Model):
    """Monats-Zählprotokoll: physischer Bargeldbestand vs. Buchbestand (Soll-Ist)."""
    monat = models.OneToOneField(Kassenmonat, on_delete=models.CASCADE, related_name="zaehlung")
    datum = models.DateField(null=True, blank=True)
    n100 = models.PositiveIntegerField(default=0)
    n50 = models.PositiveIntegerField(default=0)
    n20 = models.PositiveIntegerField(default=0)
    n10 = models.PositiveIntegerField(default=0)
    n5 = models.PositiveIntegerField(default=0)
    m2 = models.PositiveIntegerField(default=0)
    m1 = models.PositiveIntegerField(default=0)
    m050 = models.PositiveIntegerField(default=0)
    m020 = models.PositiveIntegerField(default=0)
    m010 = models.PositiveIntegerField(default=0)
    m005 = models.PositiveIntegerField(default=0)
    m002 = models.PositiveIntegerField(default=0)
    m001 = models.PositiveIntegerField(default=0)
    nicht_eingetragene = models.DecimalField("nicht eingetragene Belege", max_digits=10,
                                             decimal_places=2, default=0)
    vermerke = models.TextField("Vermerke für die FiBu", blank=True)

    class Meta:
        verbose_name = "Zählprotokoll"
        verbose_name_plural = "Zählprotokolle"

    def __str__(self):
        return f"Zählprotokoll {self.monat}"

    @property
    def bargeld_gesamt(self) -> Decimal:
        return sum((wert * getattr(self, feld) for wert, feld in GELDSTUECKELUNG),
                   Decimal("0")).quantize(Decimal("0.01"))

    @property
    def neuer_bestand(self) -> Decimal:
        m = self.monat
        return (m.vortrag + m.einnahmen - m.ausgaben - self.nicht_eingetragene)

    @property
    def differenz(self) -> Decimal:
        return self.bargeld_gesamt - self.neuer_bestand


class Parameter(models.Model):
    """Team-Parameter (ein Datensatz je Jahr). Vergütungssätze NICHT hartkodieren –
    FLS-Satz und kLE/Tag stammen aus dem Senats-Umrechnungstool (Output-Blatt)."""
    jahr = models.PositiveIntegerField(default=2026, unique=True)
    teamsitzung_wochentag = models.PositiveSmallIntegerField(
        default=3, help_text="0=Mo … 3=Do … 6=So")
    teamsitzung_dauer_std = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal("3.0"))
    fls_preis = models.DecimalField("FLS-Satz €", max_digits=8, decimal_places=4, default=0,
                                    help_text="€ je Fachleistungsstunde (Senats-Tool, Output 3.)")
    kle_je_tag = models.DecimalField(
        "kLE je Leistungsberechtigte*m und Tag (Std)", max_digits=8, decimal_places=6, default=0,
        help_text="kalkulatorische Leistungseinheit – einheitlich für alle Klient*innen, "
                  "je Kalendertag (Senats-Tool, Output 3.). Deckt fallunspezifische Zeiten, "
                  "Erreichbarkeit, Wegezeiten, Sonstiges. 0 = kLE nicht in der Abrechnung.")

    class Meta:
        verbose_name = "Team-Parameter"
        verbose_name_plural = "Team-Parameter"

    def __str__(self):
        return f"Parameter {self.jahr}"


class Umrechnung(models.Model):
    """Eingabewerte des Senats-Umrechnungstools (Input 1) – je Jahr/Parameter.
    Kostensätze und Platzzahl sind individuell mit dem Kostenträger verhandelt und
    hier anpassbar; die App berechnet daraus FLS-Satz, kLE/Tag und FLS/Woche je HBG
    formelgetreu (services_senatstool) und weist die Gegenprobe aus."""
    parameter = models.OneToOneField(Parameter, on_delete=models.CASCADE, related_name="umrechnung")
    kapazitaet = models.PositiveSmallIntegerField("vereinbarte Kapazität (Plätze)", default=0)
    wochenarbeitszeit = models.DecimalField("Wochenarbeitszeit (Std)", max_digits=4,
                                            decimal_places=2, default=Decimal("38.5"))
    auslastung = models.DecimalField("Auslastung", max_digits=5, decimal_places=4,
                                     default=Decimal("0.959"),
                                     help_text="landesweit vereinbart 0,959 – abweichend anpassbar")
    fallunspez_anteil = models.DecimalField("Anteil fallunspezifische Zeiten", max_digits=4,
                                            decimal_places=3, default=Decimal("0.200"))
    erreichbarkeit_mo_fr_std = models.DecimalField(
        "Erreichbarkeit Mo–Fr (Std je Tag)", max_digits=6, decimal_places=2, default=0,
        help_text="Anzahl Mitarb. × Stunden, z. B. 1 MA 10–16 Uhr = 6")
    erreichbarkeit_we_ft_std = models.DecimalField(
        "Erreichbarkeit Sa/So/Feiertag (Std je Tag)", max_digits=6, decimal_places=2, default=0)
    wegezeit_std_vk_woche = models.DecimalField("Ø Wegezeit je VK/Woche (Std)", max_digits=5,
                                                decimal_places=2, default=Decimal("6"))
    pk_alternativ = models.DecimalField(
        "Ø-Personalkosten alternativ €", max_digits=12, decimal_places=2, default=0,
        help_text="0 = Differenzmethode aus den Maßnahmepauschalen (wie das Senats-Tool)")

    class Meta:
        verbose_name = "Umrechnung (Senats-Tool-Eingaben)"
        verbose_name_plural = "Umrechnungen (Senats-Tool-Eingaben)"

    def __str__(self):
        return f"Umrechnung {self.parameter.jahr}"


class HBGSatz(models.Model):
    """Je Hilfebedarfsgruppe (HBG 1–12): die verhandelte Maßnahmepauschale (alt,
    €/Tag) und die Belegung am Stichtag als EINGABEN des Umrechnungsrechners sowie
    die individuellen FLS PRO WOCHE als ERGEBNIS (Senats-Tool Output 5.). Die
    FLS/Woche dienen als Vorbelegung für die Bewilligung in der Belegungsliste;
    der Bescheid der/des einzelnen Klient*in kann davon abweichen."""
    parameter = models.ForeignKey(Parameter, on_delete=models.CASCADE, related_name="hbg_saetze")
    hbg = models.PositiveSmallIntegerField("HBG")
    pauschale_alt = models.DecimalField("Maßnahmepauschale alt (€/Tag)", max_digits=8,
                                        decimal_places=2, default=0)
    belegung_stichtag = models.PositiveSmallIntegerField("Belegung am Stichtag", default=0)
    fls_woche = models.DecimalField("individuelle FLS pro Woche (Std)",
                                    max_digits=7, decimal_places=4, default=0)

    class Meta:
        verbose_name = "HBG-Satz (FLS/Woche)"
        verbose_name_plural = "HBG-Sätze (FLS/Woche)"
        ordering = ["hbg"]
        constraints = [models.UniqueConstraint(fields=["parameter", "hbg"],
                                               name="ein_satz_pro_hbg_und_jahr")]

    def __str__(self):
        return f"HBG {self.hbg} · {self.fls_woche} FLS/Woche ({self.parameter.jahr})"


class Rhythmus(models.TextChoices):
    WOECHENTLICH = "woche", "wöchentlich"
    ZWEIWOECHENTLICH = "2woche", "14-täglich"
    MONATLICH = "monat", "monatlich"
    VIERTELJAEHRLICH = "quartal", "vierteljährlich"
    JAEHRLICH = "jahr", "jährlich"


class Anrechnung(models.TextChoices):
    TEILER = "teiler", "÷ Klient*innen in Betreuung"
    FEST = "fest", "fester Wert je Klient*in"
    KALENDER = "kalender", "nur Kalender (kein Nachweis)"


class WiederkehrendeLeistung(models.Model):
    """Feste, sich wiederholende Leistung/Termin (z. B. Teamsitzung, Supervision).
    Erscheint automatisch als Serie im Kalender und/oder fließt in die
    Leistungsnachweise (FLS) ein. Rhythmus, Zeitpunkt und Anrechnung sind je
    Eintrag frei einstellbar."""
    bezeichnung = models.CharField(max_length=80)
    leistungsart = models.CharField(max_length=4, choices=Leistungsart.choices,
                                    default=Leistungsart.KLE)
    team = models.ForeignKey(Team, on_delete=models.CASCADE, null=True, blank=True,
                             related_name="serienleistungen",
                             verbose_name="Team (leer = alle Teams)")
    # Rhythmus + Zeitpunkt
    rhythmus = models.CharField(max_length=8, choices=Rhythmus.choices, default=Rhythmus.WOECHENTLICH)
    wochentag = models.PositiveSmallIntegerField("Wochentag", default=3,
                                                 help_text="0=Mo … 3=Do … 6=So")
    woche_im_monat = models.SmallIntegerField(
        "Woche im Monat", default=0,
        help_text="Für monatlich per Wochentag: 1.–4., -1 = letzte. 0 = (Wochen-Rhythmus).")
    tag_im_monat = models.PositiveSmallIntegerField(
        "fester Tag im Monat", null=True, blank=True,
        help_text="1–31; wenn gesetzt, statt Wochentag-Regel (monatlich/…).")
    monat_im_jahr = models.PositiveSmallIntegerField(
        "Anker-Monat", null=True, blank=True,
        help_text="1–12: für jährlich (welcher Monat) bzw. vierteljährlich (Startmonat).")
    dauer_std = models.DecimalField("Dauer je Termin (Std)", max_digits=5, decimal_places=2,
                                    default=Decimal("1"))
    # Anrechnung je Klient*in
    anrechnung = models.CharField(max_length=8, choices=Anrechnung.choices, default=Anrechnung.TEILER)
    wert_pro_klient = models.DecimalField("fester Wert je Klient*in (Std)", max_digits=6,
                                          decimal_places=3, default=0,
                                          help_text="nur bei Anrechnung 'fester Wert'.")
    # Gültigkeit / Anzeige
    feiertage_aussparen = models.BooleanField("Berliner Feiertage aussparen", default=True)
    im_kalender = models.BooleanField("im Kalender anzeigen", default=True)
    gilt_ab = models.DateField("gültig ab", null=True, blank=True)
    gilt_bis = models.DateField("gültig bis", null=True, blank=True)
    aktiv = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Wiederkehrende Leistung"
        verbose_name_plural = "Wiederkehrende Leistungen"
        ordering = ["bezeichnung"]

    def __str__(self):
        return f"{self.bezeichnung} ({self.get_rhythmus_display()})"

    @property
    def im_nachweis(self) -> bool:
        """Fließt in Leistungsnachweise/FLS ein (alles außer 'nur Kalender')."""
        return self.anrechnung != Anrechnung.KALENDER

    @property
    def farbe(self) -> str:
        """Stabile Pastellfarbe (aus der ID) für die Serien-Darstellung im Kalender."""
        return FARBPALETTE[(self.pk or 0) % len(FARBPALETTE)]

    @property
    def zeitpunkt_text(self) -> str:
        """Menschenlesbare Beschreibung des Zeitpunkts (für Listen/Kalender)."""
        wd = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag",
              "Samstag", "Sonntag"][self.wochentag]
        if self.rhythmus in (Rhythmus.WOECHENTLICH, Rhythmus.ZWEIWOECHENTLICH):
            return f"{wd}s"
        if self.tag_im_monat:
            wann = f"am {self.tag_im_monat}."
        else:
            pos = {1: "1.", 2: "2.", 3: "3.", 4: "4.", -1: "letzter"}.get(self.woche_im_monat, "1.")
            wann = f"{pos} {wd}"
        if self.rhythmus == Rhythmus.JAEHRLICH and self.monat_im_jahr:
            monat = ["", "Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
                     "August", "September", "Oktober", "November", "Dezember"][self.monat_im_jahr]
            return f"{wann} im {monat}"
        return wann


# ==========================================================================
#  Abrechnung: Freigabe-Workflow (Monatsnachweis) + Rechnungen (Verwaltung)
# ==========================================================================
class Freigabestatus(models.TextChoices):
    """Status des Monatsnachweises je Klient*in. MA stellt fertig, Leitung gibt
    frei, Verwaltung rechnet ab. Jeder Schritt ist protokolliert (Festschreibung)."""
    OFFEN = "offen", "offen"
    EINGEREICHT = "eingereicht", "fertiggestellt (MA)"
    FREIGEGEBEN = "freigegeben", "freigegeben (Leitung)"
    ABGERECHNET = "abgerechnet", "abgerechnet"


class Rechnungsstatus(models.TextChoices):
    ENTWURF = "entwurf", "Entwurf"
    GESTELLT = "gestellt", "gestellt"
    BEZAHLT = "bezahlt", "bezahlt"
    STORNIERT = "storniert", "storniert"


class Rechnungstyp(models.TextChoices):
    RECHNUNG = "rechnung", "Rechnung"
    GUTSCHRIFT = "gutschrift", "Gutschrift (Storno)"


class Rechnung(models.Model):
    """Sammelrechnung an einen Kostenträger für einen Leistungsmonat.
    Positionen = die freigegebenen Monatsnachweise (Monatsfreigabe).
    Eine GUTSCHRIFT (typ) storniert eine bereits gestellte Rechnung beleghaft:
    negativer Betrag, eigener Nummernkreislauf-Eintrag, `storno_zu` zeigt aufs Original."""
    nummer = models.CharField("Rechnungsnummer", max_length=20, unique=True)
    typ = models.CharField(max_length=12, choices=Rechnungstyp.choices,
                           default=Rechnungstyp.RECHNUNG)
    storno_zu = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True,
                                  related_name="gutschriften", verbose_name="Gutschrift zu")
    empfaenger = models.CharField("Empfänger (Kostenträger)", max_length=120)
    empfaenger_anschrift = models.TextField("Anschrift", blank=True)
    # Strukturierter Empfänger für die E-Rechnung (Leitweg-ID, Anschrift). Nullable/abwärts-
    # kompatibel: Bestandsrechnungen behalten nur den Freitext-Empfänger.
    kostentraeger = models.ForeignKey("Kostentraeger", on_delete=models.SET_NULL,
                                      null=True, blank=True, related_name="rechnungen")
    jahr = models.PositiveIntegerField()
    monat = models.PositiveSmallIntegerField()
    datum = models.DateField("Rechnungsdatum")
    faellig_am = models.DateField("fällig am", null=True, blank=True,
                                  help_text="Rechnungsdatum + Zahlungsziel (beim Erstellen gesetzt)")
    betrag = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=10, choices=Rechnungsstatus.choices,
                              default=Rechnungsstatus.ENTWURF)
    notiz = models.CharField(max_length=255, blank=True)
    erstellt_von = models.ForeignKey(Mitarbeiter, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name="rechnungen")
    erstellt = models.DateTimeField(auto_now_add=True)
    # Vollständige Versionshistorie (jede Änderung als Snapshot, inkl. Nutzer) –
    # revisionssicher für Kostenträger-Prüfungen (§ 128 SGB IX).
    history = HistoricalRecords()

    class Meta:
        verbose_name = "Rechnung"
        verbose_name_plural = "Rechnungen"
        ordering = ["-datum", "-nummer"]

    def __str__(self):
        return f"{self.nummer} · {self.empfaenger} · {self.betrag} €"

    @property
    def monat_text(self) -> str:
        return f"{self.monat:02d}.{self.jahr}"

    # ---- Offene Posten / Mahnwesen ----
    @property
    def faelligkeit(self):
        """Fälligkeit; Bestandsrechnungen ohne faellig_am: Rechnungsdatum + 30 Tage."""
        return self.faellig_am or (self.datum + _td(30))

    @property
    def bezahlt_summe(self) -> Decimal:
        return sum((z.betrag for z in self.zahlungen.all()), Decimal("0"))

    @property
    def offener_betrag(self) -> Decimal:
        return (self.betrag or Decimal("0")) - self.bezahlt_summe

    @property
    def ist_offen(self) -> bool:
        """Zählt als offener Posten: gestellt und noch nicht (voll) bezahlt."""
        return self.status == Rechnungsstatus.GESTELLT and self.offener_betrag > 0

    def tage_ueberfaellig(self, stichtag=None) -> int:
        """Tage über Fälligkeit (negativ = noch nicht fällig). Nur für offene relevant."""
        stichtag = stichtag or date.today()
        return (stichtag - self.faelligkeit).days

    @property
    def mahnstufe(self) -> int:
        """Höchste bereits versandte Mahnstufe (0 = noch nicht gemahnt)."""
        m = self.mahnungen.order_by("-stufe").first()
        return m.stufe if m else 0

    def zahlungsstand_aktualisieren(self):
        """Setzt den Status auf 'bezahlt', sobald die Zahlungen den Betrag decken
        (bzw. zurück auf 'gestellt', wenn eine Zahlung gelöscht wurde). Das Schreiben
        läuft als BEDINGTES DB-Update (nur aus dem erwarteten Alt-Status heraus) –
        so kann ein paralleler Storno nie mit 'bezahlt' überschrieben werden."""
        if self.status == Rechnungsstatus.STORNIERT:
            return
        voll = self.offener_betrag <= 0 and (self.betrag or 0) > 0
        neu = Rechnungsstatus.BEZAHLT if voll else (
            Rechnungsstatus.GESTELLT if self.status == Rechnungsstatus.BEZAHLT else self.status)
        if neu != self.status:
            geaendert = (type(self).objects
                         .filter(pk=self.pk, status=self.status)      # nur aus Alt-Status
                         .exclude(status=Rechnungsstatus.STORNIERT)
                         .update(status=neu))
            if geaendert:
                self.status = neu


class Zahlung(models.Model):
    """Zahlungseingang zu einer Rechnung (Teilzahlungen möglich).
    Deckt die Summe den Rechnungsbetrag, wird die Rechnung automatisch 'bezahlt'."""
    rechnung = models.ForeignKey(Rechnung, on_delete=models.CASCADE, related_name="zahlungen")
    datum = models.DateField("Zahlungseingang")
    betrag = models.DecimalField(max_digits=12, decimal_places=2,
                                 validators=[MinValueValidator(Decimal("0.01"))])
    notiz = models.CharField(max_length=200, blank=True)
    erfasst_von = models.ForeignKey(Mitarbeiter, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name="+")
    erstellt = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Zahlung"
        verbose_name_plural = "Zahlungen"
        ordering = ["-datum", "-id"]

    def __str__(self):
        return f"{self.rechnung.nummer} · {self.betrag} € am {self.datum}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.rechnung.zahlungsstand_aktualisieren()

    def delete(self, *args, **kwargs):
        r = self.rechnung
        super().delete(*args, **kwargs)
        r.zahlungsstand_aktualisieren()


class Mahnstufe(models.IntegerChoices):
    ERINNERUNG = 1, "Zahlungserinnerung"
    MAHNUNG_1 = 2, "1. Mahnung"
    MAHNUNG_2 = 3, "2. Mahnung (letzte)"


class Mahnung(models.Model):
    """Versandte Zahlungserinnerung/Mahnung zu einer offenen Rechnung (Historie je Stufe).
    Behörden zahlen i. d. R. nach Erinnerung – die App bildet 3 Stufen ohne Mahngebühren ab
    (öffentliche Kostenträger; Verzugspauschalen wären hier unüblich)."""
    rechnung = models.ForeignKey(Rechnung, on_delete=models.CASCADE, related_name="mahnungen")
    stufe = models.PositiveSmallIntegerField(choices=Mahnstufe.choices)
    datum = models.DateField("Mahndatum")
    frist_tage = models.PositiveSmallIntegerField("Zahlungsfrist (Tage)", default=14)
    notiz = models.CharField(max_length=200, blank=True)
    erstellt_von = models.ForeignKey(Mitarbeiter, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name="+")
    erstellt = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Mahnung"
        verbose_name_plural = "Mahnungen"
        ordering = ["-datum", "-stufe"]
        constraints = [models.UniqueConstraint(fields=["rechnung", "stufe"],
                                               name="eine_mahnung_je_stufe")]

    def __str__(self):
        return f"{self.rechnung.nummer} · {self.get_stufe_display()} vom {self.datum}"

    @property
    def zahlbar_bis(self):
        return self.datum + _td(self.frist_tage)


class Monatsfreigabe(models.Model):
    """Freigabe-/Abrechnungsstatus eines Monatsnachweises (Klient*in × Monat).
    Workflow: OFFEN → (MA) EINGEREICHT → (Leitung) FREIGEGEBEN → (Verwaltung) ABGERECHNET.
    fls_summe/betrag werden beim Einreichen/Freigeben festgeschrieben (abrechnungsrelevant)."""
    klient = models.ForeignKey(Klient, on_delete=models.PROTECT, related_name="freigaben")
    jahr = models.PositiveIntegerField()
    monat = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=12, choices=Freigabestatus.choices,
                              default=Freigabestatus.OFFEN)
    fls_summe = models.DecimalField("Σ FLS Ist (festgeschrieben)", max_digits=8, decimal_places=3, default=0)
    # § 18 Abs. 3 Anlage 4 örV: die Monatsrechnung weist Soll und Ist getrennt aus,
    # das Ist unterteilt nach einzeln/in Gruppe erbracht (Buchst. d/e).
    fls_einzeln = models.DecimalField("davon einzeln erbracht", max_digits=8, decimal_places=3, default=0)
    fls_gruppe = models.DecimalField("davon in Gruppe erbracht", max_digits=8, decimal_places=3, default=0)
    soll_fls = models.DecimalField("Σ FLS nach Bescheid (Monat)", max_digits=8, decimal_places=3, default=0,
                                   help_text="bewilligte FLS/Monat (§ 18 Abs. 3 Buchst. d)")
    vorschuss = models.DecimalField("bewilligter Vorschuss €", max_digits=12, decimal_places=2, default=0,
                                    help_text="(Soll-FLS + Ø-kLE/Monat) × FLS-Satz (§ 18 Abs. 2)")
    kle_summe = models.DecimalField("Σ kLE (festgeschrieben, Std)", max_digits=8, decimal_places=3, default=0,
                                    help_text="kLE je Tag × Kalendertage des Monats (pauschal, § 18 Abs. 1 b)")
    # M3: Abrechnungsart des Monats. 'fls' = Berliner BEW (FLS+kLE, wie bisher);
    # 'tagessatz' = (teil-)stationär über den Belegungskalender (Tage × Entgeltsatz).
    abrechnungsart = models.CharField(max_length=12, default="fls",
                                      choices=[("fls", "FLS + kLE"), ("tagessatz", "Tagessatz")])
    belegungstage = models.PositiveSmallIntegerField("Belegungstage (festgeschrieben)", default=0)
    verguetet_tage = models.DecimalField("vergütete Tage (Äquivalent)", max_digits=6,
                                         decimal_places=2, default=0)
    betrag = models.DecimalField("Betrag € (festgeschrieben)", max_digits=12, decimal_places=2, default=0)
    hinweis = models.CharField("Hinweis (Rückweisung)", max_length=255, blank=True)
    eingereicht_am = models.DateTimeField(null=True, blank=True)
    eingereicht_von = models.ForeignKey(Mitarbeiter, on_delete=models.SET_NULL, null=True, blank=True,
                                        related_name="+")
    freigegeben_am = models.DateTimeField(null=True, blank=True)
    freigegeben_von = models.ForeignKey(Mitarbeiter, on_delete=models.SET_NULL, null=True, blank=True,
                                        related_name="+")
    abgerechnet_am = models.DateTimeField(null=True, blank=True)
    rechnung = models.ForeignKey(Rechnung, on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name="positionen")
    geaendert = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Monatsfreigabe"
        verbose_name_plural = "Monatsfreigaben"
        ordering = ["-jahr", "-monat", "klient__nachname"]
        constraints = [models.UniqueConstraint(fields=["klient", "jahr", "monat"],
                                               name="eine_freigabe_pro_klient_monat")]

    def __str__(self):
        return f"{self.klient} · {self.monat:02d}.{self.jahr} · {self.get_status_display()}"

    @property
    def monat_text(self) -> str:
        return f"{self.monat:02d}.{self.jahr}"

    @property
    def ist_gesperrt(self) -> bool:
        """Nachweis festgeschrieben (nicht mehr durch MA änderbar)?"""
        return self.status in (Freigabestatus.FREIGEGEBEN, Freigabestatus.ABGERECHNET)


# =====================================================================
#  Bewilligung / Kostenzusage (Phase-1-Ausbau: führendes Abrechnungsobjekt)
# =====================================================================
# Umrechnung Bescheid-Einheiten -> Monatswerte (wie services_senatstool/bewilligung_vorschlag):
WOCHEN_JE_MONAT = Decimal("365.25") / Decimal(7) / Decimal(12)   # 4,348214…
TAGE_JE_MONAT = Decimal("365.25") / Decimal(12)                  # 30,4375


class KostentraegerTyp(models.TextChoices):
    BEZIRKSAMT = "Bezirksamt", "Bezirksamt"
    UEBEROERTLICH = "überörtlich", "überörtlicher Träger"
    SELBSTZAHLER = "Selbstzahler", "Selbstzahler"
    SONSTIGE = "Sonstige", "Sonstige"


class Kostentraeger(models.Model):
    """Rechnungsempfänger (Bezirksamt/überörtlicher Träger). Ersetzt den bisherigen
    Freitext am Klienten – gleiche Rechnungen bündeln jetzt zuverlässig über die FK."""
    name = models.CharField("Name", max_length=140)
    typ = models.CharField(max_length=20, choices=KostentraegerTyp.choices,
                           default=KostentraegerTyp.BEZIRKSAMT)
    amt = models.CharField("Amt / Fachbereich", max_length=140, blank=True)
    adresse = models.TextField("Anschrift", blank=True)
    ansprechpartner = models.CharField(max_length=140, blank=True)
    leitweg_id = models.CharField("Leitweg-ID (XRechnung)", max_length=60, blank=True)
    zahlungsziel_tage = models.PositiveSmallIntegerField("Zahlungsziel (Tage)", default=30)
    debitorenkonto = models.CharField("DATEV Debitorenkonto", max_length=9, blank=True,
                                      help_text="für den Buchungsstapel-Export (P4b)")
    aktiv = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Kostenträger"
        verbose_name_plural = "Kostenträger"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Rechnungssteller(models.Model):
    """Stammdaten des rechnungsstellenden Trägers für die E-Rechnung (Verkäufer/BG-4).
    Bewusst als DB-Datensatz (Singleton) – die echten Träger-/Steuerdaten stehen NIE im
    Code/Repo, sondern werden auf der jeweiligen Instanz gepflegt. Eingliederungshilfe ist
    i. d. R. umsatzsteuerfrei (§ 4 Nr. 16 UStG) → USt-Kategorie „E" mit Befreiungsgrund."""
    name = models.CharField("Name / Träger", max_length=160, blank=True)
    strasse = models.CharField("Straße + Nr.", max_length=160, blank=True)
    plz = models.CharField("PLZ", max_length=10, blank=True)
    ort = models.CharField("Ort", max_length=100, blank=True)
    land = models.CharField("Ländercode", max_length=2, default="DE")
    ust_id = models.CharField("USt-IdNr. (BT-31)", max_length=20, blank=True)
    steuernummer = models.CharField("Steuernummer (BT-32)", max_length=30, blank=True)
    # Zahlung
    iban = models.CharField("IBAN", max_length=34, blank=True)
    bic = models.CharField("BIC", max_length=11, blank=True)
    bank = models.CharField("Kreditinstitut", max_length=120, blank=True)
    zahlungsziel_tage = models.PositiveSmallIntegerField("Zahlungsziel (Tage)", default=30)
    # Kontakt (BG-6)
    kontakt_name = models.CharField("Ansprechpartner*in", max_length=120, blank=True)
    kontakt_tel = models.CharField("Telefon", max_length=40, blank=True)
    kontakt_mail = models.EmailField("E-Mail", blank=True)
    # Umsatzsteuer
    ust_befreit = models.BooleanField("umsatzsteuerbefreit", default=True)
    befreiungsgrund = models.CharField("Befreiungsgrund", max_length=200,
                                       default="Steuerfrei nach § 4 Nr. 16 UStG")
    # DATEV-Export (P4b) – Werte kommen vom Steuerbüro
    datev_berater = models.CharField("DATEV Berater-Nr.", max_length=7, blank=True)
    datev_mandant = models.CharField("DATEV Mandanten-Nr.", max_length=5, blank=True)
    datev_erloeskonto = models.CharField("DATEV Erlöskonto", max_length=8, blank=True,
                                         help_text="z. B. steuerfreie Umsätze – mit dem Steuerbüro abstimmen")

    class Meta:
        verbose_name = "Rechnungssteller"
        verbose_name_plural = "Rechnungssteller"

    def __str__(self):
        return self.name or "Rechnungssteller (unvollständig)"

    @classmethod
    def load(cls):
        """Singleton: den einen Stammdatensatz holen/anlegen."""
        obj = cls.objects.first()
        if obj is None:
            obj = cls.objects.create()
        return obj

    @property
    def vollstaendig(self) -> bool:
        """Minimalfelder für eine gültige E-Rechnung vorhanden?"""
        return bool(self.name and self.strasse and self.plz and self.ort
                    and (self.ust_id or self.steuernummer) and self.iban)


class BewilligungStatus(models.TextChoices):
    AKTIV = "aktiv", "aktiv"
    ABGELAUFEN = "abgelaufen", "abgelaufen"
    STORNIERT = "storniert", "storniert"


class Leistungstyp(models.TextChoices):
    FLS_KLE = "FLS", "Fachleistungsstunden + kLE"


class Bewilligung(models.Model):
    """Kostenzusage/Bewilligung als führendes Objekt: WER (Kostenträger) bewilligt
    WAS (Leistungstyp), in welchem ZEITRAUM und welchem KONTINGENT. Speichert die
    Bescheid-nativen Einheiten (FLS/Woche, kLE/Tag); Monatswerte werden abgeleitet.
    Fortschreibungen/Änderungsbescheide bilden über `vorgaenger` eine Kette."""
    klient = models.ForeignKey(Klient, on_delete=models.CASCADE, related_name="bewilligungen")
    kostentraeger = models.ForeignKey(Kostentraeger, on_delete=models.PROTECT,
                                      null=True, blank=True, related_name="bewilligungen")
    aktenzeichen = models.CharField("Aktenzeichen", max_length=60, blank=True)
    leistungstyp = models.CharField(max_length=8, choices=Leistungstyp.choices,
                                    default=Leistungstyp.FLS_KLE)
    # Mehr-Bereichs-Fundament (M1): optionaler Bezug auf den Leistungskatalog.
    # Leer = bisheriges Berliner BEW-Verhalten (FLS+kLE); gesetzt = der Katalogeintrag
    # bestimmt Einheit/Entgelt (Jugendhilfe-FLS, Tagessatz …) für künftige Rechnungsläufe.
    katalog = models.ForeignKey("Leistungskatalog", on_delete=models.PROTECT,
                                null=True, blank=True, related_name="bewilligungen")
    gueltig_von = models.DateField("bewilligt ab", null=True, blank=True)
    gueltig_bis = models.DateField("bewilligt bis", null=True, blank=True)
    fls_woche = models.DecimalField("FLS/Woche (bewilligt)", max_digits=7, decimal_places=4,
                                    default=0, validators=[MinValueValidator(Decimal("0"))])
    kle_tag = models.DecimalField("kLE/Tag", max_digits=7, decimal_places=6,
                                  default=0, validators=[MinValueValidator(Decimal("0"))])
    hbg = models.PositiveSmallIntegerField("HBG (Herkunft)", null=True, blank=True)
    status = models.CharField(max_length=12, choices=BewilligungStatus.choices,
                              default=BewilligungStatus.AKTIV)
    vorgaenger = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="nachfolger", verbose_name="Fortschreibung von")
    kommentar = models.CharField(max_length=200, blank=True)
    erstellt = models.DateTimeField(auto_now_add=True)
    # Versionshistorie: jede Änderung an einer Kostenzusage nachvollziehbar (Snapshots).
    history = HistoricalRecords()

    class Meta:
        verbose_name = "Bewilligung"
        verbose_name_plural = "Bewilligungen"
        ordering = ["-gueltig_von", "-erstellt"]
        indexes = [models.Index(fields=["klient", "status"])]

    def __str__(self):
        z = f"{self.gueltig_von or '?'}–{self.gueltig_bis or 'offen'}"
        return f"{self.klient} · {self.aktenzeichen or 'ohne Az'} · {z}"

    @property
    def al_monat(self) -> Decimal:
        """Bewilligte Fachleistungsstunden pro Monat = FLS/Woche × 4,3482."""
        return ((self.fls_woche or Decimal("0")) * WOCHEN_JE_MONAT).quantize(Q3, ROUND_HALF_UP)

    @property
    def kle_monat(self) -> Decimal:
        """kLE-Monatsäquivalent = kLE/Tag × 30,4375 (Kalendertage/Monat)."""
        return ((self.kle_tag or Decimal("0")) * TAGE_JE_MONAT).quantize(Q3, ROUND_HALF_UP)

    @property
    def fls_gesamt_monat(self) -> Decimal:
        return self.al_monat + self.kle_monat

    @property
    def ist_gueltig_heute(self) -> bool:
        heute = date.today()
        if self.status != BewilligungStatus.AKTIV:
            return False
        if self.gueltig_von and self.gueltig_von > heute:
            return False
        if self.gueltig_bis and self.gueltig_bis < heute:
            return False
        return True

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Abwärtskompatiblen Cache am Klienten nachziehen (Abrechnung liest weiter al/kle/kue_bis).
        self.klient.sync_cache_aus_bewilligung()

    def delete(self, *args, **kwargs):
        klient = self.klient
        super().delete(*args, **kwargs)
        klient.sync_cache_aus_bewilligung()


# ==========================================================================
#  Phase 2: Teilhabe-Dokumentation — Ziele der Ziel- und Leistungsplanung
# ==========================================================================
class ZielArt(models.TextChoices):
    RICHTUNGSZIEL = "richtungsziel", "Richtungsziel"
    HANDLUNGSZIEL = "handlungsziel", "Handlungsziel"


class ZielStatus(models.TextChoices):
    AKTIV = "aktiv", "aktiv"
    ERREICHT = "erreicht", "erreicht"
    ANGEPASST = "angepasst", "angepasst (fortgeschrieben)"
    AUFGEGEBEN = "aufgegeben", "nicht weiterverfolgt"


class Ziel(models.Model):
    """Ziel der Ziel- und Leistungsplanung (ZLP) je Klient*in — Berliner EGH-Systematik
    (§ 11 BRV EGH, Gesamtplan §§ 117 ff. SGB IX): Richtungsziel mit untergeordneten
    Handlungszielen, je mit Indikator der Zielerreichung. Bereichs-neutral angelegt —
    der Hilfeplan § 36 SGB VIII (Jugendhilfe) nutzt dieselbe Struktur (Richtungs-/
    Handlungsziele + Indikatoren). Die Verlaufsdoku (Leistung) kann sich auf Ziele
    beziehen; Änderungen sind versioniert (Fortschreibung nachvollziehbar)."""
    klient = models.ForeignKey(Klient, on_delete=models.CASCADE, related_name="ziele")
    art = models.CharField(max_length=16, choices=ZielArt.choices,
                           default=ZielArt.HANDLUNGSZIEL)
    uebergeordnet = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name="unterziele",
                                      verbose_name="gehört zu (Richtungsziel)")
    titel = models.CharField("Ziel", max_length=200)
    beschreibung = models.TextField("Beschreibung / Handlungsschritte", blank=True)
    indikator = models.TextField("Indikator der Zielerreichung", blank=True,
                                 help_text="Woran erkennen wir, dass das Ziel erreicht ist?")
    status = models.CharField(max_length=12, choices=ZielStatus.choices,
                              default=ZielStatus.AKTIV)
    gueltig_von = models.DateField("vereinbart am", null=True, blank=True)
    gueltig_bis = models.DateField("Zielhorizont", null=True, blank=True)
    reihenfolge = models.PositiveSmallIntegerField(default=0)
    erstellt = models.DateTimeField(auto_now_add=True)
    geaendert = models.DateTimeField(auto_now=True)
    # Fortschreibungen/Anpassungen nachvollziehbar (wie Bewilligung/Rechnung)
    history = HistoricalRecords()

    class Meta:
        verbose_name = "Ziel"
        verbose_name_plural = "Ziele"
        ordering = ["reihenfolge", "id"]
        indexes = [models.Index(fields=["klient", "status"])]

    def __str__(self):
        return f"{self.klient} · {self.get_art_display()}: {self.titel}"

    @property
    def ist_aktiv(self) -> bool:
        return self.status == ZielStatus.AKTIV


# ==========================================================================
#  Phase 2: Berichts-Engine — Berichte mit Vorlagen (als Daten) und Workflow
# ==========================================================================
class Berichtsvorlage(models.Model):
    """Berichtstyp als DATEN statt Code (bereichs-neutral): der EGH-Entwicklungsbericht
    und der Informationsbericht (Vorlage 1.01) sind zwei Datensätze; der Hilfeplan-
    Bericht § 36 SGB VIII (Jugendhilfe) kommt später als weiterer dazu — kein Code-Fork."""
    name = models.CharField(max_length=120)
    bereich = models.CharField(max_length=60, blank=True,
                               help_text="z. B. EGH, Jugendhilfe – rein informativ")
    beschreibung = models.CharField(max_length=255, blank=True)
    abschnitte = models.JSONField("Gliederung", default=list, blank=True,
                                  help_text="Liste der Abschnitts-Überschriften")
    aktiv = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Berichtsvorlage"
        verbose_name_plural = "Berichtsvorlagen"
        ordering = ["name"]

    def __str__(self):
        return self.name


class BerichtsStatus(models.TextChoices):
    OFFEN = "offen", "offen"
    IN_ARBEIT = "in_arbeit", "in Arbeit"
    BESPROCHEN = "besprochen", "mit Klient*in besprochen"
    VERSENDET = "versendet", "versendet"


class Bericht(models.Model):
    """Bericht je Klient*in (Entwicklungs-/Informationsbericht) mit Workflow:
    offen → in Arbeit → mit Klient*in besprochen (Pflicht-Schritt örV/AV Hilfeplanung)
    → versendet. Die Fälligkeit kommt i. d. R. aus der KÜ-Frist; 'versendet' pflegt
    das bestehende Feld Klient.versendet_am automatisch nach."""
    klient = models.ForeignKey(Klient, on_delete=models.CASCADE, related_name="berichte")
    vorlage = models.ForeignKey(Berichtsvorlage, on_delete=models.SET_NULL,
                                null=True, blank=True, related_name="berichte")
    zeitraum_von = models.DateField("Berichtszeitraum von", null=True, blank=True)
    zeitraum_bis = models.DateField("Berichtszeitraum bis", null=True, blank=True)
    faellig_am = models.DateField("fällig am", null=True, blank=True)
    status = models.CharField(max_length=12, choices=BerichtsStatus.choices,
                              default=BerichtsStatus.OFFEN)
    inhalt = models.TextField("Berichtstext", blank=True,
                              help_text="entsteht i. d. R. KI-gestützt in FEGH-Bericht (TeilhabeAssist)")
    besprochen_am = models.DateField(null=True, blank=True)
    versendet_am = models.DateField(null=True, blank=True)
    # Wann wurde zuletzt das Rohpaket für FEGH-Bericht (TeilhabeAssist) exportiert?
    # Feld-Änderung landet im Auditlog -> Wer/Wann-Nachweis für den Art-9-Export.
    exportiert_am = models.DateTimeField(null=True, blank=True)
    notiz = models.CharField(max_length=200, blank=True)
    erstellt_von = models.ForeignKey(Mitarbeiter, on_delete=models.SET_NULL,
                                     null=True, blank=True, related_name="+")
    erstellt = models.DateTimeField(auto_now_add=True)
    geaendert = models.DateTimeField(auto_now=True)
    # Workflow-Historie ohne den Art-9-Berichtstext (Datenminimierung in der History-Tabelle)
    history = HistoricalRecords(excluded_fields=["inhalt"])

    class Meta:
        verbose_name = "Bericht"
        verbose_name_plural = "Berichte"
        ordering = ["-faellig_am", "-id"]
        indexes = [models.Index(fields=["klient", "status"])]

    def __str__(self):
        v = self.vorlage.name if self.vorlage else "Bericht"
        return f"{self.klient} · {v} · fällig {self.faellig_am or '—'}"

    @property
    def ueberfaellig(self) -> bool:
        return (self.status != BerichtsStatus.VERSENDET and self.faellig_am is not None
                and self.faellig_am < date.today())


# ==========================================================================
#  Mehr-Bereichs-Fundament (M1): Leistungskatalog + Entgeltsätze als DATEN
#  (Vivendi-Prinzip: Leistungsarten/Preise sind konfigurierbar, kein Code-Fork)
# ==========================================================================
class Abrechnungseinheit(models.TextChoices):
    FLS_STUNDE = "fls_stunde", "Fachleistungsstunde (dokumentiert)"
    KLE_TAG = "kle_tag", "kLE je Kalendertag (pauschal)"
    TAGESSATZ = "tagessatz", "Tagessatz je Belegungstag"
    OEFFNUNGSTAG = "oeffnungstag", "Tagessatz je Öffnungstag (teilstationär)"
    PAUSCHALE = "pauschale", "Pauschale (je Monat/Ereignis)"


class Leistungskatalog(models.Model):
    """Abrechenbarer Leistungstyp als Datensatz: WAS wird nach WELCHER Einheit und
    Rechtsgrundlage vergütet. Berliner BEW-FLS, kLE, Jugendhilfe-FLS und Tagessätze
    sind Katalogeinträge — neue Bereiche (Wohnheim, Tagesgruppe …) kommen als Daten
    dazu, nicht als Code."""
    name = models.CharField(max_length=120, unique=True)
    rechtsgrundlage = models.CharField(max_length=80, blank=True,
                                       help_text="z. B. SGB IX §§ 113 ff. / SGB VIII § 31")
    einheit = models.CharField(max_length=16, choices=Abrechnungseinheit.choices,
                               default=Abrechnungseinheit.FLS_STUNDE)
    beschreibung = models.CharField(max_length=255, blank=True)
    aktiv = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Leistungskatalog-Eintrag"
        verbose_name_plural = "Leistungskatalog"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Entgeltsatz(models.Model):
    """Preis eines Katalogeintrags als ZEITSCHEIBE: Fortschreibungen (jährliche
    VK-/Kommissions-Beschlüsse) werden als neuer Satz ab Stichtag angelegt und
    preisen laufende Fälle um — ohne neue Bewilligung. `kostentraeger` leer =
    landeseinheitlich/für alle (z. B. Berliner Jugendhilfe-FLS); gesetzt =
    trägerindividuell verhandelter Satz. Tagessätze weisen die drei Entgelt-
    bestandteile getrennt aus (BRV Jug: Leistungsentgelt/Nebenkosten § 39/Invest)."""
    katalog = models.ForeignKey(Leistungskatalog, on_delete=models.CASCADE,
                                related_name="saetze")
    kostentraeger = models.ForeignKey(Kostentraeger, on_delete=models.CASCADE,
                                      null=True, blank=True, related_name="entgeltsaetze",
                                      verbose_name="Kostenträger (leer = alle)")
    variante = models.CharField(max_length=60, blank=True,
                                help_text="z. B. „mit Leitungsanteil“ / „ohne“")
    gueltig_von = models.DateField("gültig ab")
    gueltig_bis = models.DateField("gültig bis", null=True, blank=True)
    betrag = models.DecimalField("Betrag €", max_digits=9, decimal_places=4,
                                 validators=[MinValueValidator(Decimal("0"))])
    betrag_nebenkosten = models.DecimalField("davon Nebenkosten €", max_digits=9,
                                             decimal_places=4, default=0)
    betrag_investition = models.DecimalField("davon Investition €", max_digits=9,
                                             decimal_places=4, default=0)
    kommentar = models.CharField(max_length=200, blank=True,
                                 help_text="z. B. Beschluss-Nr. der Fortschreibung")
    history = HistoricalRecords()

    class Meta:
        verbose_name = "Entgeltsatz"
        verbose_name_plural = "Entgeltsätze"
        ordering = ["katalog", "-gueltig_von"]
        indexes = [models.Index(fields=["katalog", "gueltig_von"])]

    def __str__(self):
        kt = self.kostentraeger.name if self.kostentraeger else "alle"
        return f"{self.katalog} · {self.betrag} € ab {self.gueltig_von} ({kt})"

    def gilt_am(self, stichtag) -> bool:
        if self.gueltig_von > stichtag:
            return False
        return self.gueltig_bis is None or self.gueltig_bis >= stichtag


# ==========================================================================
#  Mehr-Bereichs-Fundament (M2): Angebote, Belegung, Abwesenheits-Regeln
#  ((teil-)stationäre Bereiche: Wohnheim, WG, Wohngruppe/Tagesgruppe SGB VIII)
# ==========================================================================
class AngebotsTyp(models.TextChoices):
    BEW_EINZEL = "bew", "BEW / TBEW (ambulant, Einzelwohnen)"
    WG_VERBUND = "wg", "WG / verbundene Wohnform (EGH)"
    BESONDERE_WOHNFORM = "wohnform", "besondere Wohnform (EGH, ehem. stationär)"
    WOHNGRUPPE_JUG = "wohngruppe", "Wohngruppe Jugendhilfe (§ 34/35a SGB VIII)"
    TAGESGRUPPE = "tagesgruppe", "Tagesgruppe (§ 32 SGB VIII, teilstationär)"


class Erreichbarkeit(models.TextChoices):
    OHNE = "ohne", "ohne besondere Erreichbarkeit"
    TAG = "tag", "Tag-Präsenz"
    NACHT = "nacht", "Nacht-Bereitschaft/-Präsenz"
    TAG_NACHT = "tag_nacht", "Tag + Nacht (24h)"


class Angebot(models.Model):
    """Leistungsangebot/Standort zwischen Team und Klient*in (Vivendi: Bereichsbaum).
    Trägt Platzzahl, Erreichbarkeitsprofil (örV-Vergleichskreise) und den Default-
    Leistungstyp für die Abrechnung. BEW braucht kein Angebot — es ist der Trivialfall."""
    name = models.CharField(max_length=120)
    team = models.ForeignKey(Team, on_delete=models.PROTECT, related_name="angebote")
    typ = models.CharField(max_length=16, choices=AngebotsTyp.choices,
                           default=AngebotsTyp.WG_VERBUND)
    katalog = models.ForeignKey(Leistungskatalog, on_delete=models.PROTECT,
                                null=True, blank=True, related_name="angebote",
                                verbose_name="Standard-Leistungstyp (Abrechnung)")
    erreichbarkeit = models.CharField(max_length=12, choices=Erreichbarkeit.choices,
                                      default=Erreichbarkeit.OHNE)
    plaetze = models.PositiveSmallIntegerField("Plätze", default=0)
    betriebserlaubnis = models.CharField("Betriebserlaubnis (§ 45 SGB VIII) / Kennung",
                                         max_length=80, blank=True)
    adresse = models.CharField(max_length=160, blank=True)
    aktiv = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Angebot"
        verbose_name_plural = "Angebote"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.get_typ_display()})"


class Belegung(models.Model):
    """Platz-Belegung: Klient*in wohnt/ist im Angebot von Einzug bis Auszug.
    Aufnahme- und Entlasstag zählen je als voller Belegungstag (BRV Jug)."""
    klient = models.ForeignKey(Klient, on_delete=models.CASCADE, related_name="belegungen")
    angebot = models.ForeignKey(Angebot, on_delete=models.PROTECT, related_name="belegungen")
    platz = models.CharField("Platz/Zimmer", max_length=40, blank=True)
    einzug = models.DateField()
    auszug = models.DateField(null=True, blank=True)
    kommentar = models.CharField(max_length=200, blank=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = "Belegung"
        verbose_name_plural = "Belegungen"
        ordering = ["-einzug"]
        indexes = [models.Index(fields=["angebot", "einzug"])]

    def __str__(self):
        return f"{self.klient} in {self.angebot.name} ab {self.einzug}"

    def belegt_am(self, tag) -> bool:
        if tag < self.einzug:
            return False
        return self.auszug is None or tag <= self.auszug


class AbwesenheitsBasis(models.TextChoices):
    JE_EREIGNIS = "ereignis", "je Ereignis (zusammenhängend)"
    KALENDERJAHR = "jahr", "kumulativ je Kalenderjahr"


class AbwesenheitsartKlient(models.Model):
    """Abwesenheitsart mit VERGÜTUNGSREGELN ALS DATEN (Vivendi-Prinzip): die Regeln
    aus BRV Jug Tz 22 (Krankenhaus 3 Monate, Urlaub 30 T/Jahr, Entweichung 14 T …)
    und Beschluss 8/2007 EGH (Freihaltegeld minus Beköstigung, 91-Tage-Kontingent,
    Kurzbesuch ≤ 3 T ohne Anrechnung) sind Datensätze — neue Regeln ohne Code."""
    name = models.CharField(max_length=80, unique=True)
    kuerzel = models.CharField(max_length=4, help_text="fürs Kalenderraster, z. B. KH")
    verguetung_prozent = models.PositiveSmallIntegerField(
        "Vergütung %", default=100,
        help_text="Anteil des Tagessatzes innerhalb der Weiterzahlungsgrenze")
    abzug_je_tag = models.DecimalField(
        "Abzug €/Tag", max_digits=7, decimal_places=2, default=0,
        help_text="z. B. Beköstigungssatz beim EGH-Freihaltegeld")
    max_tage = models.PositiveSmallIntegerField(
        "Weiterzahlungsgrenze (Tage)", null=True, blank=True,
        help_text="leer = unbegrenzt; darüber 0 % Vergütung")
    basis = models.CharField(max_length=10, choices=AbwesenheitsBasis.choices,
                             default=AbwesenheitsBasis.JE_EREIGNIS)
    meldefrist_tage = models.PositiveSmallIntegerField(
        "Meldefrist (Tage)", null=True, blank=True,
        help_text="Warnung, wenn die Abwesenheit länger dauert und nicht gemeldet ist "
                  "(BRV Jug: Meldung ans Jugendamt ab dem 4. Tag → 3)")
    kommentar = models.CharField(max_length=200, blank=True)
    aktiv = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Abwesenheitsart (Klient)"
        verbose_name_plural = "Abwesenheitsarten (Klient)"
        ordering = ["name"]

    def __str__(self):
        return self.name


class KlientAbwesenheit(models.Model):
    """Abwesenheit einer belegten Klient*in (Krankenhaus, Urlaub …). Konvention:
    `von` = erster Abwesenheitstag (Abreisetag zählt als abwesend), `bis` = letzter
    Abwesenheitstag — der Rückkehrtag wird NICHT eingetragen (zählt als Anwesenheit,
    Beschluss 8/2007). `gemeldet_am` dokumentiert die Meldung an den Kostenträger."""
    belegung = models.ForeignKey(Belegung, on_delete=models.CASCADE,
                                 related_name="abwesenheiten")
    art = models.ForeignKey(AbwesenheitsartKlient, on_delete=models.PROTECT,
                            related_name="abwesenheiten")
    von = models.DateField("abwesend ab (Abreisetag)")
    bis = models.DateField("letzter Abwesenheitstag", null=True, blank=True,
                           help_text="leer = dauert an")
    gemeldet_am = models.DateField("dem Kostenträger gemeldet am", null=True, blank=True)
    kommentar = models.CharField(max_length=200, blank=True)
    # Freitext (kann Gesundheitsbezug haben) bleibt aus der History-Tabelle heraus –
    # konsistent zur Auditlog-Datenminimierung (exclude_fields in settings).
    history = HistoricalRecords(excluded_fields=["kommentar"])

    class Meta:
        verbose_name = "Klienten-Abwesenheit"
        verbose_name_plural = "Klienten-Abwesenheiten"
        ordering = ["-von", "-id"]

    def __str__(self):
        return f"{self.belegung.klient} · {self.art} ab {self.von}"

    def abwesend_am(self, tag) -> bool:
        if tag < self.von:
            return False
        return self.bis is None or tag <= self.bis


# ==========================================================================
#  P4a: QM-Pflichtkern — Vorkommnis-Meldewesen (§ 37a SGB IX Gewaltschutz,
#  WTG Berlin § 19 f. besondere Vorkommnisse, § 8a SGB VIII Kindeswohl)
# ==========================================================================
class VorkommnisKategorie(models.TextChoices):
    GEWALT = "gewalt", "Gewaltvorfall / Übergriff (§ 37a SGB IX)"
    KINDESWOHL = "kindeswohl", "Gefährdungseinschätzung (§ 8a SGB VIII)"
    UNFALL = "unfall", "Unfall / medizinischer Notfall"
    MEDIKATION = "medikation", "Medikationsfehler"
    BESCHWERDE = "beschwerde", "Beschwerde"
    SONSTIG = "sonstig", "sonstiges besonderes Vorkommnis"


class VorkommnisStatus(models.TextChoices):
    OFFEN = "offen", "offen"
    IN_BEARBEITUNG = "in_bearbeitung", "in Bearbeitung"
    ABGESCHLOSSEN = "abgeschlossen", "abgeschlossen"


class Vorkommnis(models.Model):
    """Besonderes Vorkommnis mit Melde-Workflow: Erfassung → Sofortmaßnahmen →
    Meldung an Aufsicht/Kostenträger (WTG: unverzüglich!) → Auswertung/Maßnahmen →
    Abschluss durch die Leitung. Kernstück des QM-Pflichtteils (§ 37a Gewaltschutz);
    die Auswertung („Was ändern wir?") ist bewusst Pflicht vor dem Abschluss."""
    datum = models.DateField("Vorfallsdatum")
    uhrzeit = models.TimeField(null=True, blank=True)
    kategorie = models.CharField(max_length=12, choices=VorkommnisKategorie.choices)
    klient = models.ForeignKey(Klient, on_delete=models.SET_NULL, null=True, blank=True,
                               related_name="vorkommnisse",
                               verbose_name="betroffene Klient*in (optional)")
    team = models.ForeignKey(Team, on_delete=models.PROTECT, related_name="vorkommnisse")
    angebot = models.ForeignKey(Angebot, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="vorkommnisse")
    beschreibung = models.TextField("Was ist passiert?")                # Art-9-Freitext
    sofortmassnahmen = models.TextField("Sofortmaßnahmen", blank=True)  # Art-9-Freitext
    massnahmen = models.TextField("Auswertung / abgeleitete Maßnahmen", blank=True,
                                  help_text="Pflicht vor dem Abschluss")
    gemeldet_an = models.CharField("gemeldet an", max_length=160, blank=True,
                                   help_text="z. B. WTG-Aufsicht, Jugendamt, Kostenträger, Polizei")
    gemeldet_am = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=VorkommnisStatus.choices,
                              default=VorkommnisStatus.OFFEN)
    abgeschlossen_am = models.DateField(null=True, blank=True)
    abgeschlossen_von = models.ForeignKey(Mitarbeiter, on_delete=models.SET_NULL,
                                          null=True, blank=True, related_name="+")
    erstellt_von = models.ForeignKey(Mitarbeiter, on_delete=models.SET_NULL,
                                     null=True, blank=True, related_name="+")
    erstellt = models.DateTimeField(auto_now_add=True)
    geaendert = models.DateTimeField(auto_now=True)
    # Workflow-Historie ohne die Art-9-Freitexte (Datenminimierung wie Bericht/Ziel)
    history = HistoricalRecords(excluded_fields=["beschreibung", "sofortmassnahmen",
                                                 "massnahmen"])

    class Meta:
        verbose_name = "Vorkommnis"
        verbose_name_plural = "Vorkommnisse"
        ordering = ["-datum", "-id"]
        indexes = [models.Index(fields=["team", "status"])]

    def __str__(self):
        return f"{self.get_kategorie_display()} am {self.datum} ({self.team.name})"

    MELDEPFLICHTIG = ("gewalt", "kindeswohl", "unfall", "medikation")

    @property
    def meldung_faellig(self) -> bool:
        """Meldepflichtige Kategorie ohne dokumentierte Meldung (WTG: unverzüglich)."""
        return (self.kategorie in self.MELDEPFLICHTIG
                and self.gemeldet_am is None
                and self.status != VorkommnisStatus.ABGESCHLOSSEN)

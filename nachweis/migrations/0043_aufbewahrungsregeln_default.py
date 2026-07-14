"""Default-Aufbewahrungsregeln (Rechtsstand Juli 2026). Idempotent per get_or_create –
die/der Datenschutzbeauftragte kann die Werte je Instanz anpassen. Rechtsgrundlagen
recherchiert; für die belastbare Endfassung mit Fachjurist*in/Kostenträger gegenprüfen
(v. a. § 9b SGB VIII für freie Träger – greift nur bei entsprechender Vereinbarung)."""
from django.db import migrations

REGELN = [
    ("abrechnung", "Abrechnung & Buchungsbelege", 8,
     "§ 147 Abs. 3 i.V.m. Abs. 1 Nr. 4 AO; § 257 HGB; § 14b UStG",
     "seit BEG IV (01.01.2025) 8 statt 10 J.; Frist ab Schluss des Kalenderjahres"),
    ("leistungsnachweis", "Leistungsnachweise (Abrechnungsgrundlage)", 8,
     "§ 147 AO (als Buchungsbeleg)",
     "im Zweifel an die Fachakte koppeln, nicht vor dem Leistungsfall löschen"),
    ("kasse", "Kassenbuch & Zählprotokolle", 10,
     "§ 147 Abs. 1 Nr. 1 AO (h. M.)",
     "Kassenbuch konservativ 10 J.; Einzelbelege/Protokolle wären 8 J."),
    ("fachdoku_egh", "Fachakte Eingliederungshilfe (SGB IX)", 10,
     "abgeleitet: Verjährung/Nachweispflicht + Art. 17 DSGVO",
     "nicht spezialgesetzlich fixiert; bei Haftungsrisiko bis 30 J. (§ 199 BGB)"),
    ("fachdoku_jug", "Fachakte Jugendhilfe (SGB VIII)", 70,
     "§ 9b Abs. 2 SGB VIII (seit 01.07.2025)",
     "70 J. nach Vollendung des 30. Lj.; für freie Träger nur bei Vereinbarung"),
    ("wtg", "Dokumentation stationär (WTG Berlin)", 5,
     "§ 22 Abs. 4 WTG Berlin",
     "einrichtungsseitige Doku; NICHT mit § 34 (10 J., nur Aufsichtsbehörde) verwechseln"),
    ("dokument", "Abgelegte Dokumente", 10,
     "je nach Inhalt (Bescheide/Verträge) – Fachakte-analog",
     "Default an die längste zugeordnete Fachfrist koppeln"),
    ("personal", "Arbeitszeit & Dienstplan", 2,
     "§ 16 Abs. 2 ArbZG; § 17 Abs. 1 MiLoG",
     "Arbeitszeitnachweise 2 J.; im Heimkontext teils 5 J."),
]


def seed(apps, schema_editor):
    Regel = apps.get_model("nachweis", "Aufbewahrungsregel")
    for kat, bez, jahre, grund, hinweis in REGELN:
        Regel.objects.get_or_create(
            kategorie=kat,
            defaults={"bezeichnung": bez, "jahre": jahre,
                      "rechtsgrundlage": grund, "hinweis": hinweis, "aktiv": True})


def entfernen(apps, schema_editor):
    Regel = apps.get_model("nachweis", "Aufbewahrungsregel")
    Regel.objects.filter(kategorie__in=[r[0] for r in REGELN]).delete()


class Migration(migrations.Migration):
    dependencies = [("nachweis", "0042_aufbewahrungsregel")]
    operations = [migrations.RunPython(seed, entfernen)]

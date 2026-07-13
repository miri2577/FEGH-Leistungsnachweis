# Standard-Berichtsvorlagen (idempotent): EGH-Entwicklungsbericht + Informationsbericht 1.01.
# Vorlagen sind DATEN – weitere (z. B. Hilfeplan-Bericht § 36 SGB VIII) kommen ohne Migration
# über die Verwaltung dazu.
from django.db import migrations

VORLAGEN = [
    {
        "name": "Entwicklungsbericht Eingliederungshilfe",
        "bereich": "EGH",
        "beschreibung": "Bericht zur Fortschreibung der Kostenübernahme (10 Wochen vor KÜ-Ende)",
        "abschnitte": [
            "Aktuelle Lebenssituation",
            "Verlauf der Betreuung im Berichtszeitraum",
            "Zielerreichung (ZLP) und Indikatoren",
            "Veränderungen des Bedarfs",
            "Perspektive und Empfehlung",
        ],
    },
    {
        "name": "Informationsbericht (Vorlage 1.01)",
        "bereich": "EGH",
        "beschreibung": "Berliner Informationsbericht – kompatibel zur KI-Erstellung in FEGH-Bericht (TeilhabeAssist)",
        "abschnitte": [
            "Anlass des Berichts",
            "Aktuelle Situation",
            "Zielerreichung",
            "Weiterer Unterstützungsbedarf",
            "Ausblick / Empfehlung",
        ],
    },
    # SGB VIII: Berichte der Jugend-/Familienhilfe sehen ANDERS aus als die EGH-Berichte
    # (AV Hilfeplanung Berlin: Bericht 2 Wochen vor jeder Hilfekonferenz, Wirkungs-
    # dimensionen Ist/Soll, mit Familie/jungem Menschen zu besprechen).
    {
        "name": "Entwicklungsbericht zur Hilfekonferenz (§ 36 SGB VIII)",
        "bereich": "Jugendhilfe/Familienhilfe",
        "beschreibung": "i. d. R. 2 Wochen vor der Hilfekonferenz; vorab mit Familie/jungem Menschen besprechen, Kopie aushändigen",
        "abschnitte": [
            "Anlass und Hilfeverlauf seit der letzten Hilfekonferenz",
            "Situation des jungen Menschen / der Familie",
            "Zielerreichung mit Wirkungsdimensionen (Ist/Soll)",
            "Zusammenarbeit mit der Familie und weiteren Beteiligten",
            "Einschätzung und Empfehlung zur Fortführung der Hilfe",
        ],
    },
    {
        "name": "Abschlussbericht Hilfe zur Erziehung (SGB VIII)",
        "bereich": "Jugendhilfe/Familienhilfe",
        "beschreibung": "zum Abschlussgespräch (4–6 Wochen vor Hilfeende) vorab zu übermitteln",
        "abschnitte": [
            "Hilfeverlauf im Überblick",
            "Erreichte Ziele und Wirkungen",
            "Gründe der Beendigung",
            "Übergänge und Anschlussperspektiven (§ 41 SGB VIII)",
            "Abschließende Einschätzung",
        ],
    },
]


def vorwaerts(apps, schema_editor):
    Berichtsvorlage = apps.get_model("nachweis", "Berichtsvorlage")
    for v in VORLAGEN:
        Berichtsvorlage.objects.get_or_create(name=v["name"], defaults=v)


def rueckwaerts(apps, schema_editor):
    Berichtsvorlage = apps.get_model("nachweis", "Berichtsvorlage")
    Berichtsvorlage.objects.filter(name__in=[v["name"] for v in VORLAGEN],
                                   berichte__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [("nachweis", "0026_berichtsvorlage_historicalbericht_bericht")]
    operations = [migrations.RunPython(vorwaerts, rueckwaerts)]

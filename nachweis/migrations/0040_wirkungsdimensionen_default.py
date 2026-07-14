# Die 8 Berliner Wirkungsdimensionen (idempotent) — Quelle: Fachkonzept der Berliner
# Wirkungsevaluation (Senatsbericht Fach- und Finanzcontrolling HzE, Drs. 19/1350;
# verbindlich im Hilfeplanverfahren seit AV Hilfeplanung vom 01.05.2026, Abschnitt 4).
# 5 personenbezogene + 3 familienbezogene Dimensionen; Skala 7-stufig (niedriger = besser).
from django.db import migrations

DIMENSIONEN = [
    ("Entwicklung, Selbstständigkeit und Teilhabe", "person"),
    ("Psychische/emotionale Stabilität und Gesundheit", "person"),
    ("Sicherheit, Schutz und Obhut", "person"),
    ("Kita, Schule, Ausbildung und Förderung", "person"),
    ("Sozial- und Beziehungsverhalten", "person"),
    ("Erziehungs- und Beziehungskompetenz", "familie"),
    ("Ressourcen in der Familie und im Umfeld", "familie"),
    ("Materielle Ressourcen", "familie"),
]


def vorwaerts(apps, schema_editor):
    Wirkungsdimension = apps.get_model("nachweis", "Wirkungsdimension")
    for i, (name, bereich) in enumerate(DIMENSIONEN):
        Wirkungsdimension.objects.get_or_create(
            name=name, defaults={"bereich": bereich, "reihenfolge": i})


def rueckwaerts(apps, schema_editor):
    Wirkungsdimension = apps.get_model("nachweis", "Wirkungsdimension")
    Wirkungsdimension.objects.filter(
        name__in=[n for n, _ in DIMENSIONEN], einschaetzungen__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [("nachweis", "0039_wirkungsdimension_historicalziel_erreicht_grad_and_more")]
    operations = [migrations.RunPython(vorwaerts, rueckwaerts)]

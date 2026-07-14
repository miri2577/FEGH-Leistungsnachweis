# Standard-Schichtarten (idempotent) – Zeiten sind trägerindividuell anpassbar.
from django.db import migrations

ARTEN = [
    {"name": "Frühdienst", "kuerzel": "F", "beginn": "06:30", "ende": "14:30",
     "farbe": "#2e9e5b"},
    {"name": "Tagdienst", "kuerzel": "T", "beginn": "09:00", "ende": "17:00",
     "farbe": "#0e7490"},
    {"name": "Spätdienst", "kuerzel": "S", "beginn": "13:30", "ende": "21:30",
     "farbe": "#e08600"},
    {"name": "Nachtdienst", "kuerzel": "N", "beginn": "21:00", "ende": "07:00",
     "farbe": "#6f5bd1", "ist_nachtdienst": True},
    {"name": "Bereitschaft (Nacht)", "kuerzel": "B", "beginn": "21:00", "ende": "07:00",
     "farbe": "#8a97a6", "ist_nachtdienst": True},
]


def vorwaerts(apps, schema_editor):
    Schichtart = apps.get_model("nachweis", "Schichtart")
    for a in ARTEN:
        Schichtart.objects.get_or_create(name=a["name"], defaults=a)


def rueckwaerts(apps, schema_editor):
    Schichtart = apps.get_model("nachweis", "Schichtart")
    Schichtart.objects.filter(name__in=[a["name"] for a in ARTEN],
                              dienste__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [("nachweis", "0037_schichtart_dienst")]
    operations = [migrations.RunPython(vorwaerts, rueckwaerts)]

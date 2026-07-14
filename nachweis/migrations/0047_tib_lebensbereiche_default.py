"""Die 12 Berliner TIB-Lebensbereiche (ICF-Aktivitäten/Teilhabe d1–d9; d8/d9
aufgeteilt). Idempotent per get_or_create; eigene ergänzbar. Quelle: TIB-Manual
(Teilhabeinstrument Berlin, § 118 SGB IX)."""
from django.db import migrations

BEREICHE = [
    ("Lernen und Wissensanwendung", "d1"),
    ("Allgemeine Aufgaben und Anforderungen", "d2"),
    ("Kommunikation", "d3"),
    ("Mobilität", "d4"),
    ("Selbstversorgung", "d5"),
    ("Häusliches Leben", "d6"),
    ("Interpersonelle Interaktionen und Beziehungen", "d7"),
    ("Erziehung und Bildung", "d8"),
    ("Arbeit und Beschäftigung", "d8"),
    ("Wirtschaftliches Leben", "d8"),
    ("Gemeinschaftsleben, Erholung/Freizeit, Religion/Spiritualität", "d9"),
    ("Menschenrechte, Politisches Leben, Staatsbürgerschaft", "d9"),
]


def seed(apps, schema_editor):
    LB = apps.get_model("nachweis", "TibLebensbereich")
    for i, (name, code) in enumerate(BEREICHE, start=1):
        LB.objects.get_or_create(name=name, defaults={"icf_code": code, "reihenfolge": i, "aktiv": True})


def entfernen(apps, schema_editor):
    LB = apps.get_model("nachweis", "TibLebensbereich")
    LB.objects.filter(name__in=[n for n, _ in BEREICHE]).delete()


class Migration(migrations.Migration):
    dependencies = [("nachweis", "0046_tiblebensbereich_bedarfsermittlung_and_more")]
    operations = [migrations.RunPython(seed, entfernen)]

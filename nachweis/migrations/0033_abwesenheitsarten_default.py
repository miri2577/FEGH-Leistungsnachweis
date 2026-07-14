# Abwesenheitsarten mit Vergütungsregeln ALS DATEN (idempotent):
# BRV Jug Tz 22 (Jugendhilfe stationär) + Beschluss 8/2007 Kommission 75 (EGH bes. Wohnform).
# Beträge wie der Beköstigungssatz (EGH-Freihaltegeld) sind trägerindividuell -> abzug_je_tag
# pflegt die Leitung selbst; hier stehen nur die öffentlichen Fristen/Prozente.
from django.db import migrations

ARTEN = [
    # --- Jugendhilfe (BRV Jug Tz 22) ---
    {"name": "Krankenhaus/Kur (Jugendhilfe)", "kuerzel": "KH",
     "verguetung_prozent": 100, "max_tage": 92, "basis": "ereignis",
     "meldefrist_tage": 3,
     "kommentar": "BRV Jug Tz 22: Weiterzahlung max. 3 Monate (Näherung 92 Tage – exakte "
                  "Kalenderfrist im Einzelfall prüfen); Meldung ans JA ab dem 4. Tag"},
    {"name": "Beurlaubung/Ferien (Jugendhilfe)", "kuerzel": "URL",
     "verguetung_prozent": 100, "max_tage": 30, "basis": "jahr",
     "meldefrist_tage": 3,
     "kommentar": "BRV Jug Tz 22: max. 30 Tage je Kalenderjahr"},
    {"name": "Entweichung (Jugendhilfe)", "kuerzel": "ENT",
     "verguetung_prozent": 100, "max_tage": 14, "basis": "ereignis",
     "meldefrist_tage": 3,
     "kommentar": "BRV Jug Tz 22: Weiterzahlung max. 14 Tage je Ereignis"},
    {"name": "Inobhutnahme (Jugendhilfe)", "kuerzel": "ION",
     "verguetung_prozent": 100, "max_tage": 2, "basis": "ereignis",
     "meldefrist_tage": None,
     "kommentar": "BRV Jug Tz 22: Weiterzahlung max. 2 Tage"},
    # --- EGH besondere Wohnform (Beschluss 8/2007, Kommission 75) ---
    {"name": "Urlaub/Krankenhaus/Kur (EGH Wohnform)", "kuerzel": "FRH",
     "verguetung_prozent": 100, "max_tage": 91, "basis": "jahr",
     "meldefrist_tage": None,
     "kommentar": "Beschluss 8/2007: Freihaltegeld = volle Vergütung MINUS Beköstigungssatz "
                  "(abzug_je_tag trägerindividuell eintragen!); Jahreskontingent 91 Tage"},
    {"name": "Kurzbesuch ≤ 3 Tage (EGH Wohnform)", "kuerzel": "KB",
     "verguetung_prozent": 100, "max_tage": 3, "basis": "ereignis",
     "meldefrist_tage": None,
     "kommentar": "Beschluss 8/2007: volle Vergütung NUR bis 3 Tage (darüber = Freihaltegeld-"
                  "Fall FRH erfassen!), keine Anrechnung aufs Jahreskontingent"},
    {"name": "Betreuung am anderen Ort (EGH)", "kuerzel": "BAO",
     "verguetung_prozent": 100, "max_tage": None, "basis": "ereignis",
     "meldefrist_tage": 0,
     "kommentar": "Beschluss 8/2007: volle Vergütung, vorherige/unverzügliche Info + Bericht PFLICHT"},
]


def vorwaerts(apps, schema_editor):
    Art = apps.get_model("nachweis", "AbwesenheitsartKlient")
    for a in ARTEN:
        Art.objects.get_or_create(name=a["name"], defaults=a)


def rueckwaerts(apps, schema_editor):
    Art = apps.get_model("nachweis", "AbwesenheitsartKlient")
    Art.objects.filter(name__in=[a["name"] for a in ARTEN],
                       abwesenheiten__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [("nachweis", "0032_abwesenheitsartklient_angebot_belegung_and_more")]
    operations = [migrations.RunPython(vorwaerts, rueckwaerts)]

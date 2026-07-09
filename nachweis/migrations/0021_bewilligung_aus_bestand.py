"""Daten-Migration: die bisher impliziten Bewilligungs-Felder am Klienten
(al/kle/hbg/kue_bis/kostentraeger-Freitext) in echte Kostentraeger- + Bewilligung-
Objekte überführen. Rückwärts löscht sie die erzeugten Bewilligungen wieder."""
from decimal import Decimal, ROUND_HALF_UP
from datetime import date

from django.db import migrations

Q4 = Decimal("0.0001")
WOCHEN_JE_MONAT = Decimal("365.25") / Decimal(7) / Decimal(12)   # 4,3482…
TAGE_JE_MONAT = Decimal("365.25") / Decimal(12)                  # 30,4375


def vorwaerts(apps, schema_editor):
    Klient = apps.get_model("nachweis", "Klient")
    Kostentraeger = apps.get_model("nachweis", "Kostentraeger")
    Bewilligung = apps.get_model("nachweis", "Bewilligung")

    # 1) Kostenträger aus den distinkten Freitext-Werten anlegen (dedupliziert).
    kt_cache = {}
    for name in (Klient.objects.exclude(kostentraeger="")
                 .values_list("kostentraeger", flat=True).distinct()):
        clean = (name or "").strip()
        if clean and clean not in kt_cache:
            kt_cache[clean] = Kostentraeger.objects.create(name=clean)

    # 2) Je Klient mit Bewilligungsdaten eine Bewilligung erzeugen.
    heute = date.today()
    for k in Klient.objects.all():
        al = k.al or Decimal("0")
        kle = k.kle or Decimal("0")
        if al == 0 and kle == 0 and not k.kue_bis:
            continue   # keine Bewilligungsdaten -> nichts zu migrieren
        fls_woche = (al / WOCHEN_JE_MONAT).quantize(Q4, ROUND_HALF_UP) if al else Decimal("0")
        kle_tag = (kle / TAGE_JE_MONAT).quantize(Decimal("0.000001"), ROUND_HALF_UP) if kle else Decimal("0")
        abgelaufen = bool(k.kue_bis and k.kue_bis < heute)
        Bewilligung.objects.create(
            klient=k,
            kostentraeger=kt_cache.get((k.kostentraeger or "").strip()),
            aktenzeichen=k.person_id or "",
            leistungstyp="FLS",
            gueltig_von=None,               # Startdatum aus dem Bestand nicht bekannt
            gueltig_bis=k.kue_bis,
            fls_woche=fls_woche,
            kle_tag=kle_tag,
            hbg=k.hbg,
            status="abgelaufen" if abgelaufen else "aktiv",
            kommentar="aus Bestand migriert",
        )


def rueckwaerts(apps, schema_editor):
    Bewilligung = apps.get_model("nachweis", "Bewilligung")
    Kostentraeger = apps.get_model("nachweis", "Kostentraeger")
    Bewilligung.objects.filter(kommentar="aus Bestand migriert").delete()
    Kostentraeger.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [("nachweis", "0020_kostentraeger_bewilligung")]
    operations = [migrations.RunPython(vorwaerts, rueckwaerts)]

# Standard-Leistungskatalog (idempotent) + öffentliche landeseinheitliche Sätze.
# EGH-Sätze sind trägerindividuell verhandelt -> die pflegt die Leitung selbst
# (Parameter-Tab/Katalog-Seite); hier stehen nur ÖFFENTLICHE Werte aus Beschlüssen.
from decimal import Decimal

from django.db import migrations

KATALOG = [
    {"name": "FLS Eingliederungshilfe Berlin (BEW/TBEW)",
     "rechtsgrundlage": "SGB IX §§ 113 ff. · örV Berlin",
     "einheit": "fls_stunde",
     "beschreibung": "dokumentierte Fachleistungsstunden, Satz trägerindividuell (Senats-Umrechnung)"},
    {"name": "kLE Eingliederungshilfe Berlin",
     "rechtsgrundlage": "SGB IX §§ 113 ff. · örV Berlin (Beschluss 3/2026)",
     "einheit": "kle_tag",
     "beschreibung": "kalkulatorische Leistungseinheit je Klient*in und Kalendertag, pauschal"},
    {"name": "FLS ambulante Jugendhilfe Berlin (§§ 29–31, 35)",
     "rechtsgrundlage": "SGB VIII § 77 · BRV Jug Anlage D.1",
     "einheit": "fls_stunde",
     "beschreibung": "landeseinheitlicher Satz, alle indirekten Zeiten/Wegezeiten pauschal enthalten"},
    {"name": "Tagessatz Jugendhilfe (teil-)stationär",
     "rechtsgrundlage": "SGB VIII §§ 78a ff. · BRV Jug",
     "einheit": "tagessatz",
     "beschreibung": "je Belegungstag; drei Entgeltbestandteile (Leistung/Nebenkosten §39/Invest)"},
    {"name": "Tagessatz besondere Wohnform EGH (Übergang bis 2026)",
     "rechtsgrundlage": "SGB IX · § 39 BRV EGH (GP+MP+IB)",
     "einheit": "tagessatz",
     "beschreibung": "Übergangsrecht; ab 2027 gilt FLS+kLE auch für besondere Wohnformen (örV)"},
]

# Öffentliche landeseinheitliche Sätze (VK-Jugend-Beschluss 02/2025, ab 01.01.2026)
SAETZE_JUGEND = [
    {"variante": "mit Leitungsanteil", "betrag": Decimal("86.44")},
    {"variante": "ohne Leitungsanteil", "betrag": Decimal("79.29")},
]


def vorwaerts(apps, schema_editor):
    Leistungskatalog = apps.get_model("nachweis", "Leistungskatalog")
    Entgeltsatz = apps.get_model("nachweis", "Entgeltsatz")
    for k in KATALOG:
        Leistungskatalog.objects.get_or_create(name=k["name"], defaults=k)
    jug = Leistungskatalog.objects.get(name__startswith="FLS ambulante Jugendhilfe")
    from datetime import date
    for s in SAETZE_JUGEND:
        Entgeltsatz.objects.get_or_create(
            katalog=jug, kostentraeger=None, variante=s["variante"],
            gueltig_von=date(2026, 1, 1),
            defaults={"betrag": s["betrag"],
                      "kommentar": "VK Jugend Beschluss 02/2025 (Fortschreibung 2026)"})


def rueckwaerts(apps, schema_editor):
    Leistungskatalog = apps.get_model("nachweis", "Leistungskatalog")
    Leistungskatalog.objects.filter(
        name__in=[k["name"] for k in KATALOG], bewilligungen__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [("nachweis", "0030_leistungskatalog_historicalentgeltsatz_and_more")]
    operations = [migrations.RunPython(vorwaerts, rueckwaerts)]

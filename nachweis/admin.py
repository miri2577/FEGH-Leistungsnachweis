from django.contrib import admin

from .models import Mitarbeiter, Klient, Leistung, Gruppe, Parameter


@admin.register(Mitarbeiter)
class MitarbeiterAdmin(admin.ModelAdmin):
    list_display = ("name", "vorname", "kuerzel", "rolle", "aktiv")
    list_filter = ("rolle", "aktiv")
    search_fields = ("name", "vorname", "kuerzel")


@admin.register(Klient)
class KlientAdmin(admin.ModelAdmin):
    list_display = ("nachname", "vorname", "bezugsbetreuer", "al", "kle",
                    "fls_gesamt_display", "hbg", "status")
    list_filter = ("status", "bezugsbetreuer", "hbg")
    search_fields = ("nachname", "vorname", "person_id")
    autocomplete_fields = ("bezugsbetreuer", "vertretung1", "vertretung2")
    fieldsets = (
        ("Person", {"fields": ("nachname", "vorname", "geburtsdatum", "person_id")}),
        ("Betreuung", {"fields": ("bezugsbetreuer", "vertretung1", "vertretung2", "status")}),
        ("Fachleistungsstunden (pro Monat)", {"fields": ("al", "kle", "hbg")}),
        ("Verwaltung", {"fields": ("kue_bis", "brp_bis", "versendet_am", "thfd", "kommentar")}),
    )

    @admin.display(description="FLS gesamt/Monat")
    def fls_gesamt_display(self, obj):
        return obj.fls_gesamt


@admin.register(Leistung)
class LeistungAdmin(admin.ModelAdmin):
    list_display = ("datum", "klient", "leistungsart", "taetigkeit", "betreuer",
                    "beginn", "ende", "dauer_display", "auto")
    list_filter = ("leistungsart", "betreuer", "auto", "datum")
    search_fields = ("klient__nachname", "klient__vorname", "taetigkeit", "notiz")
    autocomplete_fields = ("klient", "betreuer")
    date_hierarchy = "datum"

    @admin.display(description="Dauer (Std)")
    def dauer_display(self, obj):
        return obj.dauer_stunden


@admin.register(Gruppe)
class GruppeAdmin(admin.ModelAdmin):
    list_display = ("datum", "thema", "leistungsart", "beginn", "ende",
                    "anz_ma", "anzahl_teilnehmer", "zeit_pro_klient_display")
    list_filter = ("leistungsart", "datum")
    search_fields = ("thema",)
    filter_horizontal = ("teilnehmer",)

    @admin.display(description="Zeit/Klient (Std)")
    def zeit_pro_klient_display(self, obj):
        return obj.zeit_pro_klient


@admin.register(Parameter)
class ParameterAdmin(admin.ModelAdmin):
    list_display = ("jahr", "teamsitzung_wochentag", "teamsitzung_dauer_std", "fls_preis")


admin.site.site_header = "FEGH-Leistungsnachweis · Team TBEW"
admin.site.site_title = "FEGH-Leistungsnachweis"
admin.site.index_title = "Verwaltung"

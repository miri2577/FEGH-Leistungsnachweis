from django.contrib import admin

from .models import (Mitarbeiter, Klient, Leistung, Gruppe, Parameter,
                     Arbeitszeit, Abwesenheit, Team, Stempelung)


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("name", "typ", "aktiv", "anzahl_mitglieder", "anzahl_klienten")
    list_filter = ("typ", "aktiv")
    search_fields = ("name",)

    @admin.display(description="Mitglieder")
    def anzahl_mitglieder(self, obj):
        return obj.mitglieder.count()

    @admin.display(description="Klient*innen")
    def anzahl_klienten(self, obj):
        return obj.klienten.count()


@admin.register(Mitarbeiter)
class MitarbeiterAdmin(admin.ModelAdmin):
    list_display = ("name", "vorname", "kuerzel", "rolle", "team",
                    "wochenstunden", "urlaubstage", "aktiv")
    list_editable = ("rolle", "team", "wochenstunden", "urlaubstage")
    list_filter = ("rolle", "team", "aktiv")
    search_fields = ("name", "vorname", "kuerzel")
    autocomplete_fields = ("user",)
    filter_horizontal = ("leitet",)

    def has_add_permission(self, request):
        # Anlegen ausschließlich über die App-Seite "Mitarbeiter-Verwaltung"
        # (mit Aktivierungslink) – keine Dopplung im Django-Admin.
        return False
    fieldsets = (
        ("Person", {"fields": ("user", "name", "vorname", "kuerzel", "aktiv")}),
        ("Rolle & Team", {"fields": ("rolle", "team", "leitet")}),
        ("Arbeitszeit & Urlaub (Selfservice)", {"fields": ("wochenstunden", "urlaubstage")}),
    )


@admin.register(Klient)
class KlientAdmin(admin.ModelAdmin):
    list_display = ("nachname", "vorname", "team", "bezugsbetreuer", "al", "kle",
                    "fls_gesamt_display", "hbg", "kue_bis", "status")
    list_filter = ("status", "team", "bezugsbetreuer", "hbg")
    search_fields = ("nachname", "vorname", "person_id")
    autocomplete_fields = ("bezugsbetreuer", "vertretung1", "vertretung2")
    fieldsets = (
        ("Person", {"fields": ("nachname", "vorname", "geburtsdatum", "person_id")}),
        ("Team & Betreuung", {"fields": ("team", "bezugsbetreuer", "vertretung1", "vertretung2", "status")}),
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


@admin.register(Arbeitszeit)
class ArbeitszeitAdmin(admin.ModelAdmin):
    list_display = ("mitarbeiter", "datum", "beginn", "ende", "pause_min", "dauer_display", "status")
    list_filter = ("status", "mitarbeiter", "datum")
    list_editable = ("status",)
    date_hierarchy = "datum"
    autocomplete_fields = ("mitarbeiter",)

    @admin.display(description="Dauer (Std)")
    def dauer_display(self, obj):
        return obj.dauer_stunden


@admin.register(Abwesenheit)
class AbwesenheitAdmin(admin.ModelAdmin):
    list_display = ("mitarbeiter", "art", "von", "bis", "werktage_display", "status")
    list_filter = ("art", "status", "mitarbeiter")
    list_editable = ("status",)
    date_hierarchy = "von"
    autocomplete_fields = ("mitarbeiter",)

    @admin.display(description="Werktage")
    def werktage_display(self, obj):
        return obj.werktage


@admin.register(Stempelung)
class StempelungAdmin(admin.ModelAdmin):
    list_display = ("mitarbeiter", "beginn", "ende", "offen")
    list_filter = ("mitarbeiter",)
    date_hierarchy = "beginn"
    autocomplete_fields = ("mitarbeiter",)


admin.site.site_header = "FEGH-Leistungsnachweis · Team TBEW"
admin.site.site_title = "FEGH-Leistungsnachweis"
admin.site.index_title = "Verwaltung"

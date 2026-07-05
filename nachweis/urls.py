from django.contrib.auth import views as auth_views
from django.urls import path

from . import views, views_2fa, views_onboarding, views_stammdaten, views_kasse

app_name = "nachweis"

urlpatterns = [
    path("", views.mein_ueberblick, name="start"),
    path("fachleistungsstunden/", views.dashboard, name="dashboard"),
    path("erfassung/", views.erfassung, name="erfassung"),
    path("druck/", views.druck, name="druck"),
    path("druck/pdf/", views.druck_pdf, name="druck_pdf"),
    path("gruppen/", views.gruppen, name="gruppen"),
    path("gruppen/save/", views.gruppe_save, name="gruppe_save"),
    path("gruppen/delete/", views.gruppe_delete, name="gruppe_delete"),

    # Wochenkalender (Team-Termine, Mo–So)
    path("kalender/", views.kalender, name="kalender"),
    path("kalender/save/", views.termin_save, name="termin_save"),
    path("kalender/delete/", views.termin_delete, name="termin_delete"),
    path("kalender/move/", views.termin_move, name="termin_move"),
    path("kalender/druck/", views.kalender_druck, name="kalender_druck"),

    # Druck-Center (Sammelseite unten in der Sidebar) + weitere Druck-Nachweise
    path("nachweise/", views.druck_center, name="druck_center"),
    path("arbeitszeit/druck/", views.arbeitszeit_druck, name="arbeitszeit_druck"),
    path("gruppen/<int:pk>/druck/", views.gruppe_druck, name="gruppe_druck"),
    path("kasse/druck/", views_kasse.kasse_druck, name="kasse_druck"),
    path("doku/druck/", views.doku_druck, name="doku_druck"),

    # Arbeitszeit (Selfservice)
    path("versendet/", views.versendet_setzen, name="versendet_setzen"),
    path("stempeln/", views.stempeln, name="stempeln"),
    path("arbeitszeit/", views.arbeitszeit, name="arbeitszeit"),
    path("api/arbeitszeit/", views.api_arbeitszeit, name="api_arbeitszeit"),
    path("api/arbeitszeit/save/", views.api_arbeitszeit_save, name="api_arbeitszeit_save"),
    path("api/arbeitszeit/delete/", views.api_arbeitszeit_delete, name="api_arbeitszeit_delete"),

    # Arbeitszeit-Freigaben (Leitung)
    path("arbeitszeit/freigaben/", views.arbeitszeit_freigaben, name="arbeitszeit_freigaben"),
    path("arbeitszeit/status/", views.arbeitszeit_status, name="arbeitszeit_status"),

    # Kasse (Kassenbuch + Zählprotokoll)
    path("kasse/", views_kasse.kasse, name="kasse"),
    path("kasse/buchung/", views_kasse.buchung_save, name="kasse_buchung_save"),
    path("kasse/buchung/delete/", views_kasse.buchung_delete, name="kasse_buchung_delete"),
    path("kasse/vortrag/", views_kasse.vortrag_save, name="kasse_vortrag_save"),
    path("kasse/anlegen/", views_kasse.kasse_anlegen, name="kasse_anlegen"),
    path("kasse/zaehlprotokoll/", views_kasse.zaehlprotokoll, name="zaehlprotokoll"),

    # Abwesenheiten (Urlaub / Freizeitausgleich)
    path("abwesenheit/", views.abwesenheit, name="abwesenheit"),
    path("abwesenheit/save/", views.abwesenheit_save, name="abwesenheit_save"),
    path("abwesenheit/status/", views.abwesenheit_status, name="abwesenheit_status"),

    # API (Erfassungs-Grid)
    path("api/leistungen/", views.api_leistungen, name="api_leistungen"),
    path("api/leistungen/save/", views.api_leistung_save, name="api_leistung_save"),
    path("api/leistungen/delete/", views.api_leistung_delete, name="api_leistung_delete"),
    path("api/wochen-fls/", views.api_wochen_fls, name="api_wochen_fls"),
    path("api/suche/", views.api_suche, name="api_suche"),
    path("api/ping/", views.api_ping, name="api_ping"),

    # Wiederherstellungs-Timeline (nur Superuser)
    path("timeline/", views.timeline, name="timeline"),
    path("timeline/restore/", views.timeline_restore, name="timeline_restore"),

    # Auth
    path("login/", auth_views.LoginView.as_view(
        template_name="nachweis/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(next_page="nachweis:login"), name="logout"),

    # Stammdaten (Leitung)
    path("belegungsliste/", views_stammdaten.belegungsliste, name="belegungsliste"),
    path("belegungsliste/neu/", views_stammdaten.klient_form, name="klient_neu"),
    path("belegungsliste/<int:pk>/", views_stammdaten.klient_form, name="klient_bearbeiten"),
    path("belegungsliste/speichern/", views_stammdaten.klient_speichern, name="klient_speichern"),
    path("parameter/", views_stammdaten.parameter, name="parameter"),
    path("parameter/serie/speichern/", views_stammdaten.serie_save, name="serie_save"),
    path("parameter/serie/loeschen/", views_stammdaten.serie_delete, name="serie_delete"),

    # Teams (Admin)
    path("teams/", views_onboarding.teams_liste, name="teams_liste"),
    path("teams/speichern/", views_onboarding.team_speichern, name="team_speichern"),
    path("teams/aktion/", views_onboarding.team_aktion, name="team_aktion"),
    # Onboarding / Mitarbeiter-Verwaltung (Admin)
    path("mitarbeiter/", views_onboarding.mitarbeiter_liste, name="mitarbeiter_liste"),
    path("mitarbeiter/neu/", views_onboarding.mitarbeiter_neu, name="mitarbeiter_neu"),
    path("mitarbeiter/aktion/", views_onboarding.mitarbeiter_aktion, name="mitarbeiter_aktion"),
    # Konto-Aktivierung (öffentlich, per signiertem Link)
    path("aktivieren/<uidb64>/<token>/", views_onboarding.aktivieren, name="aktivieren"),

    # Zwei-Faktor (TOTP)
    path("2fa/setup/", views_2fa.zwei_faktor_setup, name="2fa_setup"),
    path("2fa/verify/", views_2fa.zwei_faktor_verify, name="2fa_verify"),
    path("2fa/status/", views_2fa.zwei_faktor_status, name="2fa_status"),
    path("2fa/deaktivieren/", views_2fa.zwei_faktor_deaktivieren, name="2fa_deaktivieren"),
]

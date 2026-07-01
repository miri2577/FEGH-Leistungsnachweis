from django.contrib.auth import views as auth_views
from django.urls import path

from . import views, views_2fa, views_onboarding, views_stammdaten

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

    # Arbeitszeit (Selfservice)
    path("stempeln/", views.stempeln, name="stempeln"),
    path("arbeitszeit/", views.arbeitszeit, name="arbeitszeit"),
    path("api/arbeitszeit/", views.api_arbeitszeit, name="api_arbeitszeit"),
    path("api/arbeitszeit/save/", views.api_arbeitszeit_save, name="api_arbeitszeit_save"),
    path("api/arbeitszeit/delete/", views.api_arbeitszeit_delete, name="api_arbeitszeit_delete"),

    # Abwesenheiten (Urlaub / Freizeitausgleich)
    path("abwesenheit/", views.abwesenheit, name="abwesenheit"),
    path("abwesenheit/save/", views.abwesenheit_save, name="abwesenheit_save"),
    path("abwesenheit/status/", views.abwesenheit_status, name="abwesenheit_status"),

    # API (Erfassungs-Grid)
    path("api/leistungen/", views.api_leistungen, name="api_leistungen"),
    path("api/leistungen/save/", views.api_leistung_save, name="api_leistung_save"),
    path("api/leistungen/delete/", views.api_leistung_delete, name="api_leistung_delete"),

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

from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "nachweis"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("erfassung/", views.erfassung, name="erfassung"),
    path("druck/", views.druck, name="druck"),
    path("druck/pdf/", views.druck_pdf, name="druck_pdf"),

    # API (Erfassungs-Grid)
    path("api/leistungen/", views.api_leistungen, name="api_leistungen"),
    path("api/leistungen/save/", views.api_leistung_save, name="api_leistung_save"),
    path("api/leistungen/delete/", views.api_leistung_delete, name="api_leistung_delete"),

    # Auth
    path("login/", auth_views.LoginView.as_view(
        template_name="nachweis/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(next_page="nachweis:login"), name="logout"),
]

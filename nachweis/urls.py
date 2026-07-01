from django.urls import path

from . import views

app_name = "nachweis"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
]

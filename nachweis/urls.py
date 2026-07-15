from django.contrib.auth import views as auth_views
from django.urls import path

from . import (views, views_2fa, views_onboarding, views_stammdaten, views_kasse,
               views_abrechnung, views_feld, views_ziele, views_berichte,
               views_controlling, views_belegung, views_qm, views_dienstplan,
               views_dokumente, views_loeschfristen, views_fallakte, views_wohnkosten,
               views_bedarf, views_kontakte, views_qualifikation)

app_name = "nachweis"

urlpatterns = [
    path("", views.mein_ueberblick, name="start"),
    path("fachleistungsstunden/", views.dashboard, name="dashboard"),
    path("controlling/", views_controlling.controlling, name="controlling"),
    path("controlling/csv/", views_controlling.controlling_csv, name="controlling_csv"),
    path("erfassung/", views.erfassung, name="erfassung"),
    path("druck/", views.druck, name="druck"),
    path("druck/pdf/", views.druck_pdf, name="druck_pdf"),
    path("gruppen/", views.gruppen, name="gruppen"),
    path("fristen/", views.fristen, name="fristen"),
    path("gruppen/save/", views.gruppe_save, name="gruppe_save"),
    path("gruppen/delete/", views.gruppe_delete, name="gruppe_delete"),

    # Klient-Fallakte (zentrale Detailseite mit Reitern)
    path("klient/<int:pk>/", views_fallakte.klient_detail, name="klient_detail"),
    path("klient/<int:pk>/verlauf/", views_fallakte.klient_verlauf, name="klient_verlauf"),

    # Ziele (ZLP, Phase 2)
    path("ziele/<int:pk>/", views_ziele.ziele, name="ziele"),
    path("ziele/speichern/", views_ziele.ziel_speichern, name="ziel_speichern"),
    path("ziele/status/", views_ziele.ziel_status, name="ziel_status"),
    path("ziele/loeschen/", views_ziele.ziel_loeschen, name="ziel_loeschen"),
    path("api/ziele/", views_ziele.api_ziele, name="api_ziele"),

    # ICF-Bedarfsermittlung (Teilhabeinstrument Berlin, TIB)
    path("bedarf/<int:pk>/", views_bedarf.bedarf, name="bedarf"),
    path("bedarf/neu/", views_bedarf.bedarf_neu, name="bedarf_neu"),
    path("bedarf/speichern/", views_bedarf.bedarf_speichern, name="bedarf_speichern"),
    path("bedarf/loeschen/", views_bedarf.bedarf_loeschen, name="bedarf_loeschen"),

    # Wirkungsmessung (Berliner Wirkungsdimensionen, Ist/Soll 7er-Skala)
    path("wirkung/<int:pk>/", views_ziele.wirkung, name="wirkung"),
    path("wirkung/speichern/", views_ziele.wirkung_speichern, name="wirkung_speichern"),
    path("wirkung/loeschen/", views_ziele.wirkung_loeschen, name="wirkung_loeschen"),

    # Löschkonzept / Aufbewahrungsfristen (DSGVO)
    path("loeschfristen/", views_loeschfristen.loeschfristen, name="loeschfristen"),
    path("loeschfristen/<int:pk>/", views_loeschfristen.loeschfristen_klient, name="loeschfristen_klient"),
    path("loeschfristen/anonymisieren/", views_loeschfristen.loeschfristen_anonymisieren, name="loeschfristen_anonymisieren"),

    # Selbstzahler / Wohnkosten (WBVG)
    path("wohnkosten/", views_wohnkosten.wohnkosten, name="wohnkosten"),
    path("wohnkosten/vereinbarung/anlegen/", views_wohnkosten.vereinbarung_anlegen, name="wohnkosten_vereinbarung_anlegen"),
    path("wohnkosten/vereinbarung/<int:pk>/", views_wohnkosten.wohnkosten_vereinbarung, name="wohnkosten_vereinbarung"),
    path("wohnkosten/vereinbarung/speichern/", views_wohnkosten.vereinbarung_speichern, name="wohnkosten_vereinbarung_speichern"),
    path("wohnkosten/position/speichern/", views_wohnkosten.position_speichern, name="wohnkosten_position_speichern"),
    path("wohnkosten/position/loeschen/", views_wohnkosten.position_loeschen, name="wohnkosten_position_loeschen"),
    path("wohnkosten/erzeugen/", views_wohnkosten.wohnkosten_erzeugen, name="wohnkosten_erzeugen"),
    path("wohnkosten/rechnung/<int:pk>/", views_wohnkosten.selbstzahler_rechnung, name="selbstzahler_rechnung"),
    path("wohnkosten/rechnung/<int:pk>/pdf/", views_wohnkosten.selbstzahler_pdf, name="selbstzahler_pdf"),
    path("wohnkosten/rechnung/aktion/", views_wohnkosten.selbstzahler_aktion, name="selbstzahler_aktion"),

    # Dokumentenablage (DMS light)
    path("dokumente/<int:pk>/", views_dokumente.dokumente, name="dokumente"),
    path("dokumente/hochladen/", views_dokumente.dokument_hochladen, name="dokument_hochladen"),
    path("dokument/<int:pk>/download/", views_dokumente.dokument_download, name="dokument_download"),
    path("dokument/<int:pk>/inline/", views_dokumente.dokument_inline, name="dokument_inline"),
    path("dokument/<int:pk>/ansehen/", views_dokumente.dokument_ansicht, name="dokument_ansicht"),
    path("dokumente/loeschen/", views_dokumente.dokument_loeschen, name="dokument_loeschen"),
    path("kontakte/<int:pk>/", views_kontakte.kontakte, name="kontakte"),
    path("kontakte/<int:pk>/speichern/", views_kontakte.kontakt_speichern, name="kontakt_speichern"),
    path("kontakte/<int:pk>/loeschen/", views_kontakte.kontakt_loeschen, name="kontakt_loeschen"),
    path("qualifikationen/", views_qualifikation.qualifikationen, name="qualifikationen"),
    path("qualifikationen/speichern/", views_qualifikation.qualifikation_speichern, name="qualifikation_speichern"),
    path("qualifikationen/loeschen/", views_qualifikation.qualifikation_loeschen, name="qualifikation_loeschen"),

    # Berichte (Phase 2)
    path("berichte/<int:pk>/", views_berichte.berichte, name="berichte"),
    path("berichte/speichern/", views_berichte.bericht_speichern, name="bericht_speichern"),
    path("berichte/status/", views_berichte.bericht_status, name="bericht_status"),
    path("berichte/loeschen/", views_berichte.bericht_loeschen, name="bericht_loeschen"),
    path("bericht/<int:pk>/druck/", views_berichte.bericht_druck, name="bericht_druck"),
    path("bericht/<int:pk>/rohpaket/", views_berichte.bericht_rohpaket, name="bericht_rohpaket"),

    # Unterwegs-Modus (mobile Vor-Ort-Doku)
    path("unterwegs/", views_feld.feld_heute, name="feld_heute"),
    path("unterwegs/speichern/", views_feld.feld_speichern, name="feld_speichern"),

    # Wochenkalender (Team-Termine, Mo–So)
    path("kalender/", views.kalender, name="kalender"),
    path("kalender/save/", views.termin_save, name="termin_save"),
    path("kalender/delete/", views.termin_delete, name="termin_delete"),
    path("kalender/move/", views.termin_move, name="termin_move"),
    path("kalender/zeit/", views.termin_zeit, name="termin_zeit"),
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

    # Abrechnung (Freigabe-Workflow MA→Leitung→Verwaltung + Rechnungen)
    path("abrechnung/", views_abrechnung.abrechnung, name="abrechnung"),
    path("abrechnung/aktion/", views_abrechnung.freigabe_aktion, name="freigabe_aktion"),
    path("rechnungen/", views_abrechnung.rechnungen, name="rechnungen"),
    path("rechnungen/neu/", views_abrechnung.rechnung_neu, name="rechnung_neu"),
    path("rechnungslauf/", views_abrechnung.rechnungslauf_ausfuehren, name="rechnungslauf_ausfuehren"),
    path("rechnungen/<int:pk>/", views_abrechnung.rechnung_detail, name="rechnung_detail"),
    path("rechnungen/<int:pk>/pdf/", views_abrechnung.rechnung_pdf, name="rechnung_pdf"),
    path("rechnungen/<int:pk>/mail/", views_abrechnung.rechnung_mail, name="rechnung_mail"),
    path("rechnungen/<int:pk>/csv/", views_abrechnung.rechnung_csv, name="rechnung_csv"),
    path("rechnungen/<int:pk>/eabrechnung/", views_abrechnung.rechnung_eabrechnung,
         name="rechnung_eabrechnung"),
    path("rechnungen/<int:pk>/xrechnung/", views_abrechnung.rechnung_xrechnung,
         name="rechnung_xrechnung"),
    path("rechnungen/<int:pk>/status/", views_abrechnung.rechnung_status, name="rechnung_status"),
    path("rechnungen/<int:pk>/gutschrift/", views_abrechnung.rechnung_gutschrift, name="rechnung_gutschrift"),
    path("rechnungssteller/", views_abrechnung.rechnungssteller, name="rechnungssteller"),
    path("offene-posten/", views_abrechnung.offene_posten, name="offene_posten"),
    path("zahlungsabgleich/", views_abrechnung.zahlungsabgleich, name="zahlungsabgleich"),
    path("datev/", views_abrechnung.datev_export, name="datev_export"),

    # QM: Vorkommnis-Meldewesen (§ 37a SGB IX / WTG / § 8a SGB VIII)
    path("vorkommnisse/", views_qm.vorkommnisse, name="vorkommnisse"),
    path("vorkommnisse/speichern/", views_qm.vorkommnis_speichern, name="vorkommnis_speichern"),
    path("vorkommnisse/status/", views_qm.vorkommnis_status, name="vorkommnis_status"),

    # Dienstplanung (P5)
    path("dienstplan/", views_dienstplan.dienstplan, name="dienstplan"),
    path("dienstplan/setzen/", views_dienstplan.dienst_setzen, name="dienst_setzen"),
    path("schichtarten/", views_dienstplan.schichtarten, name="schichtarten"),
    path("rechnungen/<int:pk>/zahlung/", views_abrechnung.zahlung_erfassen, name="zahlung_erfassen"),
    path("zahlung/loeschen/", views_abrechnung.zahlung_loeschen, name="zahlung_loeschen"),
    path("rechnungen/<int:pk>/mahnung/", views_abrechnung.mahnung_erstellen, name="mahnung_erstellen"),
    path("mahnung/<int:pk>/druck/", views_abrechnung.mahnung_druck, name="mahnung_druck"),
    path("mahnung/<int:pk>/mail/", views_abrechnung.mahnung_mail, name="mahnung_mail"),

    # Kasse (Kassenbuch + Zählprotokoll)
    path("kasse/", views_kasse.kasse, name="kasse"),
    path("kasse/buchung/", views_kasse.buchung_save, name="kasse_buchung_save"),
    path("kasse/buchung/delete/", views_kasse.buchung_delete, name="kasse_buchung_delete"),
    path("kasse/vortrag/", views_kasse.vortrag_save, name="kasse_vortrag_save"),
    path("kasse/anlegen/", views_kasse.kasse_anlegen, name="kasse_anlegen"),
    path("kasse/zustaendigkeit/", views_kasse.kasse_zustaendigkeit, name="kasse_zustaendigkeit"),
    path("kasse/zaehlprotokoll/", views_kasse.zaehlprotokoll, name="zaehlprotokoll"),

    # Abwesenheiten (Urlaub / Freizeitausgleich)
    path("abwesenheit/", views.abwesenheit, name="abwesenheit"),
    path("abwesenheit/save/", views.abwesenheit_save, name="abwesenheit_save"),
    path("abwesenheit/status/", views.abwesenheit_status, name="abwesenheit_status"),
    path("fehlzeiten/", views.fehlzeiten, name="fehlzeiten"),
    path("dienstabgleich/", views_dienstplan.dienst_abgleich, name="dienst_abgleich"),

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

    # Über diese App / Impressum (öffentlich erreichbar)
    path("ueber/", views.ueber, name="ueber"),

    # Stammdaten (Leitung)
    path("belegungsliste/", views_stammdaten.belegungsliste, name="belegungsliste"),
    path("belegungsliste/neu/", views_stammdaten.klient_form, name="klient_neu"),
    path("belegungsliste/<int:pk>/", views_stammdaten.klient_form, name="klient_bearbeiten"),
    path("belegungsliste/speichern/", views_stammdaten.klient_speichern, name="klient_speichern"),
    path("belegungsliste/<int:pk>/bewilligungen/", views_stammdaten.bewilligungen, name="bewilligungen"),
    path("bewilligung/speichern/", views_stammdaten.bewilligung_speichern, name="bewilligung_speichern"),
    path("bewilligung/loeschen/", views_stammdaten.bewilligung_loeschen, name="bewilligung_loeschen"),
    path("kostentraeger/", views_stammdaten.kostentraeger_liste, name="kostentraeger_liste"),
    path("kostentraeger/speichern/", views_stammdaten.kostentraeger_speichern, name="kostentraeger_speichern"),
    path("kostentraeger/bezirke/", views_stammdaten.kostentraeger_bezirke, name="kostentraeger_bezirke"),
    path("leistungskatalog/", views_stammdaten.leistungskatalog, name="leistungskatalog"),
    path("angebote/", views_belegung.angebote, name="angebote"),
    path("angebote/<int:pk>/belegung/", views_belegung.belegungskalender, name="belegungskalender"),
    path("angebote/<int:pk>/zimmer/", views_belegung.zimmer, name="zimmer"),
    path("zimmer/loeschen/", views_belegung.zimmer_loeschen, name="zimmer_loeschen"),
    path("belegung/speichern/", views_belegung.belegung_speichern, name="belegung_speichern"),
    path("klient-abwesenheit/speichern/", views_belegung.klient_abwesenheit_speichern,
         name="klient_abwesenheit_speichern"),
    path("klient-abwesenheit/aktion/", views_belegung.klient_abwesenheit_aktion,
         name="klient_abwesenheit_aktion"),
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
    path("mitarbeiter/<int:pk>/bearbeiten/", views_onboarding.mitarbeiter_bearbeiten,
         name="mitarbeiter_bearbeiten"),
    path("mitarbeiter/aktion/", views_onboarding.mitarbeiter_aktion, name="mitarbeiter_aktion"),
    # Konto-Aktivierung (öffentlich, per signiertem Link)
    path("aktivieren/<uidb64>/<token>/", views_onboarding.aktivieren, name="aktivieren"),

    # Zwei-Faktor (TOTP)
    path("2fa/setup/", views_2fa.zwei_faktor_setup, name="2fa_setup"),
    path("2fa/verify/", views_2fa.zwei_faktor_verify, name="2fa_verify"),
    path("2fa/status/", views_2fa.zwei_faktor_status, name="2fa_status"),
    path("2fa/deaktivieren/", views_2fa.zwei_faktor_deaktivieren, name="2fa_deaktivieren"),
]

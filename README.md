# FEGH-Leistungsnachweis

Web-App zur Dokumentation von **Leistungsnachweisen** für die **Rechnungsstellung** im
Team **TBEW** (Therapeutisch Betreutes Einzelwohnen) der Berliner Eingliederungshilfe.
Löst die bisherige Excel-Mappe ab und ist von Anfang an **mehrbenutzerfähig**.

Fachliche Grundlage: Berlin ab 01.01.2026 (FLS = FS/WFS/BAO, kalkulatorische
Leistungseinheiten kLE, Beschluss 3/2026). Bewilligte FLS = **AL + kLE pro Monat**.

> **Status: Prototyp mit FIKTIVEN Demodaten.** Keine echten Klientendaten – so entwickeln
> wir ohne Datenschutz-Risiko. Vor dem Einsatz mit echten (Art.-9-DSGVO-)Daten: Hosting in
> DE/EU + Freigabe durch Träger/Datenschutzbeauftragte, Revisionssicherheit, TLS.

## Tech-Stack
- **Django 5.1** (Python) – Auth, Rollen, Admin, ORM, serverseitige Fachlogik
- **SQLite** (Prototyp) → PostgreSQL (Produktion)
- Datengrid (Excel-artig) folgt als nächster Schritt (Tabulator/AG Grid als JS-Insel)
- Design orientiert sich an **Connext Vivendi** (ruhige Blau-/Weißtöne, klare Tabellen, Sidebar)

## Lokal starten
```bash
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py seed            # fiktive Demodaten + Demo-Login admin/admin
python manage.py runserver
```
- Übersicht:  http://127.0.0.1:8000/
- Admin/Erfassung:  http://127.0.0.1:8000/admin/  (Demo-Login `admin` / `admin`)

## Datenmodell (aus der Excel abgeleitet)
- **Mitarbeiter** (Rolle Betreuer/Teamleitung)
- **Klient** (Belegungsliste: AL, kLE, HBG, Bezugsbetreuer, Status, …)
- **Leistung** (Leistungsnachweis: Datum, Klient, Leistungsart {FS,WFS,BAO,FUS,FZ,AL,KLE,FH}, Zeit)
- **Gruppe** (Teilnehmer m:n; Zeit/Klient = Gesamtzeit ÷ Teilnehmer ÷ Anz. MA)
- **Parameter** (Teamsitzung-Dauer, Wochentag, FLS-Preis – pro Jahr)
- Teamsitzung wird berechnet: Donnerstage ohne Berliner Feiertage × Dauer ÷ Anzahl Klienten

## Roadmap
- [x] Datenmodell + Auswertung Fachleistungsstunden + Admin-Erfassung + Demodaten
- [ ] Excel-artiges Erfassungs-Grid (Inline-Edit, Filter nach Betreuer/Klient/Monat)
- [ ] Rollen: Betreuer*in sieht nur eigene Klient*innen
- [ ] Amtlicher Druck-Nachweis je Klient/Monat als PDF (WeasyPrint)
- [ ] Design-Feinschliff nach Connext-Vivendi-Vorbild
- [ ] Produktion: PostgreSQL, Hosting DE/EU, Audit-Trail, Backups

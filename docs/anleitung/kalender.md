# Wochenkalender

Der Wochenkalender zeigt die Termine des Teams auf einen Blick – wer ist wann bei welcher Klient*in, wann sind interne Termine wie Teamsitzung oder Supervision. Er dient der Team-Übersicht und der Wochenplanung; die eigentliche Leistungserfassung passiert weiterhin im Leistungsnachweis.

!!! note "Wer sieht den Kalender?"
    Der Kalender ist an die Klientenarbeit gekoppelt und damit **team-scoped**: Sichtbar sind nur Mitarbeiter*innen und Klient*innen der eigenen (bzw. bei Leitung: geleiteten) Teams. **Admin** und **Verwaltung** haben *keinen* Kalenderzugriff – der Menüpunkt wird ausgeblendet, ein direkter Aufruf leitet zur Startseite zurück.

## Die drei Ansichten

Oben rechts schaltest du über den **Segment-Umschalter** zwischen drei Ansichten um. Die gewählte Ansicht bleibt beim Blättern und beim Filtern erhalten.

| Ansicht | Darstellung | Wofür |
|---------|-------------|-------|
| **Tag** | Eine Karte je Mitarbeiter*in mit den Terminen des Tages | Detailblick auf einen konkreten Tag |
| **Woche** | Team-Matrix: Zeilen = Mitarbeiter*innen, Spalten = Mo–So | Wochenplanung, Standardansicht |
| **Monat** | Klassisches Kalender-Grid (Mo–So), alle Termine je Tag | Grobüberblick, Fristen, Auslastung |

Direkt neben dem Umschalter blätterst du mit **‹** / **›** eine Einheit zurück bzw. vor (ein Tag, eine Woche, ein Monat), **Heute** springt zurück auf den aktuellen Zeitraum. Die aktuelle Ansicht steht als Überschrift, z. B. `KW 27 · 29.06.–05.07.2026` oder `Juli 2026`.

!!! tip "Standardansicht"
    Ohne weitere Auswahl öffnet der Kalender die **Wochenansicht** der laufenden Kalenderwoche.

### Wochenansicht (Team-Matrix)

Die Wochenansicht ist das Herzstück. Jede Zeile ist eine Mitarbeiter*in, jede Spalte ein Wochentag (Mo–So, Wochenende leicht abgesetzt). Der heutige Tag ist in der Kopfzeile farblich hervorgehoben, **deine eigene Zeile** ist links mit einem farbigen Balken und dem Zusatz *(ich)* markiert.

### Tagesansicht (Karten)

Pro Mitarbeiter*in eine Karte mit allen Terminen des gewählten Tages – inkl. Uhrzeit, Klient*in bzw. internem Titel und Ort. Leere Karten zeigen „—".

### Monatsansicht (Grid)

Ein Kalender-Monat als Raster. Tage außerhalb des Monats sind ausgegraut, der heutige Tag ist hinterlegt. Termine erscheinen kompakt mit Anfangszeit und Kürzel; beim Überfahren mit der Maus zeigt der Tooltip Mitarbeiter*in, Uhrzeit und Klartext.

## Vollbild

Der Button **⛶ Vollbild** blendet Seitenleiste und Kopfzeile aus, sodass der Kalender die ganze Fläche nutzt – ideal fürs Aushängen am großen Monitor oder in der Teamsitzung.

!!! tip "Vollbild verlassen"
    Mit der Taste **Esc** (oder erneutem Klick auf den Button) kehrst du zur normalen Ansicht zurück.

## Filter

Über der Kalenderfläche stehen bis zu drei Auswahlfelder. Sie greifen sofort bei Auswahl und bleiben beim Ansichtswechsel und Blättern erhalten.

| Filter | Wirkung |
|--------|---------|
| **Team** | Nur bei mehreren geleiteten Teams sichtbar; grenzt auf ein Team ein („Alle Teams" = Standard) |
| **Mitarbeiter*in** | Zeigt nur die Termine einer Person |
| **Klient*in** | Zeigt nur Termine zu einer bestimmten Klient*in |

!!! note
    Die Filter kombinieren sich (UND-Verknüpfung). Der Klient*innen-Filter reduziert die angezeigten Termine, ohne die Mitarbeiter*innen-Zeilen zu entfernen.

## Farbcodierung, Kürzel und Legende

Jede*r Klient*in bekommt eine **stabile Pastellfarbe** (fest aus der Datensatz-ID abgeleitet) und ein **Kürzel**. Termine werden in dieser Farbe angezeigt und mit dem Kürzel beschriftet – so sind Klient*innen auf einen Blick unterscheidbar, ohne den vollen Namen auszuschreiben.

- Das **Kürzel** stammt aus dem gepflegten Feld *Kürzel* der Belegungsliste. Ist es leer, wird automatisch aus dem Nachnamen ein Kürzel gebildet (erste drei Buchstaben).
- **Interne Termine** ohne Klient*in erscheinen neutral grau und tragen ihren Titel statt eines Kürzels.
- Unter jeder Ansicht steht eine **Legende**: Farbfeld + Kürzel = voller Klient*innen-Name. Sie listet nur die im aktuellen Zeitraum tatsächlich vorkommenden Klient*innen.

## Termine anlegen und bearbeiten

!!! warning "Nur eigene Termine"
    Du kannst **ausschließlich deine eigenen Termine** anlegen, bearbeiten und löschen. Termine von Kolleg*innen siehst du, kannst sie aber nicht verändern – sie sind nicht anklickbar. Das serverseitig erzwungene Prinzip: Jeder Termin gehört genau einer Mitarbeiter*in.

### Neuen Termin anlegen

- **Wochenansicht:** In einer leeren Zelle deiner eigenen Zeile erscheint beim Überfahren ein **＋** – Klick öffnet das Formular mit vorbelegtem Datum.
- **Tagesansicht:** Der Button **＋ Termin** unten auf deiner Karte legt einen Termin für den angezeigten Tag an.

Das Formular öffnet sich unterhalb des Kalenders (Sprungmarke `#form`).

### Eigenen Termin bearbeiten oder löschen

Klicke einen deiner eigenen Termine an – das Formular öffnet sich vorausgefüllt im Bearbeiten-Modus. Über **Speichern** änderst du ihn, über **Termin löschen** (mit Sicherheitsabfrage) entfernst du ihn. **Abbrechen** verwirft die Bearbeitung.

### Felder eines Termins

Ein Termin ist entweder einer **Klient*in** zugeordnet **oder** trägt einen **internen Titel** – eines von beidem ist Pflicht.

| Feld | Pflicht | Hinweis |
|------|---------|---------|
| **Datum** | ja | bei ＋-Klick vorbelegt |
| **Beginn** | ja | Uhrzeit |
| **Ende** | nein | Uhrzeit |
| **Klient*in** | eins von beiden | Auswahl aus der eigenen Belegungsliste; „— (interner Termin)" lässt es frei |
| **Titel** | eins von beiden | für interne Termine, z. B. *Teamsitzung*, *Supervision* |
| **Ort** | nein | |
| **Notiz** | nein | Kurztext |

!!! danger "Datensparsamkeit (DSGVO Art. 9)"
    Der Kalender arbeitet bewusst mit **Kürzeln statt Klarnamen** in der Fläche. Trage in Notiz/Titel keine sensiblen Gesundheits- oder Sozialdaten ein, die über die reine Terminplanung hinausgehen.

## Wochenplan drucken

Der Kalender selbst hat keinen eigenen Druckknopf. Der **Team-Wochenplan** wird zentral über die Sammelseite **Druck-Nachweise → Karte „Wochenplan"** gedruckt.

- Format: **A4 quer**.
- Aus Gründen der Datensparsamkeit erscheinen im Ausdruck **nur die Kürzel** der Klient*innen – keine Klarnamen.
- Die im Kalender gesetzten Filter (Team/Zeitraum) gelten sinngemäß auch für den Druck.

!!! note "Warum getrennt?"
    Die Druckseite ist ein eigenes, für Papier optimiertes Layout. So bleibt der interaktive Kalender schlank und der Ausdruck bewusst reduziert.

## Für Neugierige: Technik dahinter

!!! note "Nur zur Nachvollziehbarkeit"
    Diese Abschnitte sind für die Bedienung nicht nötig.

- **Views** in `nachweis/views.py`: `_kalender_kontext` baut Zeitraum, Filter, Matrix/Karten/Grid und Legende; `kalender` rendert die Seite (inkl. Bearbeiten-Objekt via `?edit=<id>`); `termin_save` und `termin_delete` verarbeiten das Formular (POST, `@login_required`, Besitzprüfung `mitarbeiter=me`); `kalender_druck` rendert das Druck-Layout.
- **Berechtigung:** `services.ohne_klientenarbeit(request.user)` blockt Admin/Verwaltung; Speichern/Löschen setzen zusätzlich `mitarbeiter=me` und lehnen Fremdtermine mit `HttpResponseForbidden` bzw. `get_object_or_404` ab.
- **Modell `Termin`** (`nachweis/models.py`): `mitarbeiter`, optional `klient`, `datum`, `beginn`, optionales `ende`, `titel`, `ort`, `notiz`. Eigenschaft `anzeige` liefert das Klient*innen-Kürzel oder den Titel; `farbe` die Klient*innen-Farbe oder Neutralgrau `#e5e7eb`.
- **Modell `Klient`**: `kuerzel_anzeige` = gepflegtes Kürzel oder die ersten drei Buchstaben des Nachnamens; `farbe` = stabile Pastellfarbe aus `FARBPALETTE[pk % len]`.
- **Template:** `nachweis/templates/nachweis/kalender.html` (Segment-Umschalter, Filter, drei Ansichten, Legende, Formular, Vollbild-JS via `body.kal-fs` und Esc-Handler).

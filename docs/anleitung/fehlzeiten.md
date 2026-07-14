# Fehlzeiten-Statistik

Die Fehlzeiten-Statistik gibt der Leitung einen kompakten Jahresüberblick über die Ausfallzeiten aller aktiven Mitarbeiter*innen im Team. Für jede Person siehst du die **Fehlquote in Prozent der Werktage** – fortlaufend fürs laufende Jahr bis heute –, aufgeschlüsselt nach Urlaub, Krank, Fortbildung, Freizeitausgleich (FZA) und Sonstiges, dazu die hochgerechneten Fehlstunden und eine separate Krankquote mit Ampelfarbe. Die Seite ist ein reines Auswertungs-Werkzeug für die Personalplanung: Sie liest die genehmigten Abwesenheiten aus und rechnet sie zusammen, sie erfasst selbst nichts.

Du erreichst die Seite über den Menüpunkt **Fehlzeiten** in der Seitenleiste. Sie ist nur für die Leitung sichtbar.

!!! warning "Nur für die Leitung – Beschäftigtendatenschutz"
    Fehlzeiten (insbesondere Krankheitstage) sind Beschäftigtendaten und besonders schützenswert. Der Zugriff ist deshalb technisch auf die **Leitung** beschränkt und zeigt ausschließlich Mitarbeiter*innen der von dir geleiteten Team(s). Wer keine Leitungsrolle hat, bekommt die Seite gar nicht erst zu Gesicht (der Server weist den Aufruf ab). Betreuer*innen, Verwaltung und Admin sehen diese Auswertung nicht.

## Was die Tabelle zeigt

Jede Zeile ist eine aktive Mitarbeiter*in, sortiert nach **Fehlquote absteigend** (die auffälligsten Fälle stehen oben). Die Spalten:

| Spalte | Bedeutung |
| --- | --- |
| Mitarbeiter*in | Name, Vorname und Team |
| Urlaub | genehmigte Urlaubstage im Zeitraum (Werktage) |
| Krank | genehmigte Krankheitstage im Zeitraum (Werktage) |
| Fortbild. | Tage für Fortbildung |
| FZA | Tage Freizeitausgleich |
| Sonst. | Sonstige genehmigte Abwesenheiten |
| Σ Fehltage | Summe aller Fehltage-Spalten |
| Fehlstd. | Fehlstunden = Σ Fehltage × Tagessoll |
| Fehlquote | Σ Fehltage ÷ Werktage des Zeitraums, in % |
| Krankquote | nur Krank-Tage ÷ Werktage des Zeitraums, in % |

Über der Tabelle steht der Wert **Zeitraum-Werktage**: die möglichen Arbeitstage (Mo–Fr ohne Berliner Feiertage) im ausgewerteten Zeitraum. Er ist der gemeinsame Nenner für alle Prozentangaben und für jede Person in der Auswertung gleich.

!!! note "Nur genehmigte Abwesenheiten zählen"
    In die Statistik gehen ausschließlich Abwesenheiten mit dem Status **genehmigt** ein. Beantragte oder abgelehnte Anträge werden nicht mitgezählt. Damit die Quoten stimmen, müssen offene Anträge also zuerst über den Genehmigungs-Workflow entschieden sein.

## Zeitraum: fortlaufend bis heute

Für das **laufende Jahr** wird nicht bis zum 31.12. gerechnet, sondern nur bis **heute**. Die Fehlquote bezieht sich damit auf die bereits vergangenen Werktage – eine Krankheitswoche im Januar schlägt bei einem noch jungen Jahr stärker durch als am Jahresende. Für vergangene Jahre wird das volle Kalenderjahr herangezogen. Ein reines Zukunftsjahr liefert eine leere Tabelle.

Werktage sind durchgängig **Mo–Fr ohne Berliner Feiertage** (inkl. Internationaler Frauentag am 8.3.). Wochenenden und Feiertage sind weder Basis noch Fehltag.

## So rechnet die Quote

- **Fehltage je Art:** Für jede genehmigte Abwesenheit werden die Werktage im Schnittbereich mit dem Auswertungszeitraum gezählt und der passenden Art (Urlaub/Krank/Fortbildung/FZA/Sonstige) zugeordnet.
- **Fehlquote** = Σ Fehltage ÷ Zeitraum-Werktage × 100.
- **Krankquote** = Krank-Tage ÷ Zeitraum-Werktage × 100 – bewusst getrennt ausgewiesen.
- **Fehlstunden** = Σ Fehltage × Tagessoll, wobei das Tagessoll das hinterlegte Wochen-Soll der Person geteilt durch 5 ist. Wer weniger Wochenstunden hat, dessen Fehltage schlagen mit entsprechend weniger Stunden zu Buche.

!!! tip "Krankquote ist die aussagekräftigere Kennzahl"
    Urlaub ist geplante Abwesenheit und keine „Fehlzeit" im engeren Sinn – er lässt die Fehlquote hoch aussehen, obwohl alles nach Plan läuft. Für die Personalplanung und das Erkennen von Belastungsmustern ist deshalb vor allem die **Krankquote** relevant. Sie hat in der Tabelle eine eigene, farblich hervorgehobene Spalte.

## Ampel

Fehlquote und Krankquote sind farblich als Ampel hinterlegt, damit Auffälligkeiten sofort ins Auge springen:

| Kennzahl | Grün | Gelb | Rot |
| --- | --- | --- | --- |
| Fehlquote | unter 10 % | 10 % bis unter 20 % | ab 20 % |
| Krankquote | unter 4 % | 4 % bis unter 8 % | ab 8 % |

Die Farben sind eine reine Orientierungshilfe, keine Bewertung. Gerade bei kleinen Zeiträumen früh im Jahr können schon wenige Tage die Quote über eine Schwelle heben.

## Filter

Oben stehen zwei Filter:

| Filter | Wirkung |
| --- | --- |
| Team | Nur bei mehreren geleiteten Teams sichtbar. Schränkt die Auswertung auf ein Team ein; „Alle" zeigt alle deine Teams. |
| Jahr | Auswertungsjahr. Das laufende Jahr rechnet fortlaufend bis heute, vergangene Jahre über das volle Kalenderjahr. |

Nach einer Änderung mit **Anzeigen** neu berechnen (der Team-Filter aktualisiert sich automatisch). Es werden nur **aktive** Mitarbeiter*innen der ausgewählten Team(s) gelistet.

!!! note "Team-Scoping und Datensparsamkeit"
    Die Liste ist auf die von dir geleiteten Team(s) begrenzt – du siehst keine Personen aus fremden Teams. Angezeigt werden nur die für die Planung nötigen aggregierten Zahlen (Tage je Art, Quoten, Fehlstunden), nicht einzelne Krankmeldungen oder Diagnosen. Diese Datensparsamkeit ist mit Blick auf besonders schützenswerte Gesundheitsdaten (Art. 9 DSGVO) bewusst so gehalten.

## Für Neugierige: Technik dahinter

!!! note "Nur zur Nachvollziehbarkeit"
    Dieser Abschnitt beschreibt die technische Umsetzung und ist für die Bedienung nicht nötig.

- **View:** `fehlzeiten` in `nachweis/views.py` – prüft `services.ist_leitung(request.user)` und antwortet sonst mit `HttpResponseForbidden`. Lädt die aktiven `Mitarbeiter` der über `services.teams_fuer(...)` gescopten (optional per `?team=` gefilterten) Team(s) und übergibt das Ergebnis von `fehlzeiten_statistik` an das Template.
- **Berechnung:** `services.fehlzeiten_statistik(mitarbeitende, jahr)` in `nachweis/services.py` – ermittelt die Basis über `services.werktage(...)` (Mo–Fr ohne `berliner_feiertage`), klemmt den Zeitraum im laufenden Jahr auf `heute`, summiert je Person die Werktage der `Abwesenheit`-Einträge mit Status `AbwesenheitStatus.GENEHMIGT` je `AbwesenheitArt` und liefert `fehlquote`, `krankquote`, `summe`, `tage` und `fehlstunden`; sortiert nach `fehlquote` absteigend.
- **Modelle:** `Mitarbeiter` (Property `tagessoll` = `wochenstunden` ÷ 5), `Abwesenheit`, `AbwesenheitArt` (`URLAUB`, `KRANK`, `FORTBILDUNG`, `FREIZEITAUSGLEICH`, `SONSTIGE`) und der Status aus `Genehmigungsstatus` (Alias `AbwesenheitStatus`) in `nachweis/models.py`.
- **Template:** `nachweis/templates/nachweis/fehlzeiten.html` – rendert die Tabelle, die Ampelklassen (`gut`/`mittel`/`hoch`) über die Schwellen 10/20 (Fehlquote) bzw. 4/8 (Krankquote) und den Team-/Jahr-Filter.
- **Route:** `fehlzeiten/` (Name `nachweis:fehlzeiten`) in `nachweis/urls.py`.

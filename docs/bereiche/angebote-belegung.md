# Angebote, Belegung & Tagessatz

Diese Seite erklärt das Mehr-Bereichs-Fundament der App für die **(teil-)stationären Bereiche** – Wohnheim, WG/verbundene Wohnform, Wohn- und Tagesgruppe der Jugendhilfe. Du legst dort **Angebote** (Standorte mit Plätzen) an, verwaltest über den **Belegungskalender** die Ein- und Auszüge, erfasst **Klient-Abwesenheiten** (Krankenhaus, Urlaub, Freihaltung …) und rechnest **je Belegungstag über einen Tagessatz** ab. Die Vergütungsregeln – Freihaltegeld, Weiterzahlungsgrenzen, Kontingente, Meldefristen – stecken als **Daten** in den Abwesenheitsarten, nicht im Programmcode: neue Regeln pflegst du ohne Programmierung.

!!! info "Für wen gilt das?"
    Nur für Teams mit stationären/teilstationären Angeboten. Das **ambulante BEW/TBEW** braucht **kein** Angebot und keine Belegung – dort läuft die Abrechnung wie gewohnt über [FLS + kLE](../fachliches/fls-kle.md). Alle Ansichten hier sind der **Leitung** vorbehalten und **team-gescopt**: Du siehst ausschließlich Angebote, Belegungen und Bewohner*innen der Teams, für die du Leitung bist.

## Angebote anlegen (Standorte & Wohnformen)

Unter **Angebote & Standorte** bildest du jede Wohnform als eigenen Datensatz ab: WG, besondere Wohnform, Wohngruppe, Tagesgruppe. Die Tabelle zeigt pro Angebot **Plätze**, **belegt heute** und den zugeordneten Standard-Leistungstyp; ist ein Angebot voll (belegt ≥ Plätze), wird der Zählwert grün hervorgehoben.

| Feld | Bedeutung | Hinweise |
|---|---|---|
| **Name** \* | Bezeichnung der Wohnform/WG/Gruppe | Pflichtfeld, max. 120 Zeichen |
| **Team** \* | zugehöriges Team | Nur **eigene** Teams wählbar; steuert die Sichtbarkeit |
| **Typ** | WG · besondere Wohnform · Wohngruppe (§ 34/35a) · Tagesgruppe (§ 32) · BEW | Default: WG / verbundene Wohnform |
| **Erreichbarkeit** | ohne · Tag-Präsenz · Nacht-Bereitschaft · Tag + Nacht (24h) | örV-Vergleichskreise |
| **Plätze** | Platzzahl (0–500) | Basis der Auslastungsberechnung |
| **Standard-Leistungstyp** | Katalogeintrag für die Abrechnung | Nur **aktive** Kataloge wählbar; siehe unten |
| **Betriebserlaubnis / Kennung** | z. B. § 45 SGB VIII | Freitext, max. 80 Zeichen |
| **Adresse** | Standortadresse | Freitext |
| **aktiv** | steuert, ob das Angebot in Auswahllisten auftaucht | Neue Angebote sind standardmäßig aktiv |

!!! tip "Standard-Leistungstyp ist nur der Fallback"
    Der am Angebot hinterlegte Leistungstyp gilt nur, wenn die aktive **Bewilligung** der Klient*in keinen eigenen Katalog trägt. Trägt die Bewilligung einen Katalog, gewinnt dieser – so kann eine Bewohner*in nach einem anderen Satz abgerechnet werden als der Standard des Hauses.

!!! note "Ein bereits zugeordneter, inzwischen inaktiver Katalog verschwindet nicht still"
    Wird ein Leistungstyp später deaktiviert, bleibt er beim betroffenen Angebot erhalten und wird im Bearbeiten-Formular als „(inaktiv)" angezeigt. Nur **neue** Zuordnungen sind auf aktive Kataloge beschränkt.

## Belegungskalender: Einzug, Auszug, Anwesenheit

Über **Belegung** zu einem Angebot öffnest du den **Anwesenheitskalender** – eine Matrix *Bewohner*in × Tage* für den gewählten Monat. Jeder belegte Tag ist markiert:

| Anzeige | Bedeutung |
|---|---|
| **A** (grün) | anwesend – voller Tagessatz (100 %) |
| **Kürzel** (gelb) | abwesend, aber innerhalb der Weiterzahlungsgrenze (anteilig vergütet) |
| **Kürzel** (rot) | abwesend über der Weiterzahlungsgrenze → **0 %** Vergütung |
| leer (grau) | Tag außerhalb des Belegungszeitraums |

Rechts stehen je Zeile **BT** (Belegungstage), **verg.** (vergütete Tage als Äquivalent) und der **Betrag** in Euro. Oben siehst du die **Auslastung** des Monats in Prozent, sofern das Angebot Plätze hat.

### Einzug

Im Panel **Einzug** wählst du eine Klient*in aus den **Kandidaten** – das sind Klient*innen deines Teams im Status *Betreuung*, die aktuell nicht bereits hier wohnen – gibst ein **Einzugsdatum** und optional **Platz/Zimmer** an und klickst **Einziehen**.

!!! warning "Doppelbelegungen sind gesperrt"
    Überschneidet der neue Zeitraum eine andere Belegung derselben Klient*in – auch eine offene oder künftige –, wird der Einzug **abgelehnt**. Aufnahme- und Entlasstag zählen dabei je als voller Belegungstag.

!!! danger "Cross-Team-Einzug ist blockiert"
    Gehört die Klient*in zu einem **anderen Team** als das Angebot, wird der Einzug verweigert. Grund: Die Belegungssichtbarkeit hängt am Angebots-Team – ein teamfremder Einzug würde die Person für fremde Leitungen sichtbar machen. Passe zuerst das Team der Klient*in in der [Belegungsliste](../administration/belegungsliste.md) an.

### Auszug

Über das **…**-Menü einer Zeile setzt du **Auszug** und ggf. **Platz**. Ein Auszug vor dem Einzug wird abgelehnt, ebenso ein Zeitraum, der eine andere Belegung schneidet.

!!! note "Offene Abwesenheiten enden mit dem Auszug"
    Setzt du einen Auszug, werden noch offene Abwesenheiten (ohne „bis") automatisch auf das Auszugsdatum geschlossen und über den Auszug hinausragende Abwesenheiten entsprechend gekürzt. Das verhindert, dass eine vergessene offene Abwesenheit Kontingent verbraucht oder Warnungen für Tage nach dem Auszug erzeugt. Die App meldet dir, wie viele Abwesenheiten beendet wurden.

## Abwesenheiten mit Regel-Engine

Im Panel **Abwesenheit erfassen** wählst du **Bewohner*in**, **Art**, **von (Abreisetag)**, optional **bis (letzter Abw.-Tag)** und **gemeldet am**.

!!! abstract "Tageskonventionen (BRV Jug Tz 22 / Beschluss 8/2007)"
    - **von** = erster Abwesenheitstag; der **Abreisetag zählt als abwesend**.
    - **bis** = letzter Abwesenheitstag; **leer** heißt „dauert an".
    - Der **Rückkehrtag** wird **nicht** eingetragen – er zählt als Anwesenheit.

Die eigentlichen Vergütungsregeln liegen in der **Abwesenheitsart** (Stammdaten, ohne Programmierung pflegbar):

| Regel-Feld | Bedeutung |
|---|---|
| **Kürzel** | fürs Kalenderraster, z. B. `KH`, `FRH`, `KB` |
| **Vergütung %** | Anteil des Tagessatzes **innerhalb** der Weiterzahlungsgrenze |
| **Abzug €/Tag** | Abzug an vergüteten Abwesenheitstagen, z. B. der Beköstigungssatz beim EGH-Freihaltegeld |
| **Weiterzahlungsgrenze (Tage)** | leer = unbegrenzt; **darüber 0 %** Vergütung |
| **Basis** | *je Ereignis* (zusammenhängend) **oder** *kumulativ je Kalenderjahr* |
| **Meldefrist (Tage)** | Warnschwelle für die Meldung an den Kostenträger |

!!! example "Wie die Regeln greifen"
    - **Krankenhaus (KH):** Weiterzahlungsgrenze z. B. 3 Monate *je Ereignis* – die ersten Tage voll, darüber 0 %.
    - **Urlaub:** z. B. 30 Tage *kumulativ je Kalenderjahr* – die App zählt über **alle** Belegungen der Klient*in im Jahr zusammen.
    - **Freihaltegeld (FRH, EGH, Beschluss 8/2007):** Weiterzahlung z. B. minus **Beköstigungssatz** über `Abzug €/Tag`, Kontingent ~91 Tage.
    - **Kurzbesuch (KB):** ≤ 3 Tage ohne Anrechnung – ein längerer Zeitraum wird abgelehnt mit dem Hinweis, stattdessen die Freihaltegeld-Art (FRH) zu erfassen.

!!! warning "Abwesenheit muss im Belegungszeitraum liegen"
    Ein Zeitraum, der (teilweise) vor dem Einzug oder nach dem Auszug liegt, wird abgelehnt – das verhindert Kontingent- und Anzeige-„Geister".

### Kontingent-Zählung (Kalenderjahr)

Bei Arten mit Basis *Kalenderjahr* zählt die App die **Tagesmengen je Klient*in und Art**:

- Überlappende Einträge zählen **nicht doppelt**.
- Jeder Tag wird auf den jeweiligen **Belegungszeitraum geclippt** – Tage nach dem Auszug verbrauchen **kein** Kontingent.
- Ist das Kontingent überschritten, fällt die Vergütung ab dem überzähligen Tag auf 0 % (im Kalender rot).

### Meldefristen an den Kostenträger

Hat eine Abwesenheitsart eine **Meldefrist** und die Abwesenheit dauert länger, ohne dass ein **gemeldet am** gesetzt ist, erscheint oben im Kalender eine Warnbox **„Meldung an den Kostenträger fällig"** mit Dauer und Frist. Per Klick **„heute gemeldet ✓"** dokumentierst du die Meldung.

!!! tip "Meldedatum jederzeit setzen oder Abwesenheit löschen"
    Über die Aktionen einer Abwesenheit kannst du das **gemeldet-Datum** nachtragen oder den Eintrag **löschen**. Das Meldedatum dokumentiert die Meldung an den Kostenträger (BRV Jug: Meldung ans Jugendamt ab dem 4. Abwesenheitstag; BAO/WTG: sofort).

## Leistungskatalog & Entgeltsatz-Zeitscheiben

Ein **Leistungskatalog-Eintrag** beschreibt, **was** nach **welcher Einheit** und **Rechtsgrundlage** vergütet wird. Für die Bereiche hier ist die **Abrechnungseinheit** entscheidend:

| Einheit | Bedeutung |
|---|---|
| **Tagessatz je Belegungstag** | stationär – Abrechnung über den Belegungskalender |
| **Tagessatz je Öffnungstag** | teilstationär (Tagesgruppe) |
| Fachleistungsstunde / kLE je Tag / Pauschale | die anderen Bereiche (siehe FLS + kLE) |

Der **Preis** hängt am **Entgeltsatz** – und zwar als **Zeitscheibe**: Jährliche Fortschreibungen (Kommissions-/VK-Beschlüsse) legst du als **neuen Satz ab Stichtag** an; laufende Fälle werden automatisch umgepreist, ohne neue Bewilligung.

| Entgeltsatz-Feld | Bedeutung |
|---|---|
| **Betrag €** | Tagessatz |
| **davon Nebenkosten € / davon Investition €** | getrennter Ausweis der Entgeltbestandteile (BRV Jug: Leistungsentgelt / Nebenkosten § 39 / Invest) |
| **gültig ab / gültig bis** | Zeitscheibe; „bis" leer = läuft weiter |
| **Kostenträger (leer = alle)** | leer = landeseinheitlich; gesetzt = trägerindividuell verhandelt |
| **Variante** | z. B. „mit Leitungsanteil" / „ohne" |
| **Kommentar** | z. B. Beschluss-Nr. der Fortschreibung |

## Tagessatz-Abrechnung über den Kalender

Der Betrag je Bewohner*in und Monat ergibt sich direkt aus dem Kalender:

!!! abstract "Abrechnungsformel (Monat, je Belegung)"
    ```
    Betrag = Σ(vergüteter Anteil je Tag × Tagessatz) − Σ Abzüge an vergüteten Abw.-Tagen
    ```
    - Anwesend = Anteil 1, Abwesend = Anteil laut Regel der Art (0…1), außerhalb der Belegung = kein Tag.
    - Der **Tagessatz** wird je Belegung aufgelöst: Katalog aus der **aktiven Bewilligung** der Klient*in, sonst der **Standard-Leistungstyp** des Angebots; Kostenträger aus der Bewilligung. Kaufmännische Rundung auf 2 Nachkommastellen.

Zeigt eine Zeile beim Betrag „—", ließ sich **kein Entgeltsatz auflösen** – dann fehlt ein passender Katalog oder ein gültiger Satz zum Stichtag. Prüfe Bewilligung, Standard-Leistungstyp und die Gültigkeit der Entgeltsätze.

!!! danger "Datenschutz: Art-9-Datensparsamkeit"
    Abwesenheiten können einen Gesundheitsbezug haben (Krankenhaus). Deshalb ist der **Kommentar**-Freitext bewusst aus der Historie/Audit-Tabelle ausgenommen – konsistent zur Datenminimierung besonderer Kategorien nach Art. 9 DSGVO. Erfasse in Kommentaren keine sensiblen Details, die nicht abrechnungsnotwendig sind. Sämtliche Ansichten bleiben team-gescopt.

## Für Neugierige: Technik dahinter

!!! note "Nur zur Nachvollziehbarkeit"
    Dieser Abschnitt nennt die echten Views, Modelle und Templates beim Namen – er ist keine Bedienanleitung.

- **Views** (`nachweis/views_belegung.py`, alle `@login_required` + `services.ist_leitung`, team-gescopt über `_meine_angebote`): `angebote` (Anlegen/Bearbeiten, Auslastung via `belegt_am`), `belegungskalender` (Matrix + `auslastung` + `melde_warnungen`), `belegung_speichern` (Einzug/Auszug mit `_ueberlappt`-Overlap-Schutz und Cross-Team-Sperre), `klient_abwesenheit_speichern`, `klient_abwesenheit_aktion`.
- **Service-Logik** (`nachweis/services_belegung.py`): `monatskalender` (Tagesliste + Summen, `verguetet_aequiv`, `abzug`, `betrag`), `tages_verguetung` (Weiterzahlungsgrenze je Ereignis/Kalenderjahr), `_jahres_tagesmenge` (dedupliziertes, auf den Belegungszeitraum geclipptes Kontingent), `satz_fuer_belegung` (Katalog aus `aktive_bewilligung`, sonst `angebot.katalog`), `tagessatz_monat` (M3-Monatsabrechnung), `melde_warnungen`. Beträge durchgängig `Decimal` mit `ROUND_HALF_UP`.
- **Modelle** (`nachweis/models.py`): `Angebot` (`AngebotsTyp`, `Erreichbarkeit`, `plaetze`, `katalog`), `Belegung` (`einzug`/`auszug`, `belegt_am`, `HistoricalRecords`), `AbwesenheitsartKlient` (`verguetung_prozent`, `abzug_je_tag`, `max_tage`, `basis` via `AbwesenheitsBasis`, `meldefrist_tage`), `KlientAbwesenheit` (`von`/`bis`, `gemeldet_am`, `abwesend_am`; `kommentar` aus der History ausgeschlossen), `Leistungskatalog` (`einheit` via `Abrechnungseinheit`), `Entgeltsatz` (Zeitscheibe `gueltig_von`/`gueltig_bis`, `betrag_nebenkosten`, `betrag_investition`, `gilt_am`).
- **Templates**: `nachweis/templates/nachweis/angebote.html` (Angebotsliste + Formular) und `nachweis/templates/nachweis/belegungskalender.html` (Anwesenheitsmatrix, Warnbox, Einzugs- und Abwesenheits-Panels).

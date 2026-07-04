# Rechtsgrundlage & Informationspflichten (Art. 6/9/13)

!!! abstract "Ausfüllbare Vorlage"
    | Feld | Angabe |
    |------|--------|
    | **Dokumententyp** | Rechtsgrundlagen-Memo + Informationsblätter nach Art. 13 DSGVO |
    | **Stand** | **[AUSFUELLEN: Datum der aktuellen Fassung ]** |
    | **Verantwortlich (Träger)** | **[AUSFUELLEN: Name des Trägers, Anschrift ]** |
    | **Erstellt/geprüft durch DSB** | **[AUSFUELLEN: Name der/des Datenschutzbeauftragten ]** |
    | **Freigabe** | **[AUSFUELLEN: Name, Funktion, Datum, Unterschrift ]** |
    | **Nächste Prüfung** | **[AUSFUELLEN: Datum ]** |

!!! danger "Prototyp mit fiktiven Daten"
    Der aktuelle Systemstand ist ein **Prototyp mit ausschließlich fiktiven Demodaten**. Dieses Dokument ist – ausgefüllt und freigegeben – **Voraussetzung, bevor der erste echte Klientendatensatz** erfasst wird (geplanter, begrenzter Pilotbetrieb).

!!! note "So füllen Sie diese Vorlage aus"
    Alle technischen und betrieblichen Angaben sind aus dem Systembefund **vorbefüllt**. Alle Stellen, die der **Träger (Verantwortlicher)** gemeinsam mit der/dem **Datenschutzbeauftragten (DSB)** entscheiden oder eintragen muss, sind einheitlich mit **[AUSFUELLEN: … ]** markiert und im Dokument per Textsuche auffindbar.

---

## Rollen und Beteiligte

| Rolle | Angabe |
|-------|--------|
| **Verantwortlicher (Art. 4 Nr. 7 DSGVO)** | der **Träger**: **[AUSFUELLEN: Name, Anschrift, gesetzl. Vertretung ]** |
| **Betreiber / Auftragsverarbeiter (Art. 28 DSGVO)** | Mirko Richter, Stillerzeile 29, 12587 Berlin — Beschäftigungs-/Beauftragungsverhältnis zum Träger: **[AUSFUELLEN: Art des Verhältnisses (z. B. Angestellter / beauftragter Dienstleister mit AVV) ]** |
| **Datenschutzbeauftragte(r)** | **[AUSFUELLEN: Name, Kontakt ]** |
| **Hosting-Auftragsverarbeiter** | STRATO GmbH (V-Server + HiDrive), Rechenzentrum Deutschland, ISO-27001-zertifiziert; AVV Version 3.6, Kundennr. 78213667, abgeschlossen 27.08.2025, liegt vor |

---

# Teil A — Rechtsgrundlagen-Memo

Dieses Memo benennt und begründet die datenschutzrechtlichen Erlaubnisnormen für die Verarbeitungen der Anwendung. Es unterscheidet **Klientendaten** (besondere Kategorien, Art. 9 DSGVO) und **Beschäftigtendaten**.

## A.1 Verarbeitete Datenkategorien (Systembefund)

!!! info "Aus dem Datenmodell verifiziert (`nachweis/models.py`)"
    **Klient*innen (leistungsberechtigte Personen):** Name, Geburtsdatum, Hilfebedarfsgruppe (HBG), bewilligte Leistung (AL + kalkulatorische Leistungseinheit / FLS pro Monat), Person-ID, Betreuungs- und Berichtsfristen (KÜ/BRP), Kürzel, Kommentar, Team, Bezugsbetreuer, Status.

    **Leistungsdokumentation:** Datum/Uhrzeit, Leistungsart, Betreuer, Verlaufs-/Dokumentationstext, Notiz.

    **Weitere Verarbeitungen:** Termine, Arbeitszeit, Abwesenheit (inkl. Art *„Krank“* = Gesundheitsdatum der **Beschäftigten**), Gruppennachweise, Team-Handkasse (Kassenbuchung/Zählprotokoll), Mitarbeiterdaten.

    **Ausdrücklich NICHT gespeichert:** Diagnosen, Adressen, Kostenträger-Korrespondenz.

Die Klientendaten lassen als Ganzes Rückschlüsse auf **Gesundheit und soziale Lage** zu (Bewilligung von Eingliederungshilfe, Hilfebedarfsgruppe, Betreuungsverläufe) und sind damit **besondere Kategorien personenbezogener Daten** im Sinne von **Art. 9 Abs. 1 DSGVO**.

## A.2 Rechtsgrundlage für Klientendaten (besondere Kategorien)

| Ebene | Norm |
|-------|------|
| **Erlaubnistatbestand Art. 9** | **Art. 9 Abs. 2 lit. h DSGVO** — Verarbeitung für Zwecke der Gesundheits-/Sozialversorgung bzw. -verwaltung und der Erbringung sozialer Leistungen |
| **Fachrechtliche Grundlage** | **SGB IX** (Eingliederungshilfe, Leistungserbringung) und **SGB X** (Sozialdatenschutz, Erforderlichkeit für die Durchführung/Abrechnung) |
| **Nationale Öffnungsklausel** | **§ 22 BDSG** (Verarbeitung besonderer Kategorien; geeignete und spezifische Maßnahmen nach § 22 Abs. 2 BDSG) |
| **Allgemeine Grundlage** | ergänzend **Art. 6 Abs. 1 lit. c DSGVO** (rechtliche Verpflichtung zur Leistungsdokumentation/Abrechnung) |

**Herleitung der Erforderlichkeit (Art. 5 Abs. 1 lit. c, Art. 9 Abs. 2 lit. h DSGVO):**

- Die Erbringung Therapeutisch Betreuten Einzelwohnens (TBEW) im Rahmen der Berliner Eingliederungshilfe ist **ohne** personenbezogene Leistungsdokumentation nicht möglich: Fachleistungsstunden (FLS/kLE) müssen personenbezogen erbracht, dokumentiert und gegenüber dem Kostenträger **nachgewiesen und abgerechnet** werden.
- Erhoben werden nur die für **Nachweis, Steuerung und Abrechnung** notwendigen Merkmale (HBG, bewilligtes Leistungsvolumen, erbrachte Leistungen, Fristen). Diagnosen, Adressen und Kostenträger-Korrespondenz werden **bewusst nicht** gespeichert (Datenminimierung).
- **Zweckbindung:** Nutzung ausschließlich für Leistungsnachweis/Abrechnung und interne Steuerung; keine zweckfremde Verwendung.
- **Geeignete/spezifische Maßnahmen nach § 22 Abs. 2 BDSG** sind technisch/organisatorisch umgesetzt (siehe A.4).

## A.3 Rechtsgrundlage für Beschäftigtendaten

| Verarbeitung | Norm |
|--------------|------|
| Mitarbeiterstammdaten, Arbeitszeit, Termine, Abwesenheiten, Handkasse | **§ 26 Abs. 1 BDSG** (Datenverarbeitung für Zwecke des Beschäftigungsverhältnisses) i. V. m. **Art. 6 Abs. 1 lit. b DSGVO** (Durchführung des Arbeitsvertrags) und **lit. c** (gesetzliche/arbeitsrechtliche Pflichten) |
| Abwesenheitsart **„Krank“** (Gesundheitsdatum) | **§ 26 Abs. 3 BDSG** i. V. m. **Art. 9 Abs. 2 lit. b DSGVO** (Erfüllung arbeitsrechtlicher Pflichten aus dem Beschäftigungsverhältnis) |

!!! note "Abwesenheitsart „Krank“ — Standard-Personalverwaltung"
    Erfasst wird lediglich die **Tatsache der krankheitsbedingten Abwesenheit** (kein Diagnosebezug). Das entspricht der üblichen Personal-/Dienstplanverwaltung und ist zur Einsatzsteuerung und Entgeltfortzahlung erforderlich. Es handelt sich um ein Gesundheitsdatum im Sinne von Art. 9 DSGVO, das über § 26 Abs. 3 BDSG gedeckt ist.

## A.4 Geeignete und spezifische Maßnahmen (§ 22 Abs. 2 BDSG)

Als Schutzmaßnahmen für die Verarbeitung besonderer Kategorien sind u. a. umgesetzt (Details siehe [Datenschutz-TOM](../sicherheit/datenschutz.md), [Härtung](../sicherheit/haertung.md), [Row-Level-Security](../sicherheit/rls.md)):

- **Zugriffstrennung** auf Team-Ebene, auf App-Ebene **und** datenbank-erzwungen (PostgreSQL Row-Level-Security, FORCE); Rolle **„Admin“ ohne Klientenzugriff**.
- **Argon2-Passwort-Hashing**, **Zwei-Faktor-Pflicht (TOTP)** inkl. Break-Glass-Konto, Brute-Force-Sperre (django-axes), automatische Abmeldung nach 15 Min Inaktivität.
- **Lückenloses Änderungsprotokoll** (django-auditlog: wer/wann/was).
- **HTTPS/HSTS**, sichere Cookies, X-Frame-DENY, DEBUG fail-closed.
- **Verschlüsselte Backups** (age, Offline-Privatschlüssel, getesteter Restore, Offsite-Spiegel auf STRATO HiDrive, 7-Tage-Rotation, Dead-Man's-Switch-Alarm).

!!! warning "Bekannte Lücken (in Umsetzung)"
    - Keine Protokollierung **lesender** Zugriffe (nur Anlegen/Ändern/Löschen).
    - Lösch-/Anonymisierungs-Routine in Umsetzung (Klient wegen Fremdschlüssel-Schutz nicht ersatzlos löschbar).

## A.5 Bestätigung durch die/den Datenschutzbeauftragte(n)

!!! tip "Von der DSB zu bestätigen"
    - [ ] Die benannten Rechtsgrundlagen (A.2 / A.3) sind für die beschriebenen Verarbeitungen **zutreffend und vollständig**. — **[AUSFUELLEN: Bestätigung / Anmerkungen der DSB ]**
    - [ ] Die geeigneten/spezifischen Maßnahmen nach § 22 Abs. 2 BDSG sind **angemessen**. — **[AUSFUELLEN: Bestätigung / Auflagen ]**
    - [ ] Fachrechtliche Aufbewahrungs-/Löschfristen sind festgelegt (siehe Teil B, Speicherdauer). — **[AUSFUELLEN: Bestätigung ]**

    **Bestätigt am:** **[AUSFUELLEN: Datum ]** — **Name/Unterschrift DSB:** **[AUSFUELLEN ]**

---

# Teil B — Informationsblätter (Art. 13 DSGVO)

Zwei ausfüllbare Informationsblätter zur Erfüllung der Informationspflichten bei Erhebung personenbezogener Daten bei der betroffenen Person.

---

## B1 — Information für Klient*innen

!!! note "Aushändigung"
    Dieses Informationsblatt wird in der Regel **über den Träger im Rahmen der Betreuungsvereinbarung** ausgehändigt. Die inhaltlichen Angaben (Zwecke, Rechtsgrundlage, Datenkategorien, Empfänger) sind vorbefüllt; Träger-/DSB-Kontakte und Fristen sind einzutragen.

### Wer ist für Ihre Daten verantwortlich?

| | |
|---|---|
| **Verantwortlicher** | **[AUSFUELLEN: Name des Trägers ]** |
| **Anschrift** | **[AUSFUELLEN: Straße, PLZ, Ort ]** |
| **Kontakt (Telefon/E-Mail)** | **[AUSFUELLEN: Kontaktdaten ]** |
| **Datenschutzbeauftragte(r)** | **[AUSFUELLEN: Name, Anschrift, E-Mail/Telefon ]** |

### Zu welchem Zweck verarbeiten wir Ihre Daten?

- **Dokumentation** der für Sie erbrachten Fachleistungen (Therapeutisch Betreutes Einzelwohnen),
- **Nachweis und Abrechnung** dieser Leistungen gegenüber dem **Kostenträger** (Bezirksamt / Senat Berlin),
- **interne Steuerung** der Betreuung (z. B. Termin- und Fristenplanung).

### Auf welcher Rechtsgrundlage?

- **Art. 9 Abs. 2 lit. h DSGVO** (Erbringung sozialer/gesundheitsbezogener Leistungen) i. V. m. **SGB IX / SGB X** und **§ 22 BDSG**,
- ergänzend **Art. 6 Abs. 1 lit. c DSGVO** (gesetzliche Nachweis-/Abrechnungspflichten).

### Welche Daten verarbeiten wir?

- **Stammdaten:** Name, Geburtsdatum, Kürzel, Person-ID, Status,
- **Leistungsdaten:** Hilfebedarfsgruppe (HBG), bewilligtes Leistungsvolumen (AL + kLE / Fachleistungsstunden pro Monat), Betreuungs- und Berichtsfristen,
- **Betreuungsdokumentation:** Datum/Uhrzeit, Leistungsart, zuständige Betreuungsperson, Verlaufs-/Dokumentationstext, Notizen.

!!! info "Was wir NICHT speichern"
    Wir speichern **keine Diagnosen, keine Adressen und keine Korrespondenz mit dem Kostenträger** in dieser Anwendung.

### Wer erhält Ihre Daten?

| Empfänger | Zweck |
|-----------|-------|
| **Kostenträger** (Bezirksamt / Senat Berlin) | im Rahmen von **Nachweis und Abrechnung** |
| **STRATO GmbH** (Auftragsverarbeiter, Hosting) | technischer Betrieb; vertraglich gebunden (AVV), Rechenzentrum **Deutschland** |

Eine sonstige Weitergabe an Dritte findet **nicht** statt.

!!! note "Keine Drittlandübermittlung"
    Ihre Daten werden **ausschließlich in Deutschland / der EU** verarbeitet. Eine Übermittlung in ein Drittland (außerhalb EU/EWR) findet **nicht** statt.

### Woher stammen Ihre Daten?

Die Daten werden überwiegend **bei Ihnen selbst** im Rahmen der Betreuung erhoben. Angaben zu **bewilligter Leistung und Hilfebedarfsgruppe (HBG)** stammen aus dem **Bewilligungsbescheid des Kostenträgers** (Bezirksamt / Senat Berlin).

!!! note "Herkunft der Bewilligungsdaten"
    Soweit Daten nicht direkt bei Ihnen, sondern beim Kostenträger erhoben werden, gelten ergänzend die Informationspflichten nach **Art. 14 DSGVO** (Quelle der Daten). — **[AUSFUELLEN: durch Träger/DSB bestätigen, ob und welche Klientendaten aus dem Bewilligungsbescheid übernommen werden ]**

### Wie lange speichern wir Ihre Daten?

Ihre Daten werden für die Dauer der Betreuung und darüber hinaus im Rahmen der **gesetzlichen sozialrechtlichen Aufbewahrungsfristen** gespeichert und anschließend gelöscht bzw. anonymisiert.

- **Aufbewahrungsfrist:** **[AUSFUELLEN: konkrete Frist, z. B. nach SGB / Landesrecht — vom Träger/DSB festzulegen ]**

### Ihre Rechte

Sie haben das Recht auf:

- **Auskunft** (Art. 15 DSGVO),
- **Berichtigung** unrichtiger Daten (Art. 16 DSGVO),
- **Löschung** (Art. 17 DSGVO, soweit keine Aufbewahrungspflicht entgegensteht),
- **Einschränkung der Verarbeitung** (Art. 18 DSGVO),
- **Widerspruch** gegen die Verarbeitung (Art. 21 DSGVO),
- **Beschwerde bei der Aufsichtsbehörde**.

!!! note "Datenübertragbarkeit (Art. 20 DSGVO)"
    Das Recht auf Datenübertragbarkeit besteht nur bei Verarbeitungen, die auf **Einwilligung** oder **Vertrag** beruhen. Da Ihre Daten auf einer **gesetzlichen Grundlage** (Art. 9 Abs. 2 lit. h DSGVO i. V. m. SGB IX/X, § 22 BDSG) verarbeitet werden, findet Art. 20 DSGVO auf diese Verarbeitung **keine Anwendung**.

!!! info "Keine automatisierte Entscheidungsfindung"
    Es findet **keine automatisierte Entscheidungsfindung einschließlich Profiling** im Sinne von **Art. 22 DSGVO** statt. Über Ihre Betreuung entscheiden ausschließlich Menschen.

!!! note "Keine Einwilligung"
    Die Verarbeitung beruht **nicht auf Ihrer Einwilligung**, sondern auf einer gesetzlichen Grundlage. Ein Widerrufsrecht nach Art. 7 Abs. 3 DSGVO besteht daher nicht.

!!! tip "Aufsichtsbehörde"
    **Berliner Beauftragte für Datenschutz und Informationsfreiheit (BlnBDI)** — Sie können sich jederzeit dort beschweren (Kontaktdaten und Meldewege über die Website der Behörde). — **[AUSFUELLEN: ggf. aktuelle Anschrift/Website der BlnBDI ergänzen ]**

Zur Ausübung Ihrer Rechte wenden Sie sich an: **[AUSFUELLEN: Kontaktstelle beim Träger / DSB ]**

### Müssen Sie diese Daten bereitstellen?

Die Bereitstellung der genannten Daten ist zur **Gewährung und Abrechnung** der Eingliederungshilfeleistung **erforderlich**. Ohne diese Daten können die Leistungen nicht dokumentiert und gegenüber dem Kostenträger nicht abgerechnet werden.

---

**Ausgehändigt am:** **[AUSFUELLEN: Datum ]** — **im Rahmen von:** **[AUSFUELLEN: z. B. Betreuungsvereinbarung ]**

---

## B2 — Information für Mitarbeitende

### Wer ist für Ihre Daten verantwortlich?

| | |
|---|---|
| **Verantwortlicher (Arbeitgeber/Träger)** | **[AUSFUELLEN: Name des Trägers ]** |
| **Anschrift** | **[AUSFUELLEN: Straße, PLZ, Ort ]** |
| **Kontakt (Telefon/E-Mail)** | **[AUSFUELLEN: Kontaktdaten ]** |
| **Datenschutzbeauftragte(r)** | **[AUSFUELLEN: Name, Anschrift, E-Mail/Telefon ]** |

### Zu welchem Zweck verarbeiten wir Ihre Daten?

- **Durchführung des Beschäftigungsverhältnisses** (Einsatz-, Termin- und Dienstplanung),
- **Erfassung von Arbeitszeit und Abwesenheiten**,
- **Leistungsdokumentation** (Zuordnung erbrachter Fachleistungen zur betreuenden Person),
- **Verwaltung der Team-Handkasse** (Kassenbuchungen, Zählprotokolle).

### Auf welcher Rechtsgrundlage?

- **§ 26 Abs. 1 BDSG** i. V. m. **Art. 6 Abs. 1 lit. b DSGVO** (Durchführung des Arbeitsvertrags) und **lit. c** (arbeitsrechtliche Pflichten),
- für die Abwesenheitsart **„Krank“**: **§ 26 Abs. 3 BDSG** i. V. m. **Art. 9 Abs. 2 lit. b DSGVO**.

### Welche Daten verarbeiten wir?

- **Mitarbeiterdaten:** Name, Kürzel, Team-Zuordnung, Rolle, Zugangskonto,
- **Arbeitszeit und Termine**,
- **Abwesenheiten** einschließlich der Art (u. a. **„Krank“** = krankheitsbedingte Abwesenheit, **ohne** Diagnoseangabe),
- **Handkassen-Buchungen und Zählprotokolle**.

### Wer erhält Ihre Daten?

| Empfänger | Zweck |
|-----------|-------|
| **STRATO GmbH** (Auftragsverarbeiter, Hosting) | technischer Betrieb; vertraglich gebunden (AVV), Rechenzentrum **Deutschland** |
| **Kostenträger** (Bezirksamt / Senat Berlin) | nur soweit die betreuende Person zum **Leistungsnachweis** gehört (Zuordnung erbrachter Leistungen) |

Eine sonstige Weitergabe an Dritte findet **nicht** statt.

!!! note "Keine Drittlandübermittlung"
    Ihre Daten werden **ausschließlich in Deutschland / der EU** verarbeitet. Eine Übermittlung in ein Drittland findet **nicht** statt.

### Wie lange speichern wir Ihre Daten?

Ihre Daten werden für die Dauer des Beschäftigungsverhältnisses und darüber hinaus im Rahmen der **gesetzlichen (arbeits-, steuer- und sozialrechtlichen) Aufbewahrungsfristen** gespeichert und anschließend gelöscht.

- **Aufbewahrungsfrist:** **[AUSFUELLEN: konkrete Fristen — vom Träger/DSB festzulegen ]**

### Ihre Rechte

Sie haben das Recht auf **Auskunft** (Art. 15), **Berichtigung** (Art. 16), **Löschung** (Art. 17), **Einschränkung** (Art. 18), **Widerspruch** (Art. 21) sowie das Recht auf **Beschwerde bei der Aufsichtsbehörde**.

!!! note "Datenübertragbarkeit (Art. 20 DSGVO)"
    Soweit Beschäftigtendaten zur **Durchführung des Arbeitsvertrags** (Art. 6 Abs. 1 lit. b DSGVO) automatisiert verarbeitet werden, besteht ein **Recht auf Datenübertragbarkeit** (Art. 20 DSGVO). Für Verarbeitungen aufgrund gesetzlicher Pflichten (lit. c) gilt dies nicht.

!!! info "Keine automatisierte Entscheidungsfindung"
    Es findet **keine automatisierte Entscheidungsfindung einschließlich Profiling** im Sinne von **Art. 22 DSGVO** statt.

!!! tip "Aufsichtsbehörde"
    **Berliner Beauftragte für Datenschutz und Informationsfreiheit (BlnBDI)** (Kontaktdaten und Meldewege über die Website der Behörde). — **[AUSFUELLEN: ggf. aktuelle Anschrift/Website der BlnBDI ergänzen ]**

Zur Ausübung Ihrer Rechte wenden Sie sich an: **[AUSFUELLEN: Kontaktstelle beim Träger / DSB ]**

### Müssen Sie diese Daten bereitstellen?

Die Verarbeitung der genannten Beschäftigtendaten ist zur **Durchführung des Beschäftigungsverhältnisses** und zur Erfüllung arbeits-, steuer- und sozialrechtlicher Pflichten **erforderlich**. Ohne diese Daten kann das Beschäftigungsverhältnis nicht ordnungsgemäß durchgeführt werden.

---

**Ausgehändigt am:** **[AUSFUELLEN: Datum ]** — **Empfang bestätigt (Name/Unterschrift):** **[AUSFUELLEN ]**

---

## Freigabe des Gesamtdokuments

| Rolle | Name | Datum | Unterschrift |
|-------|------|-------|--------------|
| **Verantwortlicher (Träger)** | **[AUSFUELLEN ]** | **[AUSFUELLEN ]** | **[AUSFUELLEN ]** |
| **Datenschutzbeauftragte(r)** | **[AUSFUELLEN ]** | **[AUSFUELLEN ]** | **[AUSFUELLEN ]** |

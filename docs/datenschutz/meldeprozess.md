# Meldeprozess bei Datenschutzverletzungen (Art. 33/34)

!!! abstract "Ausfüllbare Vorlage"
    **Dokumenttyp:** Meldeprozess / Incident-Response-Plan bei Verletzungen des Schutzes personenbezogener Daten (Art. 33 & Art. 34 DSGVO)
    **Verarbeitungstätigkeit:** Leistungsnachweis & Abrechnung Team TBEW (Therapeutisch Betreutes Einzelwohnen)
    **Stand / Version:** **[AUSFUELLEN: Versions-Nr. + Datum, z. B. 1.0 / 2026-__-__ ]**
    **Verantwortlich für dieses Dokument:** **[AUSFUELLEN: Name, Funktion beim Träger ]**
    **Freigabe:** **[AUSFUELLEN: Datum + Unterschrift Träger und DSB ]**

    Dies ist ein **Template**. Die technisch/betrieblichen Felder (Erkennungssignale, Sofortmaßnahmen,
    Meldekette, vorhandene Überwachung) sind aus dem verifizierten Systemstand **vorausgefüllt**. Alle
    mit **[AUSFUELLEN: … ]** markierten Felder – insbesondere **Personen, Kontaktdaten und Behörden-Adressen** –
    entscheidet und ergänzt der **Träger (Verantwortlicher) gemeinsam mit der/dem
    Datenschutzbeauftragten (DSB)**. Suchen Sie im Dokument nach dem Token `[AUSFUELLEN`, um alle
    offenen Punkte zu finden.

!!! danger "Voraussetzung vor dem Echtbetrieb"
    Das System befindet sich derzeit im **Prototyp-Stadium mit ausschließlich fiktiven Demodaten**.
    Dieser Meldeprozess ist – zusammen mit den übrigen Pflichtdokumenten – **vor dem ersten echten
    Klientendatensatz** zu vervollständigen, freizugeben und zu unterzeichnen. Ohne festgelegte
    Meldekette und benannte Kontaktpersonen ist die **72-Stunden-Frist des Art. 33 DSGVO nicht
    einhaltbar**.

---

## 0. Zweck und Anwendungsbereich

Dieser Plan regelt, **wie eine Verletzung des Schutzes personenbezogener Daten** ("Datenpanne")
im Betrieb der Leistungsnachweis-Anwendung des Teams TBEW **erkannt, eingedämmt, bewertet,
gemeldet und dokumentiert** wird. Er setzt die Pflichten aus **Art. 33 DSGVO** (Meldung an die
Aufsichtsbehörde binnen 72 Stunden) und **Art. 34 DSGVO** (Benachrichtigung der betroffenen
Personen) um.

!!! warning "Besonderer Kontext: Art.-9-Daten"
    In der Anwendung werden **besondere Kategorien personenbezogener Daten nach Art. 9 DSGVO**
    verarbeitet (Sozial- und Gesundheitsbezug der Eingliederungshilfe, u. a. Hilfebedarfsgruppen,
    Leistungsverläufe, Abwesenheitsart „Krank" von Beschäftigten). Bei Vorfällen mit solchen Daten
    ist die Schwelle zur Meldepflicht **regelmäßig überschritten**, und eine Benachrichtigung der
    Betroffenen nach Art. 34 ist **häufig einschlägig**. Im Zweifel ist zugunsten der Meldung zu
    entscheiden.

---

## 1. Was ist eine meldepflichtige Verletzung?

Eine **Verletzung des Schutzes personenbezogener Daten** (Art. 4 Nr. 12 DSGVO) ist jede
Verletzung der Sicherheit, die – unbeabsichtigt oder unrechtmäßig – zur **Vernichtung, zum
Verlust, zur Veränderung oder zur unbefugten Offenlegung von bzw. zum unbefugten Zugang zu**
personenbezogenen Daten führt. Betroffen sein können drei Schutzziele:

| Schutzziel | Bedeutung | Beispiele im Kontext dieser Anwendung |
|------------|-----------|----------------------------------------|
| **Vertraulichkeit** | Unbefugte erhalten Kenntnis / Zugriff | Unbefugter Login in ein Benutzerkonto; Datenabfluss (Export/Kopie von Klienten- oder Mitarbeiterdaten); Fehlversand (z. B. Abrechnung/Export an falschen Empfänger); Diebstahl eines Endgeräts mit aktiver Sitzung; **Verlust oder Kompromittierung des Backup-Entschlüsselungs­schlüssels (age-Privatschlüssel)** |
| **Integrität** | Daten werden unbefugt verändert / verfälscht | Manipulation von Leistungs-, Arbeitszeit- oder Kassendaten; unbefugte Änderungen an Klientenstammdaten; Ransomware-/Schadsoftware-Befall mit Datenveränderung |
| **Verfügbarkeit** | Daten sind (temporär oder dauerhaft) nicht mehr erreichbar | Längerer Ausfall des vServers ohne funktionierendes Backup; versehentliche oder böswillige Löschung von Datensätzen; **fehlgeschlagene Wiederherstellung** (Backup nicht lesbar / Schlüssel weg) |

!!! note "Auch Verfügbarkeitsverlust ist eine meldepflichtige Panne"
    Ein längerer Ausfall oder Datenverlust ist **nicht** nur ein Betriebsproblem, sondern kann eine
    meldepflichtige Datenpanne sein – etwa wenn dadurch die Leistungsdokumentation nicht mehr
    verfügbar ist und Rechte der Betroffenen (z. B. Nachweis erbrachter Leistungen) berührt werden.

**Nicht** jede Störung ist eine meldepflichtige Verletzung. Ein abgewehrter Angriff (z. B. eine
django-axes-Sperre nach Fehlversuchen ohne erfolgreichen Login) oder ein kurzer Ausfall ohne
Datenverlust ist grundsätzlich **kein** meldepflichtiger Vorfall – ist aber als **Signal** zu
bewerten (siehe Abschnitt 2) und im Zweifel zu dokumentieren.

---

## 2. Erkennung – Signale und vorhandene Überwachung

!!! danger "Ohne Monitoring ist die 72-Stunden-Frist gefährdet"
    Die 72-Stunden-Frist des Art. 33 beginnt, sobald der Verantwortliche von der Verletzung
    **Kenntnis erlangt**. Wird ein Vorfall nicht bemerkt, läuft die Frist faktisch ins Leere und die
    Meldung erfolgt zu spät. Die kontinuierliche Beobachtung der folgenden Signale ist deshalb
    sicherheitskritisch.

### 2.1 Technische und organisatorische Signale

| Signal | Quelle / Mechanismus | Mögliche Bedeutung |
|--------|----------------------|--------------------|
| **Häufung von axes-Lockouts** | Brute-Force-Sperre (django-axes) | Gezielter Angriff auf Konten; Vorstufe zu unbefugtem Login |
| **Login-Anomalien** | Änderungsprotokoll (django-auditlog), Login-Zeitpunkte/Muster | Erfolgreicher unbefugter Zugriff, kompromittierte Zugangsdaten, umgangene 2FA |
| **Unerwartete Datenänderungen** | Lückenloses Änderungsprotokoll (wer/wann/was) | Integritätsverletzung, Innentäter, kompromittiertes Konto |
| **/healthz-Ausfall** | Uptime-Monitoring auf den Health-Endpunkt | Ausfall der Anwendung / des Servers → Verfügbarkeitsverletzung |
| **Ausbleibender Backup-Ping** | Dead-Man's-Switch-Alarm des Backup-Jobs | Backups laufen nicht mehr → Verfügbarkeits-/Wiederherstellungsrisiko |
| **Fehlgeschlagener Restore-Test** | Turnusmäßiger Wiederherstellungstest | Backups unbrauchbar; drohender endgültiger Datenverlust |
| **Meldung durch Mitarbeitende** | Interner Hinweis (Fehlversand, verlorenes Gerät, verdächtige E-Mail, ungewöhnliches Systemverhalten) | Jede Art von Vorfall – oft die schnellste Erkennungsquelle |
| **Hinweis von außen** | STRATO/Hoster-Benachrichtigung, Betroffene, Dritte | Vorfall auf Infrastruktur-Ebene, Datenleck-Meldung |

### 2.2 Vorhandene Überwachung (verifizierter Stand)

- **Uptime-Monitoring** auf den `/healthz`-Endpunkt (Erkennung von Ausfällen).
- **Dead-Man's-Switch-Alarm** für den verschlüsselten Offsite-Backup-Job (Alarm bei ausbleibendem Ping).
- **Container-Healthcheck** (non-root-Betrieb).
- **Brute-Force-Sperre** (django-axes) mit Lockout-Ereignissen.
- **Lückenloses Änderungsprotokoll** (django-auditlog): protokolliert **Anlegen, Ändern, Löschen** inkl. Urheber und Zeitpunkt.

!!! warning "Bekannte Erkennungslücke: keine Protokollierung LESENDER Zugriffe"
    Das Änderungsprotokoll erfasst **nur schreibende Vorgänge** (Anlegen/Ändern/Löschen), **nicht das
    reine Lesen** von Datensätzen. Ein reiner **Auslese-/Einsichtnahme-Vorfall** (unbefugtes Ansehen
    ohne Veränderung) ist daher technisch **nur eingeschränkt nachweisbar**. Bei Verdacht auf einen
    solchen Vorfall ist die Bewertung entsprechend **vorsichtig** (tendenziell zugunsten der Meldung)
    vorzunehmen. Die Ergänzung einer Lesezugriffs-Protokollierung ist **geplant** und sollte zur
    Schließung dieser Lücke priorisiert werden.

**Zu benennen:** **[AUSFUELLEN: Wer erhält die Monitoring-/Alarm-Benachrichtigungen (E-Mail/Telefon)? Innerhalb welcher Zeit wird darauf reagiert (auch nachts/am Wochenende)? Vertretungsregelung? ]**

---

## 3. Sofortmaßnahmen (Eindämmung & Beweissicherung)

Bei Verdacht auf eine Verletzung sind **unverzüglich** – parallel zur Alarmierung der Meldekette
(Abschnitt 5) – folgende Sofortmaßnahmen zu treffen. Ziel: **Schaden begrenzen, ohne Beweise zu
vernichten.**

1. **Eindämmen / Ausbreitung stoppen**
   - Betroffene Zugänge/Konten **sofort sperren** bzw. Passwörter zurücksetzen; bei Verdacht auf
     kompromittierte Zugangsdaten **2FA-Geräte neu registrieren**.
   - Bei aktivem unbefugtem Zugriff ggf. **externe Erreichbarkeit einschränken** (z. B. Anwendung
     temporär offline nehmen) – Abwägung mit dem dadurch entstehenden Verfügbarkeitsverlust.
   - Bei Verdacht auf Kompromittierung des **Backup-Schlüssels**: betroffenen age-Schlüssel als
     kompromittiert behandeln, **neues Schlüsselpaar** erzeugen, Backups neu verschlüsseln, alten
     Schlüssel/alte Backups sicher außer Betrieb nehmen.
2. **Beweise und Logs sichern**
   - **Vor** Änderungen/Neustarts: relevante Logs sichern (Anwendungslog, django-auditlog-Einträge,
     django-axes-Ereignisse, Reverse-Proxy-/Server-Logs, Backup-Job-Logs). Kopien an einen sicheren,
     unveränderbaren Ort legen.
   - Zeitstempel, Konten, IP-Adressen, betroffene Datensätze/Tabellen notieren.
   - **Keine** vorschnelle Löschung oder Überschreibung; Systemzustand möglichst einfrieren, soweit
     mit der Eindämmung vereinbar.
3. **Wiederherstellung vorbereiten (bei Verfügbarkeitsvorfällen)**
   - Integrität der **verschlüsselten Offsite-Backups (STRATO HiDrive)** prüfen; getesteten
     **Restore-Prozess** anstoßen. Wiederherstellungsablauf siehe interne Dokumentation
     (`docs/sicherheit/backup-restore.md`, `docs/sicherheit/wiederherstellung.md`).
4. **Erste Fakten festhalten**
   - Vorfall unverzüglich im **Vorfall-Meldebogen** (Abschnitt 7) beginnen – insbesondere
     **Zeitpunkt der Kenntnis durch den Betreiber** und **Zeitpunkt der Unterrichtung des Trägers**
     (Letzterer = Start der 72-h-Frist, siehe Abschnitt 5).

!!! tip "Notfallzugang / Break-Glass"
    Für den Fall, dass reguläre Zugänge gesperrt oder nicht verfügbar sind, existiert ein
    **Break-Glass-Konto** (2FA-Pflicht). Der **Notfallzugang beim Träger** (offline hinterlegte
    Zugangs-/Wiederherstellungsinformationen, u. a. für den Fall des Ausfalls des Einzelbetreibers –
    „Bus-Faktor 1") ist zu hinterlegen: **[AUSFUELLEN: Wo liegen Break-Glass-/Notfallunterlagen, wer beim Träger hat Zugriff? ]**

---

## 4. Bewertung des Risikos für die Rechte der Betroffenen

Nach der Eindämmung bewertet die/der **DSB gemeinsam mit dem Träger** das **Risiko für die Rechte
und Freiheiten** der betroffenen Personen. Das Ergebnis entscheidet über Meldung (Art. 33) und
Benachrichtigung (Art. 34).

**Bewertungskriterien:** Art und Sensibilität der Daten (Art.-9-Daten?), Umfang/Anzahl der
Betroffenen, Identifizierbarkeit, mögliche Folgen (Diskriminierung, Stigmatisierung, finanzielle/
soziale Nachteile), Dauerhaftigkeit des Schadens, Wahrscheinlichkeit des tatsächlichen Missbrauchs
(z. B. waren die Daten **verschlüsselt**?).

| Ampel | Risikoeinschätzung | Rechtsfolge (Regelfall) |
|:-----:|--------------------|--------------------------|
| 🟢 **Niedrig** | Kein oder nur unwahrscheinliches Risiko für Rechte/Freiheiten (z. B. abgewehrter Angriff ohne Zugriff; Verlust ausschließlich **wirksam verschlüsselter** Daten, Schlüssel sicher) | **Keine** Meldung an die Aufsichtsbehörde erforderlich – aber **interne Dokumentation Pflicht** (Art. 33 Abs. 5) |
| 🟡 **Mittel** | Risiko für Rechte/Freiheiten besteht | **Meldung an BlnBDI binnen 72 h** (Art. 33). Benachrichtigung der Betroffenen (Art. 34) prüfen |
| 🔴 **Hoch** | **Hohes** Risiko (bei Art.-9-Daten regelmäßig anzunehmen: Sozial-/Gesundheitsdaten der Eingliederungshilfe) | **Meldung an BlnBDI binnen 72 h** **und** **unverzügliche Benachrichtigung der Betroffenen** (Art. 34) |

!!! warning "Faustregel für diese Anwendung"
    Da überwiegend **Art.-9-Daten** verarbeitet werden, ist bei einem **Vertraulichkeits- oder
    Integritätsvorfall mit tatsächlichem unbefugtem Zugriff/Abfluss** von einem **hohen Risiko**
    auszugehen, sofern nicht konkrete Umstände (z. B. nachweislich wirksame Verschlüsselung,
    Schlüssel nicht kompromittiert) das Risiko klar entkräften. Die **Begründung** der Einstufung ist
    im Meldebogen zu dokumentieren.

!!! note "Ausnahmen von der Benachrichtigungspflicht (Art. 34 Abs. 3)"
    Eine Benachrichtigung der Betroffenen kann entbehrlich sein, wenn (a) die Daten durch geeignete
    Maßnahmen – insbesondere **Verschlüsselung** – für Unbefugte **unzugänglich** waren, (b) durch
    Folgemaßnahmen das hohe Risiko **abgewendet** wurde, oder (c) sie einen **unverhältnismäßigen
    Aufwand** bedeuten würde (dann öffentliche Bekanntmachung). Ob eine Ausnahme greift, entscheidet
    **DSB/Träger** und dokumentiert dies.

---

## 5. Meldeweg & Zuständigkeiten

Klare, fristgerechte **Meldekette** – jede Stufe ohne schuldhaftes Zögern („unverzüglich"):

```
① Betreiber erkennt den Vorfall
        │  unverzüglich, ohne schuldhaftes Zögern
        ▼
② Meldung an die/den Datenschutzbeauftragte(n) (DSB) des Trägers
        │  DSB + Träger bewerten das Risiko (Abschnitt 4)
        ▼
③ Träger (Verantwortlicher) entscheidet über die Meldung
        │  bei Risiko: Meldung an BlnBDI über Online-Formular  ── binnen 72 h ab Kenntnis ──▶  Aufsichtsbehörde
        │
        ▼
④ bei hohem Risiko: unverzügliche Benachrichtigung der betroffenen Personen (Art. 34)
```

!!! note "Wer meldet formal an die Behörde?"
    Meldepflichtiger nach Art. 33 ist der **Verantwortliche (Träger)**. Der **Betreiber** (bzw. der
    Auftragsverarbeiter) ist verpflichtet, den Verantwortlichen **unverzüglich** zu unterrichten
    (Art. 33 Abs. 2), und unterstützt bei der Aufklärung. Die formale Meldung an die BlnBDI erfolgt
    durch den **Träger/DSB**.

**Verantwortliche Personen und Kontakte (auszufüllen und aktuell zu halten):**

| Rolle | Person / Stelle | Erreichbarkeit (Tel./E-Mail, auch außerhalb der Bürozeiten) |
|-------|-----------------|-------------------------------------------------------------|
| Erkennung / Betrieb / technische Sofortmaßnahmen | Mirko Richter (Betreiber), Stillerzeile 29, 12587 Berlin | **[AUSFUELLEN: Telefon / E-Mail, Notfallnummer ]** |
| Datenschutzbeauftragte(r) (DSB) | **[AUSFUELLEN: Name ]** | **[AUSFUELLEN: Telefon / E-Mail ]** |
| Verantwortlicher / Entscheidung Meldung (Träger) | **[AUSFUELLEN: Name, Funktion ]** | **[AUSFUELLEN: Telefon / E-Mail ]** |
| Vertretung / Eskalation (bei Nichterreichbarkeit) | **[AUSFUELLEN: Name ]** | **[AUSFUELLEN: Telefon / E-Mail ]** |

**Zuständige Aufsichtsbehörde:**

| Feld | Eintrag |
|------|---------|
| Behörde | Berliner Beauftragte für Datenschutz und Informationsfreiheit (**BlnBDI**) |
| Meldeweg | **Online-Meldeformular für Datenpannen** der BlnBDI |
| Formular-URL / Zugang | **[AUSFUELLEN: aktuelle URL des Online-Meldeformulars der BlnBDI eintragen und vorab prüfen ]** |
| Anschrift / weitere Kontaktdaten | **[AUSFUELLEN: postalische Anschrift, Telefon der BlnBDI eintragen ]** |

!!! danger "72-Stunden-Frist"
    Die Meldung an die BlnBDI hat **binnen 72 Stunden** ab **Kenntniserlangung** zu erfolgen. Ist die
    Meldung nicht binnen 72 Stunden möglich, ist sie **mit Begründung der Verzögerung** nachzuholen
    (Art. 33 Abs. 1 Satz 2). Liegen noch nicht alle Informationen vor, ist eine **Erstmeldung**
    zulässig; fehlende Angaben werden **schrittweise nachgereicht** (Art. 33 Abs. 4).

**Pflichtinhalte der Meldung nach Art. 33 Abs. 3** (im Meldebogen, Abschnitt 7, vorstrukturiert):
Art der Verletzung; Kategorien und ungefähre Zahl der betroffenen Personen und Datensätze; Name
und Kontaktdaten des DSB; wahrscheinliche Folgen; ergriffene/vorgeschlagene Maßnahmen.

**Pflichtinhalte der Benachrichtigung der Betroffenen nach Art. 34 Abs. 2** (bei hohem Risiko,
Abschnitt 7.6): Die Benachrichtigung erfolgt **in klarer und einfacher Sprache** und enthält
mindestens **Art der Verletzung**, **Name und Kontaktdaten des DSB** (bzw. weiterer Auskunftsstelle),
**wahrscheinliche Folgen** der Verletzung sowie **ergriffene/vorgeschlagene Maßnahmen** – inkl.
Empfehlungen zur Minderung nachteiliger Folgen für die Betroffenen.

!!! note "Fristbeginn: Wessen Kenntnis zählt?"
    Die 72-Stunden-Frist des Art. 33 knüpft an die Kenntnis des **Verantwortlichen (Träger)** an.
    Erlangt der **Betreiber/Auftragsverarbeiter** zuerst Kenntnis, löst dies **nicht** direkt die
    Frist aus, verpflichtet ihn aber, den Träger **unverzüglich** zu unterrichten (Art. 33 Abs. 2);
    die 72-h-Frist des Trägers läuft ab dessen Unterrichtung/Kenntnis. **Beide Zeitpunkte** (Kenntnis
    Betreiber, Unterrichtung/Kenntnis Träger) sind im Meldebogen (Abschnitt 7.1) festzuhalten. Wird
    der Betrieb über einen **Unterauftragsverarbeiter** (STRATO) berührt, hat dieser den Betreiber zu
    benachrichtigen, der wiederum den Träger unterrichtet.

---

## 6. Dokumentationspflicht (Art. 33 Abs. 5)

!!! warning "Auch bei Nicht-Meldung dokumentieren"
    **Jede** Verletzung des Schutzes personenbezogener Daten ist zu **dokumentieren** – **auch dann,
    wenn keine Meldung an die Aufsichtsbehörde erfolgt** (z. B. Einstufung „niedriges Risiko"). Die
    Dokumentation muss die Aufsichtsbehörde in die Lage versetzen, die Einhaltung des Art. 33 zu
    überprüfen. Fehlende Dokumentation ist selbst ein **bußgeldbewehrter Verstoß**.

Zu dokumentieren sind mindestens: **Fakten** der Verletzung, ihre **Auswirkungen**, die
**ergriffenen Abhilfemaßnahmen** sowie – bei Nicht-Meldung – die **Begründung der Entscheidung**.

**Ablage / Register:**

| Feld | Eintrag |
|------|---------|
| Ort der Vorfalldokumentation (Datenpannen-Register) | **[AUSFUELLEN: wo wird der Meldebogen abgelegt (Ordner/System), wer führt das Register ]** |
| Aufbewahrungsdauer der Vorfalldokumentation | **[AUSFUELLEN: Frist festlegen (Träger/DSB) ]** |
| Zugriffsberechtigte auf das Register | **[AUSFUELLEN: Personenkreis ]** |

---

## 7. Vorfall-Meldebogen (ausfüllbar)

!!! tip "Nutzung"
    Für **jeden** Vorfall (auch Verdachtsfälle und nicht gemeldete Fälle) eine Kopie dieses Bogens
    ausfüllen und im Datenpannen-Register ablegen. Der Bogen deckt die Pflichtangaben nach Art. 33
    Abs. 3 und die Dokumentationspflicht nach Art. 33 Abs. 5 ab.

### 7.1 Vorfallkopf

| Feld | Eintrag |
|------|---------|
| Laufende Vorfall-Nr. | **[AUSFUELLEN]** |
| Zeitpunkt der Kenntnis durch den **Betreiber** (Datum + Uhrzeit) | **[AUSFUELLEN]** |
| **Zeitpunkt der Unterrichtung/Kenntnis des Trägers** (Datum + Uhrzeit) – **Start der 72-h-Frist** | **[AUSFUELLEN]** |
| Ablauf der 72-h-Frist (Kenntnis Träger + 72 h) | **[AUSFUELLEN]** |
| Zeitpunkt des Vorfalls (soweit bekannt) | **[AUSFUELLEN]** |
| Wer hat den Vorfall erkannt / gemeldet? | **[AUSFUELLEN]** |
| Erkennungsquelle (axes-Lockout / Login-Anomalie / /healthz / Backup-Ping / interne Meldung / extern …) | **[AUSFUELLEN]** |
| Bearbeiter des Vorfalls | **[AUSFUELLEN]** |

### 7.2 Beschreibung und Umfang

| Feld | Eintrag |
|------|---------|
| Beschreibung der Verletzung (was ist passiert?) | **[AUSFUELLEN]** |
| Betroffenes Schutzziel (Vertraulichkeit / Integrität / Verfügbarkeit) | **[AUSFUELLEN]** |
| Betroffene Datenkategorien (z. B. Klientenstammdaten, Leistungsverläufe, Arbeitszeit/Abwesenheit inkl. „Krank", Kassendaten, Mitarbeiterdaten) | **[AUSFUELLEN]** |
| Handelt es sich um **besondere Kategorien (Art. 9)**? | **[AUSFUELLEN: ja/nein – bei Sozial-/Gesundheitsdaten i. d. R. ja ]** |
| Kategorien betroffener Personen (Klient*innen / Beschäftigte) | **[AUSFUELLEN]** |
| Ungefähre **Zahl** betroffener Personen | **[AUSFUELLEN]** |
| Ungefähre **Zahl** betroffener Datensätze | **[AUSFUELLEN]** |

### 7.3 Folgen und Maßnahmen

| Feld | Eintrag |
|------|---------|
| Wahrscheinliche Folgen für die Betroffenen | **[AUSFUELLEN]** |
| Sofortmaßnahmen (Eindämmung, Sperrungen, Beweissicherung) | **[AUSFUELLEN]** |
| Waren die Daten wirksam **verschlüsselt** / anderweitig geschützt? | **[AUSFUELLEN]** |
| Weitere/geplante Abhilfe- und Präventionsmaßnahmen | **[AUSFUELLEN]** |

### 7.4 Risikobewertung

| Feld | Eintrag |
|------|---------|
| Ampel-Einstufung (🟢 niedrig / 🟡 mittel / 🔴 hoch) | **[AUSFUELLEN]** |
| **Begründung** der Einstufung | **[AUSFUELLEN]** |
| Bewertung durchgeführt von (DSB/Träger) am | **[AUSFUELLEN]** |

### 7.5 Meldung an die Aufsichtsbehörde (Art. 33)

| Feld | Eintrag |
|------|---------|
| Meldung an BlnBDI erforderlich? | **[AUSFUELLEN: ja/nein]** |
| **Begründung** (insbesondere bei „nein" – Pflicht nach Art. 33 Abs. 5) | **[AUSFUELLEN]** |
| Datum/Uhrzeit der Meldung | **[AUSFUELLEN]** |
| Fristgerecht (≤ 72 h)? – falls nein: Begründung der Verzögerung | **[AUSFUELLEN]** |
| Art der Meldung (Erstmeldung / Nachmeldung) | **[AUSFUELLEN]** |
| Aktenzeichen / Referenz der Behörde | **[AUSFUELLEN]** |

### 7.6 Benachrichtigung der Betroffenen (Art. 34)

| Feld | Eintrag |
|------|---------|
| Benachrichtigung der Betroffenen erforderlich? | **[AUSFUELLEN: ja/nein]** |
| **Begründung** (bei „nein": ggf. Ausnahme Art. 34 Abs. 3 benennen) | **[AUSFUELLEN]** |
| Datum der Benachrichtigung | **[AUSFUELLEN]** |
| Form der Benachrichtigung (individuell / öffentlich, Art. 34 Abs. 3 lit. c) | **[AUSFUELLEN]** |
| Pflichtinhalte nach Art. 34 Abs. 2 enthalten? (Art der Verletzung, DSB-Kontakt, wahrscheinliche Folgen, Maßnahmen – in klarer, einfacher Sprache) | **[AUSFUELLEN: ja/nein]** |
| Inhalt / verwendetes Schreiben (Referenz) | **[AUSFUELLEN]** |

### 7.7 Abschluss

| Feld | Eintrag |
|------|---------|
| Vorfall abgeschlossen am | **[AUSFUELLEN]** |
| Lessons Learned / abgeleitete Verbesserungen | **[AUSFUELLEN]** |
| Ablage im Datenpannen-Register (Ort/Referenz) | **[AUSFUELLEN]** |
| Unterschrift/Freigabe (DSB und Träger) | **[AUSFUELLEN]** |

---

## 8. Verweise

- Technische Absicherung (TOM): `docs/sicherheit/haertung.md`, `docs/sicherheit/rls.md`
- Backups & Wiederherstellung: `docs/sicherheit/backup-restore.md`, `docs/sicherheit/backups-loeschkonzept.md`, `docs/sicherheit/wiederherstellung.md`
- Deployment / Betrieb: `docs/sicherheit/deployment.md`
- Datenschutz-Überblick & Verzeichnis: `docs/sicherheit/datenschutz.md`, `docs/datenschutz/vvt.md`

!!! note "Regelmäßige Überprüfung"
    Dieser Meldeprozess ist mindestens **jährlich** sowie **nach jedem Vorfall** auf Aktualität zu
    prüfen (Kontaktdaten, Behörden-URL, Monitoring-Umfang). Nächste Überprüfung: **[AUSFUELLEN: Datum ]**

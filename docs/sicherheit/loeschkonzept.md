# Aufbewahrungsfristen & Anonymisierung

Personenbezogene Daten dürfen nur so lange gespeichert werden, wie es einen Zweck dafür gibt (**Speicherbegrenzung**, Art. 5 Abs. 1 lit. e DSGVO), und sind anschließend zu löschen (**Recht auf Löschung**, Art. 17 DSGVO; im Sozialrecht **§ 84 SGB X**). Weil in der Eingliederungs- und Jugendhilfe aber gleichzeitig **lange Aufbewahrungspflichten** aus Steuer-, Handels- und Fachrecht gelten, ist „einfach löschen“ selten der richtige Weg. Diese Seite zeigt dir, wie die App dieses Spannungsfeld auflöst: Sie kennt die Fristen als pflegbare Daten, listet dir die **fälligen** beendeten Betreuungen auf und führt die Löschung **review-gestützt in zwei Stufen** aus – nichts läuft automatisch, und das Abrechnungsgerüst bleibt als anonymes Skelett erhalten.

Du erreichst die Seite als **Leitung** über den Menüpunkt **Löschfristen** (Tooltip: „Aufbewahrungsfristen & Anonymisierung"). Die Überschrift lautet dort **„Löschfristen & Anonymisierung"**.

!!! danger "Irreversibel – deshalb zweistufig und mit Bestätigung"
    Eine ausgeführte Anonymisierung lässt sich **nicht rückgängig** machen. Darum gibt es keinen Ein-Klick-Löschbutton: Du siehst erst einen **Trockenlauf** (was würde passieren) und musst die Ausführung anschließend mit dem **Nachnamen der Klient*in** ausdrücklich bestätigen. So gibt ein Mensch (Leitung/DSB) die Freigabe, nicht die Automatik.

---

## Die Fristen sind Daten, keine fest verdrahteten Zahlen

Jede Datenkategorie hat eine eigene **Aufbewahrungsregel** – ein Datensatz mit Kategorie, Dauer in Jahren, Rechtsgrundlage und einem Hinweis. Die Werte kommen per Migration als Vorschlag in die Datenbank; die **Datenschutzbeauftragte** kann sie je Instanz anpassen oder eine Regel deaktivieren, **ohne dass programmiert werden muss**. Ist zu einer Kategorie keine aktive Regel gepflegt, greift ein konservativer Fallback im Code.

Die App kennt **acht Kategorien** (Rechtsstand Juli 2026):

| Kategorie | Frist | Rechtsgrundlage | Hinweis |
|-----------|-------|-----------------|---------|
| **Abrechnung & Buchungsbelege** | 8 Jahre | § 147 Abs. 3 i. V. m. Abs. 1 Nr. 4 AO; § 257 HGB; § 14b UStG | seit BEG IV (01.01.2025) 8 statt 10 J.; Frist ab Schluss des Kalenderjahres |
| **Leistungsnachweise** (Abrechnungsgrundlage) | 8 Jahre | § 147 AO (als Buchungsbeleg) | im Zweifel an die Fachakte koppeln, nicht vor dem Leistungsfall löschen |
| **Kassenbuch & Zählprotokolle** | 10 Jahre | § 147 Abs. 1 Nr. 1 AO (h. M.) | Kassenbuch konservativ 10 J.; Einzelbelege/Protokolle wären 8 J. |
| **Fachakte Eingliederungshilfe (SGB IX)** | 10 Jahre | abgeleitet: Verjährung/Nachweispflicht + Art. 17 DSGVO | nicht spezialgesetzlich fixiert; bei Haftungsrisiko bis 30 J. (§ 199 BGB) |
| **Fachakte Jugendhilfe (SGB VIII)** | 70 Jahre | § 9b Abs. 2 SGB VIII (seit 01.07.2025) | 70 J. nach Vollendung des 30. Lj.; für freie Träger nur bei Vereinbarung |
| **Dokumentation stationär (WTG Berlin)** | 5 Jahre | § 22 Abs. 4 WTG Berlin | einrichtungsseitige Doku; NICHT mit § 34 (10 J., nur Aufsichtsbehörde) verwechseln |
| **Abgelegte Dokumente** | 10 Jahre | je nach Inhalt (Bescheide/Verträge) – Fachakte-analog | Default an die längste zugeordnete Fachfrist koppeln |
| **Arbeitszeit & Dienstplan** | 2 Jahre | § 16 Abs. 2 ArbZG; § 17 Abs. 1 MiLoG | Arbeitszeitnachweise 2 J.; im Heimkontext teils 5 J. |

Diese Tabelle findest du auf der Löschfristen-Seite im Panel **„Aufbewahrungsregeln"** wieder, inaktive Regeln erscheinen dort ausgegraut.

!!! warning "Fristen mit Fachjurist*in gegenprüfen"
    Die Werte sind **recherchierte Vorschläge**, keine verbindliche Rechtsberatung. Für die belastbare Endfassung sind sie mit Träger, Kostenträger und Datenschutzbeauftragten abzustimmen. Besonders **§ 9b SGB VIII (70 Jahre, Jugendhilfe)** greift für freie Träger nur bei entsprechender Leistungs-/Entgeltvereinbarung. Wo lange Pflichten bestehen, gilt „Sperren statt Löschen" (§ 84 SGB X, Art. 18 DSGVO).

---

## Wann eine Betreuung fällig wird

Eine Frist startet erst, wenn die Betreuung wirklich beendet ist. Die App leitet das **Betreuungsende** konservativ aus dem **spätesten** belastbaren Datum ab (KÜ-Ende, letzte Leistung, letzter Auszug), damit die Frist nie zu früh anläuft. Ist noch eine **Belegung offen** (kein Auszugsdatum), ist die Person weiter untergebracht – das Ende gilt als unklar und die Betreuung wird **nie** fällig.

Daraus berechnet die App zwei „Frei-ab"-Daten:

| Datum | Bedeutung | Fristbeginn |
|-------|-----------|-------------|
| **Fachdaten frei ab** | ab hier darf die **Fachakte** gelöscht werden | Betreuungsende + Frist *Fachakte EGH* (10 J.) |
| **Voll frei ab** | ab hier darf **zusätzlich** anonymisiert werden | zusätzlich Ende des Kalenderjahres des jüngsten Belegs + Frist *Abrechnung* (8 J.) |

„Voll frei ab" ist immer das **spätere** der beiden Daten – erst wenn auch die steuerrechtliche Abrechnungsfrist abgelaufen ist, darf das Skelett anonymisiert werden.

!!! note "Nur beendete Betreuungen zählen"
    Fällig werden ausschließlich Klient*innen im Status **Beendigung**, deren Ende bekannt ist und die noch **nicht anonymisiert** sind. Eine bereits anonymisierte Person taucht nie wieder als fällig auf.

Die Übersicht zeigt oben drei Kennzahlen (beendete Betreuungen · Fachdaten löschreif · voll anonymisierbar) und darunter eine Tabelle, in der **fällige Betreuungen zuerst** stehen. Je Zeile siehst du Betreuungsende, beide Frei-ab-Daten, den **Bestand an Fachdaten** (Ziele, Berichte, Wirkung, Dokumente, dokumentierte Leistungen) und einen Status-Badge:

| Badge | Bedeutung |
|-------|-----------|
| **läuft** (grün) | Frist noch nicht abgelaufen – nichts zu tun |
| **Fachdaten fällig** (rot) | Fachakte-Frist abgelaufen → Fachdaten-Löschung möglich |
| **voll fällig** (orange) | zusätzlich Abrechnungsfrist abgelaufen → Voll-Anonymisierung möglich |

Nur bei fälligen Zeilen erscheint der Knopf **„Prüfen & anonymisieren"**.

---

## Die zwei Stufen der Löschung

Die App unterscheidet, **wie viel** gelöscht werden darf – je nachdem, welche Frist bereits abgelaufen ist. Die Stufe wird automatisch aus dem Fristen-Status gewählt (voll, sobald auch die Abrechnung frei ist, sonst Fachdaten).

### Stufe 1 – Fachdaten-Löschung

Sobald die **Fachakte-Frist** abgelaufen ist. Die App entfernt die eigentliche Fallakte, das **Abrechnungsgerüst bleibt** (die Abrechnungsfrist läuft ja noch):

- **gelöscht:** Ziele, Berichte, Wirkungseinschätzungen, Termine sowie **Dokumente inkl. der abgelegten Dateien**
- **Gruppen-Teilnahmen gelöst** (die geteilte Gruppe selbst bleibt, nur die Zuordnung geht)
- **Art-9-Freitexte geleert** an den verbleibenden abrechnungsrelevanten Belegen: Dokumentation, Notiz, Unterschrift und Tätigkeit an den Leistungen; Beschreibung/Maßnahmen an Vorkommnissen; Kommentare an Belegungen und Abwesenheiten
- **Auditlog der Fachebene bereinigt**, damit keine Klartext-Altwerte im Änderungsprotokoll zurückbleiben

### Stufe 2 – Voll-Anonymisierung

Sobald **zusätzlich** die Abrechnungsfrist abgelaufen ist. Zusätzlich zu Stufe 1 werden die **Stammdaten pseudonymisiert**:

- Nachname → „**Gelöscht #<ID>**", Vorname/Kürzel/Person-ID/THFD/Kommentar/Kostenträger geleert, Geburtsdatum entfernt
- Freitexte und **Aktenzeichen** an den Bewilligungen geleert
- **Auditlog-Historie** von Klient und Bewilligungen gelöscht
- der **Anonymisierungs-Marker** (`anonymisiert am`) wird gesetzt

!!! tip "Warum der Datensatz nicht ganz verschwindet"
    Die Klient*in wird **anonymisiert, nicht gelöscht**: Leistungszeiten, Monatsfreigaben und Rechnungen verweisen per Schutz-Referenz auf sie. Der Datensatz bleibt als **anonymes Abrechnungsskelett** bestehen – ohne jeden Personenbezug –, damit die Buchhaltung über die steuerrechtliche Frist konsistent bleibt. Das ist gelebte Datensparsamkeit: Klartext weg, Zahlengerüst bleibt.

---

## Eine Betreuung anonymisieren (Schritt für Schritt)

1. Öffne **Löschfristen** und klicke bei einer fälligen Zeile auf **„Prüfen & anonymisieren"**.
2. Die Detailseite zeigt den **Trockenlauf**: die gewählte Stufe, beide Frei-ab-Daten und eine Liste **genau der Aktionen**, die ausgeführt würden. Es wird an dieser Stelle **noch nichts geändert**.
3. Prüfe die Aktionsliste. Sind keine Fachdaten mehr vorhanden, meldet die App das und bietet keinen Ausführen-Knopf an.
4. Gib zur Bestätigung den **Nachnamen** der Klient*in in das Feld ein (Tippschutz – ein falscher oder leerer Name wird abgelehnt).
5. Klick auf **„Jetzt anonymisieren"**. Eine zusätzliche Browser-Rückfrage muss bestätigt werden, dann läuft die Anonymisierung als eine einzige Transaktion.

!!! warning "Nur fällige Betreuungen, nur im eigenen Zugriff"
    Der Server prüft beim Ausführen erneut, ob die Frist wirklich abgelaufen ist – ist sie es nicht, wird abgelehnt („Die Aufbewahrungsfrist ist noch nicht abgelaufen"). Und du kannst ausschließlich Klient*innen deiner **eigenen bzw. geleiteten Teams** bearbeiten (Team-Scoping); ein fremder Zugriff läuft ins Leere.

---

## Zugriff und Datenschutz

!!! warning "Nur die Leitung, streng team-gescopt"
    Die gesamte Löschfristen-Funktion ist der **Leitung** vorbehalten (`services.ist_leitung`); alle anderen Rollen erhalten `HttpResponseForbidden`. Sichtbar und bearbeitbar sind nur Klient*innen aus `services.klienten_fuer(request.user)` – also den eigenen und geleiteten Teams. **Verwaltung und Admin** haben bewusst **keinen** Klientenbezug und sehen hier nichts.

!!! danger "Anonymisierung heißt: wirklich weg"
    Weil die Fachakte **Art-9-Daten** enthält (Gesundheits-/Sozialdaten), reicht es nicht, nur die sichtbaren Felder zu leeren. Die App entfernt darum auch die **Auditlog-Altwerte** der betroffenen Datensätze – sonst überdauerten Name und Tätigkeit als Klartext im Änderungsprotokoll und die Anonymisierung wäre umkehrbar. Erst damit ist sie im Sinne von § 84 SGB X / Art. 17 DSGVO **irreversibel**.

---

## Report und Anonymisierung per Kommandozeile

Für Monitoring und Batch-Betrieb gibt es denselben Ablauf als Management-Command. Der Trockenlauf ist Standard; echt ausgeführt wird nur mit **beiden** Sicherheitsflags.

```
python manage.py loeschfristen                 # Report (nichts wird geändert)
python manage.py loeschfristen --klient 42     # nur eine*n prüfen
python manage.py loeschfristen --apply --ja    # fällige anonymisieren (echt!)
```

| Option | Wirkung |
|--------|---------|
| *(ohne)* | Trockenlauf: listet fällige Betreuungen samt der Aktionen, die ausgeführt würden |
| `--klient <ID>` | beschränkt den Lauf auf eine einzelne Klient*in |
| `--apply` allein | bleibt **Trockenlauf** und weist darauf hin, zusätzlich `--ja` zu setzen |
| `--apply --ja` | führt die Anonymisierung **tatsächlich** aus |

!!! note "Exit-Codes fürs Monitoring"
    Im Trockenlauf endet der Command mit **Exit-Code 2**, sobald fällige Betreuungen vorhanden sind (sonst 0). So kann eine Überwachung ohne jede Änderung erkennen, dass etwas löschreif ist. `--apply --ja` endet regulär mit 0.

---

## Für Neugierige: Technik dahinter

!!! note "Nur zur Nachvollziehbarkeit"
    Dieser Abschnitt dient dem Verständnis; für die Bedienung brauchst du ihn nicht. Die Namen unten entsprechen dem echten Code.

- **Service-Kern:** `nachweis/services_loeschfristen.py`. `frist_jahre(kategorie)` liest die aktive `Aufbewahrungsregel` aus der DB, sonst `_FALLBACK`. `betreuungsende(klient)` liefert das späteste End-/Kontaktdatum (`None`, solange eine Belegung mit `auszug__isnull=True` offen ist). `_abrechnung_stichtag` nimmt das Jahresende des jüngsten Belegs (Freigabe/Leistung). `loeschstatus(klient)` bündelt `fach_frei_ab`, `abrechnung_frei_ab`, `voll_frei_ab` und die Flags `fach_faellig`/`voll_faellig` (nur für `Status.BEENDIGUNG` ohne `anonymisiert_am`). `faellige_klienten()` liefert alle löschreifen Beendeten.
- **Löschung:** `anonymisieren(klient, stufe, apply, heute)` – `@transaction.atomic`, `apply=False` ist Trockenlauf und gibt nur einen `report` mit `aktionen` zurück. Stufe `"fachdaten"` löscht Ziele/Berichte/Wirkung/Termine + `Dokument.delete()` (räumt Dateien mit weg), löst `klient.gruppen.clear()` und leert die Art-9-Freitexte per `update(...)`. Stufe `"voll"` ruft zusätzlich `_pseudonymisiere_stammdaten(klient)` (setzt `nachname="Gelöscht #<pk>"`, leert PII, setzt `anonymisiert_am = timezone.now()` per `save(update_fields=[…])`).
- **Auditlog-Scrub:** `_scrub_auditlog(model, pks)` löscht die `auditlog.models.LogEntry` der betroffenen Objekte über `ContentType.objects.get_for_model`. Fachebene für Dokument/Ziel/Bericht/Wirkungseinschaetzung/Termin/Vorkommnis + Leistung/Belegung; in Stufe „voll" zusätzlich Klient + Bewilligung.
- **Views:** `nachweis/views_loeschfristen.py` → `loeschfristen` (Übersicht, sortiert fällige zuerst), `loeschfristen_klient(pk)` (Trockenlauf-Vorschau, wählt `stufe`), `loeschfristen_anonymisieren` (`@require_POST`; prüft `fach_faellig`, vergleicht `bestaetigung` gegen `klient.nachname` – leerer Soll-Name lehnt immer ab –, ruft `anonymisieren(..., apply=True)`). Alle drei hinter `services.ist_leitung` und `services.klienten_fuer`.
- **Modelle:** `nachweis/models.py` → `AufbewahrungsKategorie` (TextChoices, 8 Werte) und `Aufbewahrungsregel` (`kategorie` unique, `jahre`, `rechtsgrundlage`, `hinweis`, `aktiv`). Der Marker `Klient.anonymisiert_am` ist `editable=False`. Seed der Fristen: Migration `0043_aufbewahrungsregeln_default.py` (idempotent per `get_or_create`).
- **Templates:** `nachweis/templates/nachweis/loeschfristen.html` (KPI-Karten, Tabellen „Beendete Betreuungen" und „Aufbewahrungsregeln") und `loeschfristen_klient.html` (Trockenlauf-Aktionsliste, Bestätigungsformular mit Nachname-Eingabe und `onsubmit`-confirm).
- **CLI:** `nachweis/management/commands/loeschfristen.py` (`--klient`, `--apply`, `--ja`; `raise SystemExit(2)` im Trockenlauf bei Fälligen). URLs: `nachweis:loeschfristen`, `nachweis:loeschfristen_klient`, `nachweis:loeschfristen_anonymisieren`.

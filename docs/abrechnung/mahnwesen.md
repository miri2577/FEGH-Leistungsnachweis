# Mahnwesen, Offene Posten & Storno

Ist eine Rechnung erst einmal an den Kostenträger **gestellt**, beginnt die zweite Hälfte des Abrechnungslaufs: Du behältst den Überblick über **offene Posten**, buchst **Zahlungseingänge** (auch in Teilbeträgen), erinnerst säumige Kostenträger in bis zu **drei Mahnstufen** an die Zahlung und korrigierst eine fehlerhaft gestellte Rechnung **beleghaft per Gutschrift**. Diese Seite erklärt, wie du das im Verwaltungsbereich der App bedienst – von der Offene-Posten-Liste über die Zahlungsbuchung bis zum sauberen Storno – und wie jede Änderung revisionssicher protokolliert wird.

!!! info "Wer arbeitet hier?"
    Offene Posten, Zahlungen, Mahnungen und Storno liegen komplett im **Verwaltungsbereich** und sind nur für die **Verwaltung** (bzw. den technischen Break-Glass-Superuser) sichtbar. Betreuer*innen, Leitung und Admin haben hier keinen Zugriff. Die Verwaltung sieht dabei **ausschließlich Abrechnungsdaten** (Name/Aktenzeichen, Kostenträger, Betrag, Monat, Status) – **keine Tätigkeits-Dokumentation**.

---

## Offene-Posten-Liste

Die **Offene-Posten-Liste** (Menü *Abrechnung → Offene Posten*) ist die zentrale Übersicht über alle **gestellten, noch nicht (voll) bezahlten** Rechnungen. Sie ist die Grundlage des Mahnwesens: Was hier oben steht, ist am dringendsten.

Ein Posten erscheint in der Liste, sobald eine Rechnung den Status **gestellt** hat **und** noch ein offener Betrag > 0 verbleibt. Bezahlte, stornierte und Entwurfs-Rechnungen tauchen nicht auf.

| Spalte | Bedeutung |
|---|---|
| **Rechnung / Empfänger** | Rechnungsnummer und Kostenträger. |
| **offener Betrag** | Rechnungsbetrag minus Summe der gebuchten Zahlungen. |
| **fällig am** | Fälligkeitsdatum (siehe *Fälligkeit* unten). |
| **Tage** | Tage über Fälligkeit. Negativ = noch nicht fällig, positiv = überfällig. |
| **überfällig** | Markierung, sobald das Fälligkeitsdatum überschritten ist. |
| **Mahnstufe** | Höchste bereits versandte Stufe (0 = noch nicht gemahnt). |

Die Liste ist nach **Überfälligkeit absteigend** sortiert – die am längsten überfälligen Rechnungen stehen ganz oben. Im Kopf siehst du die Kennzahlen **Summe offen**, **Summe überfällig** und die **Anzahl überfälliger** Rechnungen.

!!! tip "So arbeitest du die Liste ab"
    Von hier springst du in die jeweilige **Rechnungs-Detailseite**. Dort buchst du Zahlungen und erstellst Mahnungen – beides ist nur an der einzelnen Rechnung möglich, nicht als Sammelaktion.

---

## Zahlungseingänge buchen

Zahlungen buchst du auf der **Detailseite der Rechnung** über das Formular **„Zahlungseingang erfassen“**. Jede Buchung ist eine eigene Zeile (Datum, Betrag, optionale Notiz) – so bleibt der Zahlungsverlauf nachvollziehbar.

| Feld | Bedeutung |
|---|---|
| **Betrag** | Zahlbetrag. Komma oder Punkt sind erlaubt; muss > 0 sein. |
| **Zahlungseingang (Datum)** | Wertstellungs-/Eingangsdatum. Leer = heute. |
| **Notiz** | Freitext, z. B. Verwendungszweck oder Kontoauszugs-Nr. (max. 200 Zeichen). |

### Teilzahlungen

Kostenträger zahlen nicht immer den vollen Betrag auf einmal. Du kannst deshalb **mehrere Teilzahlungen** auf dieselbe Rechnung buchen. Die App summiert alle Zahlungen und zeigt den verbleibenden **offenen Betrag** an. Eine Rückmeldung nennt dir nach jeder Buchung, wie viel noch offen ist.

!!! warning "Keine Überzahlung"
    Ein Zahlbetrag, der den **offenen Betrag übersteigt**, wird **nicht gebucht** – die App weist ihn ab und bittet dich zu prüfen. So kann der Zahlungsstand nie ins Negative laufen. Buche stattdessen genau den offenen Restbetrag.

### Automatischer Status „bezahlt“

Sobald die Summe aller Zahlungen den Rechnungsbetrag **deckt**, setzt die App den Rechnungsstatus **automatisch auf „bezahlt“** – du musst das nicht von Hand tun. Umgekehrt gilt: Löschst du eine Zahlung wieder (z. B. Fehlbuchung), fällt die Rechnung automatisch **zurück auf „gestellt“**, falls sie durch die Löschung wieder unterdeckt ist.

!!! note "Nur gestellte Rechnungen erhalten Zahlungen"
    Zahlungen lassen sich **ausschließlich auf gestellte Rechnungen** buchen. Ein Entwurf war nie beim Kostenträger; eine bereits bezahlte oder stornierte Rechnung darf ihren Status hier nicht mehr ändern. Für Korrekturen löschst du die betreffende Zahlung (Aktion **„Zahlung löschen“**) – der Zahlungsstand aktualisiert sich sofort.

---

## Fälligkeit aus dem Zahlungsziel

Die **Fälligkeit** einer Rechnung ergibt sich beim Erstellen aus **Rechnungsdatum + Zahlungsziel**. Das Zahlungsziel (Standard: 30 Tage) pflegst du je Kostenträger bzw. beim Rechnungssteller. Das errechnete Datum wird an der Rechnung festgeschrieben (Feld *fällig am*).

!!! abstract "Fälligkeit"
    ```
    fällig am = Rechnungsdatum + Zahlungsziel (Tage)
    ```
    **Bestandsrechnungen ohne gesetztes Fälligkeitsdatum** rechnet die App ersatzweise mit **Rechnungsdatum + 30 Tage**, damit sie trotzdem korrekt in der Offene-Posten-Liste und im Mahnwesen erscheinen.

Aus der Fälligkeit leitet die App die **Überfälligkeit in Tagen** ab (Stichtag heute). Dieser Wert steuert die Sortierung der Offene-Posten-Liste und entscheidet, ob überhaupt gemahnt werden darf.

---

## Mahnstufen 1–3

Zahlt ein Kostenträger nicht fristgerecht, erinnerst du ihn über die **Detailseite der Rechnung** an die offene Zahlung. Die App bildet **drei Stufen** ab:

| Stufe | Bezeichnung |
|---|---|
| **1** | Zahlungserinnerung |
| **2** | 1. Mahnung |
| **3** | 2. Mahnung (letzte) |

Jede Stufe wird als eigener Datensatz mit **Mahndatum** und **Zahlungsfrist (Tage)** angelegt (Standardfrist 14 Tage, einstellbar 1–60). Anschließend öffnet die App direkt die **druckfertige Mahnseite** – ein Schreiben zum Ausdrucken bzw. als Browser-PDF an den Kostenträger. Die versandten Mahnungen erscheinen als Historie an der Rechnung.

!!! warning "Ohne Mahngebühren – bewusst"
    Die App kennt **keine Mahngebühren oder Verzugspauschalen**. Öffentliche Kostenträger zahlen in aller Regel nach der Erinnerung; Verzugspauschalen wären hier unüblich. Es geht rein um die dokumentierte Erinnerung, nicht um Zusatzforderungen.

### Wann die nächste Stufe möglich ist

Die App führt dich stufenweise und verhindert unplausible oder doppelte Mahnungen:

- Gemahnt werden kann **nur eine offene** Rechnung (gestellt und noch nicht voll bezahlt).
- Die **erste** Stufe (Zahlungserinnerung) ist erst möglich, **wenn die Rechnung tatsächlich fällig ist** – eine Erinnerung vor Fälligkeit lehnt die App ab und nennt dir das Fälligkeitsdatum.
- Eine **höhere** Stufe geht erst, **wenn die Frist der vorherigen Stufe abgelaufen ist** (zahlbar bis = Mahndatum + Frist).
- Nach der **2. Mahnung (Stufe 3)** ist die höchste Stufe erreicht; weitere Mahnungen sind nicht vorgesehen.

!!! note "Schutz gegen Doppelklick"
    Jede Stufe existiert je Rechnung genau einmal. Ein versehentlicher Doppelklick erzeugt **keine** zweite Mahnung derselben Stufe – die App fängt das ab und meldet es dir.

---

## Beleghafter Storno per Gutschrift

Eine **Entwurfs**-Rechnung, die noch nie beim Kostenträger war, kannst du direkt stornieren (Aktion **Status → storniert**) – ihre Positionen werden dann wieder freigegeben und können neu abgerechnet werden.

Eine **bereits gestellte** Rechnung dagegen war beim Kostenträger und darf nicht einfach verschwinden. Sie wird deshalb **beleghaft per Gutschrift** storniert (Aktion **„Stornieren (Gutschrift)“**). Die App legt dazu eine eigene **Gutschrift** an:

| Merkmal der Gutschrift | Bedeutung |
|---|---|
| **eigene Rechnungsnummer** | Die Gutschrift bekommt eine neue Nummer aus dem laufenden Nummernkreis – kein Loch, kein Überschreiben. |
| **negativer Betrag** | Sie trägt den **negativen** Betrag der Originalrechnung und hebt sie damit buchhalterisch auf. |
| **verlinkt zum Original** | Über *Gutschrift zu* zeigt sie auf die stornierte Ursprungsrechnung (beide Richtungen sichtbar). |
| **Status gestellt** | Die Gutschrift wird direkt als gestellt geführt (sie geht ebenfalls an den Kostenträger). |

Nach dem Storno wird die **Originalrechnung auf „storniert“** gesetzt und ihre **Positionen (Monatsnachweise) wieder freigegeben** – sie stehen damit erneut zur Abrechnung bereit.

!!! danger "Zahlungen zuerst klären"
    Eine gestellte Rechnung mit **bereits gebuchten Zahlungen** kann **nicht** storniert werden. Sonst hingen die Zahlungen unsichtbar an einer stornierten Rechnung, während die Positionen erneut voll fakturierbar wären. Lösche bzw. buche die Zahlungen zuerst um, dann storniere. Ebenso lässt sich zu einer Rechnung **nur eine** aktive Gutschrift anlegen, und eine **Gutschrift selbst** kann nicht erneut storniert werden.

!!! tip "Warum überhaupt eine Gutschrift?"
    Der beleghafte Storno hält die **Beleg-Disziplin** ein: Jeder Vorgang, der beim Kostenträger war, bleibt als Beleg nachvollziehbar (Rechnung + gegenläufige Gutschrift), statt einfach gelöscht zu werden. Das ist für Kostenträger-Prüfungen und die Buchhaltung (DATEV: Gutschrift = Haben auf dem Debitor) sauber.

---

## Änderungshistorie

Jede Rechnung führt eine **vollständige Versionshistorie**: Jede Änderung wird als Snapshot mit **Wer, Wann und Was** festgehalten. Auf der Rechnungs-Detailseite siehst du die letzten Einträge kompakt – wann die Rechnung angelegt oder geändert wurde, durch wen und welche Felder betroffen waren.

!!! note "Revisionssicher"
    Die lückenlose Historie macht die Abrechnung **revisionssicher** für Kostenträger-Prüfungen (§ 128 SGB IX). Zusammen mit dem beleghaften Storno bleibt jeder Vorgang nachvollziehbar.

---

## Datenschutz-Hinweise

!!! warning "Datensparsamkeit (Art. 9 DSGVO) im Verwaltungsbereich"
    Das gesamte Mahnwesen läuft im Verwaltungsbereich mit einer **bewusst reduzierten Projektion**: sichtbar sind nur Name/Aktenzeichen, Kostenträger, Betrag, Monat und Status – **keine Tätigkeits-Dokumentation**, keine Verlaufstexte. Die Verwaltung hat keinen Klientenzugriff im eigentlichen Sinn. Trage in Zahlungs- und Mahnnotizen nur das fachlich Erforderliche ein (z. B. Buchungsreferenz), keine besonderen Kategorien personenbezogener Daten.

---

## Für Neugierige: Technik dahinter

!!! note "Nur zur Nachvollziehbarkeit"
    Dieser Abschnitt richtet sich an alle, die verstehen (oder nachbauen) möchten, wie Offene Posten, Zahlungen, Mahnwesen und Storno technisch aufgebaut sind. Für die tägliche Bedienung ist er nicht nötig.

- **Views** (`nachweis/views_abrechnung.py`, alle hinter `services.darf_abrechnen(request.user)`):
    - `offene_posten(request)` – filtert `Rechnung.objects.filter(status=Rechnungsstatus.GESTELLT)` und behält nur Posten mit `r.offener_betrag > 0`; baut je Zeile `{r, offen, faellig, tage, ueberfaellig, stufe}`, sortiert nach `-tage`; Kennzahlen `summe_offen`, `summe_ueberfaellig`, `n_ueberfaellig`.
    - `zahlung_erfassen(request, pk)` (`@require_POST`) – nur bei `status == GESTELLT`; parst den Betrag (`,`→`.`, muss > 0), lehnt Überzahlung (`betrag > r.offener_betrag`) ab und legt `Zahlung.objects.create(...)` an.
    - `zahlung_loeschen(request)` (`@require_POST`) – `z.delete()`, Zahlungsstand aktualisiert sich über das Model.
    - `mahnung_erstellen(request, pk)` (`@require_POST`) – `transaction.atomic()` + `select_for_update()` gegen Races; Stufe = letzte + 1 (max. 3), prüft `r.ist_offen`, Fälligkeit (`tage_ueberfaellig > 0`) für Stufe 1 und die Restfrist der Vorstufe (`heute <= letzte.zahlbar_bis`); `frist_tage` geklammert 1–60; fängt `IntegrityError` (UniqueConstraint) ab, leitet auf `mahnung_druck` weiter.
    - `mahnung_druck(request, pk)` – rendert `nachweis/mahnung_druck.html` mit `m`, `r`, `offen`, `bezahlt`, `Rechnungssteller.load()`.
    - `rechnung_gutschrift(request, pk)` (`@require_POST`) – ruft `services.gutschrift_erstellen(r, ersteller)`, bei Fehler `messages.error`, sonst Redirect auf die **Gutschrift**-Detailseite.
    - `rechnung_status(request, pk)` (`@require_POST`) – Direkt-Storno nur für Entwürfe; blockt Storno gestellter Rechnungen (Verweis auf Gutschrift) und Storno bei vorhandenen Zahlungen; beim Direkt-Storno werden die Positionen auf `FREIGEGEBEN` zurückgesetzt (`rechnung=None`, `abgerechnet_am=None`).
    - `rechnung_detail(request, pk)` – reicht `zahlungen`, `mahnungen`, `offen = r.offener_betrag`, `naechste_stufe = min(r.mahnstufe + 1, 3)`, `stufen = dict(Mahnstufe.choices)`, die aufbereitete `historie` (aus `r.history` via `diff_against`/`prev_record`) und die aktive `gutschrift` ans Template.
- **Model `Rechnung`** (`nachweis/models.py`): `typ` (`Rechnungstyp.RECHNUNG|GUTSCHRIFT`), `storno_zu` (self-FK → `related_name="gutschriften"`), `faellig_am`. Properties: `faelligkeit` (`faellig_am` oder `datum + 30 Tage`), `bezahlt_summe`, `offener_betrag`, `ist_offen` (gestellt **und** `offener_betrag > 0`), `mahnstufe` (höchste versandte Stufe), Methode `tage_ueberfaellig(stichtag)`. `zahlungsstand_aktualisieren()` setzt `bezahlt`/zurück auf `gestellt` als **bedingtes** DB-`update()` (nur aus dem erwarteten Alt-Status, nie über einen `STORNIERT`-Status). History via `HistoricalRecords()`.
- **Model `Zahlung`** (`nachweis/models.py`): `rechnung` (FK, `related_name="zahlungen"`), `datum`, `betrag` (`MinValueValidator 0.01`), `notiz`, `erfasst_von`. `save()`/`delete()` rufen `rechnung.zahlungsstand_aktualisieren()` – daher der **automatische** Status „bezahlt“/„gestellt“.
- **Model `Mahnung`** + **`Mahnstufe`** (`IntegerChoices`: `ERINNERUNG=1`, `MAHNUNG_1=2`, `MAHNUNG_2=3`): Felder `rechnung` (FK, `related_name="mahnungen"`), `stufe`, `datum`, `frist_tage` (default 14), `notiz`, `erstellt_von`; Property `zahlbar_bis = datum + frist_tage`. `UniqueConstraint(fields=["rechnung", "stufe"], name="eine_mahnung_je_stufe")` – eine Stufe je Rechnung nur einmal. **Keine** Gebührenfelder (bewusst).
- **Service `gutschrift_erstellen(rechnung, ersteller)`** (`nachweis/services.py`): `transaction.atomic()` + `select_for_update()`; lehnt ab, wenn `typ != RECHNUNG`, `status != GESTELLT`, `r.zahlungen.exists()` oder bereits eine nicht-stornierte Gutschrift existiert. Legt sonst eine `Rechnung` mit `typ=GUTSCHRIFT`, `storno_zu=r`, `betrag=-(r.betrag)`, `status=GESTELLT`, neuer `naechste_rechnungsnummer(r.jahr)` an, setzt das Original auf `STORNIERT` und gibt die Positionen (`FREIGEGEBEN`, `rechnung=None`, `abgerechnet_am=None`) frei. Rückgabe `(gutschrift, fehler)` – genau eines ist gesetzt.
- **Templates** (`nachweis/templates/nachweis/`): `offene_posten.html`, `rechnung_detail.html` (Zahlungs-/Mahnformulare, Historie, Gutschrift-Button), `mahnung_druck.html` (druckfertiges Schreiben).
- **URL-Namen** (`nachweis/urls.py`): `nachweis:offene_posten`, `nachweis:zahlung_erfassen`, `nachweis:zahlung_loeschen`, `nachweis:mahnung_erstellen`, `nachweis:mahnung_druck`, `nachweis:rechnung_gutschrift`, `nachweis:rechnung_status`, `nachweis:rechnung_detail`.

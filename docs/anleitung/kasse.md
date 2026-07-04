# Kasse (Kassenbuch & Zaehlprotokoll)

Die **Kasse** bildet die Barkasse (Handkasse) eines Teams ab. Sie besteht aus zwei
zusammengehoerenden Teilen:

- **Kassenblatt** – das laufende Kassenbuch je Team und Monat (Belege mit Einnahmen,
  Ausgaben und laufendem Bestand).
- **Zaehlprotokoll** – der Monatsabschluss, bei dem das tatsaechlich vorhandene Bargeld
  gezaehlt und gegen den rechnerischen Buchbestand geprueft wird.

Beide landen zum Monatsende gemeinsam auf einem Druck-Beleg.

!!! note "Wer arbeitet mit der Kasse?"
    Jedes Team pflegt seine **eigene** Kasse. Die **Verwaltung** ist der zentrale
    Finanz-Hub: Sie sieht und pflegt **alle** Kassen und ist zusaetzlich fuer die
    Buchhaltungs-Felder (BuHa) zustaendig. Die App-Rolle **Admin** hat **keinen**
    Zugriff auf Kassen (DSGVO- und Aufgabentrennung – Admin verwaltet Konten, nicht
    Finanzen).

---

## Ueberblick der Rollen

| Rolle | Sieht Kassen | Pflegt Buchungen | BuHa-Felder | Kasse anlegen | Zaehlprotokoll |
|-------|--------------|------------------|-------------|---------------|----------------|
| **User** (Team-Mitglied) | nur eigenes Team | ja | nein | nein | ja |
| **Leitung** | eigene + geleitete Teams | ja | nein | nein | ja |
| **Verwaltung** (Finanz-Hub) | **alle** | ja | **ja** | ja | ja |
| **Admin** | – | – | – | – | – |
| **Break-Glass `root`** | alle (Notzugang) | ja | ja | ja | ja |

Die Sichtbarkeit steuert `services.kassen_fuer(user)`: Verwaltung/Superuser sehen alle
Kassen, Team-Mitglieder ihre eigenen bzw. geleiteten, Admin keine. Ob die BuHa-Felder
editierbar sind, entscheidet `services.kann_buha(user)` (nur Verwaltung + Break-Glass).

---

## Kassenblatt (laufendes Kassenbuch)

Aufruf ueber die Navigation **„Kasse"** (`/kasse/`). Oben waehlst du **Kasse** (falls du
Zugriff auf mehrere hast), **Jahr** und **Monat**.

### Aufbau einer Zeile

Jede Buchung (`Kassenbuchung`) besteht aus:

| Feld | Bedeutung |
|------|-----------|
| **Beleg-Nr.** | fortlaufende Nummer, wird automatisch vorbelegt (naechste freie Nr.) |
| **Datum** | Belegdatum (Pflichtfeld) |
| **Text** | Buchungstext / Verwendungszweck (Pflichtfeld) |
| **Einnahme** | Betrag, der in die Kasse fliesst (€) |
| **Ausgabe** | Betrag, der aus der Kasse geht (€) |
| **Bestand** | laufender Kassenbestand nach dieser Zeile – wird **berechnet** |

Der **laufende Bestand** wird serverseitig gerechnet
(`services.kassenblatt_zeilen`):

```
Bestand = Kassenvortrag + (Σ Einnahmen − Σ Ausgaben) bis zu dieser Zeile
```

!!! tip "Beleg erfassen"
    Datum und Text ausfuellen, dann je nach Vorgang **entweder** Einnahme **oder**
    Ausgabe eintragen. Betraege duerfen mit Komma oder Punkt eingegeben werden
    (`12,50` = `12.50`). Fehlt Datum oder Text, wird die Buchung nicht gespeichert.

### Kassenvortrag (Endbestand des Vormonats)

Der **Kassenvortrag** ist der Startbestand des Monats und entspricht dem **Endbestand
des Vormonats**. Er wird beim ersten Aufruf eines Monats **automatisch** uebernommen
(`services.kassenmonat` liest `Kassenmonat.endbestand` des Vormonats; bei Jahreswechsel
Dezember → Januar). Es gibt also keine Luecke zwischen den Monaten.

!!! warning "Vortrag manuell aendern – nur Verwaltung"
    Den Vortrag darf ausschliesslich die **Verwaltung** (BuHa-Berechtigung) korrigieren
    (z. B. beim erstmaligen Einrichten einer Kasse mit vorhandenem Anfangsbestand).
    Team-Mitglieder sehen den Vortrag, koennen ihn aber nicht ueberschreiben.

### BuHa-Felder (nur Verwaltung)

Zusaetzlich fuehrt jede Buchung Buchhaltungs-Felder, die **nur die Verwaltung** sieht und
pflegt:

| BuHa-Feld | Zweck |
|-----------|-------|
| **Buchungsdatum** | Datum der Verbuchung in der Finanzbuchhaltung |
| **Kontonr.** | Sachkonto |
| **Kostenstelle** | Kostenstellen-Code |

!!! note "Trennung Team ↔ Verwaltung"
    Team-Mitglieder erfassen den **fachlichen** Beleg (Datum, Text, Betrag). Die
    Verwaltung ergaenzt spaeter die **buchhalterische** Zuordnung. Speichert ein
    Team-Mitglied eine Buchung, bleiben vorhandene BuHa-Werte unangetastet – sie werden
    nur bei BuHa-Berechtigung geschrieben.

### Kasse anlegen (Verwaltung)

Nur die Verwaltung kann fuer ein Team, das noch keine Kasse hat, eine neue **Kasse
anlegen** (Bezeichnung wird automatisch als „Kassenbuch <Team>" gesetzt, optional mit
Kostenstelle). Teams ohne Kasse werden dafuer in der Oberflaeche angeboten. Pro Team gibt
es genau **eine** Kasse (`OneToOneField`).

---

## Zaehlprotokoll (Monatsabschluss)

Aufruf: `/kasse/zaehlprotokoll/` (aus der Kassen-Ansicht heraus, mit Kasse/Jahr/Monat).
Beim Monatsabschluss wird das **physisch vorhandene Bargeld gezaehlt** und mit dem
**Buchbestand** verglichen.

### Bargeld zaehlen (Stueckelung)

Fuer jede Note und Muenze wird die **Stueckzahl** eingetragen. Die App multipliziert mit
dem Nennwert und summiert. Erfasst werden (Konstante `GELDSTUECKELUNG`):

| Noten | Muenzen |
|-------|---------|
| 100 €, 50 €, 20 €, 10 €, 5 € | 2 €, 1 €, 0,50 €, 0,20 €, 0,10 €, 0,05 €, 0,02 €, 0,01 € |

Die Summe aller Positionen ist das **gezaehlte Bargeld** (`bargeld_gesamt`).

### Soll-Ist-Vergleich

Die App rechnet **live** den Abgleich (Modell-Properties auf `Zaehlprotokoll`):

```python
bargeld_gesamt = Σ (Nennwert × Stueckzahl)          # Ist (gezaehlt)
neuer_bestand  = Vortrag + Einnahmen − Ausgaben − nicht_eingetragene   # Soll (gebucht)
differenz      = bargeld_gesamt − neuer_bestand
```

| Feld | Bedeutung |
|------|-----------|
| **Zaehldatum** | Datum der Kassenzaehlung |
| **Nicht eingetragene Belege** | Betrag bereits ausgelegter, aber noch nicht gebuchter Belege |
| **Vermerke** | Anmerkungen fuer die Finanzbuchhaltung (FiBu) |

!!! danger "Differenz muss 0 sein"
    Ein sauberer Kassenabschluss hat **Differenz = 0,00 €**. Weicht der gezaehlte
    Bestand vom Buchbestand ab, muss die Ursache gefunden werden (fehlende/doppelte
    Buchung, falscher Betrag, nicht eingetragene Belege nachtragen). Erst wenn die
    Differenz null ist, ist der Monat sauber abgeschlossen.

!!! tip "Reihenfolge"
    1. Alle Belege des Monats im **Kassenblatt** erfassen.
    2. Bargeld zaehlen und Stueckzahlen ins **Zaehlprotokoll** eintragen.
    3. Differenz pruefen → muss 0,00 € sein.
    4. Zaehldatum setzen und speichern – damit gilt der Monat als **abgeschlossen**.

---

## Drucken (Kassenblatt + Zaehlprotokoll)

Der gemeinsame Ausdruck erfolgt ueber **„Druck-Nachweise" → Karte „Kasse"**
(`/kasse/druck/`). Auf **einem** Beleg erscheinen:

- das komplette **Kassenblatt** des Monats (mit laufendem Bestand), und
- das **Zaehlprotokoll** als Monatsabschluss.

!!! note "Vorbelegung: zuletzt abgeschlossener Monat"
    Ohne explizite Monatsangabe belegt die App den **zuletzt abgeschlossenen Monat** vor
    (`services.letzter_kassenabschluss`). Ermittelt wird:

    1. der neueste Monat mit **erfasstem Zaehlprotokoll** (Zaehldatum oder gezaehltes Bargeld), sonst
    2. der neueste Monat mit **Buchungen**, sonst
    3. der **Vormonat**.

    Ist noch kein Zaehlprotokoll erfasst, wird ein **leeres** Zaehlformular
    mitgedruckt – das Zaehlprotokoll gehoert als Monatsabschluss immer auf den Beleg.

---

## Kurzreferenz (Pfade & Logik)

| Was | Wo |
|-----|----|
| Kassenblatt-Ansicht | `/kasse/` |
| Zaehlprotokoll | `/kasse/zaehlprotokoll/` |
| Druck (Blatt + Protokoll) | `/kasse/druck/` |
| Sichtbarkeit der Kassen | `services.kassen_fuer(user)` |
| BuHa-Berechtigung | `services.kann_buha(user)` (nur Verwaltung + Break-Glass) |
| Vortrag = Endbestand Vormonat | `services.kassenmonat(...)` |
| Laufender Bestand | `services.kassenblatt_zeilen(monat)` |
| Druck-Vorbelegung | `services.letzter_kassenabschluss(kasse)` |
| Datenmodell | `Kasse`, `Kassenmonat`, `Kassenbuchung`, `Zaehlprotokoll` (`nachweis/models.py`) |
| Views | `nachweis/views_kasse.py` |

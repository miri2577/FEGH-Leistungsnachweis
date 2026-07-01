# Gruppen anlegen

Gruppenangebote (z. B. Kochgruppe, Freizeitgruppe) werden **einmal zentral** erfasst und dann rechnerisch auf die teilnehmenden Klient*innen aufgeteilt. So muss die gleiche Aktivität nicht für jede Person einzeln getippt werden. **Jede*r im Team** kann Gruppen anlegen.

## Neue Gruppe anlegen

Das Formular "Neue Gruppe anlegen" hat folgende Felder:

| Feld | Pflicht | Bedeutung |
|---|---|---|
| **Datum** | Ja | Tag des Gruppenangebots. |
| **Thema** | Ja | Freitext, z. B. "Kochgruppe". |
| **Leistungsart** | Ja | Kürzel (Standard **FS**); bestimmt, wie die Zeit zählt. |
| **Beginn** / **Ende** | – | Uhrzeiten des Angebots (`HH:MM`). |
| **Anz. Mitarbeiter** | – | Zahl der begleitenden Mitarbeitenden (mind. 1). |
| **Teilnehmer*innen** | – | Mehrfachauswahl der Klient*innen (mit Strg / ⌘). |

Nach **Gruppe speichern** erscheint die Gruppe in der Liste "Erfasste Gruppen", und du erhältst eine Bestätigung mit der Zahl der Teilnehmer*innen.

!!! warning "Pflichtangaben"
    Ohne **Datum**, **Thema** und gültige **Leistungsart** wird nicht gespeichert (Fehlermeldung "Bitte Datum, Thema und Leistungsart angeben."). Eine leere/ungültige Anzahl Mitarbeiter wird auf 1 gesetzt.

## Die Zeit/Klient-Formel

Die auf eine einzelne teilnehmende Person entfallende Zeit wird so berechnet:

$$
\text{Zeit pro Klient*in} = \frac{\text{Dauer (Ende} - \text{Beginn)}}{\text{Anzahl Teilnehmer*innen} \times \text{Anzahl Mitarbeiter}}
$$

Das Ergebnis wird auf drei Nachkommastellen kaufmännisch gerundet.

!!! example "Rechenbeispiel"
    Kochgruppe von 17:00 bis 19:00 (**2,0 h**), **4 Teilnehmer*innen**, **1 Mitarbeiter*in**:
    
    2,0 h ÷ (4 × 1) = **0,50 h** pro Person.
    
    Mit **2 Mitarbeitenden** wäre es 2,0 ÷ (4 × 2) = **0,25 h** pro Person.

Die Liste "Erfasste Gruppen" zeigt je Zeile Datum, Thema, Art, Zeit (Beginn–Ende), **Dauer**, **MA** (Anzahl Mitarbeiter), **Teiln.** (Anzahl Teilnehmer), die hervorgehobene **Zeit/Klient** sowie die Namen der Teilnehmer*innen.

!!! note "Keine Teilnehmer = 0"
    Ohne ausgewählte Teilnehmer*innen ist die Zeit pro Klient*in 0 – die Gruppe erzeugt dann keine anrechenbare Leistung. Wähle also immer die Teilnehmenden aus.

## Verhältnis zum Leistungsnachweis

Der berechnete Anteil je Klient*in fließt **automatisch** in den amtlichen [Druck-Nachweis](druck-nachweis.md) der jeweiligen Person ein und ist dort mit einem Punkt (•, "automatisch") gekennzeichnet. Du musst die Gruppenzeit also **nicht** zusätzlich im Erfassungs-Grid eintragen.

## Gruppe löschen

Am Zeilenende der Gruppenliste das rote **✕** klicken und die Rückfrage "Gruppe löschen?" bestätigen. Die Gruppe und ihre anteiligen Zeiten entfallen damit.
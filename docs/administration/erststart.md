# Erststart fuer ein echtes Team

Diese Seite beschreibt Schritt fuer Schritt, wie eine frische Instanz von den
mitgelieferten **Demodaten** auf den **echten Produktivbetrieb** eines Teams
umgestellt wird. Ziel: nachvollziehbar (was passiert und warum) und nachbaubar
(konkrete Befehle, Klickpfade, Rollen).

!!! danger "Vor dem Leerstart: Datenschutz"
    Sobald echte Klient*innen angelegt werden, verarbeitet die Instanz
    besonders geschuetzte Daten nach **Art. 9 DSGVO** (Gesundheits-/Sozialdaten).
    Stelle sicher, dass die Instanz gehaertet ist: HTTPS erzwungen, sichere
    Passwoerter, **2FA verpflichtend** (siehe unten) und regelmaessige Backups
    der PostgreSQL-Datenbank.

---

## Ausgangslage: Demo vs. Produktiv

Nach dem ersten `python manage.py seed` (ohne Flags) enthaelt die Datenbank
**frei erfundene Demodaten** (9 Mitarbeitende, 33 Klient*innen, Leistungen,
Kasse …). Alle Demo-Logins nutzen das Passwort `demo12345`. Das ist ideal fuer
Test und Schulung, aber **kein Zustand fuer den echten Betrieb**.

Der Uebergang in den Produktivstart besteht aus sechs Schritten:

| Schritt | Wer | Wo | Ergebnis |
| --- | --- | --- | --- |
| 1. Demodaten leeren | Server-Admin | Terminal | Leere DB + Rechte-Gruppen + Jahres-Parameter |
| 2. Break-Glass-Superuser | Server-Admin | Terminal | Notzugang `root` |
| 3. Teams anlegen | Superuser | Sidebar „Teams“ | reale Teams (BEW/WG/Verwaltung) |
| 4. Mitarbeitende anlegen | Admin/Superuser | „Mitarbeiter-Verwaltung“ | Konten je Rolle + Aktivierungslink |
| 5. Klient*innen anlegen | Leitung | „Belegungsliste“ | reale Belegung |
| 6. Erfassung starten | Betreuer*innen | App | Leistungen/Kalender/… |

---

## Schritt 1 – Demodaten leeren (Leerstart)

Der Seed-Befehl kennt einen **Leerstart-Modus**. Er entfernt saemtliche
Demodaten, legt aber **keine neuen an**. Zusaetzlich stellt er die technischen
Voraussetzungen fuer den Produktivbetrieb her:

- Die Rechte-Gruppen **Administration** und **Leitung** werden angelegt bzw.
  aktualisiert (`ensure_gruppen()`, idempotent).
- Der **Jahres-Parameter** (`Parameter`) fuer das aktuelle Abrechnungsjahr wird
  sichergestellt (z. B. Teamsitzung donnerstags, 3 Std.).

```bash
docker compose exec web python manage.py seed --leer
```

Erwartete Ausgabe (sinngemaess):

```text
Vorhandene Demodaten geloescht.
Leerstart bereit – keine Demodaten angelegt.
Naechste Schritte fuer den echten Produktivstart:
  1) Superuser (Break-Glass) anlegen:  python manage.py createsuperuser
  2) Einloggen -> Sidebar 'Teams' -> reale Teams anlegen (BEW/WG/Verwaltung)
  3) 'Mitarbeiter-Verwaltung' -> Mitarbeiter anlegen; jede*r erhaelt einen
     Aktivierungslink und vergibt das eigene Passwort selbst
  4) Als Leitung -> 'Belegungsliste' -> Klient*innen anlegen
```

!!! warning "`--leer` loescht unwiderruflich"
    `--leer` (wie auch das normale `seed`) fuehrt intern
    `Model.objects.all().delete()` fuer Teams, Mitarbeiter, Klienten,
    Leistungen, Kasse, Termine, Arbeitszeiten usw. aus. Zusaetzlich werden
    **alle 2FA-Geraete** (TOTP/Static) und ein evtl. alter `admin`-Superuser
    entfernt. **Nur auf einer frischen bzw. reinen Demo-Instanz ausfuehren** –
    niemals auf einer DB mit echten Daten.

!!! note "Unterschied zu den anderen Seed-Varianten"
    | Aufruf | Wirkung |
    | --- | --- |
    | `seed` | loescht Demodaten und legt **neue Demodaten** an |
    | `seed --keep` | loescht nichts, ergaenzt nur |
    | `seed --leer` | loescht Demodaten, legt **keine** an → Produktivstart |

---

## Schritt 2 – Break-Glass-Superuser anlegen

Der Superuser ist ein **technischer Notzugang** (Break-Glass) **ohne**
Mitarbeiter-Profil. Er dient dazu, sich das erste Mal einzuloggen und die realen
Teams sowie den ersten Admin einzurichten.

```bash
docker compose exec web python manage.py createsuperuser
```

Django fragt Benutzername, E-Mail und Passwort ab. Konventionell wird der
Benutzername **`root`** verwendet.

!!! tip "Alternativ: Seed-Superuser per Env"
    Der Seed kann einen Superuser `root` automatisch anlegen, wenn die
    Umgebungsvariable `DJANGO_SEED_ROOT_PASSWORD` gesetzt ist. Im lokalen
    `DEBUG`-Modus greift ersatzweise das Bequemlichkeits-Passwort `root12345`.
    In Produktion (`DEBUG=0`) **ohne** gesetzte Variable wird **kein** Superuser
    angelegt – dann ist `createsuperuser` der vorgesehene Weg.

    ```yaml
    # docker-compose.yml (Beispiel, nur wenn gewuenscht)
    environment:
      DJANGO_SEED_ROOT_PASSWORD: "<langes-zufaelliges-passwort>"
    ```

!!! danger "Warum kein App-Admin gleichzeitig Superuser ist"
    Keine App-Rolle (User/Leitung/Admin) erhaelt `is_staff`/`is_superuser`.
    Der Django-Admin wuerde das objektbezogene **Team-Scoping** umgehen: eine
    Leitung koennte teamuebergreifend alle Klient*innen sehen, ein Admin sich
    per Rollen-Feld selbst zur Leitung befoerdern (Rechte-Eskalation). Deshalb
    laeuft die gesamte Stammdatenpflege ueber die app-nativen, gescopten Seiten;
    der Superuser bleibt reiner Notzugang.

---

## Schritt 3 – Reale Teams anlegen

Als Superuser (`root`) einloggen. In der **Sidebar** den Punkt **„Teams“**
oeffnen und die realen Teams anlegen. Beim Anlegen wird jeweils ein **Typ**
gewaehlt:

| Teamtyp | Bedeutung |
| --- | --- |
| **BEW** | Betreutes Einzelwohnen (aufsuchende Betreuung) |
| **WG** | Wohngemeinschaft |
| **Verwaltung** | Verwaltung/Kasse, keine Klientenarbeit |

Ablauf: Name eingeben, Typ waehlen, speichern. Ein Team laesst sich spaeter
deaktivieren oder loeschen – **loeschen geht nur**, solange dem Team keine
Mitglieder oder Klient*innen zugeordnet sind.

!!! note
    Der Menuepunkt „Teams“ ist nur fuer **Admin** und **Superuser** sichtbar.
    Namen muessen eindeutig sein.

---

## Schritt 4 – Mitarbeitende anlegen (Onboarding)

In der Sidebar **„Mitarbeiter-Verwaltung“** oeffnen und pro Person ein Konto
anlegen (Vorname, Nachname, **Rolle**, **Team**, optional E-Mail,
Wochenstunden, Urlaubstage).

### Rollen

| Rolle | Zugriff |
| --- | --- |
| **User** | eigenes Team, eigene Klient*innen; erfasst Leistungen/Kalender |
| **Leitung** | die von ihr geleiteten Teams; pflegt Belegungsliste + Parameter |
| **Admin** | Teams + Mitarbeitende – **kein** Klientenzugriff |
| **Verwaltung** | keine Klientenarbeit, aber Kasse/Stempelung |

### Aktivierung ohne vorab gesetztes Passwort

Wichtig fuer den Datenschutz: Der Admin vergibt **kein** Passwort. Das Konto
wird ohne brauchbares Passwort angelegt (`set_unusable_password()`); die Person
vergibt ihr Passwort **selbst** ueber einen **Aktivierungslink**.

Ablauf im Hintergrund:

1. Konto anlegen → System erzeugt einen eindeutigen Benutzernamen aus dem
   Nachnamen (bei Kollision `…2`, `…3`).
2. System zeigt einen **absoluten Einmal-Link** an und mailt ihn (falls
   `EMAIL_AKTIV` und E-Mail hinterlegt).
3. Die Person oeffnet den Link, vergibt ihr Passwort, richtet ggf. 2FA ein und
   loggt sich ein.

!!! note "Eigenschaften des Aktivierungslinks"
    Der Link nutzt Djangos zustandslosen `PasswordResetTokenGenerator`. Er ist
    dadurch **einmalig** (ungueltig, sobald das Passwort gesetzt/geaendert wird)
    und **zeitlich begrenzt** ueber `PASSWORD_RESET_TIMEOUT` (Standard: 7 Tage,
    so auch im Mailtext genannt).

!!! tip "Link ohne E-Mail weitergeben"
    Ist kein Mailversand konfiguriert, zeigt die Bestaetigungsseite den Link
    direkt an – er kann sicher (z. B. persoenlich) an die Person weitergegeben
    werden. Ueber „Mitarbeiter-Verwaltung → Aktion **reset_link**“ laesst sich
    jederzeit ein neuer Link erzeugen.

### Leitung dem Team zuweisen

Eine **Leitung** sieht ihre Teams ueber das Feld „leitet“. Ordne der Leitung
die von ihr verantworteten Team(s) zu (eine Leitung kann mehrere Teams leiten).
Erst dadurch werden ihr in Belegungsliste/Parametern die richtigen Klient*innen
und Teams angezeigt (`teams_fuer` / `klienten_fuer`).

!!! tip "Weitere Aktionen in der Mitarbeiter-Verwaltung"
    - **2FA zuruecksetzen** – bei verlorenem Geraet; 2FA wird beim naechsten
      Login neu eingerichtet.
    - **Deaktivieren/Aktivieren** – sperrt bzw. entsperrt den Login, ohne das
      Konto zu loeschen.

---

## Schritt 5 – Klient*innen anlegen (Belegungsliste)

Als **Leitung** einloggen und in der Sidebar **„Belegungsliste“** oeffnen. Ueber
„Neu“ die Klient*innen des eigenen Teams anlegen. Die Ansicht ist strikt auf die
geleiteten Teams gescopt – eine Leitung sieht/pflegt nur ihre eigenen Teams.

Pflicht- und Kernfelder:

| Feld | Bedeutung |
| --- | --- |
| **Nachname** (Pflicht) | Name der Person |
| Vorname, Geburtsdatum | Stammdaten |
| **Team** (Pflicht) | eines der geleiteten Teams |
| **Bezugsbetreuer*in** (Pflicht) | Mitarbeiter*in **aus dem Team** |
| Vertretung 1/2 | optionale Vertretungen |
| **AL / kLE** | Assistenzleistung bzw. kalkulatorische Leistungseinheit pro Monat |
| **HBG** | Hilfebedarfsgruppe (1–4) |
| **KUE-Ende** (`kue_bis`) | Ende der Kostenuebernahme (steuert Berichtsfaelligkeit) |
| Kuerzel/Person-ID | Kennung (z. B. `BE-100123`) |
| Status | Betreuung / Beendigung |

!!! warning "Team + Bezugsbetreuer*in muessen zusammenpassen"
    Gespeichert wird nur, wenn **Nachname, Team und Bezugsbetreuer*in** gesetzt
    sind **und** die Bezugsbetreuung tatsaechlich zu einem der geleiteten Teams
    gehoert. Andernfalls bricht die Speicherung mit einer Fehlermeldung ab.

!!! note "Team-Parameter"
    Ueber „Parameter“ pflegt die Leitung je Jahr u. a. **Teamsitzungs-Wochentag
    und -Dauer** sowie den **FLS-Preis**. Der Jahres-Parameter existiert bereits
    aus Schritt 1; hier werden nur die Werte angepasst.

---

## Schritt 6 – Erfassung startet

Sind Teams, Mitarbeitende und Klient*innen angelegt, koennen die
**Betreuer*innen** (Rolle User) direkt loslegen: Leistungen dokumentieren,
Wochenkalender/Termine pflegen, Arbeitszeiten erfassen, Abwesenheiten
beantragen. Die Verwaltung fuehrt zusaetzlich Kasse und Stempelung.

Jede*r sieht dabei nur die **eigenen** Klient*innen bzw. die des eigenen Teams;
die Leitung sieht ihre geleiteten Teams; der Admin sieht Teams/Mitarbeitende,
aber **keine** Klientendaten.

---

## Produktion: 2FA verpflichtend

Im echten Betrieb ist Zwei-Faktor-Authentifizierung **Pflicht**. Setze dazu die
Umgebungsvariable:

```yaml
# docker-compose.yml
environment:
  DJANGO_OTP_REQUIRED: "1"
```

Danach wird jede*r Nutzer*in beim ersten Login nach dem Passwort-Setzen zur
Einrichtung eines TOTP-Geraets (z. B. Authenticator-App) gefuehrt. Der
Auch der Break-Glass-Superuser wird dann zur 2FA-Einrichtung gefuehrt (TOTP + Recovery-Codes sicher verwahren); Notfall-Rueckfallebene bleibt der Server-Shell-Zugang.

!!! warning "Reihenfolge beachten"
    `seed --leer` loescht bestehende 2FA-Geraete. Setze `DJANGO_OTP_REQUIRED=1`
    **nach** dem Leerstart bzw. sorge dafuer, dass alle produktiven Konten ihre
    2FA neu einrichten.

---

## Anhang: Demo-Logins fuer Test & Schulung

Fuer Schulung, Test oder ein Vorfuehr-System liefert der normale Seed
(`seed` ohne `--leer`) fiktive Konten. **Alle** haben das Passwort
`demo12345`. Beispiele:

| Benutzername | Rolle | Team |
| --- | --- | --- |
| `berger` | Leitung | TBEW (leitet TBEW + WG) |
| `neumann` | User | TBEW |
| `sander` | Admin | Verwaltung |
| `peters` | User (Verwaltung) | Verwaltung |
| `root` | Superuser (Break-Glass) | – |

!!! danger "Demodaten niemals in Produktion"
    Die Demo-Logins sind bewusst schwach (`demo12345`) und laufen ohne 2FA. Sie
    sind ausschliesslich fuer Test/Schulung gedacht. Vor dem Echtbetrieb immer
    `seed --leer` ausfuehren, damit **keine** Demo-Konten und -Klient*innen
    zurueckbleiben.

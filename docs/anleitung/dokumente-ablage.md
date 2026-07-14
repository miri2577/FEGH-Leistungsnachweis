# Dokumente ablegen & ansehen

Am Fall lassen sich **Dateien direkt hinterlegen** – Bewilligungsbescheide, unterschriebene Berichte, Verträge (WBVG) oder Schutzkonzepte. Die Ablage sitzt im Reiter **Dokumente** der Fallakte und ist bewusst schlank gehalten: hochladen, ansehen, herunterladen, löschen. Diese Seite erklärt, wie du Dokumente ablegst, welche Dateitypen erlaubt sind, wie die Inline-Ansicht funktioniert und warum der Download nie über einen offenen Link, sondern immer über die App läuft.

!!! info "Wer sieht die Dokumente?"
    Die Ablage ist **team-gescopt** wie die übrige Fallakte: Du siehst und pflegst nur Dokumente zu Klient*innen deines eigenen bzw. der von dir geleiteten Team(s). **Admin- und Verwaltungs-Konten** haben keinen Klientenzugriff und sehen die Dokumente-Seite gar nicht.

---

## Wo finde ich die Ablage?

Öffne die **Fallakte** einer/eines Klient*in und wechsle auf den Reiter **Dokumente**. Du siehst zwei Bereiche:

- **Abgelegte Dokumente** – die Tabelle aller bereits hinterlegten Dateien.
- **Dokument ablegen** – das Upload-Formular darunter.

Die Tabelle zeigt je Zeile:

| Spalte | Inhalt |
|---|---|
| **Dokument** | Anzeigename (Link in die Ansicht), darunter ggf. die Notiz |
| **Kategorie** | farbiges Badge (Bescheid / Bericht / Vertrag / Schutz / Sonstiges) |
| **Bewilligung** | die verknüpfte Bewilligung (Aktenzeichen, Gültig-bis) oder „—" |
| **Größe** | Dateigröße (KB oder MB) |
| **abgelegt** | Datum/Uhrzeit und Kürzel der hochladenden Person |
| (letzte Spalte) | **👁 Ansehen** (nur bei Vorschau-Typen), **↓ Download**, ggf. **✕** löschen |

Ist noch nichts abgelegt, steht dort *„Noch kein Dokument abgelegt – unten hochladen."*

---

## Ein Dokument ablegen

Im Formular **„Dokument ablegen"** füllst du aus:

| Feld | Pflicht? | Bedeutung |
|---|---|---|
| **Datei** | ja | Die hochzuladende Datei (max. 15 MB, nur erlaubte Endungen – siehe unten). |
| **Anzeigename** | nein | Frei wählbarer Name in der Liste. Bleibt das Feld leer, wird der Dateiname übernommen (max. 200 Zeichen). |
| **Kategorie** | – | Einordnung des Dokuments (Voreinstellung: *Sonstiges*). |
| **Bewilligung** | nein | Optionale Verknüpfung mit einer Bewilligung der Kostenzusage – praktisch bei Bescheiden. |
| **Notiz** | nein | Kurzer Zusatz (max. 200 Zeichen), erscheint klein unter dem Namen. |

Ein Klick auf **Hochladen** legt das Dokument ab; bei Erfolg erscheint die Meldung *„Dokument „…" abgelegt."*

### Kategorien

| Badge | Kategorie |
|---|---|
| **Bescheid** | Bewilligungsbescheid |
| **Bericht** | Bericht (unterschrieben) |
| **Vertrag** | Vertrag / WBVG |
| **Schutz** | Schutzkonzept / Vereinbarung |
| **Sonstiges** | alles Übrige |

!!! tip "Bescheide an die Bewilligung hängen"
    Legst du einen Bewilligungsbescheid ab, wähle im Feld **Bewilligung** die passende Kostenzusage aus. So findest du später auf einen Blick den Bescheid zur jeweiligen Gültigkeit – das Aktenzeichen steht dann direkt in der Tabellenspalte.

---

## Erlaubte Dateitypen & Upload-Härtung

Der Upload ist bewusst eng abgesichert. Es gibt drei Prüfungen, die alle bestanden werden müssen:

1. **Endungs-Whitelist** – nur die unten gelisteten Endungen sind zugelassen.
2. **Magic-Bytes-Prüfung** – der tatsächliche Dateiinhalt muss zur Endung passen (bei Formaten, für die das prüfbar ist). Eine in `bescheid.pdf` umbenannte `.exe` fliegt hier raus.
3. **Größen- und Leerlauf-Grenze** – maximal **15 MB**, und leere Dateien (0 Byte) werden abgewiesen.

| Endung | Typ | Inhalts-Prüfung (Magic Bytes) |
|---|---|---|
| `.pdf` | PDF | ja (`%PDF`) |
| `.png` | Bild | ja |
| `.jpg`, `.jpeg` | Bild | ja |
| `.docx`, `.xlsx` | Office (Word/Excel) | ja (ZIP-Container) |
| `.odt`, `.ods` | Office (LibreOffice) | ja (ZIP-Container) |
| `.txt` | Text | keine (Textdatei ohne festen Kopf) |

!!! warning "Typische Fehlermeldungen"
    - *„Dateityp … nicht erlaubt."* – die Endung steht nicht auf der Whitelist.
    - *„Datei zu groß (max. 15 MB)."* – Größenlimit überschritten.
    - *„Die Datei ist leer."* – 0-Byte-Datei.
    - *„Der Dateiinhalt passt nicht zur Endung …"* – Magic-Bytes-Prüfung fehlgeschlagen (Inhalt ≠ Endung).

    In allen Fällen wird **nichts** gespeichert; du landest wieder auf der Dokumente-Seite mit rotem Hinweis.

---

## Ein Dokument ansehen

Ein Klick auf den **Namen** oder auf **👁 Ansehen** öffnet die Ansichtsseite. Ob eine Vorschau im Browser möglich ist, hängt vom Dateityp ab:

| Dateityp | Ansicht in der App |
|---|---|
| **PDF** | eingebettet im `iframe` (blättern/scrollen direkt in der Seite) |
| **Bild** (PNG/JPG) | direkt als Bild angezeigt |
| **Text** (`.txt`) | eingebettet im `iframe` |
| **Office** (docx/xlsx/odt/ods) | **keine** Vorschau – Hinweis „Bitte herunterladen und lokal öffnen" |

Oben auf der Ansichtsseite stehen ein Zurück-Link **← Dokumente**, Name und Metazeile (Kategorie · Größe · Ablagedatum · Kürzel) sowie rechts **↓ Herunterladen**.

!!! note "Warum Office nur zum Download?"
    Word-/Excel-/LibreOffice-Dateien lassen sich im Browser nicht sicher und zuverlässig einbetten. Statt eine externe Vorschau einzubinden (die Daten nach außen geben würde), gibt es bewusst nur den Download. Der **👁 Ansehen**-Button erscheint bei diesen Formaten in der Tabelle deshalb erst gar nicht.

---

## Herunterladen – immer über die App

Downloads laufen **nie** über einen offenen Datei-Link (kein `MEDIA_URL`), sondern ausschließlich über eine geschützte View, die bei jedem Abruf prüft, ob die Datei zu einer/einem für dich sichtbaren Klient*in gehört. Das gilt für den **Download** ebenso wie für die **Inline-Ansicht**.

!!! danger "Besonders schützenswerte Daten (Art. 9 DSGVO)"
    Bescheide, Berichte und Verträge enthalten Gesundheits- und Sozialdaten. Deshalb ist der Zugriff konsequent **team-gescopt** und läuft nur über die App. Lade nur ab, was du fachlich brauchst, und lege nur das Nötige ab (**Datensparsamkeit**) – nicht jede Randnotiz gehört als Scan in die Fallakte.

---

## Ein Dokument löschen

Löschen darf **die Leitung** oder **die Person, die das Dokument hochgeladen hat**. Nur für diese erscheint in der Zeile der rote **✕**-Button; ein Sicherheits-Dialog *„Dokument löschen?"* muss bestätigt werden.

!!! warning "Datei wird mitgelöscht"
    Beim Löschen verschwindet nicht nur der Datenbank-Eintrag, sondern auch die **Datei auf dem Server**. Ein Wiederherstellen aus der App heraus ist nicht vorgesehen – im Zweifel vorher herunterladen.

---

## Für Neugierige: Technik dahinter

!!! note "Nur zur Nachvollziehbarkeit"
    Dieser Abschnitt richtet sich an alle, die verstehen (oder nachbauen) möchten, wie die Ablage technisch funktioniert. Für die tägliche Bedienung ist er nicht nötig.

- **Views:** alles in `nachweis/views_dokumente.py` – `dokumente(request, pk)` (Liste + Upload-Formular), `dokument_hochladen` (`@require_POST`, ruft `_upload_pruefen`), `dokument_ansicht` (Ansichtsseite), `dokument_inline` (Quelle für `iframe`/`img`), `dokument_download` und `dokument_loeschen` (`@require_POST`). URL-Namen in `nachweis/urls.py`: `dokumente`, `dokument_hochladen`, `dokument_download`, `dokument_inline`, `dokument_ansicht`, `dokument_loeschen`.
- **Upload-Härtung:** `_upload_pruefen(f)` prüft Endung gegen `Dokument.ERLAUBT` (Whitelist), Größe gegen `Dokument.MAX_GROESSE` (15 MB), 0-Byte, und liest die ersten 8 Bytes für den Magic-Bytes-Abgleich (`f.read(8)` / `f.seek(0)`). `.txt` hat `None` als Magic → kein Inhalts-Check.
- **Model:** `Dokument` in `nachweis/models.py` mit Feldern `klient` (FK, `CASCADE`), `bewilligung` (FK, optional, `SET_NULL`), `kategorie`, `name` („Anzeigename"), `datei` (`FileField`), `groesse`, `notiz`, `hochgeladen_von` (FK `Mitarbeiter`, `SET_NULL`), `hochgeladen_am` (`auto_now_add`). `DokumentKategorie` als `TextChoices` (`bescheid`/`bericht`/`vertrag`/`schutz`/`sonstig`).
- **Ableitungen am Model:** `endung`, `vorschau_typ` (`pdf`|`bild`|`text` oder `None`) und `mime` aus dem `VORSCHAU`-Dict; `groesse_anzeige` (KB/MB). `Dokument.delete()` löscht die physische Datei über `datei.delete(save=False)` mit.
- **Speicherpfad:** `_dokument_pfad(instance, filename)` → `dokumente/<klient_id>/<uuid>.<ext>` – **Zufallsname** im Dateisystem, der Originalname steht nur im Feld `name` (kein Klientenname/Sonderzeichen im Pfad).
- **Auslieferung:** `_saubere_datei(d, request, *, inline)` liefert eine `FileResponse` – `as_attachment=not inline`, gesetzter `content_type=d.mime` bei Inline, `X-Content-Type-Options: nosniff` gegen Content-Sniffing. Für Inline zusätzlich `Content-Security-Policy: default-src 'none'; frame-ancestors 'self'`, damit die Datei ins eigene `iframe` darf, aber selbst nichts nachlädt.
- **Scoping/Rollen:** jede View lädt über `services.klienten_fuer(request.user)` bzw. filtert `Dokument.objects.filter(klient__in=…)` – Admin/Verwaltung erhalten `Klient.objects.none()`. Löschrecht: `services.ist_leitung(request.user)` **oder** `d.hochgeladen_von_id == mitarbeiter_fuer(request.user).id`; sonst `HttpResponseForbidden`. `dokument_inline` gibt für Nicht-Vorschau-Typen `Http404` zurück (`if not d.vorschau_typ`).
- **Templates:** `nachweis/templates/nachweis/dokumente.html` (Tabelle + Upload-Formular, `_fallakte_kopf.html` mit `fa_tab="dokumente"`) und `nachweis/templates/nachweis/dokument_ansicht.html` (`iframe` für PDF/Text, `img` für Bild, Fallback-Panel mit Download-Hinweis für Office-Formate).

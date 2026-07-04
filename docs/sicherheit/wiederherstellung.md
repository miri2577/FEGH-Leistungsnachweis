# Wiederherstellung (Audit-Timeline)

Diese Seite beschreibt die **In-App-Wiederherstellung einzelner Datensätze** über die
Änderungs-Timeline. Sie ergänzt das [Backup & Restore](backup-restore.md) für den
gezielten Fall „ein einzelnes Feld wurde versehentlich verändert" – ohne dass ein
komplettes Datenbank-Restore nötig wird.

!!! danger "Nur für den Break-Glass-Superuser"
    Die Timeline und die Rückgängig-Funktion sind **ausschließlich für den technischen
    Notzugang** (`is_superuser`) zugänglich. Der klientenfreie **Admin** bekommt aus
    DSGVO-Gründen **bewusst KEINE** Klienten-Änderungshistorie zu sehen – die Timeline
    zeigt Klarnamen und geänderte Feldwerte (Art.-9-Daten) und wäre für die Admin-Rolle
    ein unzulässiger Klientenzugriff.

## Überblick

| Aspekt | Wert |
| --- | --- |
| Sidebar-Eintrag | „Wiederherstellung" (Gruppe *Administration*) |
| Sichtbarkeit | nur `user.is_superuser` |
| Timeline-URL | `/timeline/` |
| Rückgängig-URL | `/timeline/restore/` (nur `POST`) |
| Datenquelle | [`django-auditlog`](https://django-auditlog.readthedocs.io/) `LogEntry` |
| Rücksetzbar | nur **Updates** (Feld-Änderungen), nur nicht-relationale Felder |
| Alles andere | Löschungen / komplexe Fälle → [Backup & Restore](backup-restore.md) |

## Wozu das Ganze?

`django-auditlog` protokolliert jede Änderung an den fachlichen Modellen als `LogEntry`
(wer, wann, welches Objekt, welche Felder alt→neu). Die Timeline macht dieses Protokoll
lesbar und bietet für den häufigsten Fehlerfall – „jemand hat aus Versehen ein Feld
überschrieben" – einen **Ein-Klick-Rücksetzer**, der die betroffenen Felder auf den
Stand *vor* der Änderung zurückstellt. So bleibt ein vollständiges Backup-Restore
(mit Ausfallzeit) dem echten Katastrophenfall vorbehalten.

## Welche Modelle werden protokolliert?

Registriert wird in `config/settings.py` über `AUDITLOG_INCLUDE_TRACKING_MODELS`:

```python
AUDITLOG_INCLUDE_TRACKING_MODELS = (
    "nachweis.Klient",
    "nachweis.Leistung",
    "nachweis.Gruppe",
    "nachweis.Arbeitszeit",
    "nachweis.Abwesenheit",
    "nachweis.Kassenbuchung",
    "nachweis.Zaehlprotokoll",
    "nachweis.Mitarbeiter",
    "nachweis.Termin",
)
```

!!! note "Neues Modell protokollieren"
    Soll ein weiteres Modell in der Timeline erscheinen, genügt es, den vollqualifizierten
    Namen (`app_label.ModelName`) dieser Tupel-Liste hinzuzufügen. `django-auditlog` legt
    die Log-Einträge dann automatisch bei jedem Speichern an – kein Migrations- oder
    Code-Aufwand im Modell selbst.

## Die Timeline (`/timeline/`)

View: `nachweis/views.py` → `timeline(request)`.

### Ablauf

1. **Zugriffsschutz:** `if not request.user.is_superuser: return HttpResponseForbidden()`.
2. **Abfrage:** die letzten Einträge aus `auditlog.models.LogEntry`, absteigend nach
   `timestamp`, mit `select_related("actor", "content_type")`.
3. **Filter** (über GET-Parameter, im Template als Dropdowns):
   - `?model=<modelname>` – filtert auf `content_type__app_label="nachweis"` und
     `content_type__model=<modelname>`.
   - `?aktion=<n>` – filtert auf `action` (`0` = angelegt, `1` = geändert, `2` = gelöscht).
4. **Aufbereitung:** pro Eintrag wird ein Dict gebaut mit
   - `le` – dem `LogEntry`,
   - `aenderungen` – Liste `(feld, alt, neu)` aus den geänderten Feldern,
   - `kann_zuruecksetzen` – `True` nur, wenn `le.action == LogEntry.Action.UPDATE`.
5. Es werden **max. 150 Einträge** gerendert (`qs[:150]`).

### Änderungen robust auslesen: `_log_changes`

Die Feld-Änderungen liegen je nach `auditlog`-Version als `changes_dict`, als dict in
`changes` oder als JSON-String vor. Der Helper `_log_changes(le)` normalisiert das auf
ein Dict `{feld: [alt, neu]}`:

```python
def _log_changes(le):
    """Änderungs-Dict {feld: [alt, neu]} robust aus einem auditlog-LogEntry lesen."""
    try:
        d = le.changes_dict
        if isinstance(d, dict):
            return d
    except Exception:
        pass
    c = getattr(le, "changes", None)
    if isinstance(c, dict):
        return c
    try:
        return json.loads(c or "{}")
    except Exception:
        return {}
```

Im Template (`nachweis/templates/nachweis/timeline.html`) werden nur Paare der Form
`[alt, neu]` (Länge 2) angezeigt – alt durchgestrichen/rot, neu grün.

### Darstellung

Jede Zeile zeigt: **Zeitpunkt** · **Aktion-Badge** (angelegt / geändert / gelöscht /
Zugriff) · **Actor** (`le.actor`, sonst „System") · **Objekt-Typ + `object_repr`** ·
die Feld-Diffs. Bei Updates erscheint rechts der Button **„↩ Rückgängig"** (nur wenn
`kann_zuruecksetzen`).

## Rückgängig machen (`/timeline/restore/`)

View: `nachweis/views.py` → `timeline_restore(request)` (`@require_POST`, `@login_required`).
Ausgelöst durch das kleine POST-Formular je Timeline-Zeile (mit `confirm()`-Rückfrage
und CSRF-Token). Übergeben wird nur die `id` des `LogEntry`.

### Ablauf

```text
POST /timeline/restore/  { id: <LogEntry.pk> }
  ├─ Superuser? sonst 403
  ├─ LogEntry laden (get_object_or_404)
  ├─ action == UPDATE?  sonst: Fehlermeldung „Löschungen aus Backup"
  ├─ Zielobjekt via content_type.model_class() + object_pk laden
  │     └─ existiert nicht mehr? → „bitte aus dem Backup wiederherstellen"
  ├─ pro geändertem Feld den ALTEN Wert (paar[0]) zurückschreiben:
  │     ├─ Feld existiert nicht (get_field wirft)      → skip
  │     ├─ f.is_relation oder nicht concrete            → skip
  │     └─ setattr(obj, feld, _coerce_alt(f, paar[0]))  → zurueck
  ├─ obj.save()
  └─ Erfolgsmeldung: welche Felder zurückgesetzt, welche übersprungen
```

### Was übersprungen wird – und warum

!!! warning "Nur nicht-relationale, konkrete Felder"
    Beim Zurücksetzen werden **Relations-Felder** (`f.is_relation`) und nicht-konkrete
    Felder übersprungen. Grund: `auditlog` protokolliert bei Fremdschlüsseln die
    *Repräsentation* (z. B. den Namen), nicht die ID – ein zuverlässiges automatisches
    Zurücksetzen ist damit nicht möglich. Solche Felder erscheinen in der
    Erfolgsmeldung unter *„Nicht automatisch: …"* und müssen manuell oder über das
    Backup korrigiert werden.

### Typ-Umwandlung: `_coerce_alt`

`auditlog` speichert Werte als String. `_coerce_alt(field, val)` bringt den alten Wert
zurück in den passenden Python-Typ des Feldes:

```python
def _coerce_alt(field, val):
    from django.db.models import BooleanField
    if val is None or val == "None":
        return None
    if isinstance(field, BooleanField):
        return str(val).strip().lower() in ("true", "1", "yes", "t", "ja")
    return field.to_python(val)
```

- `None` bzw. der String `"None"` → echtes `None`.
- Boolean-Felder werden gegen eine Liste wahrer Strings geprüft (u. a. `"ja"`, `"true"`, `"1"`).
- Alle übrigen Typen laufen über Djangos `field.to_python(val)`.

### Rückmeldungen an den Nutzer

| Situation | Meldung |
| --- | --- |
| Erfolg | `„<Objekt>" zurückgesetzt (<felder>).` ggf. `Nicht automatisch: <felder>.` |
| Kein Update | `Nur Änderungen (Updates) sind automatisch rücksetzbar; Löschungen aus Backup.` |
| Objekt gelöscht | `Objekt existiert nicht mehr – bitte aus dem Backup wiederherstellen.` |
| Save-Fehler | `Zurücksetzen fehlgeschlagen: <exception>` |

## Grenzen der In-App-Wiederherstellung

!!! tip "Wann Backup, wann Timeline?"
    - **Einzelnes Feld / einzelner Datensatz versehentlich geändert** → Timeline
      „Rückgängig". Schnell, ohne Ausfallzeit.
    - **Datensatz gelöscht**, **Relationen betroffen**, **mehrere Objekte /
      Zusammenhänge kaputt**, oder **Zustand vor mehreren Schritten** gewünscht →
      Gesamt-Restore über [Backup & Restore](backup-restore.md).

Die Timeline setzt immer nur **einen** `LogEntry` zurück (auf den Stand unmittelbar
davor). Mehrfach hintereinander erfolgte Änderungen müssen einzeln – in umgekehrter
Reihenfolge – zurückgesetzt werden, oder man greift zum Backup.

## Zugriff & Sichtbarkeit im Code

- **Sidebar** (`nachweis/templates/nachweis/base.html`): der Link „Wiederherstellung"
  steht in der Gruppe *Administration* und ist mit `{% if user.is_superuser %}` gekapselt –
  für User, Leitung, Verwaltung und den klientenfreien Admin also unsichtbar.
- **Views**: beide Funktionen prüfen zusätzlich serverseitig
  `if not request.user.is_superuser: return HttpResponseForbidden()`. Die
  UI-Sichtbarkeit ist also nur Komfort; der eigentliche Schutz sitzt in der View.

!!! note "Break-Glass-Kontext"
    Der Superuser `root` besitzt kein Mitarbeiter-Profil und ist ausdrücklich der
    technische Notzugang. Jede Nutzung der Timeline/Wiederherstellung ist damit ein
    bewusster Break-Glass-Vorgang und sollte im Betriebsprotokoll vermerkt werden.

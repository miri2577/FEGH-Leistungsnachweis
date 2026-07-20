"""Löschkonzept (DSGVO Art. 5/17, § 84 SGB X): Aufbewahrungsfristen berechnen,
fällige Klient*innen ermitteln, Fachdaten löschen und Stammdaten anonymisieren.

Zwei Stufen nach Ende der Betreuung:
  1) Fachdaten-Löschung: sobald die fachliche Frist (Fachakte) abgelaufen ist —
     Ziele/Berichte/Wirkung/Dokumente/Termine löschen, Art-9-Freitexte leeren.
  2) Voll-Anonymisierung: sobald ZUSÄTZLICH die steuerrechtliche Abrechnungsfrist
     abgelaufen ist — Stammdaten pseudonymisieren. Das Abrechnungsgerüst (Leistungs-
     zeiten, Monatsfreigaben, Rechnungen) bleibt bestehen, aber ohne Klartext-PII.

Nichts wird automatisch gelöscht: Der Rechnungslauf ist review-gestützt (Übersicht +
ausdrücklicher Anwendungs-Schritt), damit ein Mensch (Leitung/DSB) freigibt.
"""
from datetime import date

from django.db import transaction

from .models import (Klient, Status, Aufbewahrungsregel, AufbewahrungsKategorie,
                     Leistung, Monatsfreigabe, Ziel, Bericht, Wirkungseinschaetzung,
                     Dokument, Termin, Vorkommnis, KlientAbwesenheit, Belegung)

# Fallback-Fristen (Jahre), falls eine Regel (noch) nicht in der DB gepflegt ist.
# Die maßgeblichen Werte stehen als Aufbewahrungsregel-Datensätze in der DB.
# Rechtsstand Juli 2026 (siehe Migrations-Seed für die Rechtsgrundlagen):
#   - Buchungsbelege: 8 J. (seit BEG IV, 01.01.2025 – vorher 10)
#   - Fachakte EGH: 10 J. (Praxis, nicht spezialgesetzlich fixiert)
#   - Jugendhilfe: 70 J. nach Vollendung des 30. Lj. (§ 9b SGB VIII, seit 01.07.2025) –
#     greift für freie Träger nur bei entsprechender Leistungs-/Entgeltvereinbarung
#   - WTG-Doku stationär: 5 J. (§ 22 Abs. 4 WTG Berlin)
#   - Arbeitszeit/Dienstplan: 2 J. (§ 16 ArbZG / § 17 MiLoG)
_FALLBACK = {
    AufbewahrungsKategorie.ABRECHNUNG: 8,
    AufbewahrungsKategorie.LEISTUNGSNACHWEIS: 8,
    AufbewahrungsKategorie.KASSE: 10,
    AufbewahrungsKategorie.FACHDOKU_EGH: 10,
    AufbewahrungsKategorie.FACHDOKU_JUG: 70,
    AufbewahrungsKategorie.WTG: 5,
    AufbewahrungsKategorie.DOKUMENT: 10,
    AufbewahrungsKategorie.PERSONAL: 2,
}

# Lesezugriffs-Protokoll (Zugriffslog): eigene kurze Aufbewahrungsfrist – das Protokoll
# ist selbst personenbezogen (wer sah wann welche Akte), § 22 BDSG / Datenminimierung.
ZUGRIFFSLOG_FRIST_JAHRE = 1


def frist_jahre(kategorie) -> int:
    """Aufbewahrungsdauer (Jahre) einer Kategorie aus der DB, sonst Fallback."""
    r = Aufbewahrungsregel.objects.filter(kategorie=kategorie, aktiv=True).first()
    return r.jahre if r else _FALLBACK.get(kategorie, 10)


def _plus_jahre(d: date, jahre: int) -> date:
    """Datum + N Jahre (29.02. → 28.02. bei Nicht-Schaltjahr)."""
    try:
        return d.replace(year=d.year + jahre)
    except ValueError:
        return d.replace(month=2, day=28, year=d.year + jahre)


def betreuungsende(klient) -> date | None:
    """Stichtag „Ende der Betreuung" = spätestes belastbares End-/Kontaktdatum.
    Konservativ das Maximum, damit die Frist nie zu früh startet. None = unklar
    (dann nie fällig). Eine noch OFFENE Belegung (auszug=None) bedeutet: die Person
    ist weiter untergebracht → Ende unklar, blockiert die Frist."""
    if klient.belegungen.filter(auszug__isnull=True).exists():
        return None
    kandidaten = []
    if klient.kue_bis:
        kandidaten.append(klient.kue_bis)
    letzte_leistung = (klient.leistungen.order_by("-datum")
                       .values_list("datum", flat=True).first())
    if letzte_leistung:
        kandidaten.append(letzte_leistung)
    letzter_auszug = (klient.belegungen.exclude(auszug__isnull=True)
                      .order_by("-auszug").values_list("auszug", flat=True).first())
    if letzter_auszug:
        kandidaten.append(letzter_auszug)
    return max(kandidaten) if kandidaten else None


def _abrechnung_stichtag(klient) -> date | None:
    """Fristbeginn Abrechnung = Ende des Kalenderjahres des jüngsten Belegs
    (Rechnung/Freigabe/Leistung) — steuerrechtliche Fristen laufen ab Jahresende."""
    jahre = []
    letzte_freigabe = klient.freigaben.order_by("-jahr").values_list("jahr", flat=True).first()
    if letzte_freigabe:
        jahre.append(letzte_freigabe)
    letzte_leistung = (klient.leistungen.order_by("-datum")
                       .values_list("datum", flat=True).first())
    if letzte_leistung:
        jahre.append(letzte_leistung.year)
    return date(max(jahre), 12, 31) if jahre else None


def _fachbestand(klient) -> dict:
    """Zählung der personenbezogenen Fachdaten (für Übersicht/Report)."""
    return {
        "ziele": klient.ziele.count(),
        "berichte": klient.berichte.count(),
        "wirkung": klient.wirkungseinschaetzungen.count(),
        "dokumente": klient.dokumente.count(),
        "termine": klient.termine.count(),
        "vorkommnisse": klient.vorkommnisse.count(),
        "gruppen": klient.gruppen.count(),
        "doku_leistungen": klient.leistungen.exclude(dokumentation="").count(),
    }


def loeschstatus(klient, heute=None) -> dict:
    """Fristen-Status einer/eines Klient*in: Anker, Frei-ab-Daten, Fälligkeit, Bestand."""
    heute = heute or date.today()
    ende = betreuungsende(klient)
    fach_frei_ab = _plus_jahre(ende, frist_jahre(AufbewahrungsKategorie.FACHDOKU_EGH)) if ende else None
    abr_stichtag = _abrechnung_stichtag(klient)
    abr_frei_ab = _plus_jahre(abr_stichtag, frist_jahre(AufbewahrungsKategorie.ABRECHNUNG)) if abr_stichtag else None
    voll_frei_ab = max([d for d in (fach_frei_ab, abr_frei_ab) if d], default=None)
    # bereits (voll-)anonymisierte Datensätze sind nie erneut fällig
    beendet = klient.status == Status.BEENDIGUNG and not klient.anonymisiert_am
    return {
        "klient": klient,
        "beendet": beendet,
        "betreuungsende": ende,
        "fach_frei_ab": fach_frei_ab,
        "abrechnung_frei_ab": abr_frei_ab,
        "voll_frei_ab": voll_frei_ab,
        # fällig nur für beendete Betreuungen mit bekanntem Ende
        "fach_faellig": bool(beendet and fach_frei_ab and fach_frei_ab <= heute),
        "voll_faellig": bool(beendet and voll_frei_ab and voll_frei_ab <= heute),
        "bestand": _fachbestand(klient),
    }


def faellige_klienten(heute=None):
    """Beendete Klient*innen, deren Fachdaten-Frist abgelaufen ist (löschreif)."""
    heute = heute or date.today()
    out = []
    for k in (Klient.objects.filter(status=Status.BEENDIGUNG, anonymisiert_am__isnull=True)
              .prefetch_related("leistungen", "belegungen", "freigaben")):
        st = loeschstatus(k, heute)
        if st["fach_faellig"]:
            out.append(st)
    return out


def zugriffslog_aufraeumen(heute=None) -> int:
    """Löscht Lesezugriffs-Protokolleinträge, die älter als ZUGRIFFSLOG_FRIST_JAHRE sind.
    Das Protokoll ist selbst personenbezogen und unterliegt einer eigenen kurzen Frist.
    Rückgabe: Anzahl gelöschter Einträge. Unabhängig vom Klient-Status (reine Zeitfrist)."""
    from .models import Zugriffslog
    heute = heute or date.today()
    grenze = _plus_jahre(heute, -ZUGRIFFSLOG_FRIST_JAHRE)
    geloescht, _ = Zugriffslog.objects.filter(zeit__date__lt=grenze).delete()
    return geloescht


def _scrub_auditlog(model, pks):
    """Löscht Auditlog-Einträge (LogEntry) der genannten Datensätze eines Modells –
    entfernt die dort als Alt-Werte gespeicherten Klartexte (Name/Tätigkeit …), damit
    die Anonymisierung wirklich irreversibel ist (§ 84 SGB X / Art. 17 DSGVO)."""
    pks = [str(p) for p in pks if p is not None]
    if not pks:
        return
    from django.contrib.contenttypes.models import ContentType
    from auditlog.models import LogEntry
    ct = ContentType.objects.get_for_model(model)
    LogEntry.objects.filter(content_type=ct, object_pk__in=pks).delete()


def _scrub_history(model, pks):
    """Löscht die simple_history-Snapshots (Historical<Model>) der genannten Datensätze.
    Auch simple_history speichert je Änderung die Alt-Werte (Freitexte/Namen) und beim
    Löschen einen zusätzlichen Lösch-Snapshot – ohne dieses Scrubbing wäre die Anonymisierung
    über die Änderungshistorie re-identifizierbar und damit NICHT irreversibel
    (§ 84 SGB X / Art. 17 DSGVO). No-op, wenn das Modell keine History führt."""
    mgr = getattr(model, "history", None)
    if mgr is None:
        return
    pks = [p for p in pks if p is not None]
    if pks:
        mgr.filter(id__in=pks).delete()


@transaction.atomic
def anonymisieren(klient, stufe="fachdaten", apply=False, heute=None) -> dict:
    """Löscht Fachdaten (und bei stufe='voll' zusätzlich die Stammdaten-PII).
    apply=False = Trockenlauf (nur Report, keine Änderung). Gibt einen Report zurück.

    stufe='fachdaten': Ziele/Berichte/Wirkung/Dokumente/Termine löschen, Art-9-
      Freitexte auf verbleibenden Belegen leeren, Gruppen-Teilnahmen lösen; das
      Abrechnungsgerüst bleibt. Auditlog-Einträge der betroffenen Datensätze werden
      mitentfernt (sonst blieben Alt-Werte als Klartext im Änderungsprotokoll).
    stufe='voll': zusätzlich Klient-Stammdaten + Bewilligungs-Freitexte anonymisieren
      und die Auditlog-Historie des Klienten löschen; setzt anonymisiert_am.
    """
    from .models import (KlientAbwesenheit, Ziel, Bericht, Wirkungseinschaetzung,
                         Dokument, Termin, Vorkommnis, Leistung, Belegung, Bewilligung,
                         FEM, Bedarfsermittlung, BedarfsEinschaetzung,
                         SelbstzahlerRechnung, Wohnkostenvereinbarung)
    heute = heute or date.today()
    report = {"klient": str(klient), "stufe": stufe, "apply": apply, "aktionen": []}

    def tue(label, fn):
        report["aktionen"].append(label)
        if apply:
            fn()

    # pks der zu LÖSCHENDEN Fachobjekte vorab merken (fürs Auditlog-Scrubbing danach)
    del_pks = {M: list(getattr(klient, rel).values_list("pk", flat=True))
               for rel, M in (("dokumente", Dokument), ("ziele", Ziel),
                              ("berichte", Bericht),
                              ("wirkungseinschaetzungen", Wirkungseinschaetzung),
                              ("termine", Termin), ("vorkommnisse", Vorkommnis))}
    # pks ALLER klientenbezogenen historisierten Fach-Datensätze vorab merken – auch die
    # beim Löschen entstehenden Lösch-Snapshots werden so später zuverlässig entfernt.
    hist_pks_fach = {
        Ziel: list(klient.ziele.values_list("pk", flat=True)),
        Bericht: list(klient.berichte.values_list("pk", flat=True)),
        Wirkungseinschaetzung: list(klient.wirkungseinschaetzungen.values_list("pk", flat=True)),
        FEM: list(klient.fem_massnahmen.values_list("pk", flat=True)),
        Vorkommnis: list(klient.vorkommnisse.values_list("pk", flat=True)),
        Belegung: list(klient.belegungen.values_list("pk", flat=True)),
        Bedarfsermittlung: list(klient.bedarfsermittlungen.values_list("pk", flat=True)),
        BedarfsEinschaetzung: list(BedarfsEinschaetzung.objects.filter(
            bedarfsermittlung__klient=klient).values_list("pk", flat=True)),
        KlientAbwesenheit: list(KlientAbwesenheit.objects.filter(
            belegung__klient=klient).values_list("pk", flat=True)),
    }

    # 1) Fachobjekte löschen (Dokument.delete räumt die Datei mit weg -> einzeln)
    n_dok = klient.dokumente.count()
    if n_dok:
        tue(f"{n_dok} Dokument(e) inkl. Dateien löschen",
            lambda: [d.delete() for d in klient.dokumente.all()])
    for rel, label in (("ziele", "Ziel(e)"), ("berichte", "Bericht(e)"),
                       ("wirkungseinschaetzungen", "Wirkungseinschätzung(en)"),
                       ("termine", "Termin(e)"), ("kontakte", "Kontaktperson(en)"),
                       ("konten", "Klientenkonto/-konten"),
                       ("fem_massnahmen", "FEM-Dokumentation(en)"),
                       ("bedarfsermittlungen", "ICF-Bedarfsermittlung(en)")):
        n = getattr(klient, rel).count()
        if n:
            tue(f"{n} {label} löschen", lambda r=rel: getattr(klient, r).all().delete())

    # Gruppen-Teilnahmen lösen (geteilte Gruppen bleiben, nur die M2M-Zeile geht)
    n_grp = klient.gruppen.count()
    if n_grp:
        tue(f"{n_grp} Gruppen-Teilnahme(n) lösen", lambda: klient.gruppen.clear())

    # 2) Art-9-Freitexte auf verbleibenden (abrechnungsrelevanten) Belegen leeren
    n_doku = klient.leistungen.exclude(dokumentation="").count()
    n_notiz = klient.leistungen.exclude(notiz="").count()
    n_sig = klient.leistungen.exclude(unterschrift="").count()
    if n_doku or n_notiz or n_sig:
        tue(f"Freitexte an {klient.leistungen.count()} Leistung(en) leeren "
            f"(Doku {n_doku}, Notiz {n_notiz}, Unterschrift {n_sig})",
            lambda: klient.leistungen.update(dokumentation="", notiz="", unterschrift="",
                                             unterschrieben_am=None, taetigkeit=""))
    n_vork = klient.vorkommnisse.count()
    if n_vork:
        tue(f"Freitexte an {n_vork} Vorkommnis(sen) leeren",
            lambda: klient.vorkommnisse.update(beschreibung="", sofortmassnahmen="", massnahmen=""))
    # Klient-Abwesenheiten hängen an den Belegungen (KlientAbwesenheit.belegung).
    abw_qs = KlientAbwesenheit.objects.filter(belegung__klient=klient)
    n_abw = abw_qs.exclude(kommentar="").count()
    if n_abw:
        tue(f"Kommentare an {n_abw} Klient-Abwesenheit(en) leeren",
            lambda: abw_qs.update(kommentar=""))
    n_bel = klient.belegungen.exclude(kommentar="").count()
    if n_bel:
        tue(f"Kommentare an {n_bel} Belegung(en) leeren",
            lambda: klient.belegungen.update(kommentar=""))

    # 3) Änderungs-Protokolle der Fachdaten-Ebene scrubben, damit keine Alt-Werte
    #    (Klartext-Freitexte/Namen) als re-identifizierbare Historie zurückbleiben:
    #    sowohl das auditlog (LogEntry) als auch die simple_history-Snapshots.
    def _scrub_fach():
        for M, pks in del_pks.items():
            _scrub_auditlog(M, pks)
        _scrub_auditlog(Leistung, klient.leistungen.values_list("pk", flat=True))
        _scrub_auditlog(Belegung, klient.belegungen.values_list("pk", flat=True))
        for M, pks in hist_pks_fach.items():
            _scrub_history(M, pks)
    tue("Änderungsprotokolle (Auditlog + Historie) der Fachdaten bereinigen", _scrub_fach)

    # 4) Voll-Anonymisierung: Stammdaten + Bewilligungs-Freitexte, Marker, Auditlog
    if stufe == "voll":
        n_bew = klient.bewilligungen.count()
        if n_bew:
            tue(f"Freitexte/Aktenzeichen an {n_bew} Bewilligung(en) leeren",
                lambda: klient.bewilligungen.update(kommentar="", aktenzeichen=""))
        # Selbstzahler-Rechnungen (PROTECT → bleiben als Beleg) tragen Klarname + Anschrift
        # der Bewohner*in – Personenbezug entfernen, Abrechnungsgerüst behalten.
        n_sz = klient.selbstzahler_rechnungen.count()
        if n_sz:
            tue(f"Name/Anschrift an {n_sz} Selbstzahler-Rechnung(en) anonymisieren",
                lambda: klient.selbstzahler_rechnungen.update(
                    empfaenger=f"Gelöscht #{klient.pk}", empfaenger_anschrift="", notiz=""))
        n_wk = klient.wohnkosten.exclude(notiz="").count()
        if n_wk:
            tue(f"Notiz an {n_wk} Wohnkostenvereinbarung(en) leeren",
                lambda: klient.wohnkosten.update(notiz=""))
        tue(f"Stammdaten anonymisieren (→ „Gelöscht #{klient.pk}“)",
            lambda: _pseudonymisiere_stammdaten(klient, heute))
        tue("Auditlog + Historie (Klient, Bewilligungen, Selbstzahler, Wohnkosten) löschen", lambda: (
            _scrub_auditlog(Klient, [klient.pk]),
            _scrub_auditlog(Bewilligung, list(klient.bewilligungen.values_list("pk", flat=True))),
            _scrub_history(Bewilligung, list(klient.bewilligungen.values_list("pk", flat=True))),
            _scrub_history(SelbstzahlerRechnung,
                           list(klient.selbstzahler_rechnungen.values_list("pk", flat=True))),
            _scrub_history(Wohnkostenvereinbarung,
                           list(klient.wohnkosten.values_list("pk", flat=True)))))

    return report


def _pseudonymisiere_stammdaten(klient, heute=None):
    """Ersetzt alle personenbeziehbaren Stammdaten-Felder durch neutrale Platzhalter.
    Der Datensatz bleibt bestehen (PROTECT-Referenzen aus der Abrechnung), enthält
    aber keinen Personenbezug mehr. Setzt den Anonymisierungs-Marker."""
    from django.utils import timezone
    klient.nachname = f"Gelöscht #{klient.pk}"
    klient.vorname = ""
    klient.kuerzel = ""
    klient.geburtsdatum = None
    klient.person_id = ""
    klient.thfd = ""
    klient.kommentar = ""
    klient.kostentraeger = ""
    # Anschrift + gesetzliche Betreuung (personenbeziehbar) mit anonymisieren
    klient.strasse = klient.plz = klient.ort = ""
    klient.betreuung_name = klient.betreuung_telefon = klient.betreuung_umfang = ""
    klient.betreuung_bis = None
    klient.anonymisiert_am = timezone.now()
    klient.save(update_fields=["nachname", "vorname", "kuerzel", "geburtsdatum",
                               "person_id", "thfd", "kommentar", "kostentraeger",
                               "strasse", "plz", "ort", "betreuung_name",
                               "betreuung_telefon", "betreuung_umfang", "betreuung_bis",
                               "anonymisiert_am"])

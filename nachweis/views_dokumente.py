"""Dokumentenablage (DMS light): Dateien je Klient*in, optional an der Bewilligung.

Sicherheitsmodell:
- Zugriff exakt wie Ziele/Berichte über `services.klienten_fuer` (Team/Vertretung,
  Leitung); Verwaltung/Admin haben keinen Klientenbezug.
- Upload nur Whitelist-Endungen, Magic-Bytes-Prüfung, Größenlimit.
- Download NIE über MEDIA_URL, sondern nur über die gescopte View (FileResponse).
- Löschen: Leitung oder die hochladende Person.
"""
import os

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpResponseForbidden
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_POST

from . import services
from .models import Dokument, DokumentKategorie, Klient


def _int0(val):
    try:
        return int(val)
    except (TypeError, ValueError):
        return 0


def _upload_pruefen(f):
    """Whitelist + Magic Bytes + Größe. Gibt Fehlertext zurück (None = ok)."""
    ext = os.path.splitext(f.name)[1].lower()
    if ext not in Dokument.ERLAUBT:
        erlaubt = ", ".join(sorted(Dokument.ERLAUBT))
        return f"Dateityp {ext or '(ohne Endung)'} nicht erlaubt. Erlaubt: {erlaubt}."
    if f.size > Dokument.MAX_GROESSE:
        return "Datei zu groß (max. 15 MB)."
    if f.size == 0:
        return "Die Datei ist leer."
    magic = Dokument.ERLAUBT[ext]
    if magic:
        kopf = f.read(8)
        f.seek(0)
        if not any(kopf.startswith(m) for m in magic):
            return f"Der Dateiinhalt passt nicht zur Endung {ext}."
    return None


@login_required
def dokumente(request, pk):
    """Dokumente-Seite je Klient*in: Liste + Upload."""
    klient = get_object_or_404(services.klienten_fuer(request.user), pk=pk)
    ma = services.mitarbeiter_fuer(request.user)
    ist_leitung = services.ist_leitung(request.user)
    docs = list(klient.dokumente.select_related("bewilligung", "hochgeladen_von"))
    for d in docs:
        d.darf_loeschen = ist_leitung or (ma and d.hochgeladen_von_id == ma.id)
    return render(request, "nachweis/dokumente.html", {
        "aktiv": "belegungsliste" if ist_leitung else "start",
        "klient": klient, "dokumente": docs,
        "kategorien": DokumentKategorie.choices,
        "bewilligungen": list(klient.bewilligungen.order_by("-gueltig_von")),
        "ist_leitung": ist_leitung,
        "max_mb": Dokument.MAX_GROESSE // (1024 * 1024),
        "endungen": ",".join(sorted(Dokument.ERLAUBT)),
    })


@require_POST
@login_required
def dokument_hochladen(request):
    klient = get_object_or_404(services.klienten_fuer(request.user),
                               pk=_int0(request.POST.get("klient")))
    f = request.FILES.get("datei")
    if not f:
        messages.error(request, "Bitte eine Datei auswählen.")
        return redirect("nachweis:dokumente", pk=klient.pk)
    fehler = _upload_pruefen(f)
    if fehler:
        messages.error(request, fehler)
        return redirect("nachweis:dokumente", pk=klient.pk)
    kategorie = request.POST.get("kategorie")
    bew = klient.bewilligungen.filter(
        pk=_int0(request.POST.get("bewilligung"))).first()
    name = (request.POST.get("name") or "").strip() or f.name
    Dokument.objects.create(
        klient=klient, bewilligung=bew,
        kategorie=(kategorie if kategorie in DokumentKategorie.values
                   else DokumentKategorie.SONSTIG),
        name=name[:200], datei=f, groesse=f.size,
        notiz=(request.POST.get("notiz") or "").strip()[:200],
        hochgeladen_von=services.mitarbeiter_fuer(request.user))
    messages.success(request, f"Dokument „{name[:60]}“ abgelegt.")
    return redirect("nachweis:dokumente", pk=klient.pk)


def _saubere_datei(d, request, *, inline):
    """FileResponse für ein Dokument (Download oder Inline). Team-Scoping über die
    Query. Setzt bewusst den erwarteten MIME-Typ + nosniff (kein Content-Sniffing)."""
    try:
        handle = d.datei.open("rb")
    except (FileNotFoundError, ValueError):
        raise Http404("Datei nicht mehr vorhanden.")
    ext = os.path.splitext(d.datei.name)[1]
    stamm = "".join(c for c in os.path.splitext(d.name)[0]
                    if c.isalnum() or c in "._- ")[:80].strip() or "dokument"
    resp = FileResponse(handle, as_attachment=not inline, filename=f"{stamm}{ext}",
                        content_type=d.mime if inline else None)
    # Content-Sniffing verhindern (Datei wird nur als der deklarierte Typ interpretiert)
    resp["X-Content-Type-Options"] = "nosniff"
    if inline:
        # Eigene CSP für die Inline-Datei: die globale Policy setzt frame-ancestors 'none'
        # (blockte das Einbetten ins eigene iframe). Hier: nur die eigene Origin darf
        # framen, die Datei selbst lädt nichts nach. Middleware überschreibt nicht,
        # wenn der Header bereits gesetzt ist.
        resp["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'self'"
    return resp


@login_required
def dokument_download(request, pk):
    d = get_object_or_404(Dokument.objects.filter(
        klient__in=services.klienten_fuer(request.user)), pk=pk)
    return _saubere_datei(d, request, inline=False)


@login_required
def dokument_inline(request, pk):
    """Liefert die Datei zur Inline-Anzeige (Content-Disposition: inline) – Quelle
    für iframe/img in der Ansichtsseite. Nur vorschaubare Typen (PDF/Bild/Text)."""
    d = get_object_or_404(Dokument.objects.filter(
        klient__in=services.klienten_fuer(request.user)), pk=pk)
    if not d.vorschau_typ:
        raise Http404("Für diesen Dateityp gibt es keine Inline-Vorschau.")
    return _saubere_datei(d, request, inline=True)


@login_required
def dokument_ansicht(request, pk):
    """Ansichtsseite: bettet PDF (iframe), Bild (img) oder Text (iframe) direkt in
    die App ein; Office-Formate bekommen einen Download-Hinweis."""
    d = get_object_or_404(Dokument.objects.select_related("klient").filter(
        klient__in=services.klienten_fuer(request.user)), pk=pk)
    return render(request, "nachweis/dokument_ansicht.html", {
        "aktiv": "belegungsliste" if services.ist_leitung(request.user) else "start",
        "dok": d, "klient": d.klient,
    })


@require_POST
@login_required
def dokument_loeschen(request):
    d = get_object_or_404(Dokument.objects.filter(
        klient__in=services.klienten_fuer(request.user)),
        pk=_int0(request.POST.get("id")))
    ma = services.mitarbeiter_fuer(request.user)
    if not (services.ist_leitung(request.user)
            or (ma and d.hochgeladen_von_id == ma.id)):
        return HttpResponseForbidden()
    kpk, name = d.klient_id, d.name
    d.delete()
    messages.success(request, f"Dokument „{name}“ gelöscht.")
    return redirect("nachweis:dokumente", pk=kpk)

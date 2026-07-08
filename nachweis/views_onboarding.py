"""Onboarding: Mitarbeiter*innen anlegen/verwalten (Admin) + Konto-Aktivierung (Nutzer).

Ablauf:
  Admin legt Konto an (ohne Passwort) -> Aktivierungslink anzeigen/mailen
  -> Nutzer öffnet Link, vergibt eigenes Passwort -> (falls Pflicht) 2FA einrichten.
"""
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.db.models import ProtectedError
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.views.decorators.http import require_POST

from . import accounts, services
from .models import Mitarbeiter, Team, Teamtyp, Rolle

User = get_user_model()


def _nur_admin(request):
    return services.ist_admin(request.user) or request.user.is_superuser


# ---------------------------------------------------------------- Admin: Teams
@login_required
def teams_liste(request):
    if not _nur_admin(request):
        return HttpResponseForbidden()
    teams = [{"t": t, "mitglieder": t.mitglieder.count(), "klienten": t.klienten.count()}
             for t in Team.objects.all()]
    bearbeiten = Team.objects.filter(pk=request.GET.get("edit")).first() if request.GET.get("edit") else None
    return render(request, "nachweis/teams_liste.html", {
        "aktiv": "teams", "teams": teams, "typen": Teamtyp.choices, "bearbeiten": bearbeiten,
    })


@require_POST
@login_required
def team_speichern(request):
    if not _nur_admin(request):
        return HttpResponseForbidden()
    name = (request.POST.get("name") or "").strip()
    typ = request.POST.get("typ")
    if not name or typ not in Teamtyp.values:
        messages.error(request, "Bitte Name und Typ angeben.")
        return redirect("nachweis:teams_liste")
    tid = request.POST.get("id")
    if tid:
        t = get_object_or_404(Team, pk=tid)
        t.name, t.typ = name, typ
        t.aktiv = request.POST.get("aktiv") == "on"
        t.save()
        messages.success(request, f"Team „{name}“ gespeichert.")
    else:
        if Team.objects.filter(name=name).exists():
            messages.error(request, "Ein Team mit diesem Namen existiert bereits.")
        else:
            Team.objects.create(name=name, typ=typ)
            messages.success(request, f"Team „{name}“ angelegt.")
    return redirect("nachweis:teams_liste")


@require_POST
@login_required
def team_aktion(request):
    if not _nur_admin(request):
        return HttpResponseForbidden()
    t = get_object_or_404(Team, pk=request.POST.get("id"))
    if request.POST.get("aktion") == "toggle":
        t.aktiv = not t.aktiv
        t.save(update_fields=["aktiv"])
        messages.success(request, f"Team „{t.name}“ {'aktiviert' if t.aktiv else 'deaktiviert'}.")
    elif request.POST.get("aktion") == "loeschen":
        if t.mitglieder.exists() or t.klienten.exists() or hasattr(t, "kasse"):
            messages.error(request, "Team nicht löschbar – es sind noch Mitglieder, Klient*innen oder eine Kasse zugeordnet.")
        else:
            try:
                name = t.name; t.delete()
                messages.success(request, f"Team „{name}“ gelöscht.")
            except ProtectedError:
                messages.error(request, "Team nicht löschbar – es hängen noch geschützte Datensätze daran.")
    return redirect("nachweis:teams_liste")


def _mail_link(user, link, betreff, art):
    """Versucht, den Link zu mailen. Rückgabe: True bei Versand, sonst False."""
    if not (settings.EMAIL_AKTIV and user.email):
        return False
    try:
        send_mail(
            betreff,
            f"Hallo {user.first_name or user.username},\n\n"
            f"für den FEGH-Leistungsnachweis wurde ein Zugang für dich {art}.\n"
            f"Bitte öffne den folgenden Link und vergib dein persönliches Passwort "
            f"(7 Tage gültig):\n\n{link}\n\n"
            f"Dein Benutzername: {user.username}\n\n"
            f"Viele Grüße\nFEGH-Leistungsnachweis",
            settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=True)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- Admin: Liste
@login_required
def mitarbeiter_liste(request):
    if not _nur_admin(request):
        return HttpResponseForbidden()
    leute = []
    for m in Mitarbeiter.objects.select_related("user", "team").prefetch_related("leitet").all():
        u = m.user
        geleitet = list(m.leitet.all())
        leute.append({
            "m": m,
            "hat_passwort": bool(u and u.has_usable_password()),
            "hat_2fa": bool(u and u.totpdevice_set.filter(confirmed=True).exists()),
            "aktiv": bool(u and u.is_active),
            "leitet": geleitet,
            # Leitung ohne geleitetes Team UND ohne eigenes Team -> sieht keine Klient*innen
            "leitung_ohne_team": m.rolle == Rolle.LEITUNG and not geleitet and not m.team_id,
        })
    return render(request, "nachweis/mitarbeiter_liste.html", {
        "aktiv": "mitarbeiter", "leute": leute,
    })


# ---------------------------------------------------------------- Admin: Neu anlegen
@login_required
def mitarbeiter_neu(request):
    if not _nur_admin(request):
        return HttpResponseForbidden()
    if request.method == "POST":
        vorname = (request.POST.get("vorname") or "").strip()
        nachname = (request.POST.get("nachname") or "").strip()
        rolle = request.POST.get("rolle")
        team_id = request.POST.get("team")
        email = (request.POST.get("email") or "").strip()
        if not nachname or rolle not in Rolle.values:
            messages.error(request, "Bitte mindestens Nachname und Rolle angeben.")
        else:
            team = Team.objects.filter(pk=team_id).first() if (team_id or "").isdigit() else None
            user = accounts.konto_anlegen(nachname, vorname, rolle, email)
            m = Mitarbeiter.objects.create(
                user=user, name=nachname, vorname=vorname,
                kuerzel=(nachname[:3] + vorname[:2]).lower(), rolle=rolle, team=team,
                wochenstunden=request.POST.get("wochenstunden") or 39,
                urlaubstage=request.POST.get("urlaubstage") or 30)
            link = accounts.aktivierungs_link(request, user)
            gemailt = _mail_link(user, link, "Dein Zugang zum FEGH-Leistungsnachweis", "angelegt")
            return render(request, "nachweis/mitarbeiter_neu_ok.html", {
                "aktiv": "mitarbeiter", "m": m, "link": link,
                "gemailt": gemailt, "email": email,
            })
    return render(request, "nachweis/mitarbeiter_neu.html", {
        "aktiv": "mitarbeiter",
        "teams": Team.objects.all(),
        "rollen": Rolle.choices,
    })


# ---------------------------------------------------------------- Admin: Bearbeiten
@login_required
def mitarbeiter_bearbeiten(request, pk):
    """Rolle, Team-Zugehörigkeit, geleitete Teams (nur Leitung) und Stammwerte
    pflegen – ersetzt den Django-Admin. Wichtig: Hier wird die Teamleitung gesetzt,
    ohne die die Leitung keine Klient*innen ihres Teams sieht/anlegen kann."""
    if not _nur_admin(request):
        return HttpResponseForbidden()
    m = get_object_or_404(Mitarbeiter, pk=pk)
    # Aufgabentrennung (ISO A.5.3 / DSGVO): Ein Admin darf die eigene Rolle, das
    # eigene Team und die eigene Teamleitung NICHT ändern – sonst könnte er sich
    # selbst zur Leitung machen und so Klienten-(Art-9-)Zugriff erlangen. Fremde
    # Konten darf er weiterhin verwalten (legitime Kontoführung).
    selbst = (m == services.mitarbeiter_fuer(request.user))
    if request.method == "POST":
        m.name = (request.POST.get("nachname") or m.name).strip()
        m.vorname = (request.POST.get("vorname") or "").strip()
        if not selbst:
            rolle = request.POST.get("rolle")
            if rolle in Rolle.values:
                m.rolle = rolle
            tid = request.POST.get("team")
            m.team = Team.objects.filter(pk=tid).first() if (tid or "").isdigit() else None
        try:
            m.wochenstunden = request.POST.get("wochenstunden") or m.wochenstunden
            m.urlaubstage = int(request.POST.get("urlaubstage") or m.urlaubstage)
        except (TypeError, ValueError):
            pass
        m.save()
        if not selbst:
            # Geleitete Teams nur für Rolle Leitung; sonst leeren.
            if m.rolle == Rolle.LEITUNG:
                ids = [int(i) for i in request.POST.getlist("leitet") if i.isdigit()]
                m.leitet.set(Team.objects.filter(pk__in=ids))
            else:
                m.leitet.clear()
            messages.success(request, f"{m} gespeichert.")
        else:
            messages.info(request, "Gespeichert. Hinweis: Die eigene Rolle, das eigene Team und die "
                          "eigene Teamleitung lassen sich aus Sicherheitsgründen (Aufgabentrennung) "
                          "nicht selbst ändern – das muss ein anderes Administrations-Konto vornehmen.")
        return redirect("nachweis:mitarbeiter_liste")
    return render(request, "nachweis/mitarbeiter_bearbeiten.html", {
        "aktiv": "mitarbeiter", "m": m, "selbst": selbst,
        "teams": Team.objects.all(),
        "rollen": Rolle.choices,
        "geleitet_ids": set(m.leitet.values_list("id", flat=True)),
    })


# ---------------------------------------------------------------- Admin: Aktionen
@require_POST
@login_required
def mitarbeiter_aktion(request):
    if not _nur_admin(request):
        return HttpResponseForbidden()
    m = get_object_or_404(Mitarbeiter, pk=request.POST.get("id"))
    aktion = request.POST.get("aktion")
    u = m.user
    if not u:
        messages.error(request, "Kein Login verknüpft.")
        return redirect("nachweis:mitarbeiter_liste")

    if aktion == "reset_link":
        link = accounts.aktivierungs_link(request, u)
        gemailt = _mail_link(u, link, "Passwort neu setzen – FEGH-Leistungsnachweis", "zurückgesetzt")
        return render(request, "nachweis/mitarbeiter_neu_ok.html", {
            "aktiv": "mitarbeiter", "m": m, "link": link, "gemailt": gemailt,
            "email": u.email, "reset": True,
        })
    if aktion == "twofa_reset":
        u.totpdevice_set.all().delete()
        from django_otp.plugins.otp_static.models import StaticDevice
        StaticDevice.objects.filter(user=u).delete()
        messages.success(request, f"2FA für {m} zurückgesetzt – wird beim nächsten Login neu eingerichtet.")
    elif aktion == "deaktivieren":
        u.is_active = False; u.save(update_fields=["is_active"])
        m.aktiv = False; m.save(update_fields=["aktiv"])
        messages.success(request, f"{m} deaktiviert (Login gesperrt).")
    elif aktion == "aktivieren":
        u.is_active = True; u.save(update_fields=["is_active"])
        m.aktiv = True; m.save(update_fields=["aktiv"])
        messages.success(request, f"{m} wieder aktiviert.")
    return redirect("nachweis:mitarbeiter_liste")


# ---------------------------------------------------------------- Nutzer: Aktivierung (öffentlich)
def aktivieren(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    gueltig = user is not None and default_token_generator.check_token(user, token)
    # Offboarding-Schutz (ISO A.8.3): Ein bewusst deaktiviertes Konto (Mitarbeiter.aktiv=False)
    # darf sich NICHT per (noch gültigem) Aktivierungslink selbst reaktivieren. Wiedereinstellung
    # läuft über die Admin-Aktion „Entsperren" – erst danach greift ein neuer Link.
    if gueltig:
        prof = Mitarbeiter.objects.filter(user=user).first()
        if prof is not None and not prof.aktiv:
            gueltig = False
    if not gueltig:
        return render(request, "nachweis/aktivieren.html", {"ungueltig": True})

    if request.method == "POST":
        form = SetPasswordForm(user, request.POST)
        if form.is_valid():
            form.save()
            user.is_active = True
            user.save(update_fields=["is_active"])
            messages.success(request, "Passwort gesetzt – bitte melde dich jetzt an.")
            return redirect("nachweis:login")
    else:
        form = SetPasswordForm(user)
    return render(request, "nachweis/aktivieren.html", {"form": form, "benutzername": user.username})

"""Struktureller Schutz (Audit P4): JEDE Finanz-/Admin-Route ist für USER (Betreuer)
gesperrt. Fängt eine künftige View ab, bei der das Rollen-Gate vergessen wurde – denn
die Gates liegen als kopierte if-Zeilen in den Views, nicht zentral."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse, get_resolver, NoReverseMatch

from . import views_abrechnung, views_onboarding
from .models import Team, Teamtyp, Mitarbeiter, Rolle

User = get_user_model()


def _routen_der_module(module_namen):
    """(name, Anzahl URL-Args) aller nachweis-Routen, deren View in den Modulen liegt."""
    out = []
    for p in get_resolver().url_patterns:
        for sp in getattr(p, "url_patterns", [p]):
            cb = getattr(sp, "callback", None)
            if cb and getattr(cb, "__module__", "") in module_namen and sp.name:
                out.append((sp.name, sp.pattern.regex.groups))
    return out


class FinanzAdminRoutenGesperrtTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="T", typ=Teamtyp.BEW)
        u = User.objects.create_user("betr", password="x")
        Mitarbeiter.objects.create(user=u, name="B", rolle=Rolle.USER, team=self.team, kuerzel="b")
        self.client.force_login(u)

    # Routen dieser Module, die für USER (Betreuer/Leitung) BEWUSST offen sind – jede hier
    # ist einzeln als legitim geprüft. Alles andere MUSS gesperrt sein; eine neue Finanz-/
    # Admin-View ohne Gate fällt hier auf (dann Gate ergänzen ODER bewusst hier eintragen).
    OFFEN_FUER_USER = {
        "abrechnung",        # Monatsübersicht der eigenen Klient*innen (MA/Leitung)
        "freigabe_aktion",   # Monat "fertig" melden / Leitung gibt frei
        "aktivieren",        # öffentliche Konto-Aktivierung (kein Login)
    }

    def test_keine_route_fuer_user_offen(self):
        module = {views_abrechnung.__name__, views_onboarding.__name__}
        routen = _routen_der_module(module)
        self.assertGreater(len(routen), 20)          # Selbstschutz: Routen wurden gefunden
        start, login = reverse("nachweis:start"), reverse("nachweis:login")
        loecher = []
        for name, nargs in routen:
            if name in self.OFFEN_FUER_USER:
                continue
            try:
                url = reverse(f"nachweis:{name}", args=[1] * nargs)
            except NoReverseMatch:
                continue
            for meth in ("get", "post"):
                resp = getattr(self.client, meth)(url)
                if resp.status_code == 405:          # Methode nicht erlaubt -> andere probieren
                    continue
                gesperrt = (resp.status_code == 403 or
                            (resp.status_code == 302 and
                             (start in resp.url or login in resp.url or "2fa" in resp.url)))
                if not gesperrt:
                    loecher.append(f"{name}[{meth}]->{resp.status_code}")
                break
        self.assertEqual(loecher, [], "Ungeschützte Finanz-/Admin-Routen: " + ", ".join(loecher))

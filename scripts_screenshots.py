"""Erzeugt App-Screenshots mit Demo-Daten für die MkDocs-Doku (docs/assets/screenshots/).
Lokaler runserver muss laufen (http://127.0.0.1:8000). Login je Rolle, Demo-Passwort."""
import os
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
OUT = "docs/assets/screenshots"
PW = "demo12345"
K = 697  # Demo-Klient mit Zielen + Bewilligung (WG Lindenhof, für berger sichtbar)
os.makedirs(OUT, exist_ok=True)

# (rolle, [(pfad, datei, full_page)])
PLAN = [
    ("neumann", [
        ("/", "mein-ueberblick.png", True),
        ("/erfassung/", "erfassung.png", False),
        ("/arbeitszeit/", "arbeitszeit.png", False),
    ]),
    ("berger", [
        ("/belegungsliste/", "belegungsliste.png", False),
        ("/kalender/", "kalender.png", False),
        ("/controlling/", "controlling.png", True),
        ("/fachleistungsstunden/", "dashboard-fls.png", True),
        (f"/klient/{K}/", "fallakte.png", True),
        (f"/belegungsliste/{K}/bewilligungen/", "bewilligungen.png", False),
        (f"/ziele/{K}/", "ziele.png", True),
        (f"/wirkung/{K}/", "wirkung.png", True),
        (f"/bedarf/{K}/", "bedarf.png", True),
        ("/kasse/", "kasse.png", False),
    ]),
    ("peters", [
        ("/rechnungen/", "rechnungen.png", True),
    ]),
    ("sander", [
        ("/mitarbeiter/", "mitarbeiter.png", False),
        ("/parameter/", "parameter.png", True),
    ]),
]


def login(page, user):
    page.goto(f"{BASE}/login/", wait_until="domcontentloaded")
    page.fill("#id_username", user)
    page.fill("#id_password", PW)
    page.click("button[type=submit]")
    page.wait_for_load_state("networkidle")
    assert "/login" not in page.url, f"Login fehlgeschlagen für {user} (URL {page.url})"


made, fehler = [], []
with sync_playwright() as p:
    browser = p.chromium.launch()
    for user, ziele in PLAN:
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page = ctx.new_page()
        try:
            login(page, user)
        except Exception as e:
            fehler.append(f"LOGIN {user}: {e!r}")
            ctx.close(); continue
        for pfad, datei, full in ziele:
            try:
                page.goto(f"{BASE}{pfad}", wait_until="networkidle", timeout=20000)
                page.wait_for_timeout(900)   # Tabulator/Chart-Rendering abwarten
                page.screenshot(path=f"{OUT}/{datei}", full_page=full)
                made.append(datei)
            except Exception as e:
                fehler.append(f"{datei}: {e!r}")
        ctx.close()
    browser.close()

print(f"\n{len(made)} Screenshots erzeugt:")
for m in made:
    sz = os.path.getsize(f"{OUT}/{m}") // 1024
    print(f"  {m}  ({sz} KB)")
if fehler:
    print(f"\n{len(fehler)} FEHLER:")
    for f in fehler:
        print("  ", f)

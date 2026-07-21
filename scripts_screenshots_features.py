"""Screenshots der eigenständigen Feature-Seiten (inkl. mobilem Unterwegs-Modus und
Such-Overlay). Ergänzt die Kern-Screenshots. Lokaler Server muss laufen."""
import os
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
OUT = "docs/assets/screenshots"
PW = "demo12345"
K = 697
os.makedirs(OUT, exist_ok=True)


def login(page, user):
    page.goto(f"{BASE}/login/", wait_until="domcontentloaded")
    page.fill("#id_username", user)
    page.fill("#id_password", PW)
    page.click("button[type=submit]")
    page.wait_for_load_state("networkidle")
    assert "/login" not in page.url, f"Login {user} fehlgeschlagen"


made, fehler = [], []
with sync_playwright() as p:
    browser = p.chromium.launch()

    def shot(user, pfad, datei, full=True, viewport=(1440, 900), vorher=None):
        try:
            ctx = browser.new_context(viewport={"width": viewport[0], "height": viewport[1]})
            pg = ctx.new_page(); login(pg, user)
            pg.goto(f"{BASE}{pfad}", wait_until="networkidle", timeout=20000)
            pg.wait_for_timeout(900)
            if vorher:
                vorher(pg); pg.wait_for_timeout(600)
            pg.screenshot(path=f"{OUT}/{datei}", full_page=full)
            made.append(datei); ctx.close()
        except Exception as e:
            fehler.append(f"{datei}: {e!r}")

    # Unterwegs-Modus im mobilen Viewport
    shot("neumann", "/unterwegs/", "unterwegs.png", full=True, viewport=(390, 844))
    # Feature-Seiten (Desktop)
    shot("berger", "/vorkommnisse/", "vorkommnisse.png", full=True)
    shot("berger", "/dienstplan/", "dienstplan.png", full=False)
    shot("berger", "/wohnkosten/", "wohnkosten.png", full=True)
    shot("berger", f"/berichte/{K}/", "berichte.png", full=True)

    # Globale Suche (Overlay) – ins Suchfeld tippen
    def such_overlay(pg):
        feld = (pg.query_selector("input[type=search]")
                or pg.query_selector("header input")
                or pg.query_selector("input[placeholder*='durchsuchen']"))
        if feld:
            feld.click(); feld.type("Bauer", delay=40)
    shot("neumann", "/", "suche-overlay.png", full=False, vorher=such_overlay)

    browser.close()

print(f"\n{len(made)} Feature-Screenshots:")
for m in made:
    print(f"  {m}  ({os.path.getsize(f'{OUT}/{m}')//1024} KB)")
if fehler:
    print(f"\n{len(fehler)} FEHLER:")
    for f in fehler:
        print("  ", f)

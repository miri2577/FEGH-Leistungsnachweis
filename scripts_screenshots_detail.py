"""Detail-/Ausschnitts-Screenshots (Dialoge, aktive Suche, Dark-Mode) für die Doku.
Ergänzt die Vollseiten-Bilder aus scripts_screenshots.py. Lokaler Server muss laufen."""
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

    # 1) Belegungsliste mit aktiver Sofortsuche (gefilterte Zeilen)
    try:
        ctx = browser.new_context(viewport={"width": 1440, "height": 720})
        pg = ctx.new_page(); login(pg, "berger")
        pg.goto(f"{BASE}/belegungsliste/", wait_until="networkidle"); pg.wait_for_timeout(500)
        pg.fill("input[data-tsuche]", "Bau")
        pg.wait_for_timeout(500)
        pg.screenshot(path=f"{OUT}/belegungsliste-suche.png", full_page=False)
        made.append("belegungsliste-suche.png"); ctx.close()
    except Exception as e:
        fehler.append(f"belegungsliste-suche: {e!r}")

    # 2) Doku-Editor-Dialog (Erfassung) – Dialog sichtbar mit Beispieltext
    try:
        ctx = browser.new_context(viewport={"width": 1440, "height": 820})
        pg = ctx.new_page(); login(pg, "neumann")
        pg.goto(f"{BASE}/erfassung/", wait_until="networkidle"); pg.wait_for_timeout(1200)
        pg.evaluate("""() => {
            const info = document.getElementById('doku-info');
            const txt  = document.getElementById('doku-text');
            const modal= document.getElementById('dokuModal');
            if (info) info.textContent = '21.07.2026 · Ackermann, Alex';
            if (txt)  txt.value = 'Hausbesuch: aktuelle Wohnsituation besprochen. Antrag auf '
                + 'Wohngeld gemeinsam ausgefüllt und Unterlagen sortiert. Klient wirkte stabil '
                + 'und motiviert; Folgetermin zur Ämter-Begleitung vereinbart.';
            if (modal) modal.hidden = false;
        }""")
        pg.wait_for_timeout(300)
        pg.screenshot(path=f"{OUT}/doku-editor.png", full_page=False)
        made.append("doku-editor.png"); ctx.close()
    except Exception as e:
        fehler.append(f"doku-editor: {e!r}")

    # 3) Kalender-Tages-Dialog (Zelle anklicken)
    try:
        ctx = browser.new_context(viewport={"width": 1440, "height": 820})
        pg = ctx.new_page(); login(pg, "berger")
        pg.goto(f"{BASE}/kalender/", wait_until="networkidle"); pg.wait_for_timeout(700)
        # erste anklickbare Kalenderzelle öffnen
        zelle = pg.query_selector(".wk-cell") or pg.query_selector(".mxcell")
        if zelle:
            zelle.click(); pg.wait_for_timeout(500)
        pg.screenshot(path=f"{OUT}/kalender-dialog.png", full_page=False)
        made.append("kalender-dialog.png"); ctx.close()
    except Exception as e:
        fehler.append(f"kalender-dialog: {e!r}")

    # 4) Dark-Mode (Startseite) – Feature-Demo
    try:
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        ctx.add_init_script("try{localStorage.setItem('fegh-theme','dark')}catch(e){}")
        pg = ctx.new_page(); login(pg, "berger")
        pg.goto(f"{BASE}/controlling/", wait_until="networkidle"); pg.wait_for_timeout(1000)
        pg.screenshot(path=f"{OUT}/dark-mode.png", full_page=False)
        made.append("dark-mode.png"); ctx.close()
    except Exception as e:
        fehler.append(f"dark-mode: {e!r}")

    browser.close()

print(f"\n{len(made)} Detail-Screenshots:")
for m in made:
    print(f"  {m}  ({os.path.getsize(f'{OUT}/{m}')//1024} KB)")
if fehler:
    print(f"\n{len(fehler)} FEHLER:")
    for f in fehler:
        print("  ", f)

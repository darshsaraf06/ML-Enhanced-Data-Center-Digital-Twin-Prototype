"""
Browser check of every screen.

Opens Home, Menu, both Setup screens, About (all sections), Live (all four tabs, the
rack sheet, the Environment sheet, the hotspot alert) and Results at 390 px and
1920 px wide, in dark and light mode. Saves screenshots to artifacts/screens/ and
fails on any browser console error, page error, failed request, HTTP error,
horizontal overflow or button smaller than 36 px.

Requires the server:  venv\\Scripts\\python -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
Run:                  venv\\Scripts\\python scripts\\ui_check.py
"""

import json
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "screens"
SIZES = {"390": (390, 844), "1920": (1920, 1080)}
THEMES = ["dark", "light"]


def api(path, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data, method="POST" if body is not None else "GET",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read() or b"null")


def wait(cond, timeout=90, step=0.5):
    end = time.time() + timeout
    while time.time() < end:
        v = cond()
        if v:
            return v
        time.sleep(step)
    return None


class Checker:
    def __init__(self):
        self.problems = []
        self.shots = []

    def attach(self, page, tag):
        page.on("console", lambda m: m.type == "error" and self.problems.append(f"[{tag}] console error: {m.text}"))
        page.on("pageerror", lambda e: self.problems.append(f"[{tag}] page error: {e}"))
        page.on("requestfailed", lambda r: self._failed(tag, r))
        page.on("response", lambda r: r.status >= 400 and self.problems.append(f"[{tag}] HTTP {r.status}: {r.url}"))

    def _failed(self, tag, req):
        if "/api/run/export" in req.url:      # downloads are aborted by the page, not failures
            return
        self.problems.append(f"[{tag}] request failed: {req.url} ({req.failure})")

    def layout(self, page, tag, name):
        res = page.evaluate("""() => {
            const out = {overflow: document.documentElement.scrollWidth - window.innerWidth, small: []};
            document.querySelectorAll('button, .btn, a.btn').forEach(b => {
                const r = b.getBoundingClientRect();
                const st = getComputedStyle(b);
                if (r.width === 0 || r.height === 0 || st.visibility === 'hidden') return;
                if (r.height < 35.5) out.small.push((b.textContent || b.getAttribute('aria-label') || '').trim().slice(0, 30) + ' ' + Math.round(r.height) + 'px');
            });
            return out;
        }""")
        if res["overflow"] > 1:
            self.problems.append(f"[{tag}] {name}: page scrolls horizontally by {res['overflow']} px")
        for s in res["small"]:
            self.problems.append(f"[{tag}] {name}: button too small: {s}")

    def shot(self, page, tag, name):
        page.wait_for_timeout(350)
        path = OUT / f"{name}_{tag}.png"
        page.screenshot(path=str(path), full_page=True)
        self.shots.append(str(path.relative_to(ROOT)))
        self.layout(page, tag, name)


def run_combo(browser, ck, theme, size):
    w, h = SIZES[size]
    tag = f"{size}_{theme}"
    ctx = browser.new_context(viewport={"width": w, "height": h}, accept_downloads=True)
    ctx.add_init_script(f"try {{ localStorage.setItem('dt_theme', '{theme}'); }} catch (e) {{}}")
    page = ctx.new_page()
    ck.attach(page, tag)
    page.goto(BASE + "/#/home")
    page.wait_for_selector(".v3-title")
    ck.shot(page, tag, "01_home")
    page.click("text=Get Started")
    page.wait_for_selector(".simple-choice")
    ck.shot(page, tag, "02_menu")
    page.click(".simple-choice >> text=Simulation")
    page.wait_for_selector("#setupForm")
    page.click("text=Advanced settings")
    page.check("input[name=fEvents][value=chosen]", force=True)
    page.click("#evSelectAll")
    ck.shot(page, tag, "03_setup_simulation")
    page.click("#evClearAll")
    page.goto(BASE + "/#/setup?mode=demo")
    page.wait_for_selector("text=Demonstration settings are fixed.")
    ck.shot(page, tag, "04_setup_demo")
    page.goto(BASE + "/#/about")
    page.wait_for_selector(".v3-about")
    page.wait_for_function("() => !document.querySelector('.v3-about-body')?.textContent.includes('Loading...')")
    page.evaluate("() => document.querySelectorAll('details').forEach(d => d.open = true)")
    page.wait_for_timeout(500)
    ck.shot(page, tag, "05_about")

    # Live run started through the real setup form
    page.goto(BASE + "/#/setup?mode=sim")
    page.wait_for_selector("#setupForm")
    page.fill("#fRacks", "8")
    page.click("#startBtn")
    page.wait_for_selector(".v3-tile")
    page.wait_for_timeout(2500)
    ck.shot(page, tag, "06_live_overview")
    page.click("[data-tab=racks]")
    page.wait_for_selector(".v3-rackcard")
    ck.shot(page, tag, "07_live_racks")
    page.click(".v3-rackcard >> nth=0")
    page.wait_for_selector(".v3-sheet [data-ctl=util]")
    ck.shot(page, tag, "08_live_rack_sheet")
    page.click(".v3-sheet [data-close]")
    page.click("[data-tab=charts]")
    page.wait_for_selector("#chart-inlet")
    page.wait_for_timeout(1500)
    ck.shot(page, tag, "09_live_charts")
    page.click("[data-tab=events]")
    page.wait_for_selector("#evList")
    ck.shot(page, tag, "10_live_events")
    page.click("[data-tab=overview]")
    page.click("#btnEnv", timeout=15000)
    page.wait_for_selector(".v3-env-wrap")
    ck.shot(page, tag, "11_live_environment")
    # trigger a chiller trip from the Environment sheet and wait for the hotspot alert
    page.click(".v3-env-wrap [data-event=cooling_failure]")
    page.click("[data-speed='25']")
    page.wait_for_selector(".v3-alert", timeout=120000)
    page.wait_for_function("() => document.querySelectorAll('.v3-solution [data-metrics] b').length >= 4", timeout=60000)
    ck.shot(page, tag, "12_hotspot_alert")
    page.click("[data-snooze]", timeout=60000)
    page.wait_for_selector(".v3-alert", state="detached", timeout=30000)
    page.wait_for_selector("#snoozeBar:not([hidden])", timeout=10000)
    ck.shot(page, tag, "12b_snoozed")
    page.click("#btnSkip")
    page.wait_for_selector("text=Simulation results", timeout=180000)
    page.wait_for_selector("#rTimeline")
    page.evaluate("() => document.querySelectorAll('details').forEach(d => d.open = true)")
    page.wait_for_timeout(800)
    ck.shot(page, tag, "13_results")
    with page.expect_download(timeout=60000) as dl:
        page.click("[data-export=pdf]")
    if dl.value.failure():
        ck.problems.append(f"[{tag}] PDF download failed: {dl.value.failure()}")
    page.goto(BASE + "/#/logs")
    page.wait_for_selector(".v3-log")
    ck.shot(page, tag, "14_past_logs")
    page.click(".v3-log >> nth=0 >> text=Open results")
    page.wait_for_selector("#rTimeline")
    page.evaluate("() => document.querySelectorAll('details').forEach(d => d.open = true)")
    page.wait_for_timeout(600)
    ck.shot(page, tag, "15_saved_results")
    ctx.close()


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    OUT.mkdir(parents=True, exist_ok=True)
    try:
        api("/api/health")
    except Exception as exc:
        print(f"Server not reachable at {BASE}: {exc}")
        return 2
    ck = Checker()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        quick = "--quick" in sys.argv
        for theme in (THEMES[:1] if quick else THEMES):
            for size in (list(SIZES)[:1] if quick else SIZES):
                t0 = time.time()
                try:
                    run_combo(browser, ck, theme, size)
                except Exception as exc:
                    ck.problems.append(f"[{size}_{theme}] step failed: {exc}")
                print(f"checked {size}px {theme} in {time.time() - t0:.0f} s")
        browser.close()
    print(f"\n{len(ck.shots)} screenshots in {OUT.relative_to(ROOT)}")
    if ck.problems:
        print(f"\n{len(ck.problems)} problem(s):")
        for pr in ck.problems:
            print("  " + pr)
        return 1
    print("UI check passed: no console errors, failed requests, overflow or undersized buttons.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

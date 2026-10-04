"""
Browser tests for the live screen (bugs 1 to 5). They drive the real app in Chromium
against the running server and are skipped when http://127.0.0.1:8000 is not reachable.
"""

import json
import time
import urllib.request

import pytest

BASE = "http://127.0.0.1:8000"


def api(path, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data, method="POST" if body is not None else "GET",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read() or b"null")


def server_up():
    try:
        return api("/api/health")["status"] == "ok"
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not server_up(), reason="server is not running on 127.0.0.1:8000")


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def page(browser):
    ctx = browser.new_context(viewport={"width": 1366, "height": 900})
    pg = ctx.new_page()
    pg.errors = []
    pg.on("console", lambda m: m.type == "error" and pg.errors.append(m.text))
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))
    yield pg
    ctx.close()
    assert pg.errors == [], f"browser console errors: {pg.errors}"


def start_run(**cfg):
    api("/api/run/start", {"mode": "sim", "saveToLogs": False, **cfg})


def open_live(page):
    page.goto(BASE + "/#/live")
    page.wait_for_selector(".v3-tile")
    page.wait_for_timeout(1500)


def test_bug1_live_values_change_at_1x(page):
    start_run(seed=31)
    api("/api/run/speed", {"speed": 1})
    open_live(page)
    first = page.locator(".v3-tile").all_inner_texts()
    clock1 = page.inner_text("#clock")
    page.wait_for_timeout(10000)
    second = page.locator(".v3-tile").all_inner_texts()
    clock2 = page.inner_text("#clock")
    assert clock1 != clock2
    assert first != second, "rack temperatures did not change in 10 s at 1x"


def test_bug2_rack_slider_keeps_value_and_backend_applies_it(page):
    start_run(seed=32)
    api("/api/run/speed", {"speed": 1})
    open_live(page)
    page.click("[data-tab=racks]")
    page.click(".v3-rackcard >> nth=0")
    slider = page.locator(".v3-sheet [data-ctl=util]")
    before = api("/api/run/state")["racks"][0]["powerKw"]
    slider.fill("90")
    page.wait_for_timeout(10000)
    assert slider.input_value() == "90", "slider was overwritten while the sheet was open"
    rack = api("/api/run/state")["racks"][0]
    assert rack["util"] == 90
    assert rack["powerKw"] > before
    assert "90 %" in page.inner_text(".v3-sheet [data-v=util]")


def test_bug3_charts_keep_size_and_count(page):
    start_run(seed=33)
    open_live(page)
    api("/api/run/speed", {"speed": 10})
    page.click("[data-tab=charts]")
    page.wait_for_selector("#chart-inlet")
    page.wait_for_timeout(2000)
    count = page.locator("canvas").count()
    heights = page.locator("canvas").evaluate_all("els => els.map(e => Math.round(e.getBoundingClientRect().height))")
    page.wait_for_timeout(30000)
    assert page.locator("canvas").count() == count == 9
    assert page.locator("canvas").evaluate_all("els => els.map(e => Math.round(e.getBoundingClientRect().height))") == heights
    assert all(h == heights[0] for h in heights) and heights[0] == 280
    points = page.evaluate("() => Chart.getChart('chart-inlet').data.datasets[0].data.length")
    assert points > 10, "charts must keep receiving data"


def test_bug4_heatmap_colors_follow_temperature(page):
    start_run(seed=34)
    api("/api/run/speed", {"speed": 10})
    api("/api/run/rack/1", {"disturbance": {"kind": "inlet_offset", "magnitude": 7, "durationMin": 20}})
    open_live(page)
    page.wait_for_function("""() => {
        const t = [...document.querySelectorAll('.v3-tile [data-f=inlet]')].map(n => parseFloat(n.textContent));
        return t.length > 1 && t[0] - t[1] > 3;
    }""", timeout=60000)
    tiles = page.locator(".v3-tile")
    c1 = tiles.nth(0).evaluate("e => getComputedStyle(e).backgroundColor")
    c2 = tiles.nth(1).evaluate("e => getComputedStyle(e).backgroundColor")
    assert c1 != c2
    assert page.locator(".v3-legend-bar").count() == 1
    assert page.locator(".v3-legend-labels span").count() >= 5


def test_bug5_skip_to_end_opens_results(page):
    start_run(seed=35, durationS=1800)
    open_live(page)
    t0 = time.time()
    page.click("#btnSkip")
    page.wait_for_selector("text=Simulation results", timeout=180000)
    page.wait_for_selector("#rTimeline")
    assert time.time() - t0 < 180
    assert page.url.endswith("#/results")
    assert page.locator("[data-export=pdf]").count() == 1


def test_setup_select_all_and_clear_all_events(page):
    page.goto(BASE + "/#/setup?mode=sim")
    page.wait_for_selector("#setupForm")
    page.check("input[name=fEvents][value=chosen]", force=True)
    boxes = page.locator("#eventChoices input[type=checkbox]")
    page.click("#evSelectAll")
    assert all(boxes.nth(i).is_checked() for i in range(boxes.count()))
    assert page.inner_text("#evCount").startswith(f"{boxes.count()} of")
    page.click("#evClearAll")
    assert not any(boxes.nth(i).is_checked() for i in range(boxes.count()))


def test_alert_has_actions_on_top_and_snooze_works(page):
    start_run(seed=36)
    open_live(page)
    api("/api/run/environment", {"event": "cooling_failure"})
    api("/api/run/speed", {"speed": 25})
    page.wait_for_selector(".v3-alert", timeout=120000)
    top = page.locator(".v3-alert-actions")
    cards = page.locator(".v3-solutions")
    assert top.bounding_box()["y"] < cards.bounding_box()["y"], "Apply Recommended and Snooze must sit above the solution cards"
    page.click("[data-snooze]")
    page.wait_for_selector(".v3-alert", state="detached", timeout=15000)
    page.wait_for_selector("#snoozeBar:not([hidden])", timeout=10000)
    page.wait_for_timeout(15000)          # about 6 simulated minutes at 25x
    assert page.locator(".v3-alert").count() == 0
    page.click("#btnUnsnooze")
    page.wait_for_selector("#snoozeBar", state="hidden", timeout=10000)


def test_past_logs_open_saved_results(page):
    runs = api("/api/runs?limit=1")
    if not runs["total"]:
        pytest.skip("no saved runs yet")
    page.goto(BASE + "/#/logs")
    page.wait_for_selector(".v3-log")
    page.click(".v3-log >> nth=0 >> text=Open results")
    page.wait_for_selector("text=Saved run, read-only.")
    page.wait_for_selector("#rTimeline")
    assert page.locator(".v3-defs").count() >= 6, "every section needs its explanations"

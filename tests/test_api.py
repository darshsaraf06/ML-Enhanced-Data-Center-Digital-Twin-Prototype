"""API tests through FastAPI's TestClient (no running server needed)."""

import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    import run_store
    run_store.RUNS_DIR = tmp_path_factory.mktemp("runs")     # keep test runs out of the real Past Logs
    from main import app
    with TestClient(app) as c:
        yield c


def wait_for(fn, timeout=90.0, step=0.25):
    end = time.time() + timeout
    while time.time() < end:
        v = fn()
        if v:
            return v
        time.sleep(step)
    raise AssertionError("condition not met in time")


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_only_frontend_files_are_served(client):
    assert client.get("/").status_code == 200
    assert client.get("/theme.css").status_code == 200
    assert client.get("/js/app.js").status_code == 200
    assert client.get("/backend/datacenter_twin.db").status_code == 404
    assert client.get("/venv/pyvenv.cfg").status_code == 404


def test_catalog_lists_trained_models(client):
    cat = client.get("/api/catalog").json()
    ids = {m["id"] for m in cat["models"] if m["available"]}
    assert {"persistence", "linear", "rf", "xgboost"} <= ids
    assert len(cat["events"]) >= 8


def test_demo_rejects_rack_and_environment_changes(client):
    assert client.post("/api/run/start", json={"mode": "demo", "saveToLogs": False}).status_code == 200
    assert client.post("/api/run/rack/1", json={"util": 90}).status_code == 403
    assert client.post("/api/run/environment", json={"event": "heatwave"}).status_code == 403
    client.post("/api/run/end")


def test_sim_rack_update_is_applied_by_backend(client):
    client.post("/api/run/start", json={"mode": "sim", "seed": 21, "saveToLogs": False})
    client.post("/api/run/speed", json={"speed": 25})
    p0 = client.get("/api/run/state").json()["racks"][0]["powerKw"]
    assert client.post("/api/run/rack/1", json={"util": 90}).status_code == 200
    def applied():
        s = client.get("/api/run/state").json()
        return s if s["racks"][0]["util"] == 90 and s["t"] > 5 else None
    s = wait_for(applied, 30)
    assert s["racks"][0]["powerKw"] > p0
    assert s["racks"][0]["workloadOverride"] == 90
    assert client.post("/api/run/rack/99", json={"util": 50}).status_code == 404
    assert client.post("/api/run/speed", json={"speed": 15}).status_code == 400


def test_skip_to_end_runs_in_background_and_results_export(client):
    client.post("/api/run/start", json={"mode": "sim", "seed": 22, "durationS": 1800})
    t0 = time.time()
    assert client.post("/api/run/skip").json()["status"] == "SKIPPING"
    wait_for(lambda: client.get("/api/run/state").json()["status"] == "FINISHED", 60)
    assert time.time() - t0 < 30
    res = wait_for(lambda: client.get("/api/run/results").json()["results"], 180, 1.0)
    assert res["elapsedS"] == 1800
    assert res["baselines"]["fixed"]["totalKwh"] > 0
    assert len(res["solutions"]) == 8
    for fmt, ctype in (("pdf", "application/pdf"), ("csv", "text/csv"), ("json", "application/json")):
        r = client.get(f"/api/run/export?format={fmt}")
        assert r.status_code == 200 and r.headers["content-type"].startswith(ctype)
        assert len(r.content) > 1000
        if fmt != "pdf":
            text = r.content.decode("utf-8")
            assert "—" not in text
            assert "Comparison vs fixed cooling" in text or "vsFixed" in text
            assert "Water Usage Effectiveness" in text, "exports must carry the explanations"
    # the finished run is saved and listed in Past Logs
    runs = client.get("/api/runs").json()
    assert runs["total"] >= 1 and runs["runs"][0]["runId"] == res["runId"]
    saved = client.get(f"/api/runs/{res['runId']}").json()
    assert saved["resources"] == res["resources"] and "explanations" in saved
    assert client.get(f"/api/runs/{res['runId']}/export?format=pdf").status_code == 200
    assert client.get("/api/runs/RUN-does-not-exist").status_code == 404
    assert client.get("/api/runs/..%2F..%2Fmain").status_code == 404


def test_about_endpoints(client):
    assert client.get("/api/about/ml").status_code == 200
    d = client.get("/api/about/dataset").json()
    assert d["rows"] > 10000 and len(d["columns"]) > 20
    assert client.get("/api/about/parameters").status_code == 200
    assert client.get("/api/about/benchmark").status_code == 200


def test_snooze_dismisses_alert_and_blocks_new_ones(client):
    client.post("/api/run/start", json={"mode": "sim", "seed": 23, "saveToLogs": False})
    client.post("/api/run/environment", json={"event": "cooling_failure"})
    client.post("/api/run/speed", json={"speed": 25})
    wait_for(lambda: client.get("/api/run/state").json()["status"] == "DECISION", 120)
    r = client.post("/api/run/snooze")
    assert r.status_code == 200 and 295 <= r.json()["secondsLeft"] <= 300
    s = client.get("/api/run/state").json()
    assert s["status"] == "RUNNING" and s["snooze"]["active"] and s["decision"] is None
    t0 = s["t"]
    wait_for(lambda: client.get("/api/run/state").json()["t"] > t0 + 900, 90)   # 15 simulated minutes later
    s = client.get("/api/run/state").json()
    assert s["status"] != "DECISION", "no alert may open while snoozed"
    titles = [e["title"] for e in s["events"]]
    assert "Hotspot alerts snoozed for 5 minutes" in titles
    assert client.post("/api/run/unsnooze").status_code == 200
    assert client.get("/api/run/state").json()["snooze"]["active"] is False
    client.post("/api/run/end")


def test_catalog_reports_percent_accuracy(client):
    models = {m["id"]: m for m in client.get("/api/catalog").json()["models"]}
    assert 0 < models["xgboost"]["acc5"] <= 100
    ml = client.get("/api/about/ml").json()
    row = ml["models"]["xgboost"]["chronological"]["15"]
    assert 0 <= row["within1Pct"] <= 100 and 0 <= row["within05Pct"] <= row["within1Pct"]

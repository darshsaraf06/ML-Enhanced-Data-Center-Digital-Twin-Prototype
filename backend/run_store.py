"""
Saved runs ("View Past Logs").

Every finished run's complete results are saved as backend/data/runs/<RUN-ID>.json with a
small <RUN-ID>.summary.json beside it, so the log list loads quickly. Saved runs are
read-only; they can be opened on the Results page and exported again.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from results_engine import EXPLANATIONS

RUNS_DIR = Path(__file__).parent / "data" / "runs"
RUN_ID = re.compile(r"^RUN-[0-9A-Za-z-]{1,80}$")


def summarise(res: Dict[str, Any]) -> Dict[str, Any]:
    cfg = res.get("config", {})
    r = res.get("resources", {})
    fixed = next((x for x in res.get("comparison", {}).get("vsFixed", []) if x["metric"] == "totalKwh"), None)
    events = cfg.get("events")
    if isinstance(events, list):
        events_text = ", ".join(e.replace("_", " ") for e in events) or "none"
    else:
        events_text = {"demo": "demonstration script", "none": "none", "random": "random"}.get(events, str(events))
    return {
        "runId": res.get("runId"), "savedAt": res.get("generatedAt"), "mode": cfg.get("mode"),
        "numRacks": cfg.get("numRacks"), "scale": cfg.get("scale"), "climate": cfg.get("climate"),
        "events": events_text, "seed": cfg.get("seed"), "mlModel": cfg.get("mlModel"),
        "durationS": res.get("durationS"), "elapsedS": res.get("elapsedS"), "endReason": res.get("endReason"),
        "peakInlet": r.get("peakInlet"), "minutesAboveLimit": r.get("minutesAboveLimit"),
        "hotspotEvents": r.get("hotspotEvents"), "totalKwh": r.get("totalKwh"), "pue": r.get("pue"),
        "waterL": r.get("waterL"), "costInr": r.get("costInr"), "alerts": len(res.get("decisions", [])),
        "energyVsFixedPercent": fixed["percent"] if fixed else None,
        "inletLimit": res.get("inletLimit"),
    }


def save_run(res: Dict[str, Any]) -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    rid = res["runId"]
    (RUNS_DIR / f"{rid}.json").write_text(json.dumps(res), encoding="utf-8")
    (RUNS_DIR / f"{rid}.summary.json").write_text(json.dumps(summarise(res)), encoding="utf-8")


def list_runs() -> List[Dict[str, Any]]:
    if not RUNS_DIR.exists():
        return []
    out = []
    for path in RUNS_DIR.glob("RUN-*.json"):
        if path.name.endswith(".summary.json"):
            continue
        side = path.with_name(path.stem + ".summary.json")
        try:
            if side.exists():
                out.append(json.loads(side.read_text(encoding="utf-8")))
            else:   # runs saved before summaries existed
                summ = summarise(json.loads(path.read_text(encoding="utf-8")))
                side.write_text(json.dumps(summ), encoding="utf-8")
                out.append(summ)
        except Exception as exc:
            print(f"[runs] could not read {path.name}: {exc}")
    out.sort(key=lambda s: s.get("savedAt") or "", reverse=True)
    return out


def load_run(run_id: str) -> Optional[Dict[str, Any]]:
    if not RUN_ID.match(run_id or ""):
        return None
    path = RUNS_DIR / f"{run_id}.json"
    if not path.exists():
        return None
    res = json.loads(path.read_text(encoding="utf-8"))
    res.setdefault("explanations", EXPLANATIONS)
    return res

"""Rule 7: no em dash (U+2014) and no emoji in the new UI, backend messages or exports."""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FILES = ["index.html", "theme.css"] + [f"js/{n}.js" for n in ("app", "api", "util", "shared", "live", "charts", "alert", "events", "results", "about", "logs")] + \
        [f"backend/{n}.py" for n in ("main", "model_params", "digital_twin", "weather_engine", "scenario_engine", "workload_engine",
                                     "alert_engine", "energy_engine", "forecasting_engine", "optimization_engine",
                                     "simulation_engine", "results_engine", "results_export", "run_controller",
                                     "benchmark_runner", "ml_training", "run_store")] + ["backend/routers/run.py", "backend/routers/about.py"]


@pytest.mark.parametrize("name", FILES)
def test_no_em_dash_or_emoji(name):
    text = (ROOT / name).read_text(encoding="utf-8")
    assert "—" not in text
    emoji = [c for c in text if 0x1F300 <= ord(c) <= 0x1FAFF or 0x2600 <= ord(c) <= 0x27BF]
    assert not emoji, f"emoji found: {emoji[:5]}"

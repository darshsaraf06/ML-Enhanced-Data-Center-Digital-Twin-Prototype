# Project Rules

1. Keep the visual theme: the "Foundry" theme in theme.css (warm graphite, molten orange, acid lime, coolant ice; Unbounded, IBM Plex Sans, IBM Plex Mono), dark and light modes, theme toggle. It replaced the original cyan theme at the user's request on 2026-10-04. New screens reuse the existing classes in theme.css.
2. Reuse and extend working code. Rewrite only what is broken, and tell me first.
3. Do not delete files without my approval.
4. One stage at a time. After each: restart the server, confirm startup and /api/health, run pytest, check the browser console for zero errors, give exact URLs and clicks to test, then STOP for my "OK". After OK: git add -A; git commit -m "<stage>".
5. Never claim something works without running it. If something fails twice, stop and explain.
6. requirements.txt stays Python 3.11 compatible.
7. No em dash character (U+2014) in visible text or exports. No emoji in new UI.
8. Every number shown in the UI or reports must come from the actual simulation or model output. No hardcoded or fake results.

# Environment

- Python environment: use ONLY `venv` (Python 3.11.2, all of backend/requirements.txt installed). `.venv` is unused.
- Start the server from the project root:
  `venv\Scripts\python -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload`
- Tests: `venv\Scripts\python -m pytest tests -q` (UI tests need the server running).
- UI check: `venv\Scripts\python scripts\ui_check.py` (screenshots in artifacts/screens/).
- Retrain models and rebuild the dataset: `venv\Scripts\python scripts\train_models.py`
- Benchmark: `venv\Scripts\python scripts\run_benchmark.py --seeds 10`

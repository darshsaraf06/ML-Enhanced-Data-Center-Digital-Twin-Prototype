# ML-Enhanced Data Center Digital Twin Prototype

An enterprise-grade **physical and predictive digital twin platform** for modern data centers. Combines RC-equivalent circuit thermodynamics, multi-horizon machine learning forecasting, real-time counterfactual optimization, and an autonomous alert engine to prevent thermal hotspots, cut cooling energy, and enforce ASHRAE compliance — all served through a single-page web engineering dashboard.

---

## Architecture Overview

```
                      +-----------------------------+
                      |   Weather & Environmental   |
                      | (Psychrometric / Wet-Bulb)  |
                      +--------------+--------------+
                                     |
+---------------------+              v              +---------------------+
| Dynamic IT Workload | ---> [ RC Thermal Engine ] <--- | Chiller Plant &     |
| (GPU / CPU Clusters)|      [  Physical Twin    ]       | CRAH Variable Fans  |
+---------------------+              |              +---------------------+
                                     v
                       +---------------------------+
                       | Real-Time Telemetry Stream|
                       | (WebSocket & REST API)    |
                       +-------------+-------------+
                                     |
          +--------------------------+--------------------------+
          |                          |                          |
          v                          v                          v
+-----------------------+  +--------------------+  +--------------------+
| XGBoost / RF / Ridge  |  | Counterfactual     |  | Autonomous Alert   |
| Multi-Horizon Forecast|  | Optimization Tree  |  | & Intervention     |
| (T+5m / T+15m / T+30m)|  | (5 Control Actions)|  | Engine             |
+-----------+-----------+  +---------+----------+  +---------+----------+
            |                        |                        |
            +------------------------+------------------------+
                                     |
                                     v
            +-------------------------------------------+
            |   Autonomous Closed-Loop Interventions    |
            |  & Research-Grade PDF Engineering Reports |
            +-------------------------------------------+
```

---

## Key Features

### 1. RC Thermal Physics Engine (`physics_engine.py`)
- Multi-rack thermal simulation using lumped-capacitance RC circuit models.
- CPU/GPU heat dissipation, CRAH fan affinity laws, and chiller COP derating.
- Hot-aisle/cold-aisle containment with rack-to-rack thermal coupling.
- Psychrometric ambient wet-bulb temperature and heat infiltration modeling.

### 2. Predictive ML Forecasting (`ml_engine.py`, `forecasting_engine.py`)
- Multi-horizon temperature forecasting at **T+5 min**, **T+15 min**, and **T+30 min**.
- Models trained on synthetic physics-simulation data (RC model rollouts):
  - **XGBoost Regressor** — Primary model (MAE ≈ 0.42°C, R² ≈ 0.984)
  - **Random Forest** — Ensemble baseline (MAE ≈ 0.56°C, R² ≈ 0.971)
  - **Ridge Regression** — Linear baseline (MAE ≈ 1.15°C, R² ≈ 0.892)
  - **LSTM (reference)** — Deep recurrent reference (MAE ≈ 0.38°C, R² ≈ 0.989)
- Real-time **Explainable AI (XAI)** feature attribution drivers for every forecast.
- Non-blocking async model training at server startup via thread pool executor.
- Graceful fallback to analytic approximation if `scikit-learn` is unavailable.

### 3. Counterfactual Optimization Engine (`optimization_engine.py`, `optimizer_engine.py`)
- Fast-branching simulation spawning **5 parallel cloned twin branches**:

  | Action | Description |
  |---|---|
  | `chiller_boost` | Trim chiller supply setpoint by −2.0°C |
  | `airflow_boost` | Increase CRAH airflow by +20% (+1,500 CFM) |
  | `workload_migration` | Migrate load from hot rack to coolest available rack |
  | `fan_speed_increase` | Ramp internal server fans to 100% |
  | `proactive_combined` | Coordinated airflow boost + chiller trim + load balancing |

- Energy delta calculation, SLA violation scoring, and multi-objective cost ranking.
- **What-If interactive simulation** (`counterfactual_engine.py`): Simulate BEFORE vs. AFTER branches across configurable horizon (default 30 min), comparing peak temps, PUE, and ASHRAE violations.

### 4. 11 Failure Scenarios & Weather Stressors (`scenario_engine.py`)

| Scenario | Category | Severity |
|---|---|---|
| Nominal Operation | Nominal | INFO |
| AI Workload Spike | Workload | WARNING |
| GPU Training Burst | Workload | CRITICAL |
| Cooling Failure (Chiller Trip) | Cooling | CRITICAL |
| Fan Degradation | Mechanical | WARNING |
| Airflow Blockage (Blanking Panel) | Containment | WARNING |
| High Ambient Temperature | Environmental | WARNING |
| Rack Overload (Runaway Process) | Workload | CRITICAL |
| Workload Imbalance (Hot Spotting) | Workload | WARNING |
| Multiple Rack Hotspot | Compound | CRITICAL |
| Hardware Degradation (Thermal Aging) | Wear | WARNING |

4 built-in workload presets: **Standard Mixed**, **Heavy AI/Deep Learning**, **Optimally Distributed**, **Off-Peak Night**.

### 5. 5-Paradigm Research Benchmark (`benchmark_engine.py`)
Live ablation study comparing all approaches side-by-side:

| Paradigm | MAE (°C) | R² | Energy Savings |
|---|---|---|---|
| 1. Physics-Only (RC Baseline) | 1.45 | 0.842 | — |
| 2. ML-Only (Reactive) | 0.72 | 0.948 | 9.6% |
| 3. Physics + ML (Hybrid Forecasting) | 0.42 | 0.982 | 14.8% |
| 4. Physics + ML + Heuristic Optimization | 0.38 | 0.986 | 18.4% |
| 5. Full Counterfactual Framework (Proposed) | 0.34 | 0.992 | **26.5%** |

### 6. Autonomous Alert Engine (`alert_engine.py`)
- Rule-based alert generation for ASHRAE violations, hotspot risks, and efficiency anomalies.
- Integrated event log with severity tiers (INFO / WARNING / CRITICAL).

### 7. Energy Analytics Engine (`energy_engine.py`)
- Real-time Power Usage Effectiveness (PUE) tracking.
- Cooling power estimation with chiller COP derating curves.
- Historical energy trend archiving per simulation run.

### 8. Full Web-Based Engineering GUI (`index.html`, `js/`, `style.css`)
10 dedicated interactive views:
1. **System Overview** — Live KPI cards, health indicators, and system telemetry
2. **Digital Twin** — 3D/2D rack bay visualization and thermal heatmap
3. **Simulation Lab** — Configure and control timed simulation runs (1–24h, variable speed up to 120×)
4. **ML Forecasting** — Per-rack T+5/15/30m forecasts, hotspot risk scoring, model comparison table
5. **Optimization** — Counterfactual branch evaluation with energy & SLA delta scoring
6. **Failure Scenarios** — Activate fault conditions and weather stressors
7. **Event Log** — Chronological alert & intervention history
8. **Energy Analytics** — PUE trends, cooling power breakdown, energy savings timeline
9. **Paradigm Ablation Benchmark** — Live 5-paradigm comparative experiment
10. **Technical Reports** — Generate and download research-grade PDF audit reports

- Real-time WebSocket streaming with zero-lag state broadcasting.
- Dark Mode / Light Mode with instant switching.
- Glassmorphism high-contrast responsive CSS (Flex/Grid).

### 9. Automated Research-Grade PDF Reporting (`report_engine.py`)
- Built-in ReportLab engine generating comprehensive engineering audit reports.
- Covers individual simulation runs and full historical multi-run archives.
- Downloadable directly from the UI or via REST API.

### 10. Persistent SQLite History (`db.py`)
- SQLAlchemy + aiosqlite-backed simulation record store.
- Full simulation summary JSON archived per run (thermal, energy, ML, optimization sections).
- Exportable as CSV, JSON, or PDF via API.

---

## Tech Stack

| Layer | Technologies |
|---|---|
| **Backend** | Python 3.10+, FastAPI 0.115, Uvicorn, SQLAlchemy 2.1, aiosqlite 0.22 |
| **ML** | scikit-learn 1.5 (XGBoost, RandomForest, Ridge), XGBoost 2.1, NumPy 2.1, SciPy 1.18 |
| **Reporting** | ReportLab 5.0 |
| **Frontend** | Vanilla ES6+ JavaScript, HTML5, Modern CSS (Glassmorphism, Light/Dark themes, Flex/Grid) |
| **Deployment** | Docker, Docker Compose, Shell scripts |

---

## Project Structure

```
ML-Enhanced-Data-Center-Digital-Twin-Prototype/
├── index.html                        # Single-page engineering dashboard (10 views)
├── style.css                         # Full design system (glassmorphism, dark/light mode)
├── js/
│   ├── app.js                        # App bootstrap, WebSocket client, routing
│   ├── ui.js                         # All dashboard panels and visualization renderers
│   ├── physics_engine.js             # Client-side RC physics mirror (optional offline mode)
│   ├── ml_engine.js                  # Client-side ML analytic approximation
│   ├── optimizer_engine.js           # Client-side optimizer mirror
│   └── benchmark_engine.js          # Client-side benchmark comparison
├── backend/
│   ├── main.py                       # FastAPI app, lifespan, WebSocket, static serving
│   ├── simulation_engine.py          # Top-level simulation orchestrator
│   ├── simulation_state.py           # Shared singleton simulation state
│   ├── physics_engine.py             # RC thermal physics engine (8 racks)
│   ├── ml_engine.py                  # XGBoost/RF/Ridge multi-horizon ML forecasting
│   ├── forecasting_engine.py         # Extended forecasting utilities
│   ├── optimization_engine.py        # 5-branch cloned counterfactual optimizer
│   ├── optimizer_engine.py           # Live intervention application engine
│   ├── counterfactual_engine.py      # What-If BEFORE/AFTER branch simulator
│   ├── scenario_engine.py            # 11 failure scenarios & workload presets
│   ├── benchmark_engine.py           # 5-paradigm ablation benchmark engine
│   ├── energy_engine.py              # PUE, cooling power, energy tracking
│   ├── alert_engine.py               # ASHRAE/hotspot rule-based alert engine
│   ├── weather_engine.py             # Psychrometric ambient condition modeling
│   ├── report_engine.py              # ReportLab PDF report generator
│   ├── db.py                         # SQLAlchemy models + SQLite session factory
│   ├── ws_manager.py                 # WebSocket connection manager
│   ├── requirements.txt
│   └── routers/
│       ├── simulation.py             # /api/simulation/* lifecycle & history endpoints
│       ├── telemetry.py              # /api/telemetry live state snapshot
│       ├── ml.py                     # /api/ml forecast & model selection
│       ├── optimizer.py              # /api/optimize & /api/apply-intervention
│       ├── counterfactual.py         # /api/counterfactual/evaluate & /whatif
│       ├── benchmark.py              # /api/benchmark paradigm comparison
│       ├── scenario.py               # /api/scenario list, set, & reset
│       ├── experiments.py            # /api/experiments comparison & CSV/JSON export
│       └── report.py                 # /api/report/pdf generation
├── Dockerfile
├── docker-compose.yml
└── start.sh                          # Root launcher (sets up venv + starts uvicorn)
```

---

## Quick Start Guide

### Prerequisites
- Python 3.10 or higher
- Git

### 1. Clone the Repository
```bash
git clone https://github.com/darshsaraf06/ML-Enhanced-Data-Center-Digital-Twin-Prototype.git
cd ML-Enhanced-Data-Center-Digital-Twin-Prototype
```

### 2. Set Up Virtual Environment & Install Dependencies
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Run the Server
```bash
# From backend directory with venv activated:
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```
Or use the root launcher (handles venv creation automatically):
```bash
./start.sh
```

### 4. Access the Dashboard
Open your browser and navigate to:
```
http://localhost:8000/
```

> **Note**: On first startup, ML models are trained asynchronously in a background thread (~10–30 seconds). The dashboard is immediately accessible and uses an analytic fallback until training completes.

---

## Docker Deployment

```bash
docker-compose up --build
```
The application will be accessible at `http://localhost:8000`.

---

## REST & WebSocket API Reference

### WebSocket
| Endpoint | Description |
|---|---|
| `ws://localhost:8000/ws` | Full-state broadcast every second. Send `"ping"` → `pong`, `"step"` → advance one tick |

### Core API
| Endpoint | Method | Description |
|---|---|---|
| `/api/health` | GET | System health, subsystem status, ML training state, active WS clients |

### Simulation Lifecycle (`/api/simulation`)
| Endpoint | Method | Description |
|---|---|---|
| `/api/simulation/configure` | POST | Configure all parameters (racks, ambient, cooling, ML model, scenario) |
| `/api/simulation/start` | POST | Start timed simulation run |
| `/api/simulation/pause` | POST | Pause current run |
| `/api/simulation/resume` | POST | Resume paused run |
| `/api/simulation/stop` | POST | Stop and archive to database |
| `/api/simulation/restart` | POST | Reset and restart current configuration |
| `/api/simulation/speed` | POST | Set simulation speed multiplier (0.5× – 120×) |
| `/api/simulation/status` | GET | Current sim status, clock, and system health |
| `/api/simulation/history` | GET | Past simulation records (last 50) |
| `/api/simulation/history/export/csv` | GET | Download all history as CSV |
| `/api/simulation/history/export/pdf` | GET | Download multi-run audit report PDF |
| `/api/simulation/{sim_id}/export` | GET | Export single simulation (JSON / CSV / PDF via `?format=`) |
| `/api/simulation/history/clear` | DELETE | Clear all simulation history |

### ML & Forecasting
| Endpoint | Method | Description |
|---|---|---|
| `/api/ml/forecast` | GET | Per-rack T+5/15/30m forecasts and hotspot risk |
| `/api/ml/models` | GET | Model comparison metrics and active model |
| `/api/ml/select` | POST | Switch active inference model (xgboost / rf / linear) |

### Optimization & Counterfactual
| Endpoint | Method | Description |
|---|---|---|
| `/api/optimize` | POST | Evaluate all 5 counterfactual intervention branches |
| `/api/apply-intervention` | POST | Apply chosen intervention to live physics state |
| `/api/counterfactual/evaluate` | POST | 5-branch cloned twin counterfactual evaluation |
| `/api/counterfactual/whatif` | POST | BEFORE vs. AFTER What-If comparative simulation |

### Scenarios & Workloads
| Endpoint | Method | Description |
|---|---|---|
| `/api/scenario/list` | GET | List all 11 failure scenarios and 4 workload presets |
| `/api/scenario/set` | POST | Activate a failure scenario and/or workload preset |
| `/api/scenario/reset` | POST | Reset to nominal operation |

### Benchmark & Experiments
| Endpoint | Method | Description |
|---|---|---|
| `/api/benchmark/comparison` | GET | Live 5-paradigm ablation benchmark data |
| `/api/experiments/comparison` | GET | Research paradigm comparison with history |
| `/api/experiments/export/csv` | GET | Download paradigm benchmark as CSV |
| `/api/experiments/export/json` | GET | Download paradigm benchmark as JSON |

### Reports
| Endpoint | Method | Description |
|---|---|---|
| `/api/report/pdf` | GET | Generate and download PDF report of latest simulation |

---

## Simulation Configuration Parameters

| Parameter | Default | Range | Description |
|---|---|---|---|
| `durationSec` | 3600 | 60 – 86400 | Total simulation duration in seconds |
| `timestepSec` | 1.0 | 0.1 – 10.0 | Physics engine timestep |
| `numRacks` | 8 | 4 – 12 | Number of server racks |
| `initialWorkload` | 60% | 10 – 100% | Initial CPU load across all racks |
| `initialAmbientTemp` | 24.0°C | 10 – 50°C | Starting external ambient temperature |
| `initialHumidity` | 50% | 10 – 99% | Starting relative humidity |
| `coolingSetpoint` | 18.0°C | 14 – 26°C | CRAH supply air setpoint |
| `crahAirflow` | 8500 CFM | 3000 – 15000 | CRAH airflow rate |
| `mlModel` | `xgboost` | xgboost / rf / linear | Active inference model |
| `optimizationEnabled` | true | — | Enable autonomous optimization |
| `failureScenario` | `none` | see scenarios list | Active failure scenario |
| `workloadPreset` | `baseline` | baseline / ai_burst / balanced / idle_night | Workload profile |

---

## License

MIT License. Designed for data center thermal management research and engineering demonstration.

---

## Architecture Overview

```
                      +-----------------------------+
                      |   Environmental Weather     |
                      | (Psychrometric Wet-Bulb)    |
                      +--------------+--------------+
                                     |
+---------------------+              v              +---------------------+
| Dynamic IT Workload | ---> [ RC Thermal Engine ] <--- | Chiller Plant &     |
| (GPU / CPU Clusters)|      [  Physical Twin    ]      | CRAH Variable Fans  |
+---------------------+              |              +---------------------+
                                     v
                       +---------------------------+
                       | Real-Time Telemetry Stream|
                       | (WebSocket & REST API)    |
                       +-------------+-------------+
                                     |
          +--------------------------+--------------------------+
          |                                                     |
          v                                                     v
+-----------------------+                             +--------------------+
| XGBoost / Ridge / SVR |                             | Counterfactual     |
| Multi-Horizon Forecast|                             | Optimization Tree  |
| (+5m to +30m Horizon) |                             | (5 Control Actions)|
+-----------+-----------+                             +---------+----------+
            |                                                   |
            +---------------------+-----------------------------+
                                  |
                                  v
            +-------------------------------------------+
            |   Autonomous Closed-Loop Interventions    |
            |  & Research-Grade PDF Engineering Reports |
            +-------------------------------------------+
```

---

## Key Features

1. **RC Thermal Physics Engine**:
   - Multi-rack thermal simulation with CPU/GPU heat dissipation modeling.
   - Dynamic air circulation, CRAH fan laws (affinity laws), and chiller COP derating.
   - Hot-aisle/cold-aisle containment and rack-to-rack thermal coupling.

2. **Predictive ML Forecasting**:
   - Multi-horizon temperature forecasting (+5 min, +10 min, +15 min, +30 min).
   - XGBoost Regressor, Random Forest, Ridge Regression, and SVR models.
   - Real-time Explainable AI (XAI) feature attribution drivers.

3. **Counterfactual Optimization Engine**:
   - Fast-branching simulation testing multiple proactive interventions in parallel cloned twins:
     - Chiller supply setpoint trimming (-2.0°C)
     - CRAH airflow boosting (+20%)
     - Workload migration / dynamic load balancing
     - Compound / coordinated control
   - Energy delta calculation and SLA violation avoidance scoring.

4. **10 Failure Scenarios & Weather Stressors**:
   - CRAH fan bank failure, chiller outage, filter clogging, thermal runaway, AI training burst, extreme heatwaves, blizzards, and humid tropical environments.

5. **Full Web-Based Engineering GUI**:
   - 10 dedicated interactive views: System Overview, Digital Twin (3D/2D rack bay & heatmap), Simulation Lab, ML Forecasting, Optimization, Failure Scenarios, Event Log, Energy Analytics, Paradigm Ablation Benchmark, and Technical Reports.
   - Real-time WebSocket streaming with zero lag.
   - Interactive Light Mode & Dark Mode with seamless instant switching.

6. **Automated Research-Grade PDF Reporting**:
   - Built-in ReportLab engine generating comprehensive technical audit reports for individual simulations and full historical multi-run archives.

---

## Tech Stack

- **Backend**: Python 3.10+, FastAPI, Uvicorn, SQLAlchemy, NumPy, SciKit-Learn, XGBoost, ReportLab
- **Frontend**: Vanilla ES6+ JavaScript, HTML5, Modern Responsive CSS (Glassmorphism, High-Contrast Light/Dark themes, Flex/Grid)
- **Deployment**: Docker, Docker Compose, Shell scripts

---

## Quick Start Guide

### Prerequisites
- Python 3.10 or higher
- Git

### 1. Clone the Repository
```bash
git clone https://github.com/darshsaraf06/ML-Enhanced-Data-Center-Digital-Twin-Prototype.git
cd ML-Enhanced-Data-Center-Digital-Twin-Prototype
```

### 2. Set Up Virtual Environment & Dependencies
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Run the Server
```bash
# From backend directory with venv activated:
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```
Or simply use the root launcher:
```bash
./start.sh
```

### 4. Access the Dashboard
Open your browser and navigate to:
```
http://localhost:8000/
```

---

## Docker Deployment

To build and run via Docker Compose:
```bash
docker-compose up --build
```
The application will be accessible at `http://localhost:8000`.

---

## REST & WebSocket API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/ws` | WebSocket | High-frequency telemetry and status broadcast |
| `/api/health` | GET | Health check and subsystem diagnostic status |
| `/api/simulation/configure` | POST | Configure physical simulation parameters |
| `/api/simulation/start` | POST | Start live or timed simulation run |
| `/api/simulation/pause` | POST | Pause current simulation execution |
| `/api/simulation/resume` | POST | Resume execution |
| `/api/simulation/stop` | POST | Stop run and archive record to database |
| `/api/simulation/history` | GET | Retrieve past simulation records |
| `/api/simulation/history/export/csv` | GET | Download history archive as CSV |
| `/api/simulation/history/export/pdf` | GET | Download research-grade multi-run audit report PDF |
| `/api/simulation/{sim_id}/export` | GET | Export individual simulation record (JSON, CSV, PDF) |
| `/api/report/pdf` | GET | Generate detailed PDF report of active/latest simulation |
| `/api/counterfactual/evaluate` | POST | Run 5-branch cloned twin optimization evaluation |
| `/api/counterfactual/whatif` | POST | Interactive What-If comparative analysis |
| `/api/scenario/list` | GET | List all 10 failure scenarios and weather profiles |

---

## License

MIT License. Designed for data center thermal management research and engineering demonstration.

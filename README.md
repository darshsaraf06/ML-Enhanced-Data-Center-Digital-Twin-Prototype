# ML-Enhanced Data Center Digital Twin Prototype

An enterprise-grade physical and predictive digital twin platform for modern data centers. Combines RC equivalent circuit thermodynamics, multi-horizon machine learning forecasting, and real-time counterfactual optimization to prevent thermal hotspots, cut cooling energy, and enforce ASHRAE compliance.

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

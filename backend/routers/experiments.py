"""
Experiments & Research Benchmark Router.
Compares the 5 research paradigms with downloadable CSV and JSON exports.
"""

import io
import csv
import json
from fastapi import APIRouter, Response
from simulation_engine import engine

router = APIRouter(prefix="/api/experiments", tags=["experiments"])


@router.get("/comparison")
async def get_benchmark_comparison():
    return {
        "paradigms": engine.benchmarks.get_comparison(),
        "simId": engine.sim_id,
        "ticks": engine.benchmarks.ticks,
    }


@router.get("/export/csv")
async def export_experiments_csv():
    comparison = engine.benchmarks.get_comparison()
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Paradigm ID",
        "Paradigm Name",
        "MAE (°C)",
        "RMSE (°C)",
        "R2 Score",
        "Thermal SLA Violations",
        "Total Energy (kWh)",
        "Peak Temp (°C)",
        "Interventions Count",
        "Energy Savings (%)",
    ])

    for p in comparison:
        writer.writerow([
            p["id"],
            p["name"],
            p["mae"],
            p["rmse"],
            p["r2"],
            p["thermalViolations"],
            p["totalEnergyKWh"],
            p["peakTemp"],
            p["interventionsCount"],
            p["energySavingsPct"],
        ])

    csv_data = output.getvalue()
    headers = {
        "Content-Disposition": 'attachment; filename="datacenter_experiments_benchmark.csv"',
        "Content-Type": "text/csv",
    }
    return Response(content=csv_data, media_type="text/csv", headers=headers)


@router.get("/export/json")
async def export_experiments_json():
    comparison = engine.benchmarks.get_comparison()
    data = json.dumps({"simId": engine.sim_id, "results": comparison}, indent=2)
    headers = {
        "Content-Disposition": 'attachment; filename="datacenter_experiments_benchmark.json"',
        "Content-Type": "application/json",
    }
    return Response(content=data, media_type="application/json", headers=headers)

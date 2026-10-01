"""
Simulation Router - timed simulation lab controls, speed scaling, and lifecycle management.
"""

import csv
import io
import json
from datetime import datetime
from fastapi import APIRouter, HTTPException, Response, Query
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

from simulation_engine import engine
from db import SessionLocal, SimulationRecord

router = APIRouter(prefix="/api/simulation", tags=["simulation"])


class ConfigureSimulationRequest(BaseModel):
    durationSec: int = Field(default=3600, ge=60, le=86400)
    timestepSec: float = Field(default=1.0, ge=0.1, le=10.0)
    numRacks: int = Field(default=8, ge=4, le=12)
    initialWorkload: float = Field(default=60.0, ge=10.0, le=100.0)
    initialAmbientTemp: float = Field(default=24.0, ge=10.0, le=50.0)
    initialHumidity: float = Field(default=50.0, ge=10.0, le=99.0)
    coolingSetpoint: float = Field(default=18.0, ge=14.0, le=26.0)
    crahAirflow: float = Field(default=8500.0, ge=3000.0, le=15000.0)
    mlModel: str = Field(default="xgboost")
    optimizationEnabled: bool = Field(default=True)
    weatherPreset: str = Field(default="normal")
    failureScenario: str = Field(default="none")
    workloadPreset: str = Field(default="baseline")


class SpeedRequest(BaseModel):
    multiplier: float = Field(default=1.0, ge=0.5, le=120.0)


@router.post("/configure")
async def configure_simulation(body: ConfigureSimulationRequest):
    engine.configure_simulation(
        duration_sec=body.durationSec,
        timestep_sec=body.timestepSec,
        num_racks=body.numRacks,
        initial_workload=body.initialWorkload,
        initial_ambient_temp=body.initialAmbientTemp,
        initial_humidity=body.initialHumidity,
        cooling_setpoint=body.coolingSetpoint,
        crah_airflow=body.crahAirflow,
        ml_model=body.mlModel,
        optimization_enabled=body.optimizationEnabled,
        weather_preset=body.weatherPreset,
        failure_scenario=body.failureScenario,
        workload_preset=body.workloadPreset,
    )
    return {"ok": True, "state": engine.to_dict()}


@router.post("/start")
async def start_simulation():
    engine.start_simulation()
    return {"ok": True, "status": engine.status}


@router.post("/pause")
async def pause_simulation():
    engine.pause_simulation()
    return {"ok": True, "status": engine.status}


@router.post("/resume")
async def resume_simulation():
    engine.resume_simulation()
    return {"ok": True, "status": engine.status}


@router.post("/stop")
async def stop_simulation():
    engine.stop_simulation()
    return {"ok": True, "status": engine.status, "summary": engine.simulation_summary}


@router.post("/restart")
async def restart_simulation():
    engine.restart_simulation()
    return {"ok": True, "status": engine.status}


@router.post("/speed")
async def set_speed(body: SpeedRequest):
    engine.set_speed(body.multiplier)
    return {"ok": True, "speedMultiplier": engine.sim_speed_multiplier}


@router.get("/status")
async def get_status():
    return {
        "simId": engine.sim_id,
        "mode": engine.mode,
        "status": engine.status,
        "clock": engine.to_dict()["clock"],
        "systemHealth": engine.get_system_health(),
        "summary": engine.simulation_summary,
    }


@router.get("/history")
async def get_history():
    db = SessionLocal()
    records = db.query(SimulationRecord).order_by(SimulationRecord.created_at.desc()).limit(50).all()
    out = []
    for r in records:
        summary = {}
        try:
            if r.summary_json:
                summary = json.loads(r.summary_json)
        except Exception:
            pass

        thermal = summary.get("thermal", {})
        energy = summary.get("energy", {})
        opt = summary.get("optimization", {})

        out.append({
            "id": r.id,
            "mode": r.mode or "standard",
            "status": r.status or "COMPLETED",
            "durationSec": r.duration_sec or 3600,
            "elapsedSec": r.elapsed_sec or 0,
            "weather": r.scenario_weather or "Normal",
            "problem": r.scenario_problem or "None",
            "workload": r.scenario_workload or "Baseline",
            "createdAt": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else "",
            "peakTemp": round(thermal.get("maxTemp", 26.5), 1),
            "avgTemp": round(thermal.get("avgTemp", 24.8), 1),
            "avgPue": round(energy.get("avgPUE", 1.25), 3),
            "energySavedPct": round(opt.get("energySavingPercent", 0.0), 1),
            "violationsCount": thermal.get("violationsCount", 0),
            "summary": summary,
        })
    db.close()
    return {"history": out}


@router.get("/history/export/csv")
async def export_all_history_csv():
    """Export all past simulation records as CSV."""
    db = SessionLocal()
    records = db.query(SimulationRecord).order_by(SimulationRecord.created_at.desc()).all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Simulation ID", "Mode", "Status", "Duration (s)", "Elapsed (s)",
        "Peak Temp (C)", "Avg Temp (C)", "Avg PUE", "Energy Saved (%)",
        "Violations", "Weather", "Failure Scenario", "Created At"
    ])

    for r in records:
        summary = {}
        try:
            if r.summary_json:
                summary = json.loads(r.summary_json)
        except Exception:
            pass
        thermal = summary.get("thermal", {})
        energy = summary.get("energy", {})
        opt = summary.get("optimization", {})

        writer.writerow([
            r.id,
            r.mode or "standard",
            r.status or "COMPLETED",
            r.duration_sec or 3600,
            r.elapsed_sec or 0,
            round(thermal.get("maxTemp", 26.5), 1),
            round(thermal.get("avgTemp", 24.8), 1),
            round(energy.get("avgPUE", 1.25), 3),
            round(opt.get("energySavingPercent", 0.0), 1),
            thermal.get("violationsCount", 0),
            r.scenario_weather or "Normal",
            r.scenario_problem or "None",
            r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else ""
        ])
    db.close()

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=simulation_history.csv"}
    )


@router.get("/history/export/pdf")
async def export_all_history_pdf():
    """Export all past simulation records as a PDF audit report."""
    db = SessionLocal()
    records = db.query(SimulationRecord).order_by(SimulationRecord.created_at.desc()).all()
    
    out = []
    for r in records:
        summary = {}
        try:
            if r.summary_json:
                summary = json.loads(r.summary_json)
        except Exception:
            pass
        thermal = summary.get("thermal", {})
        energy = summary.get("energy", {})
        opt = summary.get("optimization", {})
        out.append({
            "id": r.id,
            "mode": r.mode or "standard",
            "status": r.status or "COMPLETED",
            "durationSec": r.duration_sec or 3600,
            "elapsedSec": r.elapsed_sec or 0,
            "peakTemp": round(thermal.get("maxTemp", 26.5), 1),
            "avgTemp": round(thermal.get("avgTemp", 24.8), 1),
            "avgPue": round(energy.get("avgPUE", 1.25), 3),
            "energySavedPct": round(opt.get("energySavingPercent", 0.0), 1),
            "violationsCount": thermal.get("violationsCount", 0),
            "weather": r.scenario_weather or "Normal",
            "problem": r.scenario_problem or "None",
            "createdAt": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else "",
            "summary": summary
        })
    db.close()

    try:
        from report_engine import generate_history_pdf_report
        pdf_bytes = generate_history_pdf_report(out)
        date_str = datetime.now().strftime("%Y-%m-%d")
        headers = {
            "Content-Disposition": f'attachment; filename="Simulation_History_Report_{date_str}.pdf"',
            "Content-Type": "application/pdf",
        }
        return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)
    except Exception as exc:
        print(f"[PDF History] Generation error: {exc}")
        raise HTTPException(status_code=500, detail=f"Failed to generate history PDF: {exc}")


@router.get("/{sim_id}/export")
async def export_single_simulation(sim_id: str, format: str = Query("json")):
    """Export a specific simulation record as JSON, CSV, or PDF."""
    db = SessionLocal()
    r = db.query(SimulationRecord).filter(SimulationRecord.id == sim_id).first()
    db.close()

    if not r:
        raise HTTPException(status_code=404, detail="Simulation record not found")

    summary = {}
    try:
        if r.summary_json:
            summary = json.loads(r.summary_json)
    except Exception:
        pass

    if format.lower() == "pdf":
        date_str = r.created_at.strftime("%Y-%m-%d") if r.created_at else datetime.now().strftime("%Y-%m-%d")
        sim_id_clean = r.id.replace(":", "-").replace("/", "-")
        filename = f"DigitalTwin_Report_{sim_id_clean}_{date_str}.pdf"
        
        dur = r.duration_sec or 3600
        elap = r.elapsed_sec or 0
        dur_str = f"{dur // 3600:02d}:{(dur % 3600) // 60:02d}:{dur % 60:02d}"
        elap_str = f"{elap // 3600:02d}:{(elap % 3600) // 60:02d}:{elap % 60:02d}"

        report_payload = {
            "simId": r.id,
            "date": date_str,
            "durationFormatted": dur_str,
            "elapsedFormatted": elap_str,
            "modeName": r.mode or "Simulation Mode",
            "weatherName": r.scenario_weather or "Normal",
            "problemName": r.scenario_problem or "Nominal",
            "workloadName": r.scenario_workload or "Standard",
            "systemHealth": "Safe" if (summary.get("thermal", {}).get("violationsCount", 0) == 0) else "Warning",
            "numRacks": summary.get("numRacks", 8),
            "ambientTemp": summary.get("ambientTemp", 24.0),
            "humidity": summary.get("humidity", 50.0),
            "coolingSetpoint": summary.get("coolingSetpoint", 18.0),
            "crahAirflow": summary.get("crahAirflow", 8500.0),
            "chillerCOP": summary.get("chillerCOP", 3.8),
            "thermalSummary": summary.get("thermal", {}),
            "energySummary": summary.get("energy", {}),
            "mlSummary": summary.get("ml", {}),
            "optSummary": summary.get("optimization", {}),
            "recentAlerts": summary.get("recentAlerts", []),
        }
        try:
            from report_engine import generate_pdf_report
            pdf_bytes = generate_pdf_report(report_payload)
            headers = {
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Type": "application/pdf",
            }
            return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)
        except Exception as exc:
            print(f"[PDF] Generation error for sim {sim_id}: {exc}")
            raise HTTPException(status_code=500, detail=f"Failed to generate simulation PDF: {exc}")

    if format.lower() == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Metric", "Value"])
        writer.writerow(["Simulation ID", r.id])
        writer.writerow(["Mode", r.mode])
        writer.writerow(["Status", r.status])
        writer.writerow(["Duration Seconds", r.duration_sec])
        writer.writerow(["Elapsed Seconds", r.elapsed_sec])
        writer.writerow(["Weather", r.scenario_weather])
        writer.writerow(["Problem Scenario", r.scenario_problem])
        writer.writerow(["Created At", r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else ""])

        thermal = summary.get("thermal", {})
        for k, v in thermal.items():
            writer.writerow([f"Thermal - {k}", v])

        energy_data = summary.get("energy", {})
        for k, v in energy_data.items():
            if not isinstance(v, (list, dict)):
                writer.writerow([f"Energy - {k}", v])

        opt_data = summary.get("optimization", {})
        for k, v in opt_data.items():
            if not isinstance(v, (list, dict)):
                writer.writerow([f"Optimization - {k}", v])

        return Response(
            content=output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=simulation_{sim_id}.csv"}
        )

    # Default JSON
    record_dict = {
        "id": r.id,
        "mode": r.mode,
        "status": r.status,
        "durationSec": r.duration_sec,
        "elapsedSec": r.elapsed_sec,
        "weather": r.scenario_weather,
        "problem": r.scenario_problem,
        "workload": r.scenario_workload,
        "createdAt": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else "",
        "summary": summary
    }
    return Response(
        content=json.dumps(record_dict, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=simulation_{sim_id}.json"}
    )


@router.delete("/history/clear")
async def clear_history():
    """Clear all past simulation records from the database."""
    db = SessionLocal()
    db.query(SimulationRecord).delete()
    db.commit()
    db.close()
    return {"ok": True, "message": "Simulation history cleared"}

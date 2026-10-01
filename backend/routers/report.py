"""
Report Router - compiles and streams research-grade PDF engineering reports.
Filename format: DigitalTwin_Report_<SimulationID>_<Date>.pdf
"""

from datetime import datetime
from fastapi import APIRouter, Response, HTTPException
from simulation_engine import engine
from report_engine import generate_pdf_report

router = APIRouter(prefix="/api/report", tags=["report"])


@router.get("/pdf")
async def download_pdf_report():
    """
    Generate and stream downloadable PDF report based on current or completed simulation.
    """
    state = engine.to_dict()
    summary = engine.simulation_summary

    # Ensure summary is populated even if still running
    if not summary:
        engine._generate_completion_summary()
        summary = engine.simulation_summary

    date_str = datetime.now().strftime("%Y-%m-%d")
    sim_id_clean = engine.sim_id.replace(":", "-").replace("/", "-")
    filename = f"DigitalTwin_Report_{sim_id_clean}_{date_str}.pdf"

    report_payload = {
        "simId": engine.sim_id,
        "date": date_str,
        "durationFormatted": summary.get("durationFormatted", "01:00:00"),
        "elapsedFormatted": summary.get("elapsedFormatted", "01:00:00"),
        "modeName": summary.get("modeName", "Simulation Mode"),
        "weatherName": summary.get("weatherName", "Normal"),
        "problemName": summary.get("problemName", "Nominal"),
        "workloadName": summary.get("workloadName", "Standard"),
        "systemHealth": summary.get("systemHealth", "Safe"),
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
        "recentAlerts": engine.alerts.events[:15],
    }

    try:
        pdf_bytes = generate_pdf_report(report_payload)
        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "application/pdf",
        }
        return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)
    except Exception as exc:
        print(f"[PDF] Generation error: {exc}")
        raise HTTPException(status_code=500, detail=f"Failed to generate PDF: {exc}")


@router.get("/data")
async def get_report_data():
    """Return JSON structured data for in-browser Report viewer."""
    if not engine.simulation_summary:
        engine._generate_completion_summary()
    return engine.simulation_summary

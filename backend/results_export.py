"""
PDF, CSV and JSON exports of a run's results.

All three are generated from the same results dictionary (results_engine.compile_results),
so they contain exactly what the Results page shows, including the explanation of every
section, metric and column (results_engine.EXPLANATIONS).
"""

import csv
import io
import json
from typing import Any, Dict, List

from alert_engine import fmt_time
from results_engine import COMPARE_METRICS, EXPLANATIONS


def _fmt(v: Any, nd: int = 2) -> str:
    if v is None:
        return "n/a"
    if isinstance(v, bool):
        return "Yes" if v else "No"
    if isinstance(v, float):
        return f"{v:.{nd}f}"
    return str(v)


def _expl(results: Dict[str, Any]) -> Dict[str, Any]:
    return results.get("explanations") or EXPLANATIONS


def to_json(results: Dict[str, Any]) -> bytes:
    out = dict(results)
    out.setdefault("explanations", EXPLANATIONS)
    return json.dumps(out, indent=2).encode("utf-8")


def to_csv(results: Dict[str, Any]) -> bytes:
    ex = _expl(results)
    out = io.StringIO()
    w = csv.writer(out)

    def section(title: str, key: str = None):
        w.writerow([])
        w.writerow([f"## {title}"])
        if key and key in ex["sections"]:
            w.writerow(["What this means", ex["sections"][key]])

    w.writerow(["Data center digital twin: run results"])
    w.writerow(["Run ID", results["runId"]])
    w.writerow(["Generated", results["generatedAt"]])
    w.writerow(["Elapsed", results["elapsed"]])
    w.writerow(["End", results["endReason"]])
    cfg = results["config"]
    for k in ("mode", "numRacks", "scale", "climate", "events", "durationS", "seed", "mlModel", "inletLimit",
              "gridFactor", "priceKwh", "priceWaterKl"):
        w.writerow([f"Config {k}", json.dumps(cfg.get(k)) if isinstance(cfg.get(k), (list, dict)) else cfg.get(k)])
    section("Summary", "summary")
    w.writerow(["Summary", results["summaryText"]])

    section("Resources (this run)", "resources")
    res = results["resources"]
    w.writerow(["metric", "value", "explanation"])
    for k, v in res.items():
        if k not in ("racks", "assumptions"):
            w.writerow([k, v, ex["metrics"].get(k, "")])
    for k, v in res["assumptions"].items():
        w.writerow([f"assumption {k}", v, "Configured at setup."])

    for key, title, base in (("vsFixed", "Comparison vs fixed cooling (same seed and events)", "fixed"),
                             ("vsReactive", "Comparison vs reactive threshold cooling (same seed and events)", "reactive")):
        section(title)
        w.writerow(["Baseline", ex["baselines"][base]])
        w.writerow(["metric", "unit", "this run", "baseline", "difference", "percent", "explanation"])
        for r in results["comparison"][key]:
            w.writerow([r["label"], r["unit"], r["project"], r["baseline"], r["difference"], r["percent"],
                        ex["metrics"].get(r["metric"], "")])
        w.writerow(["difference", "", "", "", "", "", ex["metrics"]["difference"]])
        w.writerow(["percent", "", "", "", "", "", ex["metrics"]["percent"]])

    section("Solutions comparison (scenario re-run with each response)", "solutions")
    w.writerow(["variant", "description", "alerts"] + [label for _, label, _ in COMPARE_METRICS])
    for s in results["solutions"]:
        w.writerow([s["label"], s["description"], s["alerts"]] + [s.get(k) for k, _, _ in COMPARE_METRICS])

    section("Alerts and decisions", "decisions")
    for k, v in ex["decisionColumns"].items():
        w.writerow([f"column {k}", v])
    w.writerow(["decision", "time", "rack", "forecast C", "horizon min", "probability %", "option", "option explanation", "safe",
                "peak C", "energy change %", "disruption", "cost score", "recommended", "chosen", "chooser", "reason"])
    for d in results["decisions"]:
        for c in d["candidates"]:
            r = c.get("result") or {}
            w.writerow([d["id"], d["time"], d["rack"], d["forecastTemp"], d["horizonMin"], d["probabilityPercent"],
                        c["title"], ex["actions"].get(c["actionId"], ""), r.get("safe"), r.get("peakInlet"),
                        r.get("energyChangePercent"), c.get("disruption"), r.get("costScore"),
                        c["actionId"] == d["recommended"], c["actionId"] == d["chosen"],
                        d["chooser"] if c["actionId"] == d["chosen"] else "", d["reason"] if c["actionId"] == d["chosen"] else ""])

    section("Racks", "racks")
    for k, v in ex["rackColumns"].items():
        w.writerow([f"column {k}", v])
    w.writerow(["rack", "zone", "type", "max power kW", "peak inlet C", "average inlet C", "peak exhaust C",
                "average utilization %", "energy kWh", "minutes above limit", "hotspot events"])
    for r in results["racks"]:
        w.writerow([r["code"], r["zone"], r["typeLabel"], r["pmaxKw"], r["peakInlet"], r["avgInlet"], r["peakExhaust"],
                    r["avgUtil"], r["energyKwh"], r["minutesAboveLimit"], r["hotspotEvents"]])

    section("Forecast accuracy", "ml")
    for k, v in ex["mlColumns"].items():
        w.writerow([f"column {k}", v])
    w.writerow(["model", "horizon min", "accuracy within 1 C %", "within 0.5 C %", "MAE C", "RMSE C", "R2",
                "skill vs persistence", "held-out scenario MAE C"])
    for m in results["ml"]["offline"]:
        if m.get("unavailable"):
            w.writerow([m["name"], "unavailable", m["unavailable"]])
            continue
        for h, row in m["byHorizon"].items():
            w.writerow([m["name"], h, row.get("within1Pct"), row.get("within05Pct"), row["mae"], row["rmse"], row["r2"],
                        row["skillRmse"], row["heldoutMae"]])
    w.writerow([])
    w.writerow(["This run: horizon min", "accuracy within 1 C %", "within 0.5 C %", "MAE C", "RMSE C", "checks"])
    for h, row in results["ml"]["live"].items():
        w.writerow([h, row.get("within1Pct"), row.get("within05Pct"), row["mae"], row["rmse"], row["count"]])

    section("Event summary by category", "events")
    for k, v in results["events"]["counts"]["byCategory"].items():
        w.writerow([k, v, ex["categories"].get(k, "")])
    for k, v in ex["severities"].items():
        w.writerow([f"severity {k}", "", v])
    section("Events")
    w.writerow(["time", "severity", "category", "source", "title", "detail", "racks", "grouped count", "values"])
    for e in results["events"]["list"]:
        w.writerow([e["time"], e["severity"], e["category"], e["sourceId"], e["title"], e["detail"],
                    " ".join(e["racks"]), e["count"], json.dumps(e["values"])])

    section("Timeline: hottest inlet (C)", "timeline")
    w.writerow(["time s", "hottest inlet C"])
    for t, v in results["timeline"]["points"]:
        w.writerow([t, v])
    section("Over-limit periods")
    for p in results["timeline"]["overLimit"]:
        w.writerow([fmt_time(p["start"]), fmt_time(p["end"])])
    section("Workload: average utilization (%)", "workload")
    for t, v in results["workload"]["points"]:
        w.writerow([t, v])
    section("High workload periods (average above threshold)")
    for p in results["workload"]["highPeriods"]:
        w.writerow([fmt_time(p["start"]), fmt_time(p["end"])])
    return out.getvalue().encode("utf-8")


def to_pdf(results: Dict[str, Any]) -> bytes:
    from reportlab.graphics.charts.lineplots import LinePlot
    from reportlab.graphics.shapes import Drawing, Line, Rect, String
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    ex = _expl(results)
    ORANGE, INK, MUTED = colors.HexColor("#d9480f"), colors.HexColor("#1a1611"), colors.HexColor("#594e3e")
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=16 * mm,
                            bottomMargin=16 * mm, title=f"Run results {results['runId']}")
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], textColor=INK)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], textColor=ORANGE)
    body = ParagraphStyle("body", parent=ss["BodyText"], textColor=INK)
    small = ParagraphStyle("small", parent=body, fontSize=8, leading=10)
    hint = ParagraphStyle("hint", parent=body, fontSize=8.5, leading=11, textColor=MUTED)
    what = ParagraphStyle("what", parent=body, fontSize=9, leading=12, textColor=INK, backColor=colors.HexColor("#f6eee0"),
                          borderPadding=5, borderColor=colors.HexColor("#dccfb7"), borderWidth=0.5, spaceBefore=4, spaceAfter=6)
    story: List[Any] = []

    def table(rows, widths=None, font=8):
        t = Table([[Paragraph(str(c), small) for c in r] for r in rows], colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), ORANGE),
                               ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                               ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d6cbb6")),
                               ("FONTSIZE", (0, 0), (-1, -1), font), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        return t

    def meaning(key):
        if key in ex["sections"]:
            story.append(Paragraph("<b>What this means:</b> " + ex["sections"][key], what))

    def how_to_read(pairs):
        story.append(Paragraph("<b>How to read the numbers</b>", hint))
        for name, text in pairs:
            story.append(Paragraph(f"<b>{name}:</b> {text}", hint))
        story.append(Spacer(1, 4))

    def chart(series_list, title, y_label, limit=None, shade=None, x_max=None):
        d = Drawing(170 * mm, 62 * mm)
        lp = LinePlot()
        lp.x, lp.y, lp.width, lp.height = 14 * mm, 10 * mm, 150 * mm, 44 * mm
        data = [s for s, _, _ in series_list if s]
        if not data:
            return d
        lp.data = data
        for i, (_, color, _) in enumerate([x for x in series_list if x[0]]):
            lp.lines[i].strokeColor = color
            lp.lines[i].strokeWidth = 1.2
        all_y = [p[1] for s in data for p in s] + ([limit] if limit is not None else [])
        lp.yValueAxis.valueMin = min(all_y) - 0.5
        lp.yValueAxis.valueMax = max(all_y) + 0.5
        lp.xValueAxis.valueMin = 0
        lp.xValueAxis.valueMax = x_max or max(p[0] for s in data for p in s)
        lp.xValueAxis.labelTextFormat = lambda v: fmt_time(v)[:5]
        lp.xValueAxis.labels.fontSize = 6
        lp.yValueAxis.labels.fontSize = 6
        d.add(lp)
        xmin, xmax = lp.xValueAxis.valueMin, lp.xValueAxis.valueMax
        ymin, ymax = lp.yValueAxis.valueMin, lp.yValueAxis.valueMax

        def X(v):
            return lp.x + (v - xmin) / max(1e-9, xmax - xmin) * lp.width

        def Y(v):
            return lp.y + (v - ymin) / max(1e-9, ymax - ymin) * lp.height
        for p in shade or []:
            d.add(Rect(X(p["start"]), lp.y, max(0.5, X(p["end"]) - X(p["start"])), lp.height,
                       fillColor=colors.Color(0.85, 0.2, 0.1, alpha=0.15), strokeColor=None))
        if limit is not None:
            d.add(Line(lp.x, Y(limit), lp.x + lp.width, Y(limit), strokeColor=colors.HexColor("#c81e14"),
                       strokeDashArray=[3, 2]))
        d.add(String(lp.x, lp.y + lp.height + 4, title, fontSize=8))
        d.add(String(0, lp.y + lp.height / 2, y_label, fontSize=6))
        legend_x = lp.x + 75 * mm
        for i, (_, color, label) in enumerate(series_list):
            d.add(Rect(legend_x + i * 26 * mm, lp.y + lp.height + 4, 6, 3, fillColor=color, strokeColor=None))
            d.add(String(legend_x + i * 26 * mm + 8, lp.y + lp.height + 3, label, fontSize=6))
        return d

    cfg = results["config"]
    res = results["resources"]
    story.append(Paragraph("Data center digital twin: run results", h1))
    story.append(Paragraph(f"Run {results['runId']} | generated {results['generatedAt']} | elapsed {results['elapsed']} "
                           f"({results['endReason']}) | {cfg['numRacks']} racks, {cfg['scale']} scale, climate {cfg['climate']}, "
                           f"seed {cfg['seed']}, model {cfg['mlModel']}, inlet limit {cfg['inletLimit']:.0f} C", small))
    story.append(Spacer(1, 6))
    story.append(Paragraph("About this report", h2))
    story.append(Paragraph(
        "This report comes from a software digital twin of a small data hall: a physics model of racks, airflow and a "
        "water-cooled chiller plant that steps every simulated second. Machine-learning models forecast every rack's inlet "
        "temperature 5 to 60 minutes ahead; when a breach of the limit is forecast, candidate responses are simulated in "
        "cloned twins and the safest, cheapest one is recommended. Every number below was produced by this run or by "
        "re-running the same scenario (same seed, weather, workload, events and your changes) with other policies. "
        "Each section starts with what it shows; a full list of definitions is at the end.", body))
    story.append(Paragraph("Summary", h2))
    meaning("summary")
    story.append(Paragraph(results["summaryText"], body))

    story.append(Paragraph("Hottest inlet temperature over time", h2))
    meaning("timeline")
    pts = [tuple(p) for p in results["timeline"]["points"]]
    fixed_pts = [tuple(p) for p in results["baselines"].get("fixedMaxInlet", [])]
    react_pts = [tuple(p) for p in results["baselines"].get("reactiveMaxInlet", [])]
    story.append(chart([(pts, ORANGE, "This run"), (fixed_pts, colors.HexColor("#8a7d66"), "Fixed"),
                        (react_pts, colors.HexColor("#0f7489"), "Reactive")],
                       "Hottest rack inlet (C); dashed line = limit; shaded = above limit", "C",
                       limit=results["inletLimit"], shade=results["timeline"]["overLimit"], x_max=results["elapsedS"]))
    marks = results["timeline"]["markers"][:60]
    if marks:
        story.append(Paragraph("Markers on the chart", hint))
        story.append(table([["Time", "Category", "Severity", "What happened"]] + [[m["time"], m["category"], m["severity"], m["title"]] for m in marks],
                           [20 * mm, 25 * mm, 20 * mm, 110 * mm]))

    story.append(Paragraph("Workload", h2))
    meaning("workload")
    story.append(chart([([tuple(p) for p in results["workload"]["points"]], ORANGE, "Average utilization")],
                       f"Average rack utilization (%); shaded = above {results['workload']['highThreshold']:.0f} %", "%",
                       shade=results["workload"]["highPeriods"], x_max=results["elapsedS"]))

    story.append(PageBreak())
    story.append(Paragraph("Energy, water, carbon and cost", h2))
    meaning("resources")
    story.append(table([["Metric", "Value", "What it is"],
                        ["IT energy", f"{res['itKwh']:.2f} kWh", ex["metrics"]["itKwh"]],
                        ["Cooling energy", f"{res['coolingKwh']:.2f} kWh", ex["metrics"]["coolingKwh"]],
                        ["  chiller / fans / pumps", f"{res['chillerKwh']:.2f} / {res['fansKwh']:.2f} / {res['pumpsKwh']:.2f} kWh",
                         "Split of cooling energy between the three parts of the plant."],
                        ["Total energy", f"{res['totalKwh']:.2f} kWh", ex["metrics"]["totalKwh"]],
                        ["PUE", _fmt(res["pue"], 3), ex["metrics"]["pue"]],
                        ["Water", f"{res['waterL']:.1f} L", ex["metrics"]["waterL"]],
                        ["WUE", f"{_fmt(res['wueLPerKwh'], 3)} L/kWh", ex["metrics"]["wueLPerKwh"]],
                        ["Carbon", f"{res['carbonKg']:.2f} kg CO2 (factor {res['assumptions']['gridFactorKgPerKwh']} kg/kWh)", ex["metrics"]["carbonKg"]],
                        ["Cost", f"INR {res['costInr']:.2f} (INR {res['assumptions']['electricityInrPerKwh']}/kWh, INR {res['assumptions']['waterInrPerKl']}/kL)", ex["metrics"]["costInr"]],
                        ["Minutes above limit", _fmt(res["minutesAboveLimit"]), ex["metrics"]["minutesAboveLimit"]],
                        ["Hotspot events", res["hotspotEvents"], ex["metrics"]["hotspotEvents"]],
                        ["Peak inlet", f"{_fmt(res['peakInlet'])} C at {fmt_time(res['peakInletTime'])}", ex["metrics"]["peakInlet"]]],
                       [40 * mm, 50 * mm, 88 * mm]))
    for key, title, base in (("vsFixed", "Compared with fixed cooling", "fixed"),
                             ("vsReactive", "Compared with reactive threshold cooling", "reactive")):
        story.append(Paragraph(title, h2))
        story.append(Paragraph(ex["baselines"][base] + " Same seed, weather, workload, events and operator changes.", hint))
        story.append(table([["Metric", "This run", "Baseline", "Difference", "%"]] +
                           [[f"{r['label']} ({r['unit']})" if r["unit"] else r["label"], _fmt(r["project"]), _fmt(r["baseline"]),
                             _fmt(r["difference"]), _fmt(r["percent"])] for r in results["comparison"][key]],
                           [50 * mm, 30 * mm, 30 * mm, 35 * mm, 30 * mm]))
    how_to_read([("Difference", ex["metrics"]["difference"]), ("%", ex["metrics"]["percent"]),
                 ("This project", ex["baselines"]["predictive"])])

    story.append(PageBreak())
    story.append(Paragraph("Alerts and decisions", h2))
    meaning("decisions")
    if not results["decisions"]:
        story.append(Paragraph("No hotspot alerts were raised in this run.", body))
    for d in results["decisions"]:
        story.append(Paragraph(f"<b>{d['time']}: {d['headline']}</b> (probability {d['probabilityPercent']:.0f} %, racks at risk {', '.join(d['atRisk'])})", body))
        story.append(table([["Option", "Safe", "Peak C", "Energy %", "Disruption", "Cost", "Status"]] +
                           [[c["title"], _fmt((c.get("result") or {}).get("safe")), _fmt((c.get("result") or {}).get("peakInlet")),
                             _fmt((c.get("result") or {}).get("energyChangePercent")), _fmt(c.get("disruption")),
                             _fmt((c.get("result") or {}).get("costScore")),
                             ("Chosen by " + str(d["chooser"]) if c["actionId"] == d["chosen"] else "") +
                             (" Recommended" if c["actionId"] == d["recommended"] else "")] for c in d["candidates"]],
                           [45 * mm, 13 * mm, 17 * mm, 20 * mm, 20 * mm, 17 * mm, 43 * mm]))
        story.append(Paragraph("<b>Why:</b> " + (d["reason"] or ""), hint))
        story.append(Spacer(1, 4))
    how_to_read([(k.replace("Percent", " %"), v) for k, v in ex["decisionColumns"].items()]
                + [(f"Option: {k.replace('_', ' ')}", v) for k, v in ex["actions"].items()])

    story.append(Paragraph("Solutions comparison", h2))
    meaning("solutions")
    story.append(table([["Variant", "Alerts", "Energy kWh", "Peak C", "Min above", "Hotspots", "Water L", "Cost INR"]] +
                       [[s["label"], s["alerts"], _fmt(s["totalKwh"]), _fmt(s["peakInlet"]), _fmt(s["minutesAboveLimit"]),
                         s["hotspotEvents"], _fmt(s["waterL"], 1), _fmt(s["costInr"])] for s in results["solutions"]],
                       [48 * mm, 14 * mm, 20 * mm, 17 * mm, 20 * mm, 17 * mm, 18 * mm, 22 * mm]))
    how_to_read([(s["label"], s["description"]) for s in results["solutions"]])

    story.append(Paragraph("Rack by rack", h2))
    meaning("racks")
    story.append(table([["Rack", "Zone", "Type", "Peak inlet", "Avg inlet", "Peak exhaust", "Avg util %", "kWh", "Min above"]] +
                       [[r["code"], r["zone"], r["typeLabel"], _fmt(r["peakInlet"]), _fmt(r["avgInlet"]), _fmt(r["peakExhaust"]),
                         _fmt(r["avgUtil"], 1), _fmt(r["energyKwh"]), _fmt(r["minutesAboveLimit"])] for r in results["racks"]]))
    how_to_read(list(ex["rackColumns"].items()))

    story.append(PageBreak())
    story.append(Paragraph("Forecast accuracy", h2))
    meaning("ml")
    story.append(Paragraph("This run: forecasts compared with what actually happened", body))
    story.append(table([["Horizon", "Accuracy (within 1 C)", "Within 0.5 C", "MAE C", "RMSE C", "Checks"]] +
                       [[f"+{h} min", f"{_fmt(r.get('within1Pct'), 1)} %", f"{_fmt(r.get('within05Pct'), 1)} %", _fmt(r["mae"], 3),
                         _fmt(r["rmse"], 3), r["count"]] for h, r in results["ml"]["live"].items()]))
    story.append(Spacer(1, 4))
    story.append(Paragraph("Offline test sets", body))
    rows = [["Model", "Horizon", "Accuracy (within 1 C)", "MAE C", "RMSE C", "R2", "Skill", "Held-out MAE"]]
    for m in results["ml"]["offline"]:
        if m.get("unavailable"):
            rows.append([m["name"], "unavailable", m["unavailable"], "", "", "", "", ""])
            continue
        for h, r in m["byHorizon"].items():
            rows.append([m["name"] + (" (active)" if m.get("active") else ""), f"+{h} min",
                         "n/a" if r.get("within1Pct") is None else f"{r['within1Pct']:.1f} %", _fmt(r["mae"], 3),
                         _fmt(r["rmse"], 3), _fmt(r["r2"], 3), _fmt(r["skillRmse"], 3), _fmt(r["heldoutMae"], 3)])
    story.append(table(rows))
    story.append(Paragraph(results["ml"]["note"], hint))
    how_to_read([(k, v) for k, v in ex["mlColumns"].items()])

    story.append(Paragraph("Events", h2))
    meaning("events")
    counts = results["events"]["counts"]
    story.append(table([["Category", "Count", "What it covers"]] +
                       [[k, v, ex["categories"].get(k, "")] for k, v in counts["byCategory"].items() if v],
                       [30 * mm, 18 * mm, 130 * mm]))
    how_to_read(list(ex["severities"].items()))
    ev_rows = [["Time", "Severity", "Category", "Source", "Title", "Detail"]]
    for e in results["events"]["list"][:250]:
        ev_rows.append([e["time"], e["severity"], e["category"], e["sourceId"], e["title"], e["detail"]])
    story.append(table(ev_rows, [16 * mm, 16 * mm, 20 * mm, 16 * mm, 45 * mm, 62 * mm], font=7))

    story.append(PageBreak())
    story.append(Paragraph("Definitions and methods", h2))
    groups = [("Energy, water, carbon and cost", ex["metrics"]), ("Baselines and policies", ex["baselines"]),
              ("Decision table columns", ex["decisionColumns"]), ("Solution options", ex["actions"]),
              ("Rack table columns", ex["rackColumns"]), ("Forecast accuracy measures", ex["mlColumns"]),
              ("Event severities", ex["severities"]), ("Event categories", ex["categories"])]
    for title, items in groups:
        story.append(Paragraph(f"<b>{title}</b>", body))
        story.append(table([["Term", "Meaning"]] + [[k, v] for k, v in items.items()], [40 * mm, 138 * mm]))
        story.append(Spacer(1, 4))
    doc.build(story)
    return buf.getvalue()

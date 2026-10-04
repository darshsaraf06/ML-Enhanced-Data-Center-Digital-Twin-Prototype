// Results page: opens automatically when a run ends. Polls until the comparison
// replays have finished, then renders every section from the backend results object.
import { api } from './api.js';
import { esc, num, signed, hms, toast } from './util.js';
import { themeToggleHtml } from './shared.js';
import { alpha, baseOptions, bandPlugin, line, markerPlugin, pal, RACK_COLORS } from './charts.js';
import { eventHtml } from './events.js';

const what = text => `<p class="v3-what"><b>What this means:</b> ${text}</p>`;

export class ResultsScreen {
    constructor(root, savedId = null) {
        this.root = root;
        this.savedId = savedId;
        this.charts = [];
        this.timer = null;
        this.root.innerHTML = `<main class="v3-screen"><div class="v3-wrap">
            <div class="v3-topline">${savedId ? '<button class="simple-link" data-nav="#/logs">Back to Past Logs</button>' : '<span class="flow-kicker">RESULTS</span>'}${themeToggleHtml()}</div>
            <div id="resultsBody"><h1 class="v3-h1">Preparing results</h1>
            <p class="v3-lead" id="resStatus">Re-running the same scenario with other policies for a fair comparison...</p>
            <div class="simple-progress"><span id="resBar"></span></div></div>
        </div></main>`;
        this.onTheme = () => { if (this.data) this.render(this.data); };
        window.addEventListener('themechange', this.onTheme);
        if (savedId) this.loadSaved();
        else this.poll();
    }

    async loadSaved() {
        try {
            this.data = await api.savedRun(this.savedId);
            this.render(this.data);
        } catch (err) {
            this.root.querySelector('#resultsBody').innerHTML = `<h1 class="v3-h1">Saved run not found</h1><p class="v3-lead">${esc(err.message)}</p>
                <button class="btn btn-primary btn-lg" data-nav="#/logs">Back to Past Logs</button>`;
        }
    }

    destroy() {
        clearTimeout(this.timer);
        window.removeEventListener('themechange', this.onTheme);
        this.charts.forEach(c => c.destroy());
    }

    async poll() {
        try {
            const r = await api.results();
            if (r.results) { this.data = r.results; this.render(r.results); return; }
            const st = r.status || {};
            if (st.state === 'none') {
                this.root.querySelector('#resultsBody').innerHTML = `<h1 class="v3-h1">No finished run yet</h1><p class="v3-lead">Results appear here when a run reaches its end, is ended, or is skipped to the end.</p>
                <div class="v3-row"><button class="btn btn-primary btn-lg" data-nav="#/live">Back to the live run</button><button class="btn btn-outline btn-lg" data-nav="#/menu">Menu</button></div>`;
                return;
            }
            if (st.state === 'error') { this.root.querySelector('#resStatus').textContent = st.step; return; }
            const bar = this.root.querySelector('#resBar');
            if (bar) bar.style.width = `${st.progress || 0}%`;
            const status = this.root.querySelector('#resStatus');
            if (status) status.textContent = `Re-running the same scenario with other policies for a fair comparison: ${num(st.progress, 0)} %. ${st.step || ''}`;
        } catch (err) {
            toast(err.message, 'error');
        }
        this.timer = setTimeout(() => this.poll(), 1000);
    }

    render(R) {
        const EX = R.explanations || {};
        const exportBase = this.savedId ? `/api/runs/${encodeURIComponent(this.savedId)}/export` : '/api/run/export';
        this.charts.forEach(c => c.destroy());
        this.charts = [];
        const res = R.resources;
        const lim = R.inletLimit;
        const fixedE = R.comparison.vsFixed.find(x => x.metric === 'totalKwh');
        const body = this.root.querySelector('#resultsBody');
        body.innerHTML = `
            <h1 class="v3-h1">Simulation results</h1>
            ${this.savedId ? '<div class="v3-note">Saved run, read-only. Exports below are generated again from the saved results.</div>' : ''}
            <p class="v3-muted">Run ${esc(R.runId)}, ${R.endReason === 'completed' ? 'completed' : 'ended early'} at ${esc(R.elapsed)} of ${hms(R.durationS)}. ${R.config.numRacks} racks, ${esc(R.config.scale)} scale, ${esc(R.config.climate)} climate, seed ${R.config.seed}, ${R.config.mode === 'demo' ? 'Demonstration' : 'Simulation'}.</p>
            <section class="panel-card v3-panel"><h2>Summary</h2><p>${esc(R.summaryText)}</p>
            <div class="v3-kpis">
                ${tile('Peak inlet', `${num(res.peakInlet, 1)} C`, `at ${hms(res.peakInletTime)}, limit ${num(lim, 0)} C`)}
                ${tile('Minutes above limit', num(res.minutesAboveLimit, 1), `${res.hotspotEvents} hotspot episodes`)}
                ${tile('Total energy', `${num(res.totalKwh, 1)} kWh`, `PUE ${num(res.pue, 3)}`)}
                ${tile('Energy vs fixed cooling', fixedE ? `${signed(fixedE.percent, 1)} %` : 'n/a', fixedE ? `${signed(fixedE.difference, 2)} kWh, same seed and events` : '')}
            </div>
            ${what('These are the headline numbers from this run. Negative percentages mean this run used less than the baseline.')}</section>

            <section class="panel-card v3-panel"><h2>Hottest inlet over time</h2>
            <div class="v3-chart"><canvas id="rTimeline" role="img" aria-label="Hottest inlet over time"></canvas></div>
            ${what(`The orange line is the warmest rack inlet at each moment in this run; grey and blue show the same scenario with fixed and reactive cooling. Red shading marks time above the ${num(lim, 0)} C limit. Dashed vertical lines mark events, alerts, solutions and user actions (listed below).`)}
            <details class="v3-details"><summary>Markers on this chart (${R.timeline.markers.length})</summary>
            <div class="v3-table-wrap"><table class="v3-table"><thead><tr><th>Time</th><th>Category</th><th>Severity</th><th>What happened</th></tr></thead><tbody>
            ${R.timeline.markers.map(m => `<tr><td>${esc(m.time)}</td><td>${esc(m.category)}</td><td>${esc(m.severity)}</td><td>${esc(m.title)}</td></tr>`).join('')}</tbody></table></div></details></section>

            <section class="panel-card v3-panel"><h2>Workload</h2>
            <div class="v3-chart"><canvas id="rWorkload" role="img" aria-label="Workload over time"></canvas></div>
            ${what(`Average utilization across racks (thick line) and each rack (thin lines). Amber shading marks periods with average utilization above ${num(R.workload.highThreshold, 0)} %, when racks produce the most heat.`)}</section>

            <section class="panel-card v3-panel"><h2>Energy, water, carbon and cost</h2>
            ${compareTable(R)}
            ${defs('How each number is calculated', EX.metrics, ['totalKwh', 'itKwh', 'coolingKwh', 'chillerKwh', 'fansKwh', 'pumpsKwh', 'pue', 'waterL', 'wueLPerKwh', 'carbonKg', 'costInr', 'minutesAboveLimit', 'hotspotEvents', 'peakInlet', 'difference', 'percent'])}
            ${defs('The three cooling policies compared', EX.baselines)}
            <p class="v3-hint">${esc(R.baselines.fixedDescription)} ${esc(R.baselines.reactiveDescription)} Both baselines were re-run with the same seed, weather, workload, events and your changes.</p>
            <p class="v3-hint">Water = evaporation plus blowdown in the cooling tower from the heat rejected; carbon uses ${res.assumptions.gridFactorKgPerKwh} kg CO2 per kWh; cost uses INR ${res.assumptions.electricityInrPerKwh} per kWh and INR ${res.assumptions.waterInrPerKl} per 1000 L.</p>
            ${what('Each row compares this run with a conventional way of running the cooling. The percentage is the change relative to that baseline; negative means this run used less.')}</section>

            <section class="panel-card v3-panel"><h2>Alerts and decisions</h2>
            ${R.decisions.length ? R.decisions.map(decisionHtml).join('') : '<p>No hotspot alert was raised in this run.</p>'}
            ${defs('How to read the decision tables', EX.decisionColumns)}
            ${defs('What each option does', EX.actions, null, k => (R.decisions[0]?.candidates.find(c => c.actionId === k)?.title) || k)}
            ${what('Every alert lists all the options the twin simulated, which were safe, what each would have cost, who chose, and why the chosen one won.')}</section>

            <section class="panel-card v3-panel"><h2>Solutions comparison</h2>
            <div class="v3-table-wrap"><table class="v3-table"><thead><tr><th>Variant</th><th>Alerts</th><th>Energy kWh</th><th>Peak C</th><th>Min above</th><th>Hotspots</th><th>Water L</th><th>Cost INR</th></tr></thead><tbody>
            ${R.solutions.map(s => `<tr${s.variant === 'your_run' ? ' class="v3-hl"' : ''}><td><b>${esc(s.label)}</b><br><small class="v3-muted">${esc(s.description)}</small></td><td>${s.alerts}</td><td>${num(s.totalKwh, 2)}</td><td>${num(s.peakInlet, 2)}</td><td>${num(s.minutesAboveLimit, 1)}</td><td>${s.hotspotEvents}</td><td>${num(s.waterL, 0)}</td><td>${num(s.costInr, 0)}</td></tr>`).join('')}
            </tbody></table></div>
            ${what('The whole scenario was re-run from the start, each time responding to every alert the same way. This shows how much each kind of response matters over the full run, not just at one moment.')}</section>

            <section class="panel-card v3-panel"><h2>Rack by rack</h2>
            <div class="v3-table-wrap"><table class="v3-table"><thead><tr><th>Rack</th><th>Type</th><th>Peak inlet</th><th>Avg inlet</th><th>Peak exhaust</th><th>Avg util</th><th>kWh</th><th>Min above</th></tr></thead><tbody>
            ${R.racks.map(r => `<tr><td>${r.code} (${r.zone})</td><td>${esc(r.typeLabel)}</td><td class="${r.peakInlet > lim ? 'v3-bad' : ''}">${num(r.peakInlet, 2)}</td><td>${num(r.avgInlet, 2)}</td><td>${num(r.peakExhaust, 1)}</td><td>${num(r.avgUtil, 0)} %</td><td>${num(r.energyKwh, 2)}</td><td>${num(r.minutesAboveLimit, 1)}</td></tr>`).join('')}
            </tbody></table></div>
            ${defs('What each column means', EX.rackColumns)}
            ${what('Temperatures are in C. Inlet is the air entering the rack (what the limit applies to); exhaust is the hot air leaving it.')}</section>

            <section class="panel-card v3-panel"><h2>Forecast accuracy</h2>
            <p>Active model: <b>${esc(R.ml.activeModelName || 'none')}</b>. In this run, forecasts were checked against what actually happened:</p>
            <div class="v3-table-wrap"><table class="v3-table"><thead><tr><th>Horizon</th><th>Accuracy (within 1 C)</th><th>Within 0.5 C</th><th>MAE C</th><th>RMSE C</th><th>Checks</th></tr></thead><tbody>
            ${Object.entries(R.ml.live).map(([h, r]) => `<tr><td>+${h} min</td><td><b>${r.within1Pct === null || r.within1Pct === undefined ? 'n/a' : num(r.within1Pct, 1) + ' %'}</b></td><td>${r.within05Pct === null || r.within05Pct === undefined ? 'n/a' : num(r.within05Pct, 1) + ' %'}</td><td>${num(r.mae, 3)}</td><td>${num(r.rmse, 3)}</td><td>${r.count}</td></tr>`).join('')}</tbody></table></div>
            <p class="v3-hint">Checks are made when the forecast time arrives, so runs shorter than a horizon have no checks for it.</p>
            <p>Offline test sets (chronological split, and held-out scenarios never seen in training):</p>
            ${mlTable(R.ml.offline)}
            ${defs('How accuracy is measured', EX.mlColumns)}
            ${what(esc(R.ml.note) + ' Skill above 0 means the model beats simply assuming the temperature stays the same.')}</section>

            <section class="panel-card v3-panel"><h2>Events</h2>
            <div class="v3-chips">${Object.entries(R.events.counts.byCategory).filter(([, v]) => v).map(([k, v]) => `<span class="v3-chip on">${esc(k)} <b>${v}</b></span>`).join('')}</div>
            <details class="v3-details"><summary>All ${R.events.list.length} events</summary><div class="v3-event-list">${R.events.list.map(e => eventHtml(e)).join('')}</div></details>
            ${defs('Severities', EX.severities)}
            ${defs('Categories', EX.categories)}
            ${what('Events are grouped by category. Thermal events are limit crossings, Forecast events are early warnings, Decision events are actions the twin or the operator took.')}</section>

            <section class="panel-card v3-panel"><h2>Export</h2>
            <div class="v3-row"><a class="btn btn-cyan btn-lg" href="${exportBase}?format=pdf" download data-export="pdf">Export PDF</a>
            <a class="btn btn-outline btn-lg" href="${exportBase}?format=csv" download data-export="csv">Export CSV</a>
            <a class="btn btn-outline btn-lg" href="${exportBase}?format=json" download data-export="json">Export JSON</a></div>
            ${what('Each export contains everything on this page, including these explanations: summary, timelines, resources and baselines, decisions with all options, solutions, racks, forecast accuracy, the full event list and a definitions section.')}</section>

            <div class="v3-row v3-bottom-actions"><button class="btn btn-primary btn-lg v3-big" data-nav="#/setup?mode=sim">New Simulation</button><button class="btn btn-outline btn-lg v3-big" data-nav="#/logs">Past Logs</button><button class="btn btn-outline btn-lg v3-big" data-nav="#/home">Home</button></div>`;
        this.drawCharts(R);
    }

    drawCharts(R) {
        if (!window.Chart) return;
        const Chart = window.Chart;
        const lim = R.inletLimit;
        const pts = R.timeline.points.map(([x, y]) => ({ x, y }));
        const end = R.elapsedS;
        const markers = () => R.timeline.markers;
        const p = pal();
        const opts = baseOptions({ yTitle: 'Hottest inlet (C)', markers, bands: () => R.timeline.overLimit.map(b => ({ ...b, color: alpha(p.signal, 0.16) })) });
        opts.scales.x.max = end;
        this.charts.push(new Chart(this.root.querySelector('#rTimeline'), {
            type: 'line', plugins: [markerPlugin, bandPlugin], options: opts,
            data: { datasets: [
                line('This run', p.molten, pts, { borderWidth: 2.2 }),
                line('Fixed cooling', p.muted, R.baselines.fixedMaxInlet.map(([x, y]) => ({ x, y }))),
                line('Reactive cooling', p.ice, R.baselines.reactiveMaxInlet.map(([x, y]) => ({ x, y }))),
                line('Limit', p.signal, [{ x: 0, y: lim }, { x: end, y: lim }], { borderDash: [6, 4] }),
            ] },
        }));
        const wopts = baseOptions({ yTitle: 'Utilization (%)', markers, yMin: 0, yMax: 100, bands: () => R.workload.highPeriods.map(b => ({ ...b, color: alpha(p.amber, 0.16) })) });
        wopts.scales.x.max = end;
        const series = R.series || [];
        const n = series.length ? series[0].util.length : 0;
        this.charts.push(new Chart(this.root.querySelector('#rWorkload'), {
            type: 'line', plugins: [markerPlugin, bandPlugin], options: wopts,
            data: { datasets: [
                line('Average', p.molten, R.workload.points.map(([x, y]) => ({ x, y })), { borderWidth: 2.8 }),
                ...Array.from({ length: n }, (_, i) => line(`R${String(i + 1).padStart(2, '0')}`, RACK_COLORS[i % 12], series.map(p => ({ x: p.t, y: p.util[i] })), { borderWidth: 0.8 })),
            ] },
        }));
    }
}

function tile(label, value, sub) {
    return `<div class="simple-kpi v3-kpi"><span class="v3-kpi-label">${label}</span><strong class="v3-kpi-value">${value}</strong><small class="v3-kpi-sub">${sub}</small></div>`;
}

function compareTable(R) {
    const rows = R.comparison.vsFixed.map((f, i) => {
        const r = R.comparison.vsReactive[i];
        const cell = x => x ? `${num(x.baseline, 2)} <small class="${x.difference < 0 ? 'v3-good' : x.difference > 0 ? 'v3-bad' : ''}">(${x.percent === null ? signed(x.difference, 2) : signed(x.percent, 1) + ' %'})</small>` : 'n/a';
        return `<tr><td>${esc(f.label)}${f.unit ? ` (${esc(f.unit)})` : ''}</td><td><b>${num(f.project, 2)}</b></td><td>${cell(f)}</td><td>${cell(r)}</td></tr>`;
    }).join('');
    return `<div class="v3-table-wrap"><table class="v3-table"><thead><tr><th>Metric</th><th>This run</th><th>Fixed cooling (change)</th><th>Reactive cooling (change)</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}

function decisionHtml(d) {
    return `<details class="v3-decision"><summary><b>${esc(d.time)}</b> ${esc(d.headline)}: <span class="badge badge-cyan">${esc(d.candidates.find(c => c.actionId === d.chosen)?.title || 'none')}</span> by ${esc(d.chooser || 'n/a')}</summary>
        <p class="v3-muted v3-small">Probability ${num(d.probabilityPercent, 0)} %, racks at risk ${esc(d.atRisk.join(', '))}.</p>
        <div class="v3-table-wrap"><table class="v3-table"><thead><tr><th>Option</th><th>Safe</th><th>Peak C</th><th>Energy %</th><th>Disruption</th><th>Cost</th><th></th></tr></thead><tbody>
        ${d.candidates.map(c => { const r = c.result || {}; return `<tr${c.actionId === d.chosen ? ' class="v3-hl"' : ''}><td>${esc(c.title)}</td><td>${r.safe ? 'Yes' : 'No'}</td><td>${num(r.peakInlet, 2)}</td><td>${signed(r.energyChangePercent, 1)}</td><td>${num(c.disruption, 2)}</td><td>${num(r.costScore, 2)}</td><td>${c.actionId === d.recommended ? 'Recommended' : ''}${c.actionId === d.chosen ? ' Chosen' : ''}</td></tr>`; }).join('')}
        </tbody></table></div><p><b>Why:</b> ${esc(d.reason || '')}</p></details>`;
}

export function mlTable(offline) {
    const horizons = ['5', '10', '15', '30', '60'];
    const cell = r => `<b>${r.within1Pct === null || r.within1Pct === undefined ? 'n/a' : num(r.within1Pct, 1) + ' %'}</b><br><small>MAE ${num(r.mae, 2)} C, skill ${signed(r.skillRmse, 2)}, held-out MAE ${num(r.heldoutMae, 2)} C</small>`;
    return `<div class="v3-table-wrap"><table class="v3-table"><thead><tr><th>Model</th>${horizons.map(h => `<th>+${h} min<br><small>accuracy within 1 C</small></th>`).join('')}</tr></thead><tbody>
    ${offline.map(m => m.unavailable ? `<tr><td>${esc(m.name)}</td><td colspan="5">${esc(m.unavailable)}</td></tr>` :
        `<tr${m.active ? ' class="v3-hl"' : ''}><td>${esc(m.name)}${m.active ? ' (active)' : ''}</td>${horizons.map(h => `<td>${cell(m.byHorizon[h])}</td>`).join('')}</tr>`).join('')}
    </tbody></table></div>`;
}

// Collapsible list of definitions taken from the backend explanations.
function defs(title, group, keys = null, label = null) {
    if (!group) return '';
    const entries = (keys || Object.keys(group)).filter(k => group[k]).map(k => [label ? label(k) : prettify(k), group[k]]);
    if (!entries.length) return '';
    return `<details class="v3-details v3-defs"><summary>${esc(title)}</summary><dl class="v3-glossary">${entries.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('')}</dl></details>`;
}

function prettify(key) {
    const named = { totalKwh: 'Total energy', itKwh: 'IT energy', coolingKwh: 'Cooling energy', chillerKwh: 'Chiller energy', fansKwh: 'Fan energy',
        pumpsKwh: 'Pump energy', pue: 'PUE', waterL: 'Water', wueLPerKwh: 'WUE', carbonKg: 'Carbon', costInr: 'Cost', costEnergyInr: 'Electricity cost',
        costWaterInr: 'Water cost', minutesAboveLimit: 'Minutes above limit', hotspotEvents: 'Hotspot events', peakInlet: 'Peak inlet',
        heatRejectedKwh: 'Heat rejected', difference: 'Difference', percent: 'Percent', fixed: 'Fixed cooling', reactive: 'Reactive cooling',
        predictive: 'This project', safe: 'Safe', energyChangePercent: 'Energy change', disruption: 'Disruption', costScore: 'Cost score',
        recommended: 'Recommended', chooser: 'Chosen by', avgInlet: 'Average inlet', peakExhaust: 'Peak exhaust', avgUtil: 'Average utilization',
        energyKwh: 'Energy', mae: 'MAE', rmse: 'RMSE', r2: 'R2', skillRmse: 'Skill', within1Pct: 'Accuracy (within 1 C)',
        within05Pct: 'Within 0.5 C', heldoutMae: 'Held-out MAE', accuracyPct: 'Warning accuracy', precision: 'Precision', recall: 'Recall',
        f1: 'F1', leadTime: 'Lead time' };
    return named[key] || key;
}

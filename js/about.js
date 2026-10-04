// About the Project: every section is built from the backend's real parameters,
// dataset summary, model metrics and benchmark results.
import { api } from './api.js';
import { esc, num, signed, toast } from './util.js';
import { getCatalog, themeToggleHtml } from './shared.js';

const SECTIONS = [
    ['what', 'What it is and why it matters'],
    ['twin', 'How the digital twin works'],
    ['dataset', 'The dataset'],
    ['forecast', 'How forecasting works and how accurate it is'],
    ['solutions', 'How solutions are chosen'],
    ['scenarios', 'Climates and events'],
    ['benchmark', 'Why this approach is better: the benchmark'],
    ['limits', 'Limitations and assumptions'],
    ['glossary', 'Glossary'],
];

export class AboutScreen {
    constructor(root, open) {
        this.root = root;
        this.data = {};
        this.charts = [];
        this.benchTimer = null;
        root.innerHTML = `<main class="v3-screen"><div class="v3-wrap">
            <div class="v3-topline"><button class="simple-link" data-nav="#/menu">Back to Menu</button>${themeToggleHtml()}</div>
            <div class="flow-kicker">ABOUT THE PROJECT</div>
            <h1 class="v3-h1">How this digital twin works</h1>
            <p class="v3-lead">Tap a section to open it. Every number below is read from the code, the generated dataset, the trained models or the benchmark results.</p>
            <div class="v3-stack" id="aboutList">
                ${SECTIONS.map(([id, title]) => `<details class="panel-card v3-about" data-sec="${id}" ${open === id ? 'open' : ''}><summary><strong>${title}</strong></summary><div class="v3-about-body" id="sec-${id}"><p class="v3-muted">Loading...</p></div></details>`).join('')}
            </div>
        </div></main>`;
        this.load();
    }

    destroy() {
        clearTimeout(this.benchTimer);
        this.charts.forEach(c => c.destroy());
    }

    async load() {
        const settle = p => p.then(v => v, () => null);
        const [params, ml, dataset, bench, cat] = await Promise.all([settle(api.parameters()), settle(api.ml()), settle(api.dataset()), settle(api.benchmark()), settle(getCatalog())]);
        this.data = { params, ml, dataset, bench, cat };
        const set = (id, html) => { this.root.querySelector(`#sec-${id}`).innerHTML = html; };
        set('what', this.what());
        set('twin', params ? this.twin(params) : unavailable('model parameters'));
        set('dataset', dataset ? this.dataset(dataset) : unavailable('dataset summary (run scripts/train_models.py)'));
        set('forecast', ml ? this.forecast(ml) : unavailable('model metrics (run scripts/train_models.py)'));
        set('solutions', cat && params ? this.solutions(cat, params) : unavailable('catalog'));
        set('scenarios', params ? this.scenarios(params) : unavailable('catalog'));
        set('benchmark', this.benchmark(bench));
        set('limits', this.limits(params));
        set('glossary', this.glossary());
        this.bindBenchmark();
    }

    what() {
        return `<p>Data centers spend a large share of their electricity on cooling, and many keep the air colder than necessary because they cannot see trouble coming. When a rack's <b>inlet</b> air (the air its servers breathe) goes above the ASHRAE recommended 27 C, equipment is at risk.</p>
        <p>This project is a software <b>digital twin</b> of a small data hall: a physics model of racks, airflow and the cooling plant that runs in step with a simulated facility. On top of it, machine-learning models forecast every rack's inlet temperature 5 to 60 minutes ahead, and an optimizer tests possible responses in cloned copies of the twin before anything is changed.</p>
        <p>The goal is to warn early, act only when it is needed and choose the action that keeps racks safe with the least energy, water and disruption. The benchmark section measures whether that works compared with conventional fixed and reactive cooling.</p>`;
    }

    twin(p) {
        const v = p.parameters;
        return `<p>Each rack draws electrical power that becomes heat: power = maximum power x (idle share + (1 - idle share) x utilization). Server fans move enough air to warm it by about ${v.SERVER_TARGET_DELTA_T} C.</p>
        <h3 class="v3-h3">Rack inlet: supply air plus recirculation</h3>
        <p class="v3-formula">inlet = (1 - r) x supply air + r x hot-aisle air + disturbance</p>
        <p><b>r</b> is the share of hot exhaust that leaks back into the rack inlet: ${num(v.RECIRC_BASE_MIDDLE * 100, 0)} % mid-row and ${num(v.RECIRC_BASE_END * 100, 0)} % at row ends. When the cooling units (CRAH) supply less air than the servers pull, the missing air is drawn from the hot aisle, and r rises by ${v.RECIRC_STARVATION_GAIN} times the shortfall. Inlet air mixes with a ${v.COLD_AISLE_TAU_S} s time constant.</p>
        <h3 class="v3-h3">Rack exhaust: heat stored in the servers</h3>
        <p class="v3-formula">C x d(exhaust)/dt = rack power - rho cp x airflow x (exhaust - inlet)</p>
        <p>C = ${v.RACK_THERMAL_MASS_KJ_K} kJ/K per rack (servers and chassis), rho cp = ${num(v.RHO_CP_AIR, 3)} kJ per m3 per K. With typical airflow this gives a time constant of one to two minutes, so temperatures evolve over minutes, not seconds.</p>
        <h3 class="v3-h3">Cooling plant</h3>
        <p>A water-cooled chiller with a cooling tower. Capacity equals ${v.PLANT_CAPACITY_FACTOR} x the design IT power at ${v.CAPACITY_REF_WET_BULB_C} C wet-bulb and drops ${num(v.CAPACITY_DERATE_PER_K * 100, 0)} % per degree above it. If the heat load is larger than capacity, the stored heat warms the supply air: (${v.SUPPLY_THERMAL_MASS_KJ_K_PER_RACK} kJ/K per rack) x d(supply)/dt = load - capacity, which is about 1 C per minute after a full chiller trip.</p>
        <p>Chiller power = heat removed / COP, where COP = ${v.CHILLER_CARNOT_EFFICIENCY} x the Carnot COP between the chilled water (${v.CHW_APPROACH_K} K below the supply setpoint) and the condenser (${v.TOWER_APPROACH_K + v.CONDENSER_APPROACH_K} K above the outside wet-bulb). When the tower water is cold enough, a waterside economizer cools for free (ramping over ${v.FREE_COOLING_BAND_K} K). CRAH fan power follows the cube of airflow, pumps follow load squared.</p>
        <h3 class="v3-h3">Water, carbon and cost</h3>
        <p>Water = evaporation (heat rejected x evaporative share / ${v.LATENT_HEAT_KJ_KG} kJ/kg) plus blowdown at ${v.CYCLES_OF_CONCENTRATION} cycles of concentration. Carbon uses ${v.DEFAULT_GRID_FACTOR_KG_PER_KWH} kg CO2 per kWh by default (India grid weighted average, CEA CO2 Baseline Database). Cost uses INR ${v.DEFAULT_ELECTRICITY_INR_PER_KWH} per kWh and INR ${v.DEFAULT_WATER_INR_PER_KL} per 1000 L by default. All three are configurable at setup.</p>
        <p class="v3-hint">Full parameter list: docs/MODEL_PARAMETERS.md.</p>`;
    }

    dataset(d) {
        const s = d.split;
        return `<p>The models are trained on data generated by this same physics twin. Real facility telemetry with labelled hotspots, failures and control actions is rarely public, so a synthetic dataset lets us cover rare events (chiller trips, floods, power loss) many times and know the exact ground truth. The limit: the models learn the twin's physics, not a real building's, so they must be re-trained on measured data before real use.</p>
        <div class="v3-facts">
            <div><span>Rows</span><b>${d.rows.toLocaleString()}</b></div>
            <div><span>Simulation runs</span><b>${d.runCount} runs of ${num(d.runDurationS / 3600, 0)} h (${d.simulatedHours} simulated hours)</b></div>
            <div><span>Sampling interval</span><b>${d.samplingIntervalS} s per rack</b></div>
            <div><span>Rows above the ${'27'} C limit</span><b>${d.rowsAboveLimit.toLocaleString()}</b></div>
            <div><span>Chronological split</span><b>first ${num(s.chronoFraction * 100, 0)} % of each run trains (${s.train.toLocaleString()} rows), the rest tests (${s.testChronological.toLocaleString()} rows)</b></div>
            <div><span>Held-out scenarios</span><b>runs with ${esc(d.heldOutEvents.join(' and '))} events, never seen in training (${s.heldoutScenario.toLocaleString()} rows)</b></div>
        </div>
        <p><a class="btn btn-cyan btn-lg" href="/api/about/dataset.csv" download>Download dataset (CSV)</a> <span class="v3-muted v3-small">${num(d.fileBytes / 1e6, 1)} MB</span></p>
        <details class="v3-details"><summary>Scenarios (${d.runs.length} runs)</summary><div class="v3-table-wrap"><table class="v3-table"><thead><tr><th>Run</th><th>Split</th><th>Climate</th><th>Policy</th><th>Racks</th><th>Scale</th><th>Events</th><th>Disturbances</th></tr></thead><tbody>
        ${d.runs.map(r => `<tr><td>${r.runId}</td><td>${esc(r.split)}</td><td>${esc(r.climate)}</td><td>${esc(r.policy)}</td><td>${r.racks}</td><td>${esc(r.scale)}</td><td>${esc(r.events.join(', '))}</td><td>${r.operatorDisturbances}</td></tr>`).join('')}</tbody></table></div></details>
        <details class="v3-details"><summary>Columns (${d.columns.length})</summary><div class="v3-table-wrap"><table class="v3-table"><thead><tr><th>Column</th><th>Description</th></tr></thead><tbody>
        ${d.columns.map(c => `<tr><td><code>${esc(c.name)}</code></td><td>${esc(c.description)}</td></tr>`).join('')}</tbody></table></div></details>
        <details class="v3-details"><summary>Summary statistics</summary><div class="v3-table-wrap"><table class="v3-table"><thead><tr><th>Feature</th><th>Mean</th><th>Std</th><th>Min</th><th>Max</th></tr></thead><tbody>
        ${d.stats.map(c => `<tr><td><code>${esc(c.column)}</code></td><td>${c.mean}</td><td>${c.std}</td><td>${c.min}</td><td>${c.max}</td></tr>`).join('')}</tbody></table></div></details>
        <details class="v3-details"><summary>Preview (${d.preview.length} rows)</summary><div class="v3-table-wrap"><table class="v3-table"><thead><tr>${Object.keys(d.preview[0] || {}).map(k => `<th>${esc(k)}</th>`).join('')}</tr></thead><tbody>
        ${d.preview.map(r => `<tr>${Object.values(r).map(v => `<td>${esc(v ?? '')}</td>`).join('')}</tr>`).join('')}</tbody></table></div></details>
        <p class="v3-hint">Workload comes from a seeded mean-reverting random process per rack, not from a real cluster trace. Driving workload from a sample of the public Google or Alibaba cluster traces is future work.</p>`;
    }

    forecast(m) {
        const models = Object.values(m.models);
        const hs = m.horizonsMin.map(String);
        const best = models.filter(x => x.chronological).map(x => ({ id: x.id, name: x.name, s: x.chronological['15'].skillRmse })).sort((a, b) => b.s - a.s)[0];
        const xgb = m.models.xgboost;
        return `<p>Every 30 simulated seconds the twin builds ${this.data.params?.features?.length || ''} features per rack (current inlet, its recent trend, exhaust, utilization, power, airflow ratio, supply air and its rate of change, spare cooling capacity, chiller and CRAH status, weather and position) and each model predicts the change in inlet temperature 5, 10, 15, 30 and 60 minutes ahead. Each model has its own trained model per horizon (the GRU predicts all horizons at once from the last 5 minutes).</p>
        <p>The <b>persistence baseline</b> simply assumes the temperature stays as it is. <b>Skill</b> = 1 - (model RMSE / persistence RMSE): above 0 means the model is genuinely better than doing nothing.</p>
        <p><b>Accuracy</b> below is the share of forecasts that landed within 1 C of the real inlet temperature. Under it: average error (MAE), large-miss error (RMSE), R2 and skill.</p>
        <div class="v3-table-wrap"><table class="v3-table"><thead><tr><th>Model</th>${hs.map(h => `<th>+${h} min</th>`).join('')}</tr></thead><tbody>
        ${models.map(x => x.chronological ? `<tr><td>${esc(x.name)}</td>${hs.map(h => { const r = x.chronological[h]; return `<td><b class="v3-acc">${r.within1Pct === undefined ? 'n/a' : num(r.within1Pct, 1) + ' %'}</b><br><small>MAE ${num(r.mae, 2)} / RMSE ${num(r.rmse, 2)} / R2 ${num(r.r2, 3)} / skill ${signed(r.skillRmse, 2)}</small></td>`; }).join('')}</tr>` : `<tr><td>${esc(x.name)}</td><td colspan="${hs.length}">${esc(x.unavailable)}</td></tr>`).join('')}
        </tbody></table></div>
        <p class="v3-hint">Why can a model have lower accuracy than persistence at some horizons but better skill? Accuracy counts small misses; skill (RMSE) punishes large misses. The models are better at the big swings during failures and spikes, while persistence is hard to beat when nothing changes.</p>
        <p class="v3-hint">Chronological test set: the last ${num((1 - m.rows.train / (m.rows.train + m.rows.testChronological)) * 100, 0)} % of each training run (${m.rows.testChronological.toLocaleString()} rows).</p>
        <div class="v3-table-wrap"><table class="v3-table"><thead><tr><th>Held-out scenarios</th>${hs.map(h => `<th>+${h} min<br><small>accuracy within 1 C</small></th>`).join('')}</tr></thead><tbody>
        ${models.filter(x => x.heldoutScenario).map(x => `<tr><td>${esc(x.name)}</td>${hs.map(h => { const r = x.heldoutScenario[h]; return `<td><b>${r.within1Pct === undefined ? 'n/a' : num(r.within1Pct, 1) + ' %'}</b><br><small>MAE ${num(r.mae, 2)} / skill ${signed(r.skillRmse, 2)}</small></td>`; }).join('')}</tr>`).join('')}
        </tbody></table></div>
        <p class="v3-hint">Held-out scenario test: ${m.rows.heldoutScenario.toLocaleString()} rows from runs containing ${esc(m.heldOutEvents.join(' and '))} events, which never appear in training.</p>
        <h3 class="v3-h3">Hotspot warnings</h3>
        <p>A warning is raised when any forecast up to 15 minutes ahead is above the limit. Only moments when the rack is not already above the limit are scored.</p>
        <div class="v3-table-wrap"><table class="v3-table"><thead><tr><th>Model</th><th>Accuracy</th><th>Precision</th><th>Recall</th><th>F1</th><th>False alarms</th><th>Missed</th><th>Episodes warned</th><th>Mean lead time</th></tr></thead><tbody>
        ${models.filter(x => x.hotspot).map(x => { const h = x.hotspot.chronological; return `<tr><td>${esc(x.name)}</td><td>${h.accuracyPct === undefined || h.accuracyPct === null ? 'n/a' : num(h.accuracyPct, 1) + ' %'}</td><td>${num(h.precision, 3)}</td><td>${num(h.recall, 3)}</td><td>${num(h.f1, 3)}</td><td>${h.falseAlarms ?? 'n/a'}</td><td>${h.missed ?? 'n/a'}</td><td>${h.episodesWarned} of ${h.episodes}</td><td>${h.meanLeadMin === null ? 'n/a' : num(h.meanLeadMin, 1) + ' min'}</td></tr>`; }).join('')}
        </tbody></table></div>
        <p class="v3-hint">Warning accuracy is high mainly because most moments are calm and correctly get no warning; precision (how many warnings were right) and recall (how many crossings were warned) are the stricter measures.</p>
        <p><b>Why R2 looks high:</b> rack temperatures change slowly, so even "no change" explains most of the variance and gets an R2 near 1. That is why skill versus persistence is the fairer measure${best ? `; on this test set the best +15 minute skill is ${signed(best.s, 2)} (${esc(best.name)})` : ''}.</p>
        ${xgb?.featureImportance ? `<h3 class="v3-h3">What XGBoost relies on most</h3><div class="v3-bars">${xgb.featureImportance.slice(0, 8).map(f => `<div class="v3-bar-row"><span>${esc(f.label)}</span><div class="v3-bar"><i style="width:${(f.importance / xgb.featureImportance[0].importance * 100).toFixed(0)}%"></i></div><b>${num(f.importance * 100, 1)} %</b></div>`).join('')}</div><p class="v3-hint">Share of total split gain across all horizons.</p>` : ''}
        <p class="v3-hint">Trained ${esc(m.generatedAt)}.</p>`;
    }

    solutions(cat, p) {
        const v = p.parameters;
        return `<p>When a forecast says a rack inlet will cross the limit within ${v.ALERT_HORIZON_MIN} minutes (or a rack is already above it), the simulation pauses and the optimizer clones the twin once per option and simulates each clone ${num(v.BRANCH_HORIZON_S / 60, 0)} minutes ahead with today's conditions held constant (the twin does not know the future).</p>
        <div class="v3-table-wrap"><table class="v3-table"><thead><tr><th>Option</th><th>What it does</th></tr></thead><tbody>${cat.actions.map(a => `<tr><td>${esc(a.title)}</td><td>${esc(a.description)}</td></tr>`).join('')}</tbody></table></div>
        <p class="v3-formula">cost = w_energy x energy change vs no action (%) + w_temperature x 10 x max(0, peak - (limit - ${v.PREDICTIVE_SAFETY_MARGIN_K})) + w_disruption x disruption</p>
        <p>An option is <b>safe</b> if its forecast peak inlet stays at or below the limit. The recommended option is the safe option with the lowest cost; unsafe options cannot be applied. Disruption counts 0.05 per utilization point migrated and 2 per kW of power capped. The weights are set in Advanced settings.</p>
        <p>The operator has ${cat.decisionTimeoutS} s to choose; otherwise the recommended option is applied. During Skip to End the recommended option is applied automatically. Every alert, option and choice is logged.</p>
        <p>Between alerts, every ${num(v.TUNER_INTERVAL_S / 60, 0)} minutes a tuner tries nearby supply-air setpoints and CRAH airflows in cloned twins and keeps the one with the lowest energy whose forecast peak stays ${v.PREDICTIVE_SAFETY_MARGIN_K} C below the limit. That is where most energy savings come from.</p>`;
    }

    scenarios(p) {
        return `<h3 class="v3-h3">Climates</h3><div class="v3-table-wrap"><table class="v3-table"><thead><tr><th>Climate</th><th>Mean / daily swing</th><th>Humidity</th><th>Effect</th></tr></thead><tbody>
        ${p.climates.map(c => `<tr><td>${esc(c.name)}</td><td>${c.meanTemp} C / +-${c.dailySwing} C</td><td>${c.humidity} %</td><td>${esc(c.description)}</td></tr>`).join('')}</tbody></table></div>
        <h3 class="v3-h3">Events</h3><div class="v3-table-wrap"><table class="v3-table"><thead><tr><th>Event</th><th>Category</th><th>Duration</th><th>What happens in the twin</th></tr></thead><tbody>
        ${p.events.map(e => `<tr><td>${esc(e.name)}</td><td>${esc(e.category)}</td><td>${Math.round(e.durationS / 60)} min</td><td>${esc(e.description)}</td></tr>`).join('')}</tbody></table></div>
        <p class="v3-hint">Events change equipment availability, weather or workload while they are active; they never overwrite optimizer actions or operator changes.</p>`;
    }

    benchmark(b) {
        const head = `<p>The same scenarios are simulated for many seeds under three policies with identical weather, workload and events: <b>fixed cooling</b> (18 C supply, full airflow), <b>reactive threshold cooling</b> (boosts cooling once an inlet is within 1 C of the limit) and <b>this project</b> (forecasts, counterfactual decisions and the energy tuner). This is the only source of comparisons with conventional cooling in this application.</p>
        <div class="v3-row"><button class="btn btn-primary" id="benchRun">Run benchmark again (10 seeds)</button><span class="v3-muted" id="benchStatus"></span></div>
        <p class="v3-hint">Command line: venv\\Scripts\\python scripts\\run_benchmark.py --seeds 10</p>`;
        const r = b?.result;
        if (!r) return head + '<p>No benchmark results have been generated yet.</p>';
        const keys = ['totalKwh', 'waterL', 'carbonKg', 'costInr', 'minutesAboveLimit', 'hotspotEvents', 'leadTimeMin'];
        const metric = Object.fromEntries(r.metrics.map(m => [m.id, m]));
        const pol = { fixed: 'Fixed', reactive: 'Reactive', predictive: 'This project' };
        return head + `<p class="v3-hint">${esc(r.method)} ${r.seeds} seeds, ${num(r.durationS / 60, 0)} minutes each, model ${esc(r.model)}, generated ${esc(r.generatedAt)}.</p>
        ${r.scenarios.map(sc => `<h3 class="v3-h3">${esc(sc.name)}</h3><div class="v3-table-wrap"><table class="v3-table"><thead><tr><th>Metric (mean +- std)</th>${r.policies.map(p => `<th>${pol[p]}</th>`).join('')}<th>vs fixed</th><th>vs reactive</th></tr></thead><tbody>
            ${keys.map(k => { const m = metric[k]; const sv = x => sc.savings[x][k]?.percent?.mean; return `<tr><td>${esc(m.label)}${m.unit ? ` (${esc(m.unit)})` : ''}</td>${r.policies.map(p => { const s = sc.policies[p][k]; return `<td>${s.mean === null ? 'n/a' : `${num(s.mean, 2)} +- ${num(s.std, 2)}`}</td>`; }).join('')}<td>${k === 'leadTimeMin' || sv('fixed') === null || sv('fixed') === undefined ? '' : signed(sv('fixed'), 1) + ' %'}</td><td>${k === 'leadTimeMin' || sv('reactive') === null || sv('reactive') === undefined ? '' : signed(sv('reactive'), 1) + ' %'}</td></tr>`; }).join('')}
            </tbody></table></div>`).join('')}
        <div class="v3-chart"><canvas id="benchChart" role="img" aria-label="Energy by scenario and policy"></canvas></div>
        <p class="v3-hint">Lead time is the minutes between the first warning and the moment the hottest inlet crossed the limit (fixed cooling has no warning). It is n/a when the limit was never crossed. Percent columns are paired differences of this project against each baseline, same seed.</p>`;
    }

    bindBenchmark() {
        const btn = this.root.querySelector('#benchRun');
        btn?.addEventListener('click', async () => {
            try { await api.runBenchmark(10); toast('Benchmark started. It takes several minutes.', 'ok'); this.pollBench(); } catch (err) { toast(err.message, 'error'); }
        });
        const r = this.data.bench?.result;
        if (r && window.Chart) {
            const canvas = this.root.querySelector('#benchChart');
            const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
            const colors = { fixed: css('--text-3'), reactive: css('--ice'), predictive: css('--molten') };
            const text = css('--text-2');
            this.charts.push(new window.Chart(canvas, {
                type: 'bar',
                data: { labels: r.scenarios.map(s => s.name), datasets: r.policies.map(p => ({ label: { fixed: 'Fixed', reactive: 'Reactive', predictive: 'This project' }[p], backgroundColor: colors[p], data: r.scenarios.map(s => s.policies[p].totalKwh.mean) })) },
                options: { responsive: true, maintainAspectRatio: false, animation: false, plugins: { legend: { labels: { color: text } } },
                    scales: { x: { ticks: { color: text } }, y: { title: { display: true, text: 'Total energy per run (kWh)', color: text }, ticks: { color: text } } } },
            }));
        }
        if (this.data.bench?.status?.state === 'running') this.pollBench();
    }

    async pollBench() {
        clearTimeout(this.benchTimer);
        try {
            const b = await api.benchmark();
            const st = this.root.querySelector('#benchStatus');
            if (st) st.textContent = b.status.state === 'running' ? `Running: ${num(b.status.progress, 0)} %` : b.status.state === 'done' ? 'Finished.' : b.status.state === 'error' ? `Failed: ${b.status.error}` : '';
            if (b.status.state === 'running') this.benchTimer = setTimeout(() => this.pollBench(), 2000);
            else if (b.status.state === 'done') { this.data.bench = b; this.charts.forEach(c => c.destroy()); this.charts = []; this.root.querySelector('#sec-benchmark').innerHTML = this.benchmark(b); this.bindBenchmark(); }
        } catch (err) { /* keep the page usable */ }
    }

    limits(p) {
        return `<ul class="v3-list">
            <li>This is a reduced-order model (a few coupled temperatures per rack), not computational fluid dynamics. Air mixing is described by a recirculation share, not resolved in space.</li>
            <li>Parameters (thermal mass, recirculation, chiller efficiency, capacities) are typical engineering values, not measurements from a specific facility. They are listed in docs/MODEL_PARAMETERS.md and must be calibrated against real telemetry before use.</li>
            <li>The forecasting models are trained on twin-generated data. Their accuracy on a real building is unknown until they are re-trained on measured data.</li>
            <li>Counterfactual branches hold current conditions constant, so they cannot anticipate events that have not started yet.</li>
            <li>Water use assumes a cooling tower with ${p?.parameters?.CYCLES_OF_CONCENTRATION ?? 4} cycles of concentration; air-cooled or dry-cooled plants would use far less water and more energy.</li>
            <li>The carbon factor is a national grid average; actual emissions depend on the time of day and the local supply.</li>
            <li>Workload is a seeded synthetic process; real job schedules and service-level limits on migration are not modelled.</li>
            <li>The decision cost function and its weights are a design choice; different weights give different recommendations.</li>
        </ul>`;
    }

    glossary() {
        const g = [
            ['Inlet temperature', 'Temperature of the air entering a rack. ASHRAE limits apply to it.'],
            ['Exhaust temperature', 'Temperature of the hot air leaving the back of a rack.'],
            ['ASHRAE limits', 'Industry guidance for IT inlet air: 18 to 27 C recommended, up to 32 C allowable for class A1 equipment.'],
            ['CRAH', 'Computer room air handler: the fans and coils that supply cool air to the cold aisle.'],
            ['Recirculation', 'Hot exhaust air leaking back to rack inlets, usually because of missing panels or too little supply air.'],
            ['Chiller and COP', 'The chiller cools water; COP is heat removed per unit of electricity. Higher is better.'],
            ['Free cooling', 'Using cold cooling-tower water directly when outside conditions allow, so the chiller can rest.'],
            ['Wet-bulb temperature', 'The lowest temperature evaporation can reach; it limits how well a cooling tower works.'],
            ['PUE', 'Power usage effectiveness: total facility energy divided by IT energy.'],
            ['WUE', 'Water usage effectiveness: litres of water per kWh of IT energy.'],
            ['Digital twin', 'A simulation that mirrors a physical system closely enough to test decisions on it first.'],
            ['Counterfactual', 'A what-if branch: a cloned twin in which one option is tried to see what would happen.'],
            ['Persistence baseline', 'A forecast that assumes nothing changes; any useful model must beat it.'],
            ['MAE, RMSE, R2', 'Average error, error that punishes large misses, and share of variance explained.'],
            ['Skill', '1 - (model error / persistence error). Positive means better than assuming no change.'],
            ['Lead time', 'How many minutes before a limit crossing the warning was raised.'],
        ];
        return `<dl class="v3-glossary">${g.map(([t, d]) => `<dt>${t}</dt><dd>${d}</dd>`).join('')}</dl>`;
    }
}

function unavailable(what) {
    return `<p class="v3-muted">The ${esc(what)} could not be loaded.</p>`;
}

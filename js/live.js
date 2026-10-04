// Live screen: control bar, Overview, Racks, Charts and Events tabs, rack edit sheet,
// Environment sheet and the hotspot decision overlay. The DOM is built once and then
// updated in place from each server state message.
import { api, live } from './api.js';
import { esc, el, num, hms, setText, tempColor, tempTextColor, TEMP_SCALE, toast, confirmDialog } from './util.js';
import { getCatalog, navigate, themeToggleHtml } from './shared.js';
import { LiveCharts } from './charts.js';
import { DecisionOverlay } from './alert.js';
import { EventsPanel } from './events.js';

const SPEEDS = [1, 2, 5, 10, 25];
const TABS = [['overview', 'Overview'], ['racks', 'Racks'], ['charts', 'Charts'], ['events', 'Events']];

export class LiveScreen {
    constructor(root) {
        this.root = root;
        this.state = null;
        this.store = { points: [], forecasts: [], markers: [], racks: [], limit: 27 };
        this.tab = 'overview';
        this.sheet = null;
        this.seenToasts = new Set();
        this.charts = null;
        this.finishedHandled = false;
        this.renderShell();
        this.overlay = new DecisionOverlay(this);
        this.events = new EventsPanel(this.root.querySelector('#tab-events'));
        this.off = live.on(msg => this.onState(msg));
        this.init();
    }

    async init() {
        try {
            const [state, series] = await Promise.all([api.state(), api.series()]);
            if (!state.runId) { this.renderNoRun(); return; }
            this.store.points = series.points || [];
            this.store.forecasts = series.forecasts || [];
            this.store.markers = series.markers || [];
            this.store.racks = series.racks || [];
            this.store.limit = series.limit || 27;
            this.onState(state);
        } catch (err) {
            toast(`Could not load the run: ${err.message}`, 'error');
        }
    }

    destroy() {
        this.off?.();
        this.charts?.destroy();
        this.overlay.destroy();
        this.closeSheet();
        clearInterval(this.countdownTimer);
    }

    renderNoRun() {
        this.root.innerHTML = `<main class="v3-screen"><div class="v3-wrap"><h1 class="v3-h1">No simulation is running</h1>
            <p class="v3-lead">Start a Demonstration or a Simulation from the menu.</p>
            <button class="btn btn-primary btn-lg v3-big" data-nav="#/menu">Open menu</button></div></main>`;
    }

    renderShell() {
        this.root.innerHTML = `<main class="v3-live">
            <div class="v3-controlbar" id="controlBar">
                <div class="v3-controlbar-inner">
                    <div class="v3-ctrl-row">
                        <button class="btn btn-warning v3-ctrl" id="btnPause">Pause</button>
                        <button class="btn btn-danger v3-ctrl" id="btnEnd">End</button>
                        <div class="v3-speeds" role="group" aria-label="Simulation speed">
                            ${SPEEDS.map(s => `<button class="btn btn-outline v3-speed" data-speed="${s}" aria-pressed="false">${s}x</button>`).join('')}
                        </div>
                        <button class="btn btn-outline v3-ctrl" id="btnSkip">Skip to End</button>
                    </div>
                    <div class="v3-ctrl-row v3-ctrl-meta">
                        <span class="v3-clock" id="clock">00:00:00 / 00:00:00</span>
                        <span class="v3-muted" id="speedLabel">Connecting...</span>
                        <span class="v3-row v3-meta-right"><span class="badge badge-cyan" id="modeBadge"></span>${themeToggleHtml()}</span>
                    </div>
                    <div class="simple-progress v3-progress" aria-label="Run progress"><span id="progressBar"></span></div>
                </div>
                <div class="v3-ticker" aria-hidden="true"><div class="v3-ticker-track"><span data-tick></span><span data-tick></span></div></div>
            </div>
            <div class="v3-wrap v3-live-body">
                <div id="skipPanel" class="panel-card v3-skip" hidden><strong>Skipping to the end</strong><div class="simple-progress"><span id="skipBar"></span></div><span class="v3-muted" id="skipText"></span></div>
                <div id="snoozeBar" class="v3-snooze" hidden><span><b>Alerts snoozed</b> <span id="snoozeLeft"></span></span><button class="btn btn-outline btn-sm" id="btnUnsnooze">Turn alerts back on</button></div>
                <div id="activeEvents" class="v3-active-events"></div>
                <section id="tab-overview" class="v3-tab"></section>
                <section id="tab-racks" class="v3-tab" hidden></section>
                <section id="tab-charts" class="v3-tab" hidden></section>
                <section id="tab-events" class="v3-tab" hidden></section>
            </div>
            <button class="btn btn-cyan v3-fab" id="btnEnv" hidden>Environment</button>
            <nav class="v3-tabbar" aria-label="Live views">
                ${TABS.map(([id, label]) => `<button class="v3-tabbtn ${id === 'overview' ? 'active' : ''}" data-tab="${id}">${label}</button>`).join('')}
            </nav>
        </main>`;
        const r = this.root;
        r.querySelector('#tab-overview').innerHTML = `
            <div class="v3-kpis">
                ${kpi('kHottest', 'Hottest rack inlet', 'Warmest air entering any rack now. The limit is the ASHRAE value chosen at setup.')}
                ${kpi('kRisk', 'Hotspot risk', 'Chance that a rack inlet exceeds the limit within 15 minutes, from the forecast and its measured error.')}
                ${kpi('kCooling', 'Cooling power', 'Electricity used by chillers, fans and pumps right now.')}
                ${kpi('kPue', 'PUE', 'Total facility power divided by IT power. 1.0 would mean zero cooling overhead.')}
                ${kpi('kMae', 'Live forecast accuracy', 'Share of 5-minute forecasts made in this run that landed within 1 C of what actually happened, with their average error.')}
                ${kpi('kOutside', 'Outside air', 'Outside temperature and wet-bulb. Higher wet-bulb makes the cooling tower and chiller work harder.')}
            </div>
            <div class="panel-card v3-panel">
                <div class="v3-panel-head"><h2>Rack inlet heatmap</h2><span class="v3-muted" id="heatNote"></span></div>
                <div class="v3-heatmap" id="heatmap"></div>
                <div class="v3-legend" aria-label="Color legend">
                    <div class="v3-legend-bar" style="background:linear-gradient(90deg, ${TEMP_SCALE.map(([t, c]) => `rgb(${c.join(',')}) ${((t - 18) / 14 * 100).toFixed(0)}%`).join(', ')})"></div>
                    <div class="v3-legend-labels">${TEMP_SCALE.map(([t]) => `<span style="left:${((t - 18) / 14 * 100).toFixed(0)}%">${t} C</span>`).join('')}</div>
                </div>
                <p class="v3-hint">Each tile is one rack, colored by inlet air temperature (the air the servers breathe). Exhaust air is shown separately and is normally 10 to 13 C warmer.</p>
            </div>
            <div class="panel-card v3-panel"><h2>Cooling plant</h2><div class="v3-facts" id="plantFacts"></div>
            <p class="v3-hint">Supply air is what the cooling units blow into the cold aisle. If the plant cannot remove all the heat, the supply air warms up.</p></div>`;
        r.querySelector('#tab-racks').innerHTML = `<p class="v3-hint v3-top-hint" id="racksHint"></p><div class="v3-racklist" id="rackList"></div>`;
        r.querySelector('#tab-charts').innerHTML = `<div id="chartsHost"></div>`;

        r.querySelector('#btnPause').addEventListener('click', () => this.togglePause());
        r.querySelector('#btnEnd').addEventListener('click', async () => {
            if (await confirmDialog('End the simulation?', 'The run stops now and the results page opens with everything recorded so far.', 'End simulation')) {
                try { await api.end(); navigate('#/results'); } catch (err) { toast(err.message, 'error'); }
            }
        });
        r.querySelector('#btnSkip').addEventListener('click', async () => {
            try { await api.skip(); this.root.querySelector('#skipPanel').hidden = false; } catch (err) { toast(err.message, 'error'); }
        });
        r.querySelectorAll('[data-speed]').forEach(b => b.addEventListener('click', async () => {
            try { await api.speed(Number(b.dataset.speed)); } catch (err) { toast(err.message, 'error'); }
        }));
        r.querySelectorAll('[data-tab]').forEach(b => b.addEventListener('click', () => this.showTab(b.dataset.tab)));
        r.querySelector('#rackList').addEventListener('click', e => {
            const card = e.target.closest('[data-rack]');
            if (card) this.openRackSheet(Number(card.dataset.rack));
        });
        r.querySelector('#heatmap').addEventListener('click', e => {
            const tile = e.target.closest('[data-rack]');
            if (tile) { this.showTab('racks'); this.openRackSheet(Number(tile.dataset.rack)); }
        });
        r.querySelector('#btnEnv').addEventListener('click', () => this.openEnvSheet());
        r.querySelector('#btnUnsnooze').addEventListener('click', async () => {
            try { await api.unsnooze(); toast('Hotspot alerts are active again.', 'ok'); } catch (err) { toast(err.message, 'error'); }
        });
    }

    showTab(tab) {
        if (tab === this.tab) return;
        if (this.tab === 'charts') { this.charts?.destroy(); this.charts = null; }
        this.tab = tab;
        this.root.querySelectorAll('[data-tab]').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
        TABS.forEach(([id]) => { this.root.querySelector(`#tab-${id}`).hidden = id !== tab; });
        if (tab === 'charts') {
            this.charts = new LiveCharts(this.root.querySelector('#chartsHost'), this.store);
            this.charts.update();
        }
        if (tab === 'events' && this.state) this.events.update(this.state);
        window.scrollTo(0, 0);
    }

    async togglePause() {
        try {
            if (this.state?.status === 'PAUSED') await api.resume();
            else await api.pause();
        } catch (err) { toast(err.message, 'error'); }
    }

    onState(s) {
        if (!s || s.type !== 'state' || !s.runId) return;
        if (this.state && s.runId !== this.state.runId) {
            this.store.points = []; this.store.forecasts = [];
        }
        this.state = s;
        const last = this.store.points.length ? this.store.points[this.store.points.length - 1].t : -1;
        for (const p of s.newPoints || []) if (p.t > last) this.store.points.push(p);
        const lastF = this.store.forecasts.length ? this.store.forecasts[this.store.forecasts.length - 1].t : -1;
        for (const f of s.newForecasts || []) if (f.t > lastF) this.store.forecasts.push(f);
        this.store.racks = s.racks.map(r => r.code);
        this.store.limit = s.facility.inletLimit;
        this.store.model = s.kpis.model;
        this.store.markers = (s.events || []).filter(e => e.category !== 'System' && e.kind !== 'tuner').map(e => ({ t: e.t, severity: e.severity, title: e.title }));
        this.updateControls(s);
        this.updateOverview(s);
        this.updateRacks(s);
        if (this.tab === 'charts' && this.charts) this.charts.update();
        if (this.tab === 'events') this.events.update(s);
        this.overlay.update(s);
        this.updateSheet(s);
        for (const t of s.toasts || []) {
            const key = `${t.t}|${t.text}`;
            if (!this.seenToasts.has(key)) { this.seenToasts.add(key); toast(t.text, 'info'); }
        }
        if (s.status === 'FINISHED' && !this.finishedHandled) {
            this.finishedHandled = true;
            navigate('#/results');
        }
    }

    updateControls(s) {
        const r = this.root;
        const demo = s.mode === 'demo';
        setText(r, '#clock', `${hms(s.t)} / ${hms(s.durationS)}`);
        r.querySelector('#progressBar').style.width = `${s.progressPercent}%`;
        setText(r, '#modeBadge', demo ? 'DEMONSTRATION' : 'SIMULATION');
        r.querySelector('#btnEnv').hidden = demo || s.status === 'FINISHED';
        const pause = r.querySelector('#btnPause');
        pause.textContent = s.status === 'PAUSED' ? 'Resume' : 'Pause';
        pause.disabled = !['RUNNING', 'PAUSED'].includes(s.status);
        r.querySelector('#btnSkip').disabled = ['SKIPPING', 'FINISHED'].includes(s.status);
        r.querySelectorAll('[data-speed]').forEach(b => {
            const on = Number(b.dataset.speed) === s.speed;
            b.classList.toggle('btn-cyan', on); b.classList.toggle('btn-outline', !on);
            b.setAttribute('aria-pressed', on ? 'true' : 'false');
            b.disabled = ['SKIPPING', 'FINISHED'].includes(s.status);
        });
        let label;
        if (s.status === 'RUNNING') label = s.actualSpeed !== null && s.actualSpeed !== undefined ? `Running at ${num(s.actualSpeed, 1)}x real time (requested ${s.speed}x)` : `Running, requested ${s.speed}x`;
        else if (s.status === 'PAUSED') label = 'Paused';
        else if (s.status === 'DECISION') label = 'Paused for a hotspot decision';
        else if (s.status === 'SKIPPING') label = 'Skipping to the end';
        else if (s.status === 'FINISHED') label = 'Finished';
        else label = s.status;
        setText(r, '#speedLabel', label);
        const skip = r.querySelector('#skipPanel');
        skip.hidden = s.status !== 'SKIPPING';
        if (s.status === 'SKIPPING') {
            r.querySelector('#skipBar').style.width = `${s.progressPercent}%`;
            setText(r, '#skipText', `${num(s.progressPercent, 0)} % simulated (${hms(s.t)} of ${hms(s.durationS)}). Recommended solutions are applied automatically.`);
        }
        const f = s.facility, k = s.kpis, c = s.climate;
        const tick = [`HOTTEST INLET ${num(k.hottestInlet, 1)} C (${k.hottestRack})`, `RISK ${num(k.hotspotRiskPercent, 0)} %`,
            `IT LOAD ${num(f.itKw, 1)} kW`, `COOLING ${num(f.coolingKw, 1)} kW`, `PUE ${num(f.pue, 3)}`,
            `SUPPLY AIR ${num(f.supplyTemp, 1)} C`, `OUTSIDE ${num(c.outsideTemp, 1)} C / WET-BULB ${num(c.wetBulb, 1)} C`,
            `ENERGY ${num(s.resources.totalKwh, 2)} kWh`, `WATER ${num(s.resources.waterL, 1)} L`, `EVENTS ${s.eventCounts.total}`].join('   //   ') + '   //   ';
        r.querySelectorAll('[data-tick]').forEach(n => { if (n.textContent !== tick) n.textContent = tick; });
        const sz = s.snooze || {};
        r.querySelector('#snoozeBar').hidden = !sz.active;
        if (sz.active) {
            const left = Math.ceil(sz.secondsLeft || 0);
            setText(r, '#snoozeLeft', `for ${Math.floor(left / 60)}:${String(left % 60).padStart(2, '0')} more (real time). Forecast warnings are still logged.`);
        }
        const ae = r.querySelector('#activeEvents');
        const key = (s.activeEvents || []).map(e => e.eventId + e.start).join('|');
        if (ae.dataset.key !== key) {
            ae.dataset.key = key;
            ae.innerHTML = (s.activeEvents || []).map(e => `<div class="v3-event-chip sev-${e.severity.toLowerCase()}"><b>${esc(e.name)}</b> active until ${hms(e.end)}<small>${esc(e.description)}</small></div>`).join('');
        }
    }

    updateOverview(s) {
        const r = this.root.querySelector('#tab-overview');
        const k = s.kpis, f = s.facility, c = s.climate;
        const lim = f.inletLimit;
        setKpi(r, 'kHottest', `${num(k.hottestInlet, 1)} C`, `${k.hottestRack}, limit ${num(lim, 0)} C`, k.hottestInlet >= lim ? 'bad' : k.hottestInlet >= lim - 1 ? 'warn' : 'ok');
        setKpi(r, 'kRisk', `${num(k.hotspotRiskPercent, 0)} %`, k.model ? `model: ${k.model}` : 'no forecast yet', k.hotspotRiskPercent >= 50 ? 'bad' : k.hotspotRiskPercent >= 20 ? 'warn' : 'ok');
        setKpi(r, 'kCooling', `${num(k.coolingKw, 1)} kW`, `IT load ${num(f.itKw, 1)} kW`);
        setKpi(r, 'kPue', num(k.pue, 3), `COP ${num(f.cop, 1)}, free cooling ${num(f.freeCoolingPercent, 0)} %`);
        const noAcc = k.liveWithin1Pct === null || k.liveWithin1Pct === undefined;
        setKpi(r, 'kMae', noAcc ? 'waiting' : `${num(k.liveWithin1Pct, 0)} %`,
            noAcc ? 'first check after 5 simulated minutes' : `within 1 C; average error ${num(k.liveMae, 2)} C over ${k.liveMaeSamples} checks`,
            noAcc ? '' : k.liveWithin1Pct >= 80 ? 'ok' : k.liveWithin1Pct >= 60 ? 'warn' : 'bad');
        setKpi(r, 'kOutside', `${num(c.outsideTemp, 1)} C`, `${num(c.humidity, 0)} % RH, wet-bulb ${num(c.wetBulb, 1)} C, ${c.climateName}`);
        const hm = r.querySelector('#heatmap');
        if (hm.childElementCount !== s.racks.length) {
            hm.innerHTML = s.racks.map(rk => `<button class="v3-tile" data-rack="${rk.id}" aria-label="${rk.code}">
                <span class="v3-tile-code">${rk.code}</span><span class="v3-tile-temp" data-f="inlet"></span>
                <span class="v3-tile-sub">inlet</span><span class="v3-tile-ex"><i>exhaust</i> <b data-f="exh"></b></span></button>`).join('');
        }
        s.racks.forEach((rk, i) => {
            const tile = hm.children[i];
            tile.style.backgroundColor = tempColor(rk.inletTemp);
            tile.style.color = tempTextColor(rk.inletTemp);
            tile.dataset.color = tempColor(rk.inletTemp);
            tile.classList.toggle('over', rk.inletTemp >= lim);
            setText(tile, '[data-f=inlet]', `${num(rk.inletTemp, 1)} C`);
            setText(tile, '[data-f=exh]', `${num(rk.exhaustTemp, 1)} C`);
        });
        setText(r, '#heatNote', `${s.racks.filter(x => x.inletTemp >= lim).length} of ${s.racks.length} above limit`);
        const facts = r.querySelector('#plantFacts');
        const rows = [
            ['Supply air', `${num(f.supplyTemp, 1)} C (setpoint ${num(f.supplySetpoint, 1)} C)`],
            ['CRAH airflow', `${num(f.crahFraction * 100, 0)} % of design, ${num(f.airflowRatio, 2)} x server demand`],
            ['Cooling split', `chiller ${num(f.chillerKw, 1)}, fans ${num(f.fansKw, 1)}, pumps ${num(f.pumpsKw, 1)} kW`],
            ['Plant capacity', `${num(f.capacityKw, 0)} kW for ${num(f.loadKw, 0)} kW of heat${f.deficitKw > 0.05 ? `, short by ${num(f.deficitKw, 1)} kW` : ''}`],
            ['Energy so far', `${num(s.resources.totalKwh, 2)} kWh, water ${num(s.resources.waterL, 1)} L`],
        ];
        if (facts.childElementCount !== rows.length) facts.innerHTML = rows.map(() => '<div><span></span><b></b></div>').join('');
        rows.forEach(([a, b], i) => { facts.children[i].firstChild.textContent = a; facts.children[i].lastChild.textContent = b; });
    }

    updateRacks(s) {
        const list = this.root.querySelector('#rackList');
        setText(this.root, '#racksHint', s.mode === 'demo' ? 'Tap a rack to see its details. Demonstration settings are fixed.' : 'Tap a rack to change its workload, power cap, local airflow or apply a temperature disturbance.');
        if (list.childElementCount !== s.racks.length) {
            list.innerHTML = s.racks.map(rk => `<button class="v3-rackcard panel-card" data-rack="${rk.id}">
                <div class="v3-rackcard-head"><strong>${rk.name}</strong><span class="badge" data-f="status"></span></div>
                <div class="v3-muted v3-small">${esc(rk.typeLabel)}, zone ${rk.zone}</div>
                <dl class="v3-dl">
                    <div><dt>Inlet</dt><dd data-f="inlet"></dd></div>
                    <div><dt>Exhaust</dt><dd data-f="exhaust"></dd></div>
                    <div><dt>Workload</dt><dd data-f="util"></dd></div>
                    <div><dt>Power</dt><dd data-f="power"></dd></div>
                    <div><dt>Airflow</dt><dd data-f="air"></dd></div>
                    <div><dt>Risk (15 min)</dt><dd data-f="risk"></dd></div>
                </dl>
                <div class="v3-forecast"><span>Inlet forecast</span><b data-f="f5"></b><b data-f="f15"></b><b data-f="f30"></b></div>
            </button>`).join('');
        }
        s.racks.forEach((rk, i) => {
            const card = list.children[i];
            const st = card.querySelector('[data-f=status]');
            if (st.textContent !== rk.status) { st.textContent = rk.status; st.className = `badge ${rk.status === 'Safe' ? 'badge-emerald' : rk.status === 'Warning' ? 'badge-warning' : 'badge-plasma'}`; }
            setText(card, '[data-f=inlet]', `${num(rk.inletTemp, 1)} C`);
            setText(card, '[data-f=exhaust]', `${num(rk.exhaustTemp, 1)} C`);
            setText(card, '[data-f=util]', `${num(rk.util, 0)} %${rk.workloadOverride !== null && rk.workloadOverride !== undefined ? ' (set)' : ''}${rk.off ? ' (off)' : ''}`);
            setText(card, '[data-f=power]', `${num(rk.powerKw, 2)} kW${rk.powerCapKw ? ' (capped)' : ''}`);
            setText(card, '[data-f=air]', `${num(rk.airflowCfm, 0)} CFM`);
            setText(card, '[data-f=risk]', `${num(rk.riskPercent, 0)} %`);
            const f = rk.forecast;
            setText(card, '[data-f=f5]', f ? `+5 min ${num(f['5'], 1)} C` : '+5 min n/a');
            setText(card, '[data-f=f15]', f ? `+15 min ${num(f['15'], 1)} C` : '+15 min n/a');
            setText(card, '[data-f=f30]', f ? `+30 min ${num(f['30'], 1)} C` : '+30 min n/a');
        });
    }

    // ── rack edit sheet ──────────────────────────────────────────────
    openRackSheet(id) {
        const s = this.state;
        if (!s) return;
        const rk = s.racks.find(x => x.id === id);
        if (!rk) return;
        const demo = s.mode === 'demo';
        const util = rk.workloadOverride ?? Math.round(rk.util);
        this.closeSheet();
        const node = el(`<div class="v3-overlay v3-sheet-wrap" role="dialog" aria-modal="true" aria-label="${rk.name} settings">
            <div class="v3-sheet panel-card" data-sheet-rack="${id}">
                <div class="v3-panel-head"><h2>${rk.name}</h2><button class="btn btn-outline" data-close>Close</button></div>
                <p class="v3-muted v3-small">${esc(rk.typeLabel)}, zone ${rk.zone}, maximum ${num(rk.pmaxKw, 1)} kW</p>
                <div class="v3-facts" data-live></div>
                ${demo ? '<div class="v3-note">Demonstration settings are fixed. Rack changes are available in Simulation mode.</div>' : ''}
                <fieldset ${demo ? 'disabled' : ''} class="v3-sheet-controls">
                    <label class="v3-field"><span>Workload <b data-v="util">${util} %</b></span>
                        <input type="range" min="0" max="100" step="1" value="${util}" data-ctl="util" aria-label="Workload percent">
                        <small>Sets this rack's utilization. Power and heat follow immediately.</small></label>
                    <button class="btn btn-outline" data-act="autoUtil">Return workload to automatic</button>
                    <label class="v3-field"><span>Power cap (kW)</span>
                        <div class="v3-row"><input type="number" min="0.5" max="50" step="0.1" value="${rk.operatorCapKw ?? ''}" placeholder="no cap" data-ctl="cap">
                        <button class="btn btn-outline" data-act="cap">Apply cap</button><button class="btn btn-outline" data-act="clearCap">Remove</button></div>
                        <small>Limits the rack's electrical power, which limits its heat.</small></label>
                    <label class="v3-field"><span>Local airflow <b data-v="air">${Math.round(rk.airflowFactor * 100)} %</b></span>
                        <input type="range" min="50" max="150" step="5" value="${Math.round(rk.airflowFactor * 100)}" data-ctl="air" aria-label="Local airflow percent">
                        <small>Server fan airflow relative to normal. More airflow cools the exhaust but pulls more air from the aisle.</small></label>
                    <div class="v3-field"><span>Temperature disturbance</span>
                        <div class="v3-grid3">
                            <select data-ctl="dkind" aria-label="Disturbance type"><option value="heat_pulse">Heat pulse (kW)</option><option value="inlet_offset">Inlet offset (K)</option></select>
                            <input type="number" step="0.5" min="-5" max="10" value="3" data-ctl="dmag" aria-label="Disturbance size">
                            <input type="number" step="1" min="1" max="60" value="5" data-ctl="ddur" aria-label="Duration in minutes">
                        </div>
                        <small>A heat pulse adds extra heat inside the rack; an inlet offset warms (or cools) the air at its inlet, for example a blocked tile. The physics evolves from there. Size, then duration in minutes.</small>
                        <button class="btn btn-warning" data-act="dist">Apply disturbance</button></div>
                </fieldset>
            </div></div>`);
        document.body.appendChild(node);
        this.sheet = { node, id };
        this.updateSheet(s);
        const ctl = n => node.querySelector(`[data-ctl=${n}]`);
        ctl('util').addEventListener('input', e => { node.querySelector('[data-v=util]').textContent = `${e.target.value} %`; });
        ctl('util').addEventListener('change', e => this.sendRack(id, { util: Number(e.target.value) }, `workload set to ${e.target.value} %`));
        ctl('air').addEventListener('input', e => { node.querySelector('[data-v=air]').textContent = `${e.target.value} %`; });
        ctl('air').addEventListener('change', e => this.sendRack(id, { airflowPct: Number(e.target.value) }, `local airflow set to ${e.target.value} %`));
        node.addEventListener('click', e => {
            if (e.target === node || e.target.closest('[data-close]')) { this.closeSheet(); return; }
            const act = e.target.closest('[data-act]')?.dataset.act;
            if (act === 'autoUtil') this.sendRack(id, { clearUtil: true }, 'workload returned to automatic');
            if (act === 'cap') {
                const v = Number(ctl('cap').value);
                if (!(v >= 0.5)) { toast('Enter a power cap of at least 0.5 kW.', 'error'); return; }
                this.sendRack(id, { powerCapKw: v }, `power cap ${v} kW`);
            }
            if (act === 'clearCap') this.sendRack(id, { clearCap: true }, 'power cap removed');
            if (act === 'dist') this.sendRack(id, { disturbance: { kind: ctl('dkind').value, magnitude: Number(ctl('dmag').value), durationMin: Number(ctl('ddur').value) } }, 'temperature disturbance applied');
        });
    }

    async sendRack(id, body, text) {
        try {
            await api.rack(id, body);
            toast(`Rack ${String(id).padStart(2, '0')}: ${text}.`, 'ok');
        } catch (err) { toast(err.message, 'error'); }
    }

    updateSheet(s) {
        if (!this.sheet || !s) return;
        const node = this.sheet.node;
        if (!node.isConnected) { this.sheet = null; return; }
        const rk = s.racks.find(x => x.id === this.sheet.id);
        const box = node.querySelector('[data-live]');
        if (!rk || !box) return;
        const rows = [['Inlet', `${num(rk.inletTemp, 1)} C`], ['Exhaust', `${num(rk.exhaustTemp, 1)} C`],
            ['Workload now', `${num(rk.util, 0)} %`], ['Power now', `${num(rk.powerKw, 2)} kW${rk.powerCapKw ? ` (cap ${num(rk.powerCapKw, 1)} kW)` : ''}`],
            ['Airflow', `${num(rk.airflowCfm, 0)} CFM`], ['Recirculation', `${num(rk.recircPercent, 1)} % of inlet air`]];
        if (box.childElementCount !== rows.length) box.innerHTML = rows.map(() => '<div><span></span><b></b></div>').join('');
        rows.forEach(([a, b], i) => { box.children[i].firstChild.textContent = a; box.children[i].lastChild.textContent = b; });
    }

    closeSheet() {
        if (this.sheet?.node) this.sheet.node.remove();
        this.sheet = null;
        document.querySelector('.v3-env-wrap')?.remove();
    }

    // ── environment sheet ────────────────────────────────────────────
    async openEnvSheet() {
        const cat = await getCatalog();
        const s = this.state;
        this.closeSheet();
        const c = s.climate;
        const node = el(`<div class="v3-overlay v3-sheet-wrap v3-env-wrap" role="dialog" aria-modal="true" aria-label="Environment">
            <div class="v3-sheet panel-card">
                <div class="v3-panel-head"><h2>Environment</h2><button class="btn btn-outline" data-close>Close</button></div>
                <p class="v3-hint">Changes apply immediately and are logged as user actions.</p>
                <label class="v3-field"><span>Climate profile</span><select data-ctl="climate">${cat.climates.map(x => `<option value="${x.id}" ${x.id === c.climateId ? 'selected' : ''}>${esc(x.name)}</option>`).join('')}</select></label>
                <label class="v3-field"><span>Outside temperature <b data-v="temp">${num(c.outsideTemp, 1)} C</b></span><input type="range" min="-10" max="50" step="0.5" value="${num(c.outsideTemp, 1)}" data-ctl="temp"></label>
                <label class="v3-field"><span>Humidity <b data-v="hum">${num(c.humidity, 0)} %</b></span><input type="range" min="5" max="100" step="1" value="${Math.round(c.humidity)}" data-ctl="hum"></label>
                <div class="v3-row"><button class="btn btn-primary" data-act="apply">Apply climate and conditions</button><button class="btn btn-outline" data-act="auto">Follow climate profile</button></div>
                <h3 class="v3-h3">Trigger an event now</h3>
                <div class="v3-event-grid">${cat.events.map(e => `<button class="btn btn-outline v3-event-btn" data-event="${e.id}" title="${esc(e.description)}"><b>${esc(e.name)}</b><small>${esc(e.category)}, ${Math.round(e.durationS / 60)} min</small></button>`).join('')}</div>
            </div></div>`);
        document.body.appendChild(node);
        const ctl = n => node.querySelector(`[data-ctl=${n}]`);
        ctl('temp').addEventListener('input', e => { node.querySelector('[data-v=temp]').textContent = `${e.target.value} C`; });
        ctl('hum').addEventListener('input', e => { node.querySelector('[data-v=hum]').textContent = `${e.target.value} %`; });
        node.addEventListener('click', async e => {
            if (e.target === node || e.target.closest('[data-close]')) { node.remove(); return; }
            const act = e.target.closest('[data-act]')?.dataset.act;
            const ev = e.target.closest('[data-event]')?.dataset.event;
            try {
                if (act === 'apply') { await api.environment({ climate: ctl('climate').value, outsideTemp: Number(ctl('temp').value), humidity: Number(ctl('hum').value) }); toast('Environment updated.', 'ok'); }
                if (act === 'auto') { await api.environment({ climate: ctl('climate').value, autoTemp: true, autoHumidity: true }); toast('Conditions now follow the climate profile.', 'ok'); }
                if (ev) { await api.environment({ event: ev }); toast(`${cat.events.find(x => x.id === ev).name} started.`, 'ok'); node.remove(); }
            } catch (err) { toast(err.message, 'error'); }
        });
    }
}

function kpi(id, label, hint) {
    return `<div class="simple-kpi v3-kpi" id="${id}"><span class="v3-kpi-label">${label}</span><strong class="v3-kpi-value">...</strong><small class="v3-kpi-sub"></small><small class="v3-kpi-hint">${hint}</small></div>`;
}

function setKpi(root, id, value, sub, level) {
    const node = root.querySelector(`#${id}`);
    if (!node) return;
    const v = node.querySelector('.v3-kpi-value');
    if (v && v.textContent !== value && v.textContent !== '...') {
        v.classList.remove('flash');
        void v.offsetWidth;          // restart the flash animation
        v.classList.add('flash');
    }
    setText(node, '.v3-kpi-value', value);
    setText(node, '.v3-kpi-sub', sub);
    node.dataset.level = level || '';
}

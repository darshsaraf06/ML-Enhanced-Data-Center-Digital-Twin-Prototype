// View Past Logs: every finished run is saved on the server and can be reopened read-only.
import { api } from './api.js';
import { esc, num, signed, hms, toast } from './util.js';
import { themeToggleHtml } from './shared.js';

const PAGE = 20;

export class LogsScreen {
    constructor(root) {
        this.root = root;
        this.offset = 0;
        this.total = 0;
        root.innerHTML = `<main class="v3-screen"><div class="v3-wrap">
            <div class="v3-topline"><button class="simple-link" data-nav="#/menu">Back to Menu</button>${themeToggleHtml()}</div>
            <div class="flow-kicker">PAST LOGS</div>
            <h1 class="v3-h1">Previous runs</h1>
            <p class="v3-lead">Every finished run is saved with its complete results. Open one to see the full results page, or download its report again. Saved runs are read-only.</p>
            <div id="logList" class="v3-stack"><p class="v3-muted">Loading saved runs...</p></div>
            <div class="v3-row v3-bottom-actions"><button class="btn btn-outline btn-lg" id="logMore" hidden>Show older runs</button></div>
        </div></main>`;
        root.querySelector('#logMore').addEventListener('click', () => this.load(true));
        this.load(false);
    }

    destroy() {}

    async load(more) {
        try {
            if (more) this.offset += PAGE;
            const data = await api.runs(PAGE, this.offset);
            this.total = data.total;
            const list = this.root.querySelector('#logList');
            if (!more) list.innerHTML = '';
            if (!data.total) {
                list.innerHTML = `<div class="panel-card v3-panel"><h2>No saved runs yet</h2><p class="v3-muted">Finish a Demonstration or Simulation (or use End or Skip to End) and it will appear here.</p>
                    <div class="v3-row"><button class="btn btn-primary btn-lg" data-nav="#/menu">Start a run</button></div></div>`;
            }
            list.insertAdjacentHTML('beforeend', data.runs.map(card).join(''));
            this.root.querySelector('#logMore').hidden = this.offset + PAGE >= this.total;
        } catch (err) {
            toast(`Could not load past runs: ${err.message}`, 'error');
        }
    }
}

function card(r) {
    const id = encodeURIComponent(r.runId);
    const over = r.minutesAboveLimit > 0;
    return `<article class="panel-card v3-log">
        <div class="v3-panel-head"><div><strong class="v3-log-title">${esc(r.savedAt || '')}</strong>
            <div class="v3-muted v3-small">${esc(r.runId)}</div></div>
            <span class="v3-row v3-log-badges"><span class="badge badge-cyan">${r.mode === 'demo' ? 'Demonstration' : 'Simulation'}</span>
            <span class="badge ${over ? 'badge-plasma' : 'badge-emerald'}">${over ? 'Went over limit' : 'Stayed within limit'}</span></span></div>
        <p class="v3-small v3-muted">${r.numRacks} racks, ${esc(r.scale)} scale, ${esc((r.climate || '').replace(/_/g, ' '))} climate, events: ${esc(r.events)}, seed ${r.seed}, model ${esc(r.mlModel)}. ${r.endReason === 'completed' ? 'Completed' : 'Ended early'} at ${hms(r.elapsedS)} of ${hms(r.durationS)}.</p>
        <dl class="v3-dl v3-log-dl">
            <div><dt>Peak inlet</dt><dd>${num(r.peakInlet, 1)} C</dd></div>
            <div><dt>Minutes above limit</dt><dd>${num(r.minutesAboveLimit, 1)}</dd></div>
            <div><dt>Total energy</dt><dd>${num(r.totalKwh, 1)} kWh</dd></div>
            <div><dt>PUE</dt><dd>${num(r.pue, 3)}</dd></div>
            <div><dt>Water</dt><dd>${num(r.waterL, 0)} L</dd></div>
            <div><dt>Cost</dt><dd>INR ${num(r.costInr, 0)}</dd></div>
            <div><dt>Hotspot alerts</dt><dd>${r.alerts}</dd></div>
            <div><dt>Energy vs fixed cooling</dt><dd>${r.energyVsFixedPercent === null || r.energyVsFixedPercent === undefined ? 'n/a' : signed(r.energyVsFixedPercent, 1) + ' %'}</dd></div>
        </dl>
        <div class="v3-row v3-log-actions">
            <button class="btn btn-primary" data-nav="#/results?run=${id}">Open results</button>
            <a class="btn btn-outline" href="/api/runs/${id}/export?format=pdf" download>PDF</a>
            <a class="btn btn-outline" href="/api/runs/${id}/export?format=csv" download>CSV</a>
            <a class="btn btn-outline" href="/api/runs/${id}/export?format=json" download>JSON</a>
        </div>
    </article>`;
}

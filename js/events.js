// Structured event feed with severity, category and rack filters.
import { esc } from './util.js';

const SEVERITIES = ['Info', 'Warning', 'Critical'];
const CATEGORIES = ['Thermal', 'Forecast', 'Cooling', 'Power', 'Workload', 'Environment', 'Decision', 'User action', 'System'];

export function severityClass(sev) {
    return sev === 'Critical' ? 'badge-plasma' : sev === 'Warning' ? 'badge-warning' : 'badge-cyan';
}

export function eventHtml(e, open = false) {
    const grouped = e.count > 1;
    const values = Object.entries(e.values || {}).filter(([, v]) => v !== null && typeof v !== 'object')
        .map(([k, v]) => `<span class="v3-kv"><i>${esc(k)}</i> ${esc(typeof v === 'number' ? Math.round(v * 100) / 100 : v)}</span>`).join('');
    return `<details class="v3-event sev-${e.severity.toLowerCase()}" data-eid="${e.id}" ${open ? 'open' : ''}>
        <summary>
            <span class="v3-event-time">${esc(e.time)}</span>
            <span class="badge ${severityClass(e.severity)}">${esc(e.severity)}</span>
            <span class="badge badge-purple">${esc(e.category)}</span>
            <span class="v3-event-title">${esc(e.title)}${grouped ? ` <small class="v3-muted">(${e.count} grouped)</small>` : ''}</span>
        </summary>
        <div class="v3-event-body">
            <p>${esc(e.detail)}</p>
            <p class="v3-muted v3-small">Source: ${esc(e.sourceKind)} ${esc(e.sourceId)}${e.racks?.length ? `, racks ${esc(e.racks.join(', '))}` : ''}</p>
            ${values ? `<div class="v3-kvs">${values}</div>` : ''}
            ${grouped ? `<ul class="v3-event-items">${e.items.map(it => `<li><span class="v3-event-time">${esc(it.time)}</span> ${esc(it.detail)}</li>`).join('')}</ul>` : ''}
        </div>
    </details>`;
}

export class EventsPanel {
    constructor(host) {
        this.host = host;
        this.sev = new Set();
        this.cat = new Set();
        this.rack = '';
        this.key = '';
        this.last = null;
        host.innerHTML = `<div class="panel-card v3-panel">
            <div class="v3-panel-head"><h2>Events</h2><span class="v3-muted" id="evTotal"></span></div>
            <p class="v3-hint">Newest first. Similar events within 30 seconds are grouped; tap an entry to expand it.</p>
            <div class="v3-chips" id="evSev" aria-label="Severity filter"></div>
            <div class="v3-chips" id="evCat" aria-label="Category filter"></div>
            <label class="v3-field v3-inline"><span>Rack</span><select id="evRack"><option value="">All racks</option></select></label>
            <div id="evList" class="v3-event-list"></div>
        </div>`;
        host.addEventListener('click', e => {
            const chip = e.target.closest('[data-filter]');
            if (!chip) return;
            const set = chip.dataset.filter === 'sev' ? this.sev : this.cat;
            const v = chip.dataset.value;
            if (set.has(v)) set.delete(v); else set.add(v);
            this.render(true);
        });
        host.querySelector('#evRack').addEventListener('change', e => { this.rack = e.target.value; this.render(true); });
    }

    update(state) {
        this.last = state;
        this.render(false);
    }

    render(force) {
        const s = this.last;
        if (!s) return;
        const events = s.events || [];
        const key = events.length + ':' + events.map(e => `${e.id}.${e.count}`).slice(0, 5).join(',') + ':' + s.eventCounts.total;
        if (!force && key === this.key) return;
        this.key = key;
        const counts = s.eventCounts;
        this.host.querySelector('#evTotal').textContent = `${counts.total} entries`;
        this.host.querySelector('#evSev').innerHTML = SEVERITIES.map(v => `<button class="v3-chip ${this.sev.has(v) ? 'on' : ''} chip-${v.toLowerCase()}" data-filter="sev" data-value="${v}" aria-pressed="${this.sev.has(v)}">${v} <b>${counts.bySeverity[v] || 0}</b></button>`).join('');
        this.host.querySelector('#evCat').innerHTML = CATEGORIES.map(v => `<button class="v3-chip ${this.cat.has(v) ? 'on' : ''}" data-filter="cat" data-value="${v}" aria-pressed="${this.cat.has(v)}">${v} <b>${counts.byCategory[v] || 0}</b></button>`).join('');
        const sel = this.host.querySelector('#evRack');
        const codes = (s.racks || []).map(r => r.code);
        if (sel.options.length !== codes.length + 1) {
            sel.innerHTML = '<option value="">All racks</option>' + codes.map(c => `<option value="${c}">${c}</option>`).join('');
            sel.value = this.rack;
        }
        const list = this.host.querySelector('#evList');
        const open = new Set([...list.querySelectorAll('details[open]')].map(d => d.dataset.eid));
        const shown = events.filter(e => (!this.sev.size || this.sev.has(e.severity)) && (!this.cat.size || this.cat.has(e.category))
            && (!this.rack || (e.racks || []).includes(this.rack)));
        list.innerHTML = shown.length ? shown.map(e => eventHtml(e, open.has(String(e.id)))).join('') : '<p class="v3-muted">No events match these filters.</p>';
    }
}

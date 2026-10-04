// Live charts. Each chart is created once in a fixed-height box, updated in place with
// chart.update('none') and destroyed when the Charts tab is left. Long runs are
// decimated to at most MAX_POINTS points per series.
import { api } from './api.js';
import { cssVar, esc, hm } from './util.js';

const MAX_POINTS = 600;
const HORIZONS = [5, 10, 15, 30, 60];
export const RACK_COLORS = ['#ff5f1f', '#c8f135', '#7fd6e8', '#ffb627', '#e8d5a3', '#4fd1a5', '#ff9e7a', '#5aa9ff',
    '#d6ff8f', '#c47a3d', '#a3b1c2', '#ffd84d'];

// Theme colors read from CSS so charts follow dark and light mode.
export function pal() {
    const v = n => cssVar(n);
    return { molten: v('--molten'), lime: v('--lime'), ice: v('--ice'), amber: v('--amber'), signal: v('--signal'),
        text: v('--text-2'), grid: v('--line'), muted: v('--text-3') };
}

export function alpha(color, a) {
    const c = (color || '').replace('#', '');
    if (c.length !== 6) return color;
    const n = parseInt(c, 16);
    return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}
let mlMetrics = null;

export function decimate(arr, max = MAX_POINTS) {
    if (arr.length <= max) return arr;
    const step = arr.length / max;
    const out = [];
    for (let i = 0; i < max; i++) out.push(arr[Math.floor(i * step)]);
    out.push(arr[arr.length - 1]);
    return out;
}

export const markerPlugin = {
    id: 'eventMarkers',
    afterDatasetsDraw(chart, args, opts) {
        const markers = opts?.markers?.() || [];
        const x = chart.scales.x;
        if (!x || !markers.length) return;
        const { top, bottom } = chart.chartArea;
        const ctx = chart.ctx;
        ctx.save();
        ctx.setLineDash([3, 3]);
        ctx.lineWidth = 1;
        for (const m of markers) {
            if (m.t < x.min || m.t > x.max) continue;
            const px = x.getPixelForValue(m.t);
            ctx.strokeStyle = m.severity === 'Critical' ? alpha(cssVar('--signal'), 0.75) : m.severity === 'Warning' ? alpha(cssVar('--amber'), 0.7) : alpha(cssVar('--text-3'), 0.5);
            ctx.beginPath(); ctx.moveTo(px, top); ctx.lineTo(px, bottom); ctx.stroke();
        }
        ctx.restore();
    },
};

export const bandPlugin = {
    id: 'shadeBands',
    beforeDatasetsDraw(chart, args, opts) {
        const bands = opts?.bands?.() || [];
        const x = chart.scales.x;
        if (!x || !bands.length) return;
        const { top, bottom } = chart.chartArea;
        const ctx = chart.ctx;
        ctx.save();
        for (const b of bands) {
            const x0 = x.getPixelForValue(Math.max(b.start, x.min)), x1 = x.getPixelForValue(Math.min(b.end, x.max));
            if (x1 <= x0) continue;
            ctx.fillStyle = b.color || alpha(cssVar('--signal'), 0.12);
            ctx.fillRect(x0, top, x1 - x0, bottom - top);
        }
        ctx.restore();
    },
};

export function baseOptions({ yTitle, y2Title = null, stacked = false, markers = null, bands = null, legend = true, yMin = undefined, yMax = undefined }) {
    const text = cssVar('--text-2') || '#b9ae98';
    const grid = cssVar('--line') || '#3b3427';
    const scales = {
        x: { type: 'linear', title: { display: true, text: 'Simulated time (hh:mm)', color: text }, ticks: { color: text, maxTicksLimit: 8, callback: v => hm(v) }, grid: { color: grid } },
        y: { title: { display: true, text: yTitle, color: text }, ticks: { color: text }, grid: { color: grid }, stacked, min: yMin, max: yMax },
    };
    if (y2Title) scales.y2 = { position: 'right', title: { display: true, text: y2Title, color: text }, ticks: { color: text }, grid: { drawOnChartArea: false } };
    return {
        animation: false, responsive: true, maintainAspectRatio: false, parsing: false, normalized: true,
        interaction: { mode: 'nearest', intersect: false, axis: 'x' },
        elements: { point: { radius: 0 }, line: { borderWidth: 1.6, tension: 0.2 } },
        scales,
        plugins: {
            legend: { display: legend, labels: { color: text, boxWidth: 12, usePointStyle: false } },
            tooltip: { callbacks: { title: items => items.length ? hm(items[0].parsed.x) : '' } },
            eventMarkers: { markers }, shadeBands: { bands },
        },
    };
}

export function line(label, color, data, extra = {}) {
    return { label, data, borderColor: color, backgroundColor: color, fill: false, ...extra };
}

const CHARTS = [
    ['inlet', 'Inlet temperature per rack', 'Air entering each rack. The red dashed line is the limit. Click a rack in the legend to hide or show it.'],
    ['forecast', 'Forecast vs actual', 'The line shows what actually happened; the dashed line shows what the model forecast earlier for that moment, with its typical error band.'],
    ['risk', 'Hotspot risk', 'Highest chance across racks of exceeding the limit within 15 minutes.'],
    ['workload', 'Workload per rack', 'Utilization of each rack in percent.'],
    ['cooling', 'Cooling power breakdown', 'Electricity used by the chiller, the fans (CRAH and cooling tower) and the pumps, stacked.'],
    ['pue', 'PUE', 'Total facility power divided by IT power. Lower is better.'],
    ['weather', 'Outside temperature and humidity', 'Outside dry-bulb and wet-bulb (left axis) and relative humidity (right axis).'],
    ['energy', 'Cumulative energy', 'Total facility energy used since the start of the run.'],
    ['water', 'Cumulative water', 'Cooling tower water use (evaporation and blowdown) since the start of the run.'],
];

export class LiveCharts {
    constructor(host, store) {
        this.host = host;
        this.store = store;
        this.charts = {};
        this.forecastRack = 0;
        this.forecastH = 15;
        this.lastUpdate = 0;
        host.innerHTML = CHARTS.map(([id, title, hint]) => `<div class="panel-card v3-panel v3-chart-card">
            <div class="v3-panel-head"><h2>${title}</h2>${id === 'forecast' ? `<div class="v3-row">
                <select data-fc-rack aria-label="Rack">${store.racks.map((c, i) => `<option value="${i}">${c}</option>`).join('')}</select>
                <select data-fc-h aria-label="Forecast horizon">${HORIZONS.map(h => `<option value="${h}" ${h === 15 ? 'selected' : ''}>+${h} min</option>`).join('')}</select></div>` : ''}</div>
            <div class="v3-chart"><canvas id="chart-${id}" aria-label="${esc(title)} chart" role="img"></canvas></div>
            <p class="v3-hint">${hint}</p></div>`).join('');
        host.querySelector('[data-fc-rack]').addEventListener('change', e => { this.forecastRack = Number(e.target.value); this.update(true); });
        host.querySelector('[data-fc-h]').addEventListener('change', e => { this.forecastH = Number(e.target.value); this.update(true); });
        this.onTheme = () => { this.destroyCharts(); this.build(); this.update(true); };
        window.addEventListener('themechange', this.onTheme);
        this.build();
        if (!mlMetrics) api.ml().then(m => { mlMetrics = m; this.update(true); }).catch(() => {});
    }

    destroyCharts() {
        Object.values(this.charts).forEach(c => c.destroy());
        this.charts = {};
    }

    destroy() {
        window.removeEventListener('themechange', this.onTheme);
        this.destroyCharts();
        this.host.innerHTML = '';
    }

    build() {
        if (!window.Chart) return;
        const Chart = window.Chart;
        const markers = () => this.store.markers;
        const mk = (id, type, datasets, opts) => {
            this.charts[id] = new Chart(this.host.querySelector(`#chart-${id}`), { type, data: { datasets }, options: opts, plugins: [markerPlugin] });
        };
        const racks = this.store.racks;
        const p = pal();
        mk('inlet', 'line', [...racks.map((c, i) => line(c, RACK_COLORS[i % 12], [])), line('Limit', p.signal, [], { borderDash: [6, 4], borderWidth: 1.5 })],
            baseOptions({ yTitle: 'Inlet temperature (C)', markers }));
        const fopts = baseOptions({ yTitle: 'Inlet temperature (C)', markers });
        fopts.plugins.legend.labels.filter = item => !item.text.startsWith('Error band');
        mk('forecast', 'line', [
            line('Error band upper', alpha(p.ice, 0.18), [], { borderWidth: 0, fill: false }),
            line('Error band lower', alpha(p.ice, 0.18), [], { borderWidth: 0, fill: '-1', backgroundColor: alpha(p.ice, 0.18) }),
            line('Actual inlet', p.ice, [], { borderWidth: 2 }),
            line('Forecast made earlier', p.molten, [], { borderDash: [5, 4], borderWidth: 2 }),
            line('Limit', p.signal, [], { borderDash: [6, 4], borderWidth: 1.5 }),
        ], fopts);
        mk('risk', 'line', [line('Hotspot risk', p.signal, [], { fill: 'origin', backgroundColor: alpha(p.signal, 0.14) })],
            baseOptions({ yTitle: 'Risk (%)', markers, legend: false, yMin: 0, yMax: 100 }));
        mk('workload', 'line', racks.map((c, i) => line(c, RACK_COLORS[i % 12], [])), baseOptions({ yTitle: 'Utilization (%)', markers, yMin: 0, yMax: 100 }));
        mk('cooling', 'line', [
            line('Chiller', p.molten, [], { fill: 'origin', backgroundColor: alpha(p.molten, 0.4) }),
            line('Fans', p.lime, [], { fill: '-1', backgroundColor: alpha(p.lime, 0.35) }),
            line('Pumps', p.ice, [], { fill: '-1', backgroundColor: alpha(p.ice, 0.35) }),
        ], baseOptions({ yTitle: 'Power (kW)', stacked: true, markers }));
        mk('pue', 'line', [line('PUE', p.lime, [], { borderWidth: 2 })], baseOptions({ yTitle: 'PUE', markers, legend: false }));
        mk('weather', 'line', [line('Outside dry-bulb (C)', p.molten, []), line('Wet-bulb (C)', p.amber, [], { borderDash: [4, 3] }),
            line('Humidity (%)', p.ice, [], { yAxisID: 'y2' })], baseOptions({ yTitle: 'Temperature (C)', y2Title: 'Relative humidity (%)', markers }));
        mk('energy', 'line', [line('Facility energy', p.amber, [], { fill: 'origin', backgroundColor: alpha(p.amber, 0.16), borderWidth: 2 })], baseOptions({ yTitle: 'Energy (kWh)', markers, legend: false }));
        mk('water', 'line', [line('Water used', p.ice, [], { fill: 'origin', backgroundColor: alpha(p.ice, 0.16), borderWidth: 2 })], baseOptions({ yTitle: 'Water (L)', markers, legend: false }));
    }

    rmse(h) {
        const model = this.store.model;
        const row = mlMetrics?.models?.[model]?.chronological?.[String(h)];
        return row ? row.rmse : null;
    }

    update(force = false) {
        const now = performance.now();
        if (!force && now - this.lastUpdate < 900) return;
        this.lastUpdate = now;
        if (!Object.keys(this.charts).length) return;
        const pts = decimate(this.store.points);
        if (!pts.length) return;
        const t0 = pts[0].t, t1 = pts[pts.length - 1].t;
        const limit = this.store.limit;
        const limitLine = [{ x: t0, y: limit }, { x: t1, y: limit }];
        const c = this.charts;
        const nr = this.store.racks.length;
        for (let i = 0; i < nr; i++) {
            c.inlet.data.datasets[i].data = pts.map(p => ({ x: p.t, y: p.inlet[i] }));
            c.workload.data.datasets[i].data = pts.map(p => ({ x: p.t, y: p.util[i] }));
        }
        c.inlet.data.datasets[nr].data = limitLine;
        // forecast vs actual for the selected rack and horizon
        const ri = Math.min(this.forecastRack, nr - 1);
        const hi = HORIZONS.indexOf(this.forecastH);
        const fc = decimate(this.store.forecasts).map(f => ({ x: f.t + this.forecastH * 60, y: f.values[ri][hi] })).filter(p => p.x <= t1 + this.forecastH * 60);
        const err = this.rmse(this.forecastH);
        const fd = c.forecast.data.datasets;
        fd[0].data = err ? fc.map(p => ({ x: p.x, y: p.y + err })) : [];
        fd[1].data = err ? fc.map(p => ({ x: p.x, y: p.y - err })) : [];
        fd[0].label = 'Error band upper'; fd[1].label = 'Error band lower';
        fd[2].data = pts.map(p => ({ x: p.t, y: p.inlet[ri] }));
        fd[3].data = fc;
        fd[3].label = `Forecast made ${this.forecastH} min earlier${err ? ` (band +/- ${err.toFixed(2)} C)` : ''}`;
        fd[4].data = [{ x: t0, y: limit }, { x: Math.max(t1, fc.length ? fc[fc.length - 1].x : t1), y: limit }];
        c.risk.data.datasets[0].data = pts.map(p => ({ x: p.t, y: p.risk }));
        c.cooling.data.datasets[0].data = pts.map(p => ({ x: p.t, y: p.chillerKw }));
        c.cooling.data.datasets[1].data = pts.map(p => ({ x: p.t, y: p.fansKw }));
        c.cooling.data.datasets[2].data = pts.map(p => ({ x: p.t, y: p.pumpsKw }));
        c.pue.data.datasets[0].data = pts.map(p => ({ x: p.t, y: p.pue }));
        c.weather.data.datasets[0].data = pts.map(p => ({ x: p.t, y: p.outside }));
        c.weather.data.datasets[1].data = pts.map(p => ({ x: p.t, y: p.wetBulb }));
        c.weather.data.datasets[2].data = pts.map(p => ({ x: p.t, y: p.humidity }));
        c.energy.data.datasets[0].data = pts.map(p => ({ x: p.t, y: p.energyKwh }));
        c.water.data.datasets[0].data = pts.map(p => ({ x: p.t, y: p.waterL }));
        Object.values(c).forEach(ch => ch.update('none'));
    }
}

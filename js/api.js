// REST and WebSocket client for the backend.

async function request(path, options = {}) {
    const resp = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...options });
    let data = null;
    try { data = await resp.json(); } catch (e) { data = null; }
    if (!resp.ok) {
        const err = new Error((data && data.detail) ? (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)) : `HTTP ${resp.status}`);
        err.status = resp.status;
        throw err;
    }
    return data;
}

const post = (path, body) => request(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) });

export const api = {
    health: () => request('/api/health'),
    catalog: () => request('/api/catalog'),
    start: cfg => post('/api/run/start', cfg),
    pause: () => post('/api/run/pause'),
    resume: () => post('/api/run/resume'),
    end: () => post('/api/run/end'),
    skip: () => post('/api/run/skip'),
    speed: speed => post('/api/run/speed', { speed }),
    rack: (id, body) => post(`/api/run/rack/${id}`, body),
    environment: body => post('/api/run/environment', body),
    decide: actionId => post('/api/run/decision', { actionId }),
    snooze: () => post('/api/run/snooze'),
    unsnooze: () => post('/api/run/unsnooze'),
    runs: (limit = 50, offset = 0) => request(`/api/runs?limit=${limit}&offset=${offset}`),
    savedRun: id => request(`/api/runs/${encodeURIComponent(id)}`),
    state: () => request('/api/run/state'),
    series: () => request('/api/run/series'),
    results: () => request('/api/run/results'),
    parameters: () => request('/api/about/parameters'),
    ml: () => request('/api/about/ml'),
    dataset: () => request('/api/about/dataset'),
    benchmark: () => request('/api/about/benchmark'),
    runBenchmark: seeds => post(`/api/about/benchmark/run?seeds=${seeds}`),
};

// One WebSocket for the whole app; listeners receive every server state message.
class Live {
    constructor() {
        this.listeners = new Set();
        this.ws = null;
        this.closedByApp = false;
        this.retry = null;
    }
    on(fn) { this.listeners.add(fn); return () => this.listeners.delete(fn); }
    connect() {
        if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) return;
        const proto = location.protocol === 'https:' ? 'wss' : 'ws';
        const ws = new WebSocket(`${proto}://${location.host}/ws`);
        this.ws = ws;
        ws.onmessage = evt => {
            let data;
            try { data = JSON.parse(evt.data); } catch (e) { return; }
            if (data.type === 'pong') return;
            this.listeners.forEach(fn => fn(data));
        };
        ws.onclose = () => {
            this.ws = null;
            clearInterval(this.ping);
            if (!this.closedByApp) this.retry = setTimeout(() => this.connect(), 2000);
        };
        ws.onopen = () => {
            this.ping = setInterval(() => { if (ws.readyState === WebSocket.OPEN) ws.send('ping'); }, 20000);
        };
    }
}

export const live = new Live();

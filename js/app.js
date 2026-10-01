/**
 * Main Application Orchestrator for Data Center Digital Twin
 * Connects to FastAPI backend at /ws for real-time state pushes and exposes REST client.
 */

import { ThermalPhysicsEngine } from './physics_engine.js';
import { MLPredictiveEngine } from './ml_engine.js';
import { CounterfactualOptimizerEngine } from './optimizer_engine.js';
import { ResearchBenchmarkEngine } from './benchmark_engine.js';
import { UIRenderer } from './ui.js';

// ── Backend API base URL (auto-detect) ────────────────────────────────────────
const API_BASE = (() => {
    if (window.location.port === '8000') return '';
    return 'http://localhost:8000';
})();

const WS_URL = API_BASE
    ? `ws://${new URL(API_BASE).host}/ws`
    : `ws://${window.location.host}/ws`;

/**
 * REST client connecting to all backend modular engines.
 */
export class DataCenterAPI {
    constructor() {
        this.base = API_BASE;
        this.available = false;
        this.ws = null;
        this.wsHandlers = new Set();
    }

    async _fetch(path, options = {}) {
        try {
            const resp = await fetch(`${this.base}${path}`, {
                headers: { 'Content-Type': 'application/json' },
                ...options,
            });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            return await resp.json();
        } catch (err) {
            console.warn(`[API] Error on ${path}:`, err);
            return null;
        }
    }

    // Health
    async ping() {
        const data = await this._fetch('/api/health');
        this.available = data !== null;
        return this.available;
    }

    // Simulation Controls
    configureSimulation(body) {
        return this._fetch('/api/simulation/configure', { method: 'POST', body: JSON.stringify(body) });
    }
    startSimulation() {
        return this._fetch('/api/simulation/start', { method: 'POST' });
    }
    pauseSimulation() {
        return this._fetch('/api/simulation/pause', { method: 'POST' });
    }
    resumeSimulation() {
        return this._fetch('/api/simulation/resume', { method: 'POST' });
    }
    stopSimulation() {
        return this._fetch('/api/simulation/stop', { method: 'POST' });
    }
    restartSimulation() {
        return this._fetch('/api/simulation/restart', { method: 'POST' });
    }
    setSpeed(multiplier) {
        return this._fetch('/api/simulation/speed', { method: 'POST', body: JSON.stringify({ multiplier }) });
    }
    getSimStatus() {
        return this._fetch('/api/simulation/status');
    }

    // Scenarios & Weather
    getScenarios() {
        return this._fetch('/api/scenario/list');
    }
    setWeather(presetId, ambientTemp = null, humidity = null) {
        return this._fetch('/api/scenario/weather', {
            method: 'POST',
            body: JSON.stringify({ presetId, ambientTemp, humidity }),
        });
    }
    setProblem(problemId) {
        return this._fetch('/api/scenario/problem', {
            method: 'POST',
            body: JSON.stringify({ problemId }),
        });
    }
    setWorkload(workloadId) {
        return this._fetch('/api/scenario/workload', {
            method: 'POST',
            body: JSON.stringify({ workloadId }),
        });
    }
    combineScenarios(weatherId, problemId, workloadId) {
        return this._fetch('/api/scenario/combine', {
            method: 'POST',
            body: JSON.stringify({ weatherId, problemId, workloadId }),
        });
    }

    // Optimization & Counterfactual
    evaluateOptimization() {
        return this._fetch('/api/counterfactual/evaluate', { method: 'POST' });
    }
    applyIntervention(actionId) {
        return this._fetch('/api/counterfactual/apply', {
            method: 'POST',
            body: JSON.stringify({ actionId }),
        });
    }
    runWhatIf(body) {
        return this._fetch('/api/counterfactual/what-if', {
            method: 'POST',
            body: JSON.stringify(body),
        });
    }

    // Telemetry & Rack Actuators
    getState() {
        return this._fetch('/api/state');
    }
    step(ticks = 1) {
        return this._fetch('/api/step', { method: 'POST', body: JSON.stringify({ ticks }) });
    }
    updateRack(rackId, body) {
        return this._fetch(`/api/rack/${rackId}/update`, { method: 'POST', body: JSON.stringify(body) });
    }

    // Experiments & Reports
    getExperiments() {
        return this._fetch('/api/experiments/comparison');
    }
    getReportData() {
        return this._fetch('/api/report/data');
    }
    getSimulationHistory() {
        return this._fetch('/api/simulation/history');
    }
    getSimulationRecord(simId, format = 'json') {
        return this._fetch(`/api/simulation/${simId}/export?format=${format}`);
    }
    clearSimulationHistory() {
        return this._fetch('/api/simulation/history/clear', { method: 'DELETE' });
    }

    // WebSocket connection
    connectWebSocket(onMessage, onStatusChange) {
        if (this.ws) return;

        const connect = () => {
            const ws = new WebSocket(WS_URL);
            this.ws = ws;

            ws.onopen = () => {
                this.available = true;
                onStatusChange?.('connected');
                this._pingInterval = setInterval(() => {
                    if (ws.readyState === WebSocket.OPEN) ws.send('ping');
                }, 25000);
            };

            ws.onmessage = (evt) => {
                try {
                    const data = JSON.parse(evt.data);
                    if (data.type === 'pong') return;
                    onMessage(data);
                } catch (_) {}
            };

            ws.onclose = () => {
                clearInterval(this._pingInterval);
                this.ws = null;
                onStatusChange?.('disconnected');
                setTimeout(connect, 3000);
            };

            ws.onerror = () => {
                this.available = false;
                onStatusChange?.('disconnected');
            };
        };

        connect();
    }
}

// ── Application Bootstrap ─────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
    console.log('Initialising ML-Enhanced Data Center Digital Twin Platform…');

    const physics = new ThermalPhysicsEngine();
    const ml = new MLPredictiveEngine();
    const optimizer = new CounterfactualOptimizerEngine();
    const benchmark = new ResearchBenchmarkEngine();
    const api = new DataCenterAPI();

    const ui = new UIRenderer(physics, ml, optimizer, benchmark, api);
    ui.init();

    const backendUp = await api.ping();
    if (backendUp) {
        console.log('[API] ✓ Backend connected - server-side digital twin simulation active');
        ui.setBackendMode(true);

        api.connectWebSocket(
            (state) => ui.applyServerState(state),
            (status) => ui.updateConnectionStatus(status)
        );
    } else {
        console.warn('[API] Backend offline - using local client-side physics loop');
        ui.setBackendMode(false);
        ui.startLoop();
    }

    window.DigitalTwinApp = { physics, ml, optimizer, benchmark, ui, api };
});

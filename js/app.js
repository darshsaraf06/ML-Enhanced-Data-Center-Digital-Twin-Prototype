// Application shell: hash router, theme toggle and the Home, Menu and Setup screens.
import { api, live } from './api.js';
import { esc, el, toast } from './util.js';
import { LiveScreen } from './live.js';
import { ResultsScreen } from './results.js';
import { AboutScreen } from './about.js';
import { LogsScreen } from './logs.js';
import { getCatalog, navigate, themeIcon, themeToggleHtml } from './shared.js';

const app = document.getElementById('app');
let current = null;     // active screen object with optional destroy()

function toggleTheme() {
    const light = document.documentElement.getAttribute('data-theme') === 'light';
    if (light) document.documentElement.removeAttribute('data-theme');
    else document.documentElement.setAttribute('data-theme', 'light');
    try { localStorage.setItem('dt_theme', light ? 'dark' : 'light'); } catch (e) { /* storage unavailable */ }
    document.querySelectorAll('[data-theme-toggle] .theme-icon').forEach(n => { n.innerHTML = themeIcon(); });
    window.dispatchEvent(new CustomEvent('themechange'));
}

document.addEventListener('click', e => {
    if (e.target.closest('[data-theme-toggle]')) toggleTheme();
    const nav = e.target.closest('[data-nav]');
    if (nav) { e.preventDefault(); location.hash = nav.dataset.nav; }
});

function parseHash() {
    const raw = location.hash.replace(/^#\/?/, '');
    const [path, query] = raw.split('?');
    return { path: path || 'home', params: new URLSearchParams(query || '') };
}

async function route() {
    const { path, params } = parseHash();
    if (current?.destroy) current.destroy();
    current = null;
    window.scrollTo(0, 0);
    document.body.dataset.screen = path;
    try {
        if (path === 'home') current = renderHome();
        else if (path === 'menu') current = renderMenu();
        else if (path === 'setup') current = await renderSetup(params.get('mode') === 'demo' ? 'demo' : 'sim');
        else if (path === 'live') current = new LiveScreen(app);
        else if (path === 'results') current = new ResultsScreen(app, params.get('run'));
        else if (path === 'logs') current = new LogsScreen(app);
        else if (path === 'about') current = new AboutScreen(app, params.get('section'));
        else { location.hash = '#/home'; return; }
    } catch (err) {
        app.innerHTML = `<main class="v3-screen"><div class="v3-wrap"><h1>Something went wrong</h1><p class="v3-muted">${esc(err.message)}</p><button class="btn btn-primary btn-lg" data-nav="#/home">Home</button></div></main>`;
    }
}

function renderHome() {
    app.innerHTML = `<main class="v3-screen v3-home">
        <div class="v3-topbar">${themeToggleHtml()}</div>
        <div class="v3-wrap v3-home-inner">
            <div class="flow-kicker">DATA CENTER DIGITAL TWIN</div>
            <h1 class="v3-title">Predict rack hotspots before they happen, and cool only as much as needed</h1>
            <p class="v3-lead">A physics-based twin of a small data hall with machine learning forecasts of rack inlet temperature and counterfactual tests of cooling decisions.</p>
            <div class="simple-rack-preview v3-rack-preview" aria-hidden="true">${Array.from({ length: 12 }, () => '<span class="simple-rack-cell"></span>').join('')}</div>
            <button class="btn btn-primary btn-lg v3-big" data-nav="#/menu">Get Started</button>
        </div>
        <div class="v3-ticker v3-home-ticker" aria-hidden="true"><div class="v3-ticker-track">${'<span>PHYSICS TWIN   //   INLET FORECASTS +5 TO +60 MIN   //   COUNTERFACTUAL DECISIONS   //   ENERGY, WATER, CARBON, COST   //   ASHRAE 27 C LIMIT   //   </span>'.repeat(2)}</div></div>
    </main>`;
    return {};
}

function renderMenu() {
    app.innerHTML = `<main class="v3-screen">
        <div class="v3-wrap">
            <div class="v3-topline"><button class="simple-link" data-nav="#/home">Back to Home</button>${themeToggleHtml()}</div>
            <div class="flow-kicker">CHOOSE A PATH</div>
            <h1 class="v3-h1">What would you like to do?</h1>
            <div class="v3-stack">
                <button class="simple-choice" data-nav="#/setup?mode=demo"><strong>Demonstration</strong><span>Watch a scripted one-hour run: a workload spike, a chiller trip and a heatwave. Settings are fixed.</span></button>
                <button class="simple-choice" data-nav="#/setup?mode=sim"><strong>Simulation</strong><span>Choose racks, climate and events, then change workloads and the environment while the twin runs.</span></button>
                <button class="simple-choice" data-nav="#/logs"><strong>View Past Logs</strong><span>Reopen the results and reports of every run you have finished, newest first.</span></button>
                <button class="simple-choice" data-nav="#/about"><strong>About the Project</strong><span>How the twin, the forecasts and the decisions work, the dataset, model accuracy and the benchmark.</span></button>
            </div>
        </div>
    </main>`;
    return {};
}

async function renderSetup(mode) {
    const cat = await getCatalog();
    const demo = mode === 'demo';
    const d = demo ? { ...cat.defaults, climate: cat.demo.climate, seed: cat.demo.seed, durationS: cat.demo.durationS } : cat.defaults;
    const events = cat.events;
    const models = cat.models;
    const demoNote = demo ? `<div class="v3-note"><strong>Demonstration settings are fixed.</strong> Scripted events: ${cat.demo.script.map(s => `${esc(s.name)} at ${Math.round(s.start / 60)} min`).join(', ')}.</div>` : '';
    app.innerHTML = `<main class="v3-screen">
        <div class="v3-wrap">
            <div class="v3-topline"><button class="simple-link" data-nav="#/menu">Back to Menu</button>${themeToggleHtml()}</div>
            <div class="flow-kicker">${demo ? 'DEMONSTRATION' : 'SIMULATION'} SETUP</div>
            <h1 class="v3-h1">${demo ? 'Demonstration run' : 'Set up your simulation'}</h1>
            ${demoNote}
            <form id="setupForm" class="v3-form" novalidate>
                <fieldset ${demo ? 'disabled' : ''}>
                <label class="v3-field"><span>Number of racks</span><input id="fRacks" type="number" min="4" max="12" value="${d.numRacks}"><small>Between 4 and 12 racks, split into two rows (zone A and zone B).</small></label>
                <label class="v3-field"><span>Data center scale</span><select id="fScale">
                    ${[['small', 'Small (low density racks)'], ['medium', 'Medium'], ['large', 'Large (high density racks)']].map(([v, l]) => `<option value="${v}" ${d.scale === v ? 'selected' : ''}>${l}</option>`).join('')}
                </select><small>Scale changes how much power each rack draws at full load.</small></label>
                <label class="v3-field"><span>Climate</span><select id="fClimate">
                    ${cat.climates.map(c => `<option value="${c.id}" ${d.climate === c.id ? 'selected' : ''}>${esc(c.name)}</option>`).join('')}
                </select><small id="climateHint">${esc(cat.climates.find(c => c.id === d.climate)?.description || '')}</small></label>
                <div class="v3-field"><span>Events</span>
                    <div class="v3-seg" role="radiogroup" aria-label="Events">
                        ${[['none', 'None'], ['random', 'Random'], ['chosen', 'Choose']].map(([v, l]) => `<label class="v3-seg-item"><input type="radio" name="fEvents" value="${v}" ${v === 'none' ? 'checked' : ''}><span>${l}</span></label>`).join('')}
                    </div>
                    <div id="eventChoices" class="v3-checks" hidden>
                        <div class="v3-row v3-check-tools"><button type="button" class="btn btn-outline btn-sm" id="evSelectAll">Select all</button><button type="button" class="btn btn-outline btn-sm" id="evClearAll">Clear all</button><span class="v3-muted v3-small" id="evCount">0 selected</span></div>
                        ${events.map(e => `<label class="v3-check"><input type="checkbox" value="${e.id}"><span><b>${esc(e.name)}</b><small>${esc(e.description)}</small></span></label>`).join('')}
                    </div>
                    <small>Random picks seeded events; chosen events start at 10 minutes and are spread across the run.</small>
                </div>
                <details class="v3-details"><summary>Advanced settings</summary>
                    <div class="v3-grid2">
                        <label class="v3-field"><span>Duration</span><select id="fDuration">
                            ${[[900, '15 minutes'], [1800, '30 minutes'], [3600, '1 hour'], [7200, '2 hours'], [14400, '4 hours']].map(([v, l]) => `<option value="${v}" ${d.durationS === v ? 'selected' : ''}>${l}</option>`).join('')}
                        </select></label>
                        <label class="v3-field"><span>Seed</span><input id="fSeed" type="number" value="${d.seed}"><small>Same seed, same weather, workload and random events.</small></label>
                        <label class="v3-field"><span>Forecast model</span><select id="fModel">
                            ${models.map(m => `<option value="${m.id}" ${m.available ? '' : 'disabled'} ${d.mlModel === m.id ? 'selected' : ''}>${esc(m.name)}${m.acc5 !== null && m.acc5 !== undefined ? ` (${m.acc5.toFixed(0)} % within 1 C at 5 min, ${m.acc15.toFixed(0)} % at 15 min)` : ''}${m.available ? '' : ' (unavailable)'}</option>`).join('')}
                        </select><small>Accuracy = share of test forecasts within 1 C of the real inlet temperature. Details on the About page.</small></label>
                        <label class="v3-field"><span>Inlet limit</span><select id="fLimit">
                            <option value="27" selected>27 C (ASHRAE recommended)</option><option value="32">32 C (ASHRAE allowable, class A1)</option>
                        </select></label>
                        <label class="v3-field"><span>Cost weight: energy</span><input id="fWE" type="number" step="0.1" min="0" max="10" value="${d.weights.energy}"></label>
                        <label class="v3-field"><span>Cost weight: temperature</span><input id="fWT" type="number" step="0.1" min="0" max="10" value="${d.weights.temperature}"></label>
                        <label class="v3-field"><span>Cost weight: workload disruption</span><input id="fWD" type="number" step="0.1" min="0" max="10" value="${d.weights.disruption}"></label>
                        <label class="v3-field"><span>Grid emission factor (kg CO2 per kWh)</span><input id="fGrid" type="number" step="0.001" min="0" value="${d.gridFactor}"></label>
                        <label class="v3-field"><span>Electricity price (INR per kWh)</span><input id="fPrice" type="number" step="0.1" min="0" value="${d.priceKwh}"></label>
                        <label class="v3-field"><span>Water price (INR per 1000 L)</span><input id="fWater" type="number" step="1" min="0" value="${d.priceWaterKl}"></label>
                    </div>
                </details>
                </fieldset>
                <p id="setupError" class="v3-error" hidden></p>
                <button type="submit" class="btn btn-primary btn-lg v3-big v3-start" id="startBtn">START</button>
            </form>
        </div>
    </main>`;
    const form = app.querySelector('#setupForm');
    const choices = app.querySelector('#eventChoices');
    const countChosen = () => { app.querySelector('#evCount').textContent = `${choices.querySelectorAll('input[type=checkbox]:checked').length} of ${events.length} selected`; };
    const setAll = on => { choices.querySelectorAll('input[type=checkbox]').forEach(i => { i.checked = on; }); countChosen(); };
    app.querySelector('#evSelectAll').addEventListener('click', () => setAll(true));
    app.querySelector('#evClearAll').addEventListener('click', () => setAll(false));
    countChosen();
    form.addEventListener('change', e => {
        if (e.target.type === 'checkbox') countChosen();
        if (e.target.name === 'fEvents') choices.hidden = e.target.value !== 'chosen';
        if (e.target.id === 'fClimate') app.querySelector('#climateHint').textContent = cat.climates.find(c => c.id === e.target.value)?.description || '';
    });
    form.addEventListener('submit', async e => {
        e.preventDefault();
        const btn = app.querySelector('#startBtn');
        const err = app.querySelector('#setupError');
        err.hidden = true;
        let cfg;
        if (demo) cfg = { mode: 'demo' };
        else {
            const evMode = form.querySelector('input[name=fEvents]:checked').value;
            const chosen = [...choices.querySelectorAll('input[type=checkbox]:checked')].map(i => i.value);
            if (evMode === 'chosen' && !chosen.length) { err.textContent = 'Choose at least one event, or pick None or Random.'; err.hidden = false; return; }
            const racks = Number(app.querySelector('#fRacks').value);
            if (!(racks >= 4 && racks <= 12)) { err.textContent = 'Number of racks must be between 4 and 12.'; err.hidden = false; return; }
            cfg = {
                mode: 'sim', numRacks: racks, scale: app.querySelector('#fScale').value,
                climate: app.querySelector('#fClimate').value,
                events: evMode === 'chosen' ? chosen : evMode,
                durationS: Number(app.querySelector('#fDuration').value), seed: Number(app.querySelector('#fSeed').value),
                mlModel: app.querySelector('#fModel').value, inletLimit: Number(app.querySelector('#fLimit').value),
                weights: { energy: Number(app.querySelector('#fWE').value), temperature: Number(app.querySelector('#fWT').value), disruption: Number(app.querySelector('#fWD').value) },
                gridFactor: Number(app.querySelector('#fGrid').value), priceKwh: Number(app.querySelector('#fPrice').value), priceWaterKl: Number(app.querySelector('#fWater').value),
            };
        }
        btn.disabled = true; btn.textContent = 'Starting...';
        try {
            await api.start(cfg);
            navigate('#/live');
        } catch (ex) {
            err.textContent = `Could not start: ${ex.message}`; err.hidden = false;
            btn.disabled = false; btn.textContent = 'START';
        }
    });
    return {};
}

window.addEventListener('hashchange', route);
live.connect();
if (!location.hash) history.replaceState(null, '', '#/home');
route();
window.DigitalTwin = { api, live, toast, navigate };

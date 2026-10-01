/**
 * UI Renderer, Navigation Coordinator, and Telemetry Visualization Engine
 * Manages all 10 dedicated sections, WebSockets, Chart.js graphs, and interactive actuators.
 */

export class UIRenderer {
    constructor(physicsEngine, mlEngine, optimizerEngine, benchmarkEngine, api = null) {
        this.physics = physicsEngine;
        this.ml = mlEngine;
        this.optimizer = optimizerEngine;
        this.benchmark = benchmarkEngine;
        this.api = api;

        this.selectedRackId = 1;
        this.charts = {};
        this.simSpeed = 1;
        this.isBackendMode = false;
        this.isConnected = false;
        this.activeSection = 'secOverview';
        this.alertFilter = 'ALL';
        this.lastServerState = null;
    }

    // ── Initialisation ───────────────────────────────────────────────────────
    init() {
        const safe = (name, fn) => {
            try { fn(); }
            catch (err) { console.error(`[UI] Failed to bind: ${name}`, err); }
        };

        safe('ThemeToggle',        () => this.bindThemeToggle());
        safe('Navigation',         () => this.bindNavigation());
        safe('HeaderControls',     () => this.bindHeaderControls());
        safe('SimResultModal',     () => this.bindSimResultModal());
        safe('HistoryControls',    () => this.bindHistoryControls());
        safe('SimLabControls',     () => this.bindSimulationLabControls());
        safe('ScenarioControls',   () => this.bindScenarioControls());
        safe('OptControls',        () => this.bindOptimizationControls());
        safe('ForecastControls',   () => this.bindForecastingControls());
        safe('WhatIfModal',        () => this.bindWhatIfModal());
        safe('RackModal',          () => this.bindRackModal());
        safe('InitCharts',         () => this.initCharts());
        safe('LoadScenarios',      () => this.loadScenariosList());

        this.updateConnectionStatus('disconnected');

        // Expose global navigation helper
        window.navTo = (sectionId) => this.switchSection(sectionId);

        console.log('[UI] Initialisation complete.');
    }

    setBackendMode(enabled) {
        this.isBackendMode = enabled;
    }

    updateConnectionStatus(status) {
        this.isConnected = status === 'connected';
        const dot = document.getElementById('connStatusDot');
        const lbl = document.getElementById('connStatusLabel');
        const latency = document.getElementById('apiLatencyBadge');
        if (dot) {
            dot.className = `conn-dot ${status === 'connected' ? 'conn-dot-on' : 'conn-dot-off'}`;
        }
        if (lbl) {
            lbl.textContent = status === 'connected' ? 'CONNECTED (LIVE WS)' : 'DISCONNECTED';
            lbl.style.color = status === 'connected' ? '#00e676' : '#ff1744';
        }
        if (latency && status !== 'connected') {
            latency.textContent = '- ms';
        }
    }

    // ── Navigation Switching ─────────────────────────────────────────────────
    bindNavigation() {
        // Sidebar Toggle
        const toggleBtn = document.getElementById('sidebarToggle');
        const sidebar = document.getElementById('appSidebar');
        if (toggleBtn && sidebar) {
            toggleBtn.addEventListener('click', () => {
                sidebar.classList.toggle('collapsed');
            });
        }

        // Section Nav buttons
        const navItems = document.querySelectorAll('.nav-item');
        navItems.forEach((btn) => {
            btn.addEventListener('click', () => {
                const target = btn.getAttribute('data-target');
                if (target) this.switchSection(target);
            });
        });
    }

    switchSection(sectionId) {
        this.activeSection = sectionId;

        // Update nav items
        document.querySelectorAll('.nav-item').forEach((btn) => {
            btn.classList.toggle('active', btn.getAttribute('data-target') === sectionId);
        });

        // Update page sections
        document.querySelectorAll('.page-section').forEach((sec) => {
            sec.classList.toggle('active', sec.id === sectionId);
        });

        // Hide/Show Telemetry Ribbon: show on Overview & Digital Twin
        const ribbon = document.getElementById('telemetryRibbon');
        if (ribbon) {
            ribbon.style.display = (sectionId === 'secOverview' || sectionId === 'secDigitalTwin') ? 'grid' : 'none';
        }

        // Render section-specific data if needed
        if (sectionId === 'secExperiments') this.loadExperiments();
        if (sectionId === 'secReports') this.loadReportData();
        if (sectionId === 'secOptimization') this.runOptimizationEvaluation();
        if (sectionId === 'secHistory') this.loadSimulationHistory();

        // Resize charts to fit new container dimensions
        setTimeout(() => {
            Object.values(this.charts).forEach(c => c && c.resize());
        }, 100);
    }

    // ── Apply Server State (WebSocket Broadcast) ──────────────────────────────
    applyServerState(state) {
        if (!state) return;
        this.lastServerState = state;

        // 1. Update Header Clock, Mode, Status, Health
        this.updateHeaderState(state);

        // 2. Update Telemetry Ribbon
        this.updateTelemetryRibbon(state);

        // 3. Update Active Section
        if (state.digitalTwin) {
            this.renderRackBay(state.digitalTwin.racks);
            this.renderHeatmap(state.digitalTwin.racks);
        }

        if (state.forecasting) {
            this.updateHotspotWarning(state.forecasting);
            this.renderForecastingTable(state.forecasting);
            this.renderHotspotMap(state.forecasting);
            this.renderExplainability(state.forecasting);
        }

        if (state.optimization?.lastResult) {
            this.renderOptimizationResults(state.optimization.lastResult);
        }

        if (state.alerts) {
            this.renderAlerts(state.alerts);
        }

        if (state.energy) {
            this.updateEnergySection(state.energy);
        }

        if (state.summary && Object.keys(state.summary).length > 0) {
            this.renderSimulationResultScreen(state.summary);
        }

        // Auto show interactive result modal if completed or stopped mid-run
        if ((state.status === 'COMPLETED' || state.status === 'STOPPED') && state.summary && Object.keys(state.summary).length > 0) {
            const runKey = `${state.simId}_${state.status}`;
            if (this._lastShownResultKey !== runKey) {
                this._lastShownResultKey = runKey;
                this.showSimulationResultModal(state.summary, state.status);
            }
        }


        // Update Charts
        this.updateCharts(state);

        // Latency
        const latencyBadge = document.getElementById('apiLatencyBadge');
        if (latencyBadge && state.forecasting?.selectedModel?.latencyMs) {
            latencyBadge.textContent = `${state.forecasting.selectedModel.latencyMs} ms`;
        }
    }

    updateHeaderState(state) {
        // Clock
        const clockVal = document.getElementById('headerSimClock');
        const clockProg = document.getElementById('headerClockProgress');
        const labClock = document.getElementById('simLabClockDisplay');
        const labProg = document.getElementById('simLabProgressBar');
        const labProgPct = document.getElementById('simLabProgressPct');

        if (state.clock) {
            const display = state.clock.display || '00:00:00 / 01:00:00';
            const pct = state.clock.progressPercent || 0;
            if (clockVal) clockVal.textContent = display;
            if (clockProg) clockProg.style.width = `${pct}%`;
            if (labClock) labClock.textContent = display;
            if (labProg) labProg.style.width = `${pct}%`;
            if (labProgPct) labProgPct.textContent = `${pct.toFixed(1)}%`;
        }

        // Status
        const statusText = document.getElementById('headerStatusText');
        const statusBadge = document.getElementById('headerStatusBadge');
        const labStatus = document.getElementById('simLabStatusDisplay');
        const status = state.status || 'RUNNING';

        if (statusText) statusText.textContent = status;
        if (labStatus) {
            labStatus.textContent = status;
            labStatus.style.color = status === 'RUNNING' ? '#00e676' : (status === 'PAUSED' ? '#ffab00' : '#ff1744');
        }

        if (statusBadge) {
            statusBadge.className = `status-pill status-${status.toLowerCase()}`;
        }

        // Health
        const healthText = document.getElementById('headerHealthText');
        const healthBadge = document.getElementById('headerHealthBadge');
        const health = state.systemHealth || 'Safe';

        if (healthText) healthText.textContent = health.toUpperCase();
        if (healthBadge) {
            healthBadge.className = `health-pill health-${health.toLowerCase()}`;
        }

        // Mode dropdown sync
        const modeSelect = document.getElementById('globalModeSelect');
        if (modeSelect && modeSelect.value !== state.mode) {
            modeSelect.value = state.mode || 'live';
        }

        // Speed buttons sync
        const currentSpeed = state.clock?.speedMultiplier || 1;
        document.querySelectorAll('.btn-speed').forEach((btn) => {
            const spd = parseFloat(btn.getAttribute('data-speed'));
            btn.classList.toggle('active', spd === currentSpeed);
        });

        // Controls toggle (Pause vs Resume)
        const btnPause = document.getElementById('btnHeaderPause');
        const btnResume = document.getElementById('btnHeaderResume');
        const btnLabPause = document.getElementById('btnLabPause');
        const btnLabResume = document.getElementById('btnLabResume');

        if (status === 'PAUSED') {
            if (btnPause) btnPause.style.display = 'none';
            if (btnResume) btnResume.style.display = 'inline-flex';
            if (btnLabPause) btnLabPause.style.display = 'none';
            if (btnLabResume) btnLabResume.style.display = 'inline-flex';
        } else {
            if (btnPause) btnPause.style.display = 'inline-flex';
            if (btnResume) btnResume.style.display = 'none';
            if (btnLabPause) btnLabPause.style.display = 'inline-flex';
            if (btnLabResume) btnLabResume.style.display = 'none';
        }
    }

    updateTelemetryRibbon(state) {
        const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };

        const twin = state.digitalTwin;
        const lastSnap = twin?.history && twin.history.length ? twin.history[twin.history.length - 1] : null;

        if (lastSnap) {
            set('metricItPower', `${lastSnap.totalITPower?.toFixed(1) || 0.0} kW`);
            set('metricCoolingPower', `${lastSnap.coolingPower?.toFixed(1) || 0.0} kW`);
            set('metricPue', lastSnap.pue ? lastSnap.pue.toFixed(2) : '1.00');
            set('metricPeakTemp', `${lastSnap.maxTemp?.toFixed(1) || 0.0}°C`);
        }

        if (state.forecasting) {
            const risk = state.forecasting.datacenterHotspotRisk || 0;
            const el = document.getElementById('metricHotspotRisk');
            if (el) {
                el.textContent = `${risk}%`;
                el.className = `metric-val ${risk > 60 ? 'val-plasma' : (risk > 30 ? 'val-warning' : 'val-success')}`;
            }
        }

        if (state.weather) {
            set('metricAmbientInfo', `${state.weather.ambientTemp?.toFixed(1)}°C / ${state.weather.wetBulbTemp?.toFixed(1)}°C`);
            set('ovWeatherPreset', `${state.weather.presetId?.toUpperCase()}`);
            set('ovWeatherDetails', `Ambient: ${state.weather.ambientTemp?.toFixed(1)}°C, RH: ${state.weather.humidity}%, Wet-Bulb: ${state.weather.wetBulbTemp?.toFixed(1)}°C, COP Multiplier: ${state.weather.copMultiplier?.toFixed(2)}`);
        }

        if (state.scenarios) {
            const p = state.scenarios.activeProblem;
            if (p) {
                set('ovProblemScenario', p.name);
                set('ovProblemDetails', p.description);
            }
        }

        if (state.energy) {
            set('ovEnergySavings', `${state.energy.energySavingPercent || 0}% Saved`);
            set('ovEnergyDetails', `Net cooling energy abated: ${state.energy.energySavedKWh || 0} kWh (${state.energy.carbonSavedKg || 0} kg CO2e).`);
        }
    }

    updateHotspotWarning(forecast) {
        const banner = document.getElementById('hotspotWarningBanner');
        if (!banner) return;

        const risk = forecast.datacenterHotspotRisk || 0;
        const highest = forecast.highestRiskRack;

        if (risk >= 60 && highest) {
            banner.style.display = 'flex';
            const rName = document.getElementById('warnRackName');
            const rTemp = document.getElementById('warnTempVal');
            const rRisk = document.getElementById('warnRiskVal');
            if (rName) rName.textContent = highest.rackName || `Rack ${highest.rackId}`;
            if (rTemp) rTemp.textContent = `${highest.maxForecastTemp || highest.forecast15m}°C`;
            if (rRisk) rRisk.textContent = `${highest.hotspotProbability}%`;
        } else {
            banner.style.display = 'none';
        }
    }

    // ── Digital Twin Rack Grid & Inspector ───────────────────────────────────
    renderRackBay(racks) {
        const container = document.getElementById('rackBayGrid');
        if (!container || !racks) return;

        container.innerHTML = racks.map((rack) => {
            const riskClass = rack.thermalRisk === 'Critical' ? 'risk-critical' : (rack.thermalRisk === 'Warning' ? 'risk-warning' : 'risk-safe');
            const tempVal = rack.temp ? rack.temp.toFixed(1) : '24.0';

            return `
                <div class="rack-card" onclick="window.DigitalTwinApp.ui.openRackModal(${rack.id})">
                    <div class="rack-card-top">
                        <span class="rack-id">${rack.name || `Rack ${rack.id}`}</span>
                        <span class="rack-zone-badge">Zone ${rack.zone}</span>
                    </div>
                    <div class="rack-temp-display">
                        <span class="rack-temp-val ${riskClass}">${tempVal}°C</span>
                        <span class="badge ${rack.thermalRisk === 'Critical' ? 'badge-plasma' : (rack.thermalRisk === 'Warning' ? 'badge-warning' : 'badge-emerald')}">
                            ${rack.thermalRisk}
                        </span>
                    </div>
                    <div class="rack-stat-bar-group">
                        <div class="rack-bar-label"><span>CPU Util</span><span>${rack.cpuLoad}%</span></div>
                        <div class="rack-bar-track"><div class="rack-bar-fill" style="width: ${rack.cpuLoad}%; background:#00f2fe;"></div></div>
                    </div>
                    <div class="rack-stat-bar-group">
                        <div class="rack-bar-label"><span>GPU Util</span><span>${rack.gpuLoad || 0}%</span></div>
                        <div class="rack-bar-track"><div class="rack-bar-fill" style="width: ${rack.gpuLoad || 0}%; background:#7c4dff;"></div></div>
                    </div>
                    <div class="rack-metrics-footer">
                        <span>P: ${rack.powerKw ? rack.powerKw.toFixed(2) : 2.5} kW</span>
                        <span>Air: ${rack.airflowCfm || 800} CFM</span>
                        <span>Fan: ${rack.fanSpeed || 70}%</span>
                    </div>
                </div>
            `;
        }).join('');
    }

    renderHeatmap(racks) {
        const container = document.getElementById('rackHeatmapGrid');
        if (!container || !racks) return;

        container.innerHTML = racks.map((rack) => {
            const t = rack.temp || 24;
            // Interpolate color from 20°C (cool blue) to 36°C (hot red)
            const norm = Math.max(0, Math.min(1, (t - 20) / 16));
            const bg = `rgba(${Math.round(255 * norm)}, ${Math.round(180 * (1 - norm))}, ${Math.round(254 * (1 - norm))}, 0.25)`;
            const border = norm > 0.75 ? '#ff1744' : (norm > 0.5 ? '#ffab00' : '#00f2fe');

            return `
                <div class="heatmap-cell" style="background: ${bg}; border: 1px solid ${border};">
                    <span style="font-size: 10px; color:#8a99ad;">R${rack.id < 10 ? '0' + rack.id : rack.id}</span>
                    <span style="font-size: 15px; color:#fff;">${t.toFixed(1)}°C</span>
                </div>
            `;
        }).join('');
    }

    renderHotspotMap(forecast) {
        const container = document.getElementById('hotspotRiskMap');
        if (!container || !forecast?.rackForecasts) return;

        container.innerHTML = forecast.rackForecasts.map((rf) => {
            const risk = rf.hotspotProbability || 0;
            const barColor = risk >= 70 ? '#ff1744' : (risk >= 40 ? '#ffab00' : '#00e676');

            return `
                <div class="risk-row">
                    <span class="risk-row-label">R${rf.rackId < 10 ? '0' + rf.rackId : rf.rackId} (${rf.zone})</span>
                    <div class="risk-row-track">
                        <div style="height:100%; width:${risk}%; background:${barColor}; border-radius:4px;"></div>
                    </div>
                    <span class="risk-row-val" style="color:${barColor};">${risk}%</span>
                </div>
            `;
        }).join('');
    }

    // ── Forecasting Table & Explainability ─────────────────────────────────────
    renderForecastingTable(forecast) {
        const tbody = document.getElementById('forecastTableBody');
        if (!tbody || !forecast?.rackForecasts) return;

        tbody.innerHTML = forecast.rackForecasts.map((rf) => {
            const f = rf.forecasts || {};
            const breachText = rf.timeToBreachMin
                ? `<span style="color:#ff1744; font-weight:700;">⚠ Crossed in +${rf.timeToBreachMin}m</span>`
                : `<span style="color:#00e676;">Safe (&lt;33°C)</span>`;

            return `
                <tr>
                    <td><strong>${rf.rackName || `Rack ${rf.rackId}`}</strong></td>
                    <td>Zone ${rf.zone}</td>
                    <td>${rf.currentTemp ? rf.currentTemp.toFixed(1) : 24.0}°C</td>
                    <td>${f.t5m ? f.t5m.toFixed(1) : '-'}°C</td>
                    <td>${f.t10m ? f.t10m.toFixed(1) : '-'}°C</td>
                    <td><strong style="color:${f.t15m >= 33 ? '#ff1744' : '#fff'};">${f.t15m ? f.t15m.toFixed(1) : '-'}°C</strong></td>
                    <td>${f.t20m ? f.t20m.toFixed(1) : '-'}°C</td>
                    <td>${f.t25m ? f.t25m.toFixed(1) : '-'}°C</td>
                    <td>${f.t30m ? f.t30m.toFixed(1) : '-'}°C</td>
                    <td><span class="badge ${rf.hotspotProbability >= 60 ? 'badge-plasma' : (rf.hotspotProbability >= 30 ? 'badge-warning' : 'badge-emerald')}">${rf.hotspotProbability}%</span></td>
                    <td>${breachText}</td>
                </tr>
            `;
        }).join('');
    }

    renderExplainability(forecast) {
        const inspector = document.getElementById('inspectorDetailsBox');
        const select = document.getElementById('inspectRackSelect');
        if (!inspector || !select || !forecast?.rackForecasts) return;

        const rackId = parseInt(select.value);
        const rf = forecast.rackForecasts.find(r => r.rackId === rackId) || forecast.rackForecasts[0];
        if (!rf) return;

        const drivers = rf.explainabilityDrivers || [];
        inspector.innerHTML = `
            <div style="margin-bottom: 10px;">
                <strong>${rf.rackName} (Current: ${rf.currentTemp}°C | Predicted: ${rf.forecast15m}°C)</strong>
                <p style="font-size:11px; color:#8a99ad; margin-top:2px;">Hotspot Risk: <strong style="color:${rf.hotspotProbability >= 50 ? '#ff1744' : '#00e676'}">${rf.hotspotProbability}%</strong></p>
            </div>
            <div style="display:flex; flex-direction:column; gap:6px;">
                ${drivers.map(d => `
                    <div style="display:flex; justify-content:space-between; font-size:11px; padding:4px 0; border-bottom:1px solid #142035;">
                        <span style="color:#f0f4f8;">${d.feature} (${d.value})</span>
                        <span style="font-weight:700; color:${d.impact === 'High' ? '#ff1744' : (d.impact === 'Medium' ? '#ffab00' : '#00e676')}">${(d.importance * 100).toFixed(0)}% Impact</span>
                    </div>
                `).join('')}
            </div>
        `;
    }

    // ── Optimization & Counterfactual Decisions ───────────────────────────────
    renderOptimizationResults(result) {
        const tbody = document.getElementById('optCandidateTableBody');
        const rec = result.recommendedAction;
        const all = result.allEvaluations || [];

        // Update Tree branches
        all.forEach(ev => {
            const card = document.getElementById(`branchCard-${ev.actionId}`);
            if (card) {
                const tempEl = card.querySelector('.b-temp');
                if (tempEl) tempEl.textContent = `${ev.peakTemp.toFixed(1)}°C`;
            }
        });

        if (tbody) {
            tbody.innerHTML = all.map(ev => {
                const isRec = rec && rec.actionId === ev.actionId;
                const safeBadge = ev.isSafe
                    ? `<span class="badge badge-emerald">YES (SAFE)</span>`
                    : `<span class="badge badge-plasma">NO (VIOLATION)</span>`;

                const recBadge = isRec
                    ? `<span class="badge badge-emerald">RECOMMENDED</span>`
                    : `<span>-</span>`;

                return `
                    <tr style="${isRec ? 'background: rgba(0, 230, 118, 0.08); font-weight:600;' : ''}">
                        <td><strong>${ev.title}</strong></td>
                        <td>${ev.type}</td>
                        <td style="font-size:11px; color:#8a99ad;">${ev.description}</td>
                        <td>${ev.peakTemp.toFixed(1)}°C</td>
                        <td>${ev.coolingEnergyKWh.toFixed(2)} kWh</td>
                        <td>${safeBadge}</td>
                        <td>${ev.costScore.toFixed(1)}</td>
                        <td>${recBadge}</td>
                        <td>
                            <button class="btn btn-sm btn-cyan" onclick="window.DigitalTwinApp.ui.applyIntervention('${ev.actionId}')">
                                Enact
                            </button>
                        </td>
                    </tr>
                `;
            }).join('');
        }

        // Recommended Highlight Card
        if (rec) {
            const t = document.getElementById('recActionTitle');
            const d = document.getElementById('recActionDesc');
            const pt = document.getElementById('recPeakTemp');
            const en = document.getElementById('recEnergy');
            const sv = document.getElementById('recSavedPct');

            if (t) t.textContent = rec.title;
            if (d) d.textContent = rec.description;
            if (pt) pt.textContent = `${rec.peakTemp.toFixed(1)}°C`;
            if (en) en.textContent = `${rec.coolingEnergyKWh.toFixed(2)} kWh`;
            if (sv) sv.textContent = `${rec.energyDeltaPercent < 0 ? Math.abs(rec.energyDeltaPercent) : 0}%`;
        }
    }

    async applyIntervention(actionId) {
        if (!this.api) return;
        const res = await this.api.applyIntervention(actionId);
        if (res?.ok) {
            alert(`Intervention Applied: ${actionId}`);
            if (res.state) this.applyServerState(res.state);
        }
    }

    // ── Simulation Result Screen ──────────────────────────────────────────────
    renderSimulationResultScreen(summary) {
        const screen = document.getElementById('simResultScreen');
        if (!screen || !summary) return;

        screen.style.display = 'block';

        const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };

        set('resSimIdText', `Simulation ID: ${summary.simId} (${summary.modeName})`);
        if (summary.thermal) {
            set('resAvgTemp', `${summary.thermal.avgTemp}°C`);
            set('resMaxTemp', `${summary.thermal.maxTemp}°C`);
            set('resMinTemp', `${summary.thermal.minTemp}°C`);
            set('resViolations', summary.thermal.violationsCount);
            set('resMaxRisk', `${summary.thermal.maxHotspotRisk}%`);
            set('resTimeAboveWarn', `${summary.thermal.timeAboveWarningMin} mins`);
        }

        if (summary.energy) {
            set('resItEnergy', `${summary.energy.totalITKWh} kWh`);
            set('resCoolingEnergy', `${summary.energy.totalCoolingKWh} kWh`);
            set('resFacilityEnergy', `${summary.energy.totalFacilityKWh} kWh`);
            set('resPeakCoolingKw', `${summary.energy.peakCoolingPowerKW} kW`);
            set('resAvgPue', summary.energy.averagePUE);
            set('resEnergySaved', `${summary.energy.energySavingPercent}%`);
        }

        if (summary.ml) {
            set('resMlModel', summary.ml.modelName);
            set('resMlMae', `${summary.ml.mae}°C`);
            set('resMlRmse', `${summary.ml.rmse}°C`);
            set('resMlR2', summary.ml.r2);
            set('resHotspotPreds', summary.ml.hotspotPredictions);
            set('resFalseAlarms', summary.ml.falseAlarms);
        }

        if (summary.optimization) {
            set('resInterventionsCount', summary.optimization.interventionsCount);
            set('resInterventionType', summary.optimization.interventionTypes?.[0] || 'Proactive Combined');
            set('resViolationsPrevented', summary.optimization.violationsPrevented);
            set('resCoolingSavedKwh', `${summary.optimization.energySavedKWh} kWh`);
        }
    }

    // ── Alerts & Events ───────────────────────────────────────────────────────
    renderAlerts(alertsData) {
        const countBadge = document.getElementById('sidebarAlertCount');
        if (countBadge) {
            const crit = alertsData.criticalCount || 0;
            countBadge.textContent = crit;
            countBadge.style.display = crit > 0 ? 'inline-block' : 'none';
        }

        const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
        set('statTotalAlerts', alertsData.totalCount || 0);
        set('statCritAlerts', alertsData.criticalCount || 0);
        set('statWarnAlerts', alertsData.warningCount || 0);
        set('statInfoAlerts', alertsData.infoCount || 0);

        const tbody = document.getElementById('alertsTableBody');
        if (!tbody || !alertsData.recentEvents) return;

        const filtered = alertsData.recentEvents.filter((e) => {
            if (this.alertFilter === 'ALL') return true;
            return e.severity === this.alertFilter;
        });

        tbody.innerHTML = filtered.map((e) => {
            const sevBadge = e.severity === 'CRITICAL'
                ? `<span class="badge badge-plasma">CRITICAL</span>`
                : (e.severity === 'WARNING' ? `<span class="badge badge-warning">WARNING</span>` : `<span class="badge badge-cyan">INFO</span>`);

            return `
                <tr>
                    <td>${e.timestamp}</td>
                    <td>${e.simTime}</td>
                    <td><strong>${e.rackId}</strong></td>
                    <td>${sevBadge}</td>
                    <td>${e.eventType}</td>
                    <td>${e.description}</td>
                    <td>${e.actionTaken}</td>
                </tr>
            `;
        }).join('');
    }

    // ── Energy Analytics Updates ──────────────────────────────────────────────
    updateEnergySection(energy) {
        const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };

        set('enItEnergyKwh', `${energy.totalITKWh?.toFixed(2) || 0.0} kWh`);
        set('enItCost', `$${(energy.totalITKWh * 0.14).toFixed(2)} Cost`);
        set('enCoolingEnergyKwh', `${energy.totalCoolingKWh?.toFixed(2) || 0.0} kWh`);
        set('enCoolingCost', `$${(energy.totalCoolingKWh * 0.14).toFixed(2)} Cost`);
        set('enTotalEnergyKwh', `${energy.totalFacilityKWh?.toFixed(2) || 0.0} kWh`);
        set('enTotalCost', `$${energy.operationalCostUSD?.toFixed(2) || 0.0} Total`);
        set('enAvgPue', energy.averagePUE ? energy.averagePUE.toFixed(3) : '1.000');
        set('enEnergySavedKwh', `${energy.energySavedKWh?.toFixed(2) || 0.0} kWh`);
        set('enSavingPct', `${energy.energySavingPercent || 0}% Reduction`);
        set('enCarbonSavedKg', `${energy.carbonSavedKg?.toFixed(1) || 0.0} kg`);
    }

    // ── Experiments & Reports Loaders ─────────────────────────────────────────
    async loadExperiments() {
        if (!this.api) return;
        const res = await this.api.getExperiments();
        if (!res?.paradigms) return;

        const tbody = document.getElementById('experimentsTableBody');
        if (tbody) {
            tbody.innerHTML = res.paradigms.map(p => `
                <tr style="${p.id === 'full_counterfactual' ? 'background: rgba(0, 242, 254, 0.08); font-weight:600;' : ''}">
                    <td><strong>${p.name}</strong></td>
                    <td style="font-size:11px; color:#8a99ad;">${p.description}</td>
                    <td>${p.mae.toFixed(3)}</td>
                    <td>${p.rmse.toFixed(3)}</td>
                    <td>${p.r2.toFixed(4)}</td>
                    <td>${p.thermalViolations}</td>
                    <td>${p.totalEnergyKWh.toFixed(2)} kWh</td>
                    <td>${p.peakTemp.toFixed(1)}°C</td>
                    <td>${p.interventionsCount}</td>
                    <td><strong style="color:#00e676;">${p.energySavingsPct.toFixed(1)}%</strong></td>
                </tr>
            `).join('');
        }

        // Render Experiment Bar Charts
        this.renderExperimentCharts(res.paradigms);
    }

    renderExperimentCharts(paradigms) {
        const ctxAcc = document.getElementById('expAccuracyChart');
        if (ctxAcc) {
            if (this.charts.expAcc) this.charts.expAcc.destroy();
            this.charts.expAcc = new Chart(ctxAcc, {
                type: 'bar',
                data: {
                    labels: paradigms.map(p => p.id),
                    datasets: [
                        { label: 'MAE (°C)', data: paradigms.map(p => p.mae), backgroundColor: '#00f2fe' },
                        { label: 'RMSE (°C)', data: paradigms.map(p => p.rmse), backgroundColor: '#ff1744' },
                    ],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: { y: { beginAtZero: true, grid: { color: '#1a273e' } }, x: { grid: { color: '#1a273e' } } },
                    plugins: { legend: { labels: { color: '#f0f4f8' } } }
                }
            });
        }

        const ctxEnergy = document.getElementById('expEnergyChart');
        if (ctxEnergy) {
            if (this.charts.expEnergy) this.charts.expEnergy.destroy();
            this.charts.expEnergy = new Chart(ctxEnergy, {
                type: 'bar',
                data: {
                    labels: paradigms.map(p => p.id),
                    datasets: [
                        { label: 'Energy Savings (%)', data: paradigms.map(p => p.energySavingsPct), backgroundColor: '#00e676' },
                    ],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: { y: { beginAtZero: true, grid: { color: '#1a273e' } }, x: { grid: { color: '#1a273e' } } },
                    plugins: { legend: { labels: { color: '#f0f4f8' } } }
                }
            });
        }
    }

    async loadReportData() {
        if (!this.api) return;
        const rep = await this.api.getReportData();
        if (!rep) return;

        const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
        set('repSimId', rep.simId);
        set('repDate', rep.completedAt?.split(' ')[0] || new Date().toISOString().split('T')[0]);
        set('repDuration', rep.durationFormatted || '01:00:00');
        set('repMode', rep.modeName || 'Simulation Lab');
        set('repWeather', rep.weatherName || 'Normal');
        set('repScenario', rep.problemName || 'Nominal');

        if (rep.thermal) {
            set('repMaxTemp', `${rep.thermal.maxTemp}°C`);
            set('repAvgTemp', `${rep.thermal.avgTemp}°C`);
            set('repViolations', rep.thermal.violationsCount);
            set('repRisk', `${rep.thermal.maxHotspotRisk}%`);
        }

        if (rep.ml) {
            set('repModelName', rep.ml.modelName);
            set('repMae', `${rep.ml.mae}°C`);
            set('repRmse', `${rep.ml.rmse}°C`);
            set('repR2', rep.ml.r2);
        }
    }

    // ── Scenarios Loader & Binding ────────────────────────────────────────────
    async loadScenariosList() {
        if (!this.api) return;
        const res = await this.api.getScenarios();
        if (!res) return;

        // Render Weather presets
        const wGrid = document.getElementById('weatherPresetsGrid');
        if (wGrid && res.weatherPresets) {
            wGrid.innerHTML = res.weatherPresets.map(w => `
                <div class="weather-card ${res.currentWeather?.presetId === w.id ? 'active' : ''}" onclick="window.DigitalTwinApp.ui.applyWeather('${w.id}')">
                    <div style="font-size:20px;">${w.icon}</div>
                    <strong style="font-size:13px; color:#fff;">${w.name}</strong>
                    <span style="font-size:11px; color:#00f2fe;">${w.ambientTemp}°C, ${w.humidity}% RH</span>
                    <p style="font-size:10.5px; color:#8a99ad; margin-top:4px;">${w.description}</p>
                </div>
            `).join('');
        }

        // Render 10 Problem scenarios
        const pGrid = document.getElementById('problemScenariosGrid');
        if (pGrid && res.failureProblems) {
            pGrid.innerHTML = res.failureProblems.map(p => `
                <div class="scenario-card ${res.currentProblem?.id === p.id ? 'active' : ''}" onclick="window.DigitalTwinApp.ui.applyProblem('${p.id}')">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <strong style="color:#fff; font-size:13px;">${p.name}</strong>
                        <span class="badge ${p.severity === 'CRITICAL' ? 'badge-plasma' : (p.severity === 'WARNING' ? 'badge-warning' : 'badge-cyan')}">${p.severity}</span>
                    </div>
                    <p style="font-size:11px; color:#8a99ad;">${p.description}</p>
                    <div style="font-size:10px; color:#00f2fe; margin-top:4px;">
                        <span>Effect: ${p.expectedEffect}</span>
                    </div>
                </div>
            `).join('');
        }
    }

    async applyWeather(presetId) {
        if (!this.api) return;
        const res = await this.api.setWeather(presetId);
        if (res?.ok) {
            this.loadScenariosList();
        }
    }

    async applyProblem(problemId) {
        if (!this.api) return;
        const res = await this.api.setProblem(problemId);
        if (res?.ok) {
            this.loadScenariosList();
        }
    }

    // ── Controls Binding ──────────────────────────────────────────────────────
    bindHeaderControls() {
        // Mode Select
        const modeSelect = document.getElementById('globalModeSelect');
        if (modeSelect) {
            modeSelect.addEventListener('change', (e) => {
                const mode = e.target.value;
                if (mode === 'lab') {
                    this.switchSection('secSimulationLab');
                } else {
                    this.switchSection('secOverview');
                }
            });
        }

        const handleStop = async () => {
            const res = await this.api?.stopSimulation();
            if (res && res.summary) {
                this.showSimulationResultModal(res.summary, 'STOPPED');
            }
        };

        // Sim Action Buttons
        document.getElementById('btnHeaderStart')?.addEventListener('click', () => this.api?.startSimulation());
        document.getElementById('btnHeaderPause')?.addEventListener('click', () => this.api?.pauseSimulation());
        document.getElementById('btnHeaderResume')?.addEventListener('click', () => this.api?.resumeSimulation());
        document.getElementById('btnHeaderStop')?.addEventListener('click', handleStop);
        document.getElementById('btnHeaderRestart')?.addEventListener('click', () => this.api?.restartSimulation());

        // Fast-Forward Speed buttons (Immediate UI feedback + server dispatch)
        const speedBtns = document.querySelectorAll('.btn-speed');
        speedBtns.forEach((btn) => {
            btn.addEventListener('click', () => {
                speedBtns.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                const mult = parseFloat(btn.getAttribute('data-speed'));
                this.simSpeed = mult;
                const speedDisp = document.getElementById('simLabSpeedDisplay');
                if (speedDisp) speedDisp.textContent = `${mult}x Realtime`;
                this.api?.setSpeed(mult);
            });
        });

        // Global Export PDF
        const btnPdf = document.getElementById('btnGlobalExportPdf');
        if (btnPdf) {
            btnPdf.addEventListener('click', () => {
                window.location.href = '/api/report/pdf';
            });
        }
        document.getElementById('btnResultExportPdf')?.addEventListener('click', () => {
            window.location.href = '/api/report/pdf';
        });

        // Banner Counterfactual action
        document.getElementById('btnBannerCounterfactual')?.addEventListener('click', () => {
            this.switchSection('secOptimization');
            this.runOptimizationEvaluation();
        });
        document.getElementById('btnDismissBanner')?.addEventListener('click', () => {
            const b = document.getElementById('hotspotWarningBanner');
            if (b) b.style.display = 'none';
        });
    }

    bindSimulationLabControls() {
        const handleStop = async () => {
            const res = await this.api?.stopSimulation();
            if (res && res.summary) {
                this.showSimulationResultModal(res.summary, 'STOPPED');
            }
        };

        document.getElementById('btnLabStart')?.addEventListener('click', () => this.api?.startSimulation());
        document.getElementById('btnLabPause')?.addEventListener('click', () => this.api?.pauseSimulation());
        document.getElementById('btnLabResume')?.addEventListener('click', () => this.api?.resumeSimulation());
        document.getElementById('btnLabStop')?.addEventListener('click', handleStop);
        document.getElementById('btnLabRestart')?.addEventListener('click', () => this.api?.restartSimulation());

        // Duration preset toggle
        const durPreset = document.getElementById('cfgDurationPreset');
        const customGrp = document.getElementById('groupCustomDuration');
        if (durPreset && customGrp) {
            durPreset.addEventListener('change', () => {
                customGrp.style.display = durPreset.value === 'custom' ? 'block' : 'none';
            });
        }

        // Sliders value feedback
        const bindSlider = (sliderId, labelId, suffix = '') => {
            const s = document.getElementById(sliderId);
            const l = document.getElementById(labelId);
            if (s && l) s.addEventListener('input', () => { l.textContent = `${s.value}${suffix}`; });
        };
        bindSlider('cfgWorkload', 'valCfgWorkload', '%');
        bindSlider('cfgAmbientTemp', 'valCfgAmbient', '°C');
        bindSlider('cfgHumidity', 'valCfgHumidity', '%');
        bindSlider('cfgCoolingSetpoint', 'valCfgCooling', '°C');
        bindSlider('cfgAirflow', 'valCfgAirflow', ' CFM');

        // Apply configuration button
        document.getElementById('btnApplyConfiguration')?.addEventListener('click', async () => {
            let dur = parseInt(document.getElementById('cfgDurationPreset').value);
            if (isNaN(dur)) {
                dur = parseInt(document.getElementById('cfgCustomDurationMin').value) * 60;
            }

            const body = {
                durationSec: dur,
                timestepSec: parseFloat(document.getElementById('cfgTimestep').value),
                numRacks: parseInt(document.getElementById('cfgNumRacks').value),
                initialWorkload: parseFloat(document.getElementById('cfgWorkload').value),
                initialAmbientTemp: parseFloat(document.getElementById('cfgAmbientTemp').value),
                initialHumidity: parseFloat(document.getElementById('cfgHumidity').value),
                coolingSetpoint: parseFloat(document.getElementById('cfgCoolingSetpoint').value),
                crahAirflow: parseFloat(document.getElementById('cfgAirflow').value),
                mlModel: document.getElementById('cfgMlModel').value,
                optimizationEnabled: document.getElementById('cfgOptimizationEnabled').value === 'true',
            };

            const res = await this.api?.configureSimulation(body);
            if (res?.ok) {
                alert(`Simulation re-configured: ${body.durationSec}s duration, ${body.numRacks} racks. Click START to begin.`);
                if (res.state) this.applyServerState(res.state);
            }
        });
    }

    bindScenarioControls() {
        // Custom weather slider feedback
        const sAmb = document.getElementById('sliderCustomAmbient');
        const sHum = document.getElementById('sliderCustomHumidity');
        if (sAmb) sAmb.addEventListener('input', () => { document.getElementById('valCustomAmbient').textContent = `${sAmb.value}°C`; });
        if (sHum) sHum.addEventListener('input', () => { document.getElementById('valCustomHumidity').textContent = `${sHum.value}%`; });

        document.getElementById('btnApplyCustomWeather')?.addEventListener('click', async () => {
            const amb = parseFloat(sAmb.value);
            const hum = parseFloat(sHum.value);
            await this.api?.setWeather('custom', amb, hum);
            this.loadScenariosList();
        });

        // Combined Stress Test Button
        document.getElementById('btnActivateCompoundScenario')?.addEventListener('click', async () => {
            const wId = document.getElementById('combineWeatherSelect').value;
            const pId = document.getElementById('combineProblemSelect').value;
            const wkId = document.getElementById('combineWorkloadSelect').value;

            const res = await this.api?.combineScenarios(wId, pId, wkId);
            if (res?.ok) {
                alert(`Compound stress test activated: [${wId}] + [${pId}] + [${wkId}].`);
                if (res.state) this.applyServerState(res.state);
            }
        });
    }

    bindOptimizationControls() {
        document.getElementById('btnRunOptimizerManual')?.addEventListener('click', () => {
            this.runOptimizationEvaluation();
        });

        document.getElementById('btnApplyRecommendedAction')?.addEventListener('click', () => {
            const rec = this.lastServerState?.optimization?.lastResult?.recommendedAction;
            if (rec) {
                this.applyIntervention(rec.actionId);
            }
        });
    }

    async runOptimizationEvaluation() {
        if (!this.api) return;
        const res = await this.api.evaluateOptimization();
        if (res?.allEvaluations) {
            this.renderOptimizationResults(res);
        }
    }

    bindForecastingControls() {
        const select = document.getElementById('forecastModelSelect');
        if (select) {
            select.addEventListener('change', () => {
                // Trigger forecast refresh
            });
        }

        const rackInspectSelect = document.getElementById('inspectRackSelect');
        if (rackInspectSelect) {
            rackInspectSelect.addEventListener('change', () => {
                if (this.lastServerState?.forecasting) {
                    this.renderExplainability(this.lastServerState.forecasting);
                }
            });
        }
    }

    bindWhatIfModal() {
        const modal = document.getElementById('whatIfModal');
        document.getElementById('btnOpenWhatIfModal')?.addEventListener('click', () => {
            if (modal) modal.style.display = 'flex';
        });
        document.getElementById('btnCloseWhatIfModal')?.addEventListener('click', () => {
            if (modal) modal.style.display = 'none';
        });

        // Slider value feedback
        const bindWi = (sId, lId, suf = '') => {
            const s = document.getElementById(sId);
            const l = document.getElementById(lId);
            if (s && l) s.addEventListener('input', () => { l.textContent = `${s.value}${suf}`; });
        };
        bindWi('sliderWiWorkload', 'valWiWorkload', '%');
        bindWi('sliderWiCooling', 'valWiCooling', '°C');
        bindWi('sliderWiAirflow', 'valWiAirflow', ' CFM');
        bindWi('sliderWiAmbient', 'valWiAmbient', '°C');
        bindWi('sliderWiActiveRacks', 'valWiActiveRacks', ' Racks');

        document.getElementById('btnRunWhatIfSim')?.addEventListener('click', async () => {
            const body = {
                workloadPct: parseFloat(document.getElementById('sliderWiWorkload').value),
                coolingSetpoint: parseFloat(document.getElementById('sliderWiCooling').value),
                airflowCFM: parseFloat(document.getElementById('sliderWiAirflow').value),
                ambientTemp: parseFloat(document.getElementById('sliderWiAmbient').value),
                activeRacksCount: parseInt(document.getElementById('sliderWiActiveRacks').value),
                horizonMinutes: parseInt(document.getElementById('wiHorizonSelect').value),
            };

            const res = await this.api?.runWhatIf(body);
            if (res) {
                const container = document.getElementById('whatIfResultsContainer');
                if (container) container.style.display = 'block';

                const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
                set('wiBeforePeakTemp', `${res.before.peakTemp}°C`);
                set('wiBeforeCoolingKwh', `${res.before.coolingEnergyKWh} kWh`);
                set('wiBeforeRisk', `${res.before.thermalRiskPercent}%`);
                set('wiBeforeViolations', res.before.thermalViolations);

                set('wiAfterPeakTemp', `${res.after.peakTemp}°C`);
                set('wiAfterCoolingKwh', `${res.after.coolingEnergyKWh} kWh`);
                set('wiAfterRisk', `${res.after.thermalRiskPercent}%`);
                set('wiAfterViolations', res.after.thermalViolations);

                set('wiDeltaEnergy', `${res.deltas.coolingEnergySavedKWh} kWh (${res.deltas.energySavingsPercent}%)`);
                set('wiDeltaTemp', `${res.deltas.temperatureReductionC > 0 ? '-' : '+'}${Math.abs(res.deltas.temperatureReductionC)}°C`);
                set('wiDeltaViolations', `${res.deltas.thermalViolationsAvoided} Avoided`);
            }
        });
    }

    bindRackModal() {
        const modal = document.getElementById('rackDetailModal');
        document.getElementById('btnCloseRackModal')?.addEventListener('click', () => {
            if (modal) modal.style.display = 'none';
        });

        const sCpu = document.getElementById('sliderMRackCpu');
        const sFan = document.getElementById('sliderMRackFan');
        if (sCpu) sCpu.addEventListener('input', () => { document.getElementById('valMRackCpu').textContent = `${sCpu.value}%`; });
        if (sFan) sFan.addEventListener('input', () => { document.getElementById('valMRackFan').textContent = `${sFan.value}%`; });

        document.getElementById('btnSaveRackParams')?.addEventListener('click', async () => {
            if (!this.selectedRackId) return;
            const body = {
                cpuLoad: parseInt(sCpu.value),
                fanSpeed: parseInt(sFan.value),
            };
            await this.api?.updateRack(this.selectedRackId, body);
            alert(`Rack ${this.selectedRackId} parameters updated.`);
            if (modal) modal.style.display = 'none';
        });
    }

    openRackModal(rackId) {
        this.selectedRackId = rackId;
        const modal = document.getElementById('rackDetailModal');
        const racks = this.lastServerState?.digitalTwin?.racks || [];
        const r = racks.find(x => x.id === rackId) || racks[0];

        if (r && modal) {
            document.getElementById('modalRackTitle').textContent = `Inspection: ${r.name || `Rack ${r.id}`}`;
            document.getElementById('mRackZone').textContent = r.zone;
            document.getElementById('mRackTemp').textContent = `${r.temp?.toFixed(1) || 24}°C`;
            document.getElementById('mRackInlet').textContent = `${r.inletTemp?.toFixed(1) || 19}°C`;
            document.getElementById('mRackOutlet').textContent = `${r.outletTemp?.toFixed(1) || 29}°C`;
            document.getElementById('mRackPower').textContent = `${r.powerKw?.toFixed(2) || 2.5} kW`;
            document.getElementById('mRackAirflow').textContent = `${r.airflowCfm || 800} CFM`;
            document.getElementById('mRackRisk').textContent = r.thermalRisk || 'Safe';

            document.getElementById('sliderMRackCpu').value = r.cpuLoad || 50;
            document.getElementById('valMRackCpu').textContent = `${r.cpuLoad || 50}%`;
            document.getElementById('sliderMRackFan').value = r.fanSpeed || 70;
            document.getElementById('valMRackFan').textContent = `${r.fanSpeed || 70}%`;

            modal.style.display = 'flex';
        }
    }

    // ── Chart.js Telemetry Charts ─────────────────────────────────────────────
    initCharts() {
        const commonOptions = {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 300 },
            scales: {
                x: { grid: { color: 'rgba(255, 255, 255, 0.05)' }, ticks: { color: '#8a99ad', font: { family: 'JetBrains Mono', size: 9 } } },
                y: { grid: { color: 'rgba(255, 255, 255, 0.05)' }, ticks: { color: '#8a99ad', font: { family: 'JetBrains Mono', size: 9 } } },
            },
            plugins: {
                legend: { labels: { color: '#f0f4f8', font: { family: 'Inter', size: 11 } } },
            }
        };

        // Overview Temp Chart
        const ctxOvTemp = document.getElementById('overviewTempChart');
        if (ctxOvTemp) {
            this.charts.ovTemp = new Chart(ctxOvTemp, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [
                        { label: 'Max Core Temp (°C)', data: [], borderColor: '#ff1744', backgroundColor: 'rgba(255,23,68,0.1)', fill: true, tension: 0.3 },
                        { label: 'Avg Core Temp (°C)', data: [], borderColor: '#00f2fe', tension: 0.3 },
                        { label: 'Safety Limit (33°C)', data: [], borderColor: '#ffab00', borderDash: [5, 5], pointRadius: 0 },
                    ]
                },
                options: commonOptions,
            });
        }

        // Overview Power Chart
        const ctxOvPower = document.getElementById('overviewPowerChart');
        if (ctxOvPower) {
            this.charts.ovPower = new Chart(ctxOvPower, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [
                        { label: 'Total Facility Power (kW)', data: [], borderColor: '#00e676', tension: 0.3 },
                        { label: 'IT Power (kW)', data: [], borderColor: '#00f2fe', tension: 0.3 },
                        { label: 'Cooling Power (kW)', data: [], borderColor: '#ffab00', tension: 0.3 },
                    ]
                },
                options: commonOptions,
            });
        }

        // Energy Power Timeline
        const ctxEnPower = document.getElementById('energyPowerChart');
        if (ctxEnPower) {
            this.charts.enPower = new Chart(ctxEnPower, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [
                        { label: 'IT Power (kW)', data: [], borderColor: '#00f2fe', tension: 0.2 },
                        { label: 'Cooling Power (kW)', data: [], borderColor: '#ffab00', tension: 0.2 },
                    ]
                },
                options: commonOptions,
            });
        }

        // Energy PUE Timeline
        const ctxEnPue = document.getElementById('energyPueChart');
        if (ctxEnPue) {
            this.charts.enPue = new Chart(ctxEnPue, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [
                        { label: 'PUE Trend', data: [], borderColor: '#00e676', tension: 0.2 },
                        { label: 'Target PUE (1.25)', data: [], borderColor: '#7c4dff', borderDash: [4, 4], pointRadius: 0 },
                    ]
                },
                options: commonOptions,
            });
        }
    }

    updateCharts(state) {
        const history = state.digitalTwin?.history || [];
        if (!history.length) return;

        const labels = history.map(h => h.timestamp);

        // Update Overview Temp Chart
        if (this.charts.ovTemp) {
            this.charts.ovTemp.data.labels = labels;
            this.charts.ovTemp.data.datasets[0].data = history.map(h => h.maxTemp);
            this.charts.ovTemp.data.datasets[1].data = history.map(h => h.avgTemp);
            this.charts.ovTemp.data.datasets[2].data = history.map(() => 33.0);
            this.charts.ovTemp.update('none');
        }

        // Update Overview Power Chart
        if (this.charts.ovPower) {
            this.charts.ovPower.data.labels = labels;
            this.charts.ovPower.data.datasets[0].data = history.map(h => h.totalFacilityPower || (h.totalITPower + h.coolingPower));
            this.charts.ovPower.data.datasets[1].data = history.map(h => h.totalITPower);
            this.charts.ovPower.data.datasets[2].data = history.map(h => h.coolingPower);
            this.charts.ovPower.update('none');
        }

        // Update Energy Power Timeline
        if (this.charts.enPower) {
            this.charts.enPower.data.labels = labels;
            this.charts.enPower.data.datasets[0].data = history.map(h => h.totalITPower);
            this.charts.enPower.data.datasets[1].data = history.map(h => h.coolingPower);
            this.charts.enPower.update('none');
        }

        // Update Energy PUE Timeline
        if (this.charts.enPue) {
            this.charts.enPue.data.labels = labels;
            this.charts.enPue.data.datasets[0].data = history.map(h => h.pue);
            this.charts.enPue.data.datasets[1].data = history.map(() => 1.25);
            this.charts.enPue.update('none');
        }
    }

    // Fallback local loop if backend offline
    startLoop() {
        setInterval(() => {
            const snap = this.physics.step(1.0);
            this.applyServerState({
                status: 'RUNNING',
                mode: 'live',
                digitalTwin: this.physics.to_dict ? this.physics.to_dict() : { racks: this.physics.racks, history: this.physics.history },
            });
        }, 1000);
    }

    // ── Theme Management (Light / Dark) ───────────────────────────────────────
    bindThemeToggle() {
        const toggleBtn = document.getElementById('btnThemeToggle');
        const themeIcon = document.getElementById('themeIcon');
        const savedTheme = localStorage.getItem('dt_theme') || 'dark';

        const applyTheme = (theme) => {
            if (theme === 'light') {
                document.documentElement.setAttribute('data-theme', 'light');
                if (themeIcon) themeIcon.innerHTML = '&#9728;';
            } else {
                document.documentElement.removeAttribute('data-theme');
                if (themeIcon) themeIcon.innerHTML = '&#9790;';
            }
            localStorage.setItem('dt_theme', theme);
        };

        applyTheme(savedTheme);

        if (toggleBtn) {
            toggleBtn.addEventListener('click', () => {
                const currentTheme = document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
                const newTheme = currentTheme === 'light' ? 'dark' : 'light';
                applyTheme(newTheme);
            });
        }
    }


    // ── Global Results Modal (End-of-Simulation & Auto-Display on Interruption) ──
    bindSimResultModal() {
        const modal = document.getElementById('simResultModal');
        const btnClose = document.getElementById('btnCloseResultModal');
        const btnModalClose = document.getElementById('btnResModalClose');

        const closeModal = () => {
            if (modal) modal.style.display = 'none';
        };

        btnClose?.addEventListener('click', closeModal);
        btnModalClose?.addEventListener('click', closeModal);

        // JSON download
        document.getElementById('btnResModalDownloadJson')?.addEventListener('click', () => {
            if (this.currentModalSummary) {
                const blob = new Blob([JSON.stringify(this.currentModalSummary, null, 2)], { type: 'application/json' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `simulation_${this.currentModalSummary.simId || 'result'}.json`;
                a.click();
                URL.revokeObjectURL(url);
            }
        });

        // CSV download
        document.getElementById('btnResModalDownloadCsv')?.addEventListener('click', () => {
            if (this.currentModalSummary) {
                const s = this.currentModalSummary;
                let csv = 'Metric,Value\n';
                csv += `Simulation ID,${s.simId}\n`;
                csv += `Status,${s.status}\n`;
                csv += `Mode,${s.modeName}\n`;
                csv += `Duration,${s.durationFormatted}\n`;
                csv += `Elapsed,${s.elapsedFormatted}\n`;
                if (s.thermal) {
                    csv += `Average Temp,${s.thermal.avgTemp} C\n`;
                    csv += `Max Temp,${s.thermal.maxTemp} C\n`;
                    csv += `Min Temp,${s.thermal.minTemp} C\n`;
                    csv += `Thermal Violations,${s.thermal.violationsCount}\n`;
                    csv += `Peak Hotspot Risk,${s.thermal.maxHotspotRisk} %\n`;
                }
                if (s.energy) {
                    csv += `Total IT Energy,${s.energy.totalITKWh} kWh\n`;
                    csv += `Total Cooling Energy,${s.energy.totalCoolingKWh} kWh\n`;
                    csv += `Average PUE,${s.energy.averagePUE}\n`;
                    csv += `Energy Saved Percent,${s.energy.energySavingPercent} %\n`;
                }
                const blob = new Blob([csv], { type: 'text/csv' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `simulation_${s.simId || 'result'}.csv`;
                a.click();
                URL.revokeObjectURL(url);
            }
        });
    }

    showSimulationResultModal(summary, status = 'COMPLETED') {
        const modal = document.getElementById('simResultModal');
        if (!modal || !summary) return;

        this.currentModalSummary = summary;

        const isInterrupted = status === 'STOPPED' || status === 'INTERRUPTED';
        const notice = document.getElementById('resModalInterruptedNotice');
        const badge = document.getElementById('resModalStatusBadge');
        const title = document.getElementById('resModalTitle');
        const subtitle = document.getElementById('resModalSubtitle');
        const timeEl = document.getElementById('resModalInterruptedTime');

        if (isInterrupted) {
            if (notice) notice.style.display = 'flex';
            if (badge) { badge.className = 'badge badge-plasma'; badge.textContent = 'STOPPED / INTERRUPTED'; }
            if (title) title.textContent = 'Simulation Stopped - Performance Summary';
            if (subtitle) subtitle.textContent = 'Simulation execution was interrupted mid-run. Captured interim telemetry and thermodynamics recorded up to this point:';
            if (timeEl) timeEl.textContent = summary.elapsedFormatted || '00:00:00';
        } else {
            if (notice) notice.style.display = 'none';
            if (badge) { badge.className = 'badge badge-success'; badge.textContent = 'COMPLETED'; }
            if (title) title.textContent = 'Simulation Results & Engineering Performance Summary';
            if (subtitle) subtitle.textContent = 'Simulation run completed successfully. Detailed thermodynamic, energy, and ML model performance metrics captured below:';
        }

        const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };

        set('mResSimId', summary.simId || 'SIM-RUN');
        set('mResMode', summary.modeName || 'Standard Baseline');
        set('mResDuration', `${summary.elapsedFormatted || '00:00:00'} / ${summary.durationFormatted || '01:00:00'}`);
        set('mResTimestamp', summary.completedAt || new Date().toLocaleString());

        if (summary.thermal) {
            set('mResMaxTemp', `${summary.thermal.maxTemp}°C`);
            set('mResAvgTemp', `${summary.thermal.avgTemp}°C`);
            set('mResMinTemp', `${summary.thermal.minTemp}°C`);
            set('mResViolations', summary.thermal.violationsCount);
            set('mResMaxRisk', `${summary.thermal.maxHotspotRisk}%`);
        }

        if (summary.energy) {
            set('mResAvgPue', summary.energy.averagePUE || '1.25');
            set('mResEnergySaved', `${summary.energy.energySavingPercent || '0.0'}%`);
            set('mResCoolingEnergy', `${summary.energy.totalCoolingKWh || '0.0'} kWh`);
            set('mResItEnergy', `${summary.energy.totalITKWh || '0.0'} kWh`);
            set('mResPeakCooling', `${summary.energy.peakCoolingPowerKW || '0.0'} kW`);
        }

        if (summary.ml) {
            set('mResMlModel', summary.ml.modelName || 'XGBoost Regressor');
            set('mResMlMae', `${summary.ml.mae}°C`);
            set('mResMlRmse', `${summary.ml.rmse}°C`);
            set('mResMlR2', summary.ml.r2);
            set('mResMlLatency', `${summary.ml.latencyMs} ms`);
        }

        if (summary.optimization) {
            set('mResInterventionsCount', summary.optimization.interventionsCount || 0);
            set('mResPolicyName', summary.optimization.interventionTypes?.[0] || 'Proactive Combined');
            set('mResViolationsPrevented', summary.optimization.violationsPrevented || 0);
            set('mResCoolingSaved', `${summary.optimization.energySavedKWh || 0} kWh`);
        }

        modal.style.display = 'flex';
    }

    // ── Simulation History Management ─────────────────────────────────────────
    bindHistoryControls() {
        document.getElementById('btnRefreshHistory')?.addEventListener('click', () => {
            this.loadSimulationHistory();
        });
        document.getElementById('btnClearHistory')?.addEventListener('click', () => {
            this.clearSimulationHistory();
        });
    }

    async loadSimulationHistory() {
        const tbody = document.getElementById('simHistoryTableBody');
        const countBadge = document.getElementById('historyRecordCountBadge');
        if (!tbody) return;

        tbody.innerHTML = `<tr><td colspan="11" style="text-align:center; padding: 24px; color: var(--text-muted);">Fetching simulation records...</td></tr>`;

        if (!this.api) return;
        const res = await this.api.getSimulationHistory();
        const records = res?.history || [];

        if (countBadge) countBadge.textContent = `${records.length} Records`;

        if (records.length === 0) {
            tbody.innerHTML = `<tr><td colspan="11" style="text-align:center; padding: 24px; color: var(--text-muted);">No archived simulation records found yet. Run or stop a simulation to record history.</td></tr>`;
            return;
        }

        tbody.innerHTML = records.map(r => {
            const statusClass = r.status === 'COMPLETED' ? 'badge-emerald' : (r.status === 'STOPPED' ? 'badge-plasma' : 'badge-warning');
            return `
                <tr>
                    <td><code>${r.id}</code></td>
                    <td><span class="badge badge-outline">${r.mode.toUpperCase()}</span></td>
                    <td><span class="badge ${statusClass}">${r.status}</span></td>
                    <td>${r.durationSec}s</td>
                    <td>${r.elapsedSec}s</td>
                    <td><strong>${r.peakTemp}°C</strong></td>
                    <td>${r.avgPue}</td>
                    <td style="color:#00e676;">${r.energySavedPct}%</td>
                    <td>${r.violationsCount}</td>
                    <td style="font-size:11px; color:var(--text-muted);">${r.createdAt}</td>
                    <td>
                        <a href="/api/simulation/${r.id}/export?format=pdf" class="btn btn-xs btn-export-pdf btn-download-record" download>PDF</a>
                        <a href="/api/simulation/${r.id}/export?format=csv" class="btn btn-xs btn-cyan btn-download-record" download>CSV</a>
                        <a href="/api/simulation/${r.id}/export?format=json" class="btn btn-xs btn-outline btn-download-record" download>JSON</a>
                    </td>
                </tr>
            `;
        }).join('');
    }

    async clearSimulationHistory() {
        if (!confirm('Are you sure you want to clear all archived simulation records?')) return;
        if (!this.api) return;
        const res = await this.api.clearSimulationHistory();
        if (res?.ok) {
            this.loadSimulationHistory();
        }
    }
}

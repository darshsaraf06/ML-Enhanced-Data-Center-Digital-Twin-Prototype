/**
 * Physics-Informed RC Thermal Engine for Data Center Digital Twin
 * Equation: C_i * (dT_i/dt) = Q_i - UA_i * (T_i - T_cool) + Sum( K_ij * (T_j - T_i) )
 */

export class ThermalPhysicsEngine {
    constructor() {
        this.ambientTemp = 28.0;     // °C ambient external
        this.coolingSupplyTemp = 18.0; // °C cold supply air from CRAH
        this.crahAirflowCFM = 8500;   // Total cooling airflow
        this.crahFanPowerKW = 45.0;   // CRAH Fan power
        this.chillerCOP = 3.8;        // Coefficient of Performance

        // 8 Racks divided into 2 Zones (Zone A: Racks 1-4, Zone B: Racks 5-8)
        this.racks = [
            { id: 1, name: "Rack 01 [Web/API]", zone: "A", cpuLoad: 45, servers: 12, temp: 24.5, inletTemp: 19.2, outletTemp: 28.1, thermalCap: 3.2, ua: 0.45, fanSpeed: 65, workloadType: "Web Servers" },
            { id: 2, name: "Rack 02 [Database]", zone: "A", cpuLoad: 60, servers: 14, temp: 26.8, inletTemp: 19.8, outletTemp: 31.4, thermalCap: 3.5, ua: 0.48, fanSpeed: 70, workloadType: "PostgreSQL DB" },
            { id: 3, name: "Rack 03 [Cache/KV]", zone: "A", cpuLoad: 52, servers: 10, temp: 25.4, inletTemp: 19.4, outletTemp: 29.2, thermalCap: 3.0, ua: 0.44, fanSpeed: 65, workloadType: "Redis Cluster" },
            { id: 4, name: "Rack 04 [Analytics]", zone: "A", cpuLoad: 58, servers: 12, temp: 26.1, inletTemp: 19.5, outletTemp: 30.8, thermalCap: 3.2, ua: 0.46, fanSpeed: 68, workloadType: "Spark Nodes" },
            { id: 5, name: "Rack 05 [ML Train 1]", zone: "B", cpuLoad: 78, servers: 8, temp: 29.4, inletTemp: 21.2, outletTemp: 35.6, thermalCap: 4.2, ua: 0.52, fanSpeed: 85, workloadType: "GPU Cluster A" },
            { id: 6, name: "Rack 06 [ML Train 2]", zone: "B", cpuLoad: 82, servers: 8, temp: 30.8, inletTemp: 21.8, outletTemp: 37.2, thermalCap: 4.2, ua: 0.54, fanSpeed: 90, workloadType: "GPU Cluster B" },
            { id: 7, name: "Rack 07 [AI LLM Infer]", zone: "B", cpuLoad: 88, servers: 8, temp: 32.1, inletTemp: 22.4, outletTemp: 39.8, thermalCap: 4.5, ua: 0.55, fanSpeed: 92, workloadType: "LLM Inference" },
            { id: 8, name: "Rack 08 [Storage]", zone: "B", cpuLoad: 40, servers: 16, temp: 25.2, inletTemp: 20.1, outletTemp: 29.0, thermalCap: 3.8, ua: 0.42, fanSpeed: 60, workloadType: "NVMe Array" }
        ];

        // Spatial thermal coupling matrix (heat transfer rate K_ij between adjacent racks)
        this.couplingMatrix = [
            [0, 0.08, 0.02, 0, 0.05, 0, 0, 0],
            [0.08, 0, 0.09, 0.02, 0, 0.06, 0, 0],
            [0.02, 0.09, 0, 0.08, 0, 0, 0.05, 0],
            [0, 0.02, 0.08, 0, 0, 0, 0, 0.04],
            [0.05, 0, 0, 0, 0, 0.09, 0.03, 0],
            [0, 0.06, 0, 0, 0.09, 0, 0.10, 0.02],
            [0, 0, 0.05, 0, 0.03, 0.10, 0, 0.08],
            [0, 0, 0, 0.04, 0, 0.02, 0.08, 0]
        ];

        this.timeStepSec = 1; // 1 second physics step
        this.history = [];
        this.maxHistoryLength = 60;
    }

    /**
     * Compute Heat Generation Q_i (kW) for a rack based on CPU load and server count
     */
    computeRackPower(rack) {
        // Base idle power per server ~ 0.12 kW, Max load power ~ 0.48 kW
        const powerPerServer = 0.12 + (rack.cpuLoad / 100) * 0.36;
        return rack.servers * powerPerServer; // Total kW heat generation
    }

    /**
     * Update thermal differential equation step for all racks
     */
    step(dt = 1.0) {
        const newTemps = [];
        let totalITPower = 0;

        // Step 1: Calculate heat generated and temperature changes per rack
        for (let i = 0; i < this.racks.length; i++) {
            const rack = this.racks[i];
            const Qi = this.computeRackPower(rack); // kW heat generated
            totalITPower += Qi;

            // Effective cooling airflow temperature received by rack
            const Tcool = this.coolingSupplyTemp + (rack.zone === "B" ? 2.5 : 0.8);

            // Heat dissipated to cooling air: Q_cool = UA * (T_i - T_cool) * (fanSpeed / 100)
            const coolingRate = rack.ua * (rack.fanSpeed / 100.0) * (rack.temp - Tcool);

            // Inter-rack heat exchange with neighbors
            let neighborHeatExchange = 0;
            for (let j = 0; j < this.racks.length; j++) {
                if (i !== j) {
                    const Kij = this.couplingMatrix[i][j];
                    neighborHeatExchange += Kij * (this.racks[j].temp - rack.temp);
                }
            }

            // Ambient environmental leakage
            const ambientLeakage = 0.015 * (this.ambientTemp - rack.temp);

            // Differential temperature change dT/dt
            // C_i * (dT/dt) = Q_i - Q_cool + Q_neighbors + Q_ambient
            const dTdt = (Qi - coolingRate + neighborHeatExchange + ambientLeakage) / rack.thermalCap;

            // Numerical integration (Euler step)
            let nextTemp = rack.temp + dTdt * dt;

            // Bound physical limits
            nextTemp = Math.max(18.0, Math.min(50.0, nextTemp));
            newTemps.push(nextTemp);
        }

        // Apply updated temperatures
        for (let i = 0; i < this.racks.length; i++) {
            this.racks[i].temp = newTemps[i];
            // Inlet is slightly affected by room air mixing
            this.racks[i].inletTemp = this.coolingSupplyTemp + (this.racks[i].temp - this.coolingSupplyTemp) * 0.22;
            // Outlet temp is higher proportional to rack load
            this.racks[i].outletTemp = this.racks[i].temp + (this.computeRackPower(this.racks[i]) * 1.8);
        }

        // Calculate CRAH Cooling Power & PUE
        const totalCoolingPowerKW = (totalITPower / this.chillerCOP) + (this.crahFanPowerKW * (this.crahAirflowCFM / 10000));
        const pue = (totalITPower + totalCoolingPowerKW) / totalITPower;

        // Record history snapshot
        const snapshot = {
            timestamp: new Date().toLocaleTimeString(),
            racks: this.racks.map(r => ({ id: r.id, temp: r.temp, cpuLoad: r.cpuLoad, power: this.computeRackPower(r) })),
            totalITPower: totalITPower,
            coolingPower: totalCoolingPowerKW,
            pue: pue,
            maxTemp: Math.max(...this.racks.map(r => r.temp)),
            avgTemp: this.racks.reduce((a, b) => a + b.temp, 0) / this.racks.length
        };

        this.history.push(snapshot);
        if (this.history.length > this.maxHistoryLength) {
            this.history.shift();
        }

        return snapshot;
    }

    /**
     * Create a clone of the current physics state (used for counterfactual simulations)
     */
    clone() {
        const cloned = new ThermalPhysicsEngine();
        cloned.ambientTemp = this.ambientTemp;
        cloned.coolingSupplyTemp = this.coolingSupplyTemp;
        cloned.crahAirflowCFM = this.crahAirflowCFM;
        cloned.crahFanPowerKW = this.crahFanPowerKW;
        cloned.racks = JSON.parse(JSON.stringify(this.racks));
        return cloned;
    }
}

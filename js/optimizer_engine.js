/**
 * Counterfactual Decision & Multi-Objective Optimization Engine
 * Evaluates candidate cooling/workload interventions inside cloned physics engines.
 * Cost Function: J = w1*E_cooling + w2*T_peak + w3*H_risk + w4*SLA_violations
 */

export class CounterfactualOptimizerEngine {
    constructor() {
        this.weights = {
            coolingEnergy: 0.35,  // w1
            peakTemp: 0.30,       // w2
            hotspotRisk: 0.20,    // w3
            slaViolations: 0.15   // w4
        };
    }

    /**
     * Run counterfactual simulation for a candidate intervention action over N time steps
     */
    evaluateAction(action, basePhysicsEngine, horizonSteps = 15) {
        // Clone physics state for sandbox simulation
        const twinClone = basePhysicsEngine.clone();

        // Apply candidate intervention to the cloned digital twin
        if (action.id === "airflow_boost") {
            twinClone.crahAirflowCFM += 1800; // Boost CRAH fans
            twinClone.crahFanPowerKW += 8.5;
            twinClone.racks.forEach(r => r.fanSpeed = Math.min(100, r.fanSpeed + 15));
        } else if (action.id === "chiller_boost") {
            twinClone.coolingSupplyTemp = Math.max(14.0, twinClone.coolingSupplyTemp - 2.2); // Cool supply air
        } else if (action.id === "workload_migration") {
            // Find hottest rack and coolest rack
            const sortedRacks = [...twinClone.racks].sort((a, b) => b.temp - a.temp);
            const hotRack = sortedRacks[0];
            const coolRack = sortedRacks[sortedRacks.length - 1];

            if (hotRack.cpuLoad > 40) {
                const shiftLoad = Math.min(20, hotRack.cpuLoad - 30);
                hotRack.cpuLoad -= shiftLoad;
                coolRack.cpuLoad += shiftLoad;
            }
        } else if (action.id === "proactive_combined") {
            // Smart combined optimization
            const sortedRacks = [...twinClone.racks].sort((a, b) => b.temp - a.temp);
            const hotRack = sortedRacks[0];
            const coolRack = sortedRacks[sortedRacks.length - 1];

            // 1. Shift load
            if (hotRack.cpuLoad > 40) {
                const shiftLoad = Math.min(18, hotRack.cpuLoad - 30);
                hotRack.cpuLoad -= shiftLoad;
                coolRack.cpuLoad += shiftLoad;
            }
            // 2. Modest targeted fan adjustment
            twinClone.racks.forEach(r => {
                if (r.zone === hotRack.zone) r.fanSpeed = Math.min(100, r.fanSpeed + 8);
            });
            twinClone.coolingSupplyTemp = Math.max(16.5, twinClone.coolingSupplyTemp - 0.8);
        }

        // Simulate N steps into the future in the twin
        let totalCoolingEnergyKWh = 0;
        let peakRecordedTemp = 0;
        let slaViolationTicks = 0;

        for (let t = 0; t < horizonSteps; t++) {
            const snap = twinClone.step(60); // 60s per tick in simulation time
            totalCoolingEnergyKWh += (snap.coolingPower * (60 / 3600));
            peakRecordedTemp = Math.max(peakRecordedTemp, snap.maxTemp);
            if (snap.maxTemp > 33.0) {
                slaViolationTicks++;
            }
        }

        // Calculate hotspot risk percentage
        const finalMaxTemp = Math.max(...twinClone.racks.map(r => r.temp));
        const hotspotRisk = finalMaxTemp >= 33.0 ? Math.min(100, (finalMaxTemp - 32.0) * 40) : Math.max(0, (finalMaxTemp - 30.0) * 15);

        // Multi-objective cost computation (normalized scale)
        const energyCost = totalCoolingEnergyKWh * 2.5;
        const tempCost = Math.max(0, finalMaxTemp - 25.0) * 3.0;
        const riskCost = hotspotRisk * 0.8;
        const slaCost = slaViolationTicks * 15.0;

        const totalCost = (
            this.weights.coolingEnergy * energyCost +
            this.weights.peakTemp * tempCost +
            this.weights.hotspotRisk * riskCost +
            this.weights.slaViolations * slaCost
        );

        return {
            id: action.id,
            title: action.title,
            description: action.description,
            peakTemp: Number(finalMaxTemp.toFixed(1)),
            energyDeltaPercent: Number((((totalCoolingEnergyKWh - 0.25) / 0.25) * 100).toFixed(1)),
            hotspotRiskPercent: Math.round(hotspotRisk),
            slaViolationsCount: slaViolationTicks,
            totalCostScore: Number(totalCost.toFixed(2)),
            simulatedTwinState: twinClone
        };
    }

    /**
     * Compare candidate actions side-by-side for the Counterfactual UI Drawer
     */
    runCounterfactualEvaluation(basePhysicsEngine) {
        const candidateActions = [
            { id: "status_quo", title: "Action A: Status Quo", description: "Maintain current fixed cooling and workload settings." },
            { id: "airflow_boost", title: "Action B: Boost CRAH Fans", description: "Increase cooling fan speed by +15% across Zone B." },
            { id: "chiller_boost", title: "Action C: Lower Supply Temp", description: "Reduce CRAH air supply temperature by -2.2 °C." },
            { id: "workload_migration", title: "Action D: Workload Migration", description: "Redistribute 18% CPU load from Rack 07 to Rack 02." },
            { id: "proactive_combined", title: "Action E: Proactive ML Optimal", description: "Dynamic load balancing + minor targeted cooling boost." }
        ];

        const evaluations = candidateActions.map(action => this.evaluateAction(action, basePhysicsEngine));

        // Sort by lowest cost score (best optimal action)
        evaluations.sort((a, b) => a.totalCostScore - b.totalCostScore);

        return {
            timestamp: new Date().toLocaleTimeString(),
            bestAction: evaluations[0],
            allEvaluations: evaluations
        };
    }
}

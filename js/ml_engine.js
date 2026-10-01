/**
 * Machine Learning Predictive Thermal Engine
 * Simulates real-time multi-horizon thermal forecasting and hotspot risk assessment.
 */

export class MLPredictiveEngine {
    constructor() {
        this.models = {
            "xgboost": { name: "XGBoost Regressor", mae: 0.42, rmse: 0.58, inferenceMs: 4.2, r2: 0.984 },
            "rf": { name: "Random Forest", mae: 0.56, rmse: 0.74, inferenceMs: 12.8, r2: 0.971 },
            "lstm": { name: "LSTM Deep Recurrent", mae: 0.38, rmse: 0.49, inferenceMs: 28.5, r2: 0.989 },
            "linear": { name: "Linear Regression Baseline", mae: 1.15, rmse: 1.62, inferenceMs: 0.8, r2: 0.892 }
        };
        this.selectedModel = "xgboost";
    }

    /**
     * Forecast thermal state for a given rack over 5m, 15m, 30m horizons
     */
    predictRackForecast(rack, physicsEngine) {
        const power = physicsEngine.computeRackPower(rack);
        const cpuLoad = rack.cpuLoad;

        // Rate of thermal change estimate based on load and cooling
        const loadThermalTrend = (cpuLoad - 50) * 0.045; 
        const coolingOffset = (18.0 - physicsEngine.coolingSupplyTemp) * 0.15;
        const ambientOffset = (physicsEngine.ambientTemp - 28.0) * 0.12;

        const baseRate = loadThermalTrend + coolingOffset + ambientOffset;

        // Model noise & precision based on selected model's RMSE
        const rmse = this.models[this.selectedModel].rmse;
        const uncertainty = (rmse / 2) * (Math.random() - 0.5);

        // Calculate predictions for T+5m, T+15m, T+30m
        const temp5m = Number((rack.temp + (baseRate * 0.5) + uncertainty * 0.3).toFixed(1));
        const temp15m = Number((rack.temp + (baseRate * 1.5) + uncertainty * 0.6).toFixed(1));
        const temp30m = Number((rack.temp + (baseRate * 2.8) + uncertainty * 1.0).toFixed(1));

        // Hotspot Risk Threshold > 33.0 °C
        const hotspotThreshold = 33.0;
        let maxPredicted = Math.max(temp5m, temp15m, temp30m);
        
        let riskProb = 0;
        if (maxPredicted >= hotspotThreshold) {
            riskProb = Math.min(99, Math.round(50 + (maxPredicted - hotspotThreshold) * 25));
        } else if (maxPredicted >= 31.0) {
            riskProb = Math.round((maxPredicted - 31.0) * 20);
        }

        return {
            rackId: rack.id,
            rackName: rack.name,
            currentTemp: Number(rack.temp.toFixed(1)),
            forecast5m: Math.max(19.0, temp5m),
            forecast15m: Math.max(19.0, temp15m),
            forecast30m: Math.max(19.0, temp30m),
            hotspotRiskPercent: riskProb,
            isHotspotLikely: riskProb > 60
        };
    }

    /**
     * Generate full datacenter forecast across all racks
     */
    generateDatacenterForecast(physicsEngine) {
        const forecasts = physicsEngine.racks.map(rack => this.predictRackForecast(rack, physicsEngine));
        
        const highestRiskRack = forecasts.reduce((prev, current) => 
            (prev.hotspotRiskPercent > current.hotspotRiskPercent) ? prev : current
        );

        return {
            timestamp: new Date().toLocaleTimeString(),
            selectedModel: this.models[this.selectedModel],
            rackForecasts: forecasts,
            datacenterHotspotRisk: highestRiskRack.hotspotRiskPercent,
            highestRiskRack: highestRiskRack,
            hotspotCount: forecasts.filter(f => f.isHotspotLikely).length
        };
    }
}

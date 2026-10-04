"""
Model parameters for the data center digital twin.

Every physical constant, default and threshold used by the twin lives here so
that the simulation, the forecasting dataset, the optimizer, the baselines and
the documentation (docs/MODEL_PARAMETERS.md) all use the same values.
"""

# ── Air properties ────────────────────────────────────────────────────────────
AIR_DENSITY = 1.20            # kg/m3 at about 20 C, sea level
AIR_CP = 1.006                # kJ/(kg K)
RHO_CP_AIR = AIR_DENSITY * AIR_CP   # kJ/(m3 K), heat carried per m3 of air per kelvin
M3S_TO_CFM = 2118.88          # 1 m3/s expressed in cubic feet per minute

# ── Thermal limits (ASHRAE TC 9.9 class A1, rack inlet air) ─────────────────
RECOMMENDED_INLET_LIMIT_C = 27.0
ALLOWABLE_INLET_LIMIT_C = 32.0
DEFAULT_INLET_LIMIT_C = RECOMMENDED_INLET_LIMIT_C

# ── Simulation timing ────────────────────────────────────────────────────────
PHYSICS_DT_S = 1.0            # fixed internal physics step; identical at every speed
FORECAST_INTERVAL_S = 30      # ML forecasts are produced every 30 simulated seconds
SERIES_INTERVAL_S = 5         # chart samples are stored every 5 simulated seconds
TUNER_INTERVAL_S = 300        # predictive setpoint/airflow tuning every 5 minutes
FORECAST_HORIZONS_MIN = [5, 10, 15, 30, 60]
ALERT_HORIZON_MIN = 15        # a hotspot alert fires when a breach is forecast within 15 min
ALERT_COOLDOWN_S = 600        # after an alert pop-up, 10 simulated minutes without another pop-up (risks are handled automatically)
ALERT_RELATCH_S = 1800        # a rack that stays hot may raise a new alert after 30 minutes
ALERT_CLEAR_MARGIN_K = 0.5    # a rack is re-armed once its inlet is this far below the limit and no breach is forecast
SNOOZE_S = 300                # Snooze suppresses hotspot alerts for 5 minutes (wall clock)
EVENT_MERGE_WINDOW_S = 30     # events of the same type within 30 s are grouped

# ── Rack types ───────────────────────────────────────────────────────────────
# pmax_kw: rack IT power at 100 % utilization for the Medium scale.
# idle_fraction: share of pmax drawn at 0 % utilization (servers idle at 30-40 %).
# base_util: mean utilization in normal operation (percent).
RACK_TYPES = {
    "web":     {"label": "Web servers",        "pmax_kw": 7.0,  "idle_fraction": 0.35, "base_util": 45},
    "db":      {"label": "Database",           "pmax_kw": 8.0,  "idle_fraction": 0.40, "base_util": 55},
    "cache":   {"label": "Cache cluster",      "pmax_kw": 6.0,  "idle_fraction": 0.40, "base_util": 50},
    "compute": {"label": "Analytics compute",  "pmax_kw": 9.0,  "idle_fraction": 0.30, "base_util": 58},
    "gpu":     {"label": "GPU training",       "pmax_kw": 14.0, "idle_fraction": 0.25, "base_util": 62},
    "infer":   {"label": "AI inference",       "pmax_kw": 12.0, "idle_fraction": 0.30, "base_util": 60},
    "storage": {"label": "Storage",            "pmax_kw": 5.0,  "idle_fraction": 0.55, "base_util": 40},
}

# Physical layout: racks fill two rows (zone A, zone B) facing one cold aisle.
RACK_LAYOUT = ["web", "db", "cache", "compute", "gpu", "gpu", "infer", "storage",
               "web", "db", "infer", "storage"]

SCALE_DENSITY = {"small": 0.7, "medium": 1.0, "large": 1.35}

# ── Server airflow ───────────────────────────────────────────────────────────
SERVER_TARGET_DELTA_T = 11.0      # K, server fans aim for this inlet-to-exhaust rise
SERVER_DESIGN_DELTA_T = 12.0      # K, defines maximum fan airflow at pmax
SERVER_MIN_FLOW_FRACTION = 0.35   # fans never drop below 35 % of design airflow
RACK_THERMAL_MASS_KJ_K = 60.0     # heat capacity of servers and chassis per rack
COLD_AISLE_TAU_S = 30.0           # mixing time constant of cold-aisle air at the inlet

# ── Recirculation (hot exhaust mixing into rack inlets) ─────────────────────
RECIRC_BASE_MIDDLE = 0.04         # share of inlet air that is recirculated exhaust, mid-row
RECIRC_BASE_END = 0.08            # end-of-row racks see more recirculation
RECIRC_STARVATION_GAIN = 0.9      # extra recirculation per unit of airflow deficit
ZONE_SUPPLY_OFFSET_C = {"A": 0.0, "B": 0.5}   # zone B is farther from the CRAH units

# ── Cooling plant (water-cooled chiller with cooling tower) ──────────────────
CRAH_DESIGN_OVERSUPPLY = 1.15     # CRAH design airflow = 1.15 x server airflow at pmax
CRAH_FAN_SFP_KW_PER_M3S = 0.8     # CRAH fan power at design airflow, per m3/s
PLANT_CAPACITY_FACTOR = 1.0       # chiller capacity = 1.0 x design IT power at reference wet-bulb
CAPACITY_REF_WET_BULB_C = 24.0
CAPACITY_DERATE_PER_K = 0.03      # capacity loss per K of wet-bulb above the reference
SUPPLY_TAU_S = 120.0              # supply-air control response when capacity is available
SUPPLY_THERMAL_MASS_KJ_K_PER_RACK = 400.0  # air, coils and chilled-water loop mass that heats up during a cooling deficit
CHW_APPROACH_K = 6.0              # chilled water is 6 K colder than the supply-air setpoint
TOWER_APPROACH_K = 4.0            # condenser water leaves the tower 4 K above wet-bulb
CONDENSER_APPROACH_K = 4.0        # refrigerant condenses 4 K above condenser water
CHILLER_CARNOT_EFFICIENCY = 0.25  # fraction of Carnot COP achieved
COP_MIN, COP_MAX = 2.0, 9.0
FREE_COOLING_BAND_K = 4.0         # waterside economizer ramps over 4 K
PUMP_DESIGN_FRACTION = 0.03       # pump power at design load = 3 % of design cooling capacity
TOWER_FAN_FRACTION = 0.008        # tower fan power = 0.8 % of heat rejected
ENVELOPE_UA_KW_K_PER_RACK = 0.015 # building envelope conductance per rack

DEFAULT_SUPPLY_SETPOINT_C = 20.0
SETPOINT_MIN_C, SETPOINT_MAX_C = 16.0, 24.0
DEFAULT_CRAH_FRACTION = 0.85      # share of CRAH design airflow
CRAH_FRACTION_MIN, CRAH_FRACTION_MAX = 0.45, 1.2

# ── Water ────────────────────────────────────────────────────────────────────
LATENT_HEAT_KJ_KG = 2430.0        # evaporation enthalpy of water at about 30 C
CYCLES_OF_CONCENTRATION = 4.0     # blowdown = evaporation / (cycles - 1)

def evaporative_fraction(wet_bulb_c: float) -> float:
    """Share of rejected heat removed by evaporation in the cooling tower.
    Rises with wet-bulb because warmer air accepts less sensible heat."""
    return max(0.60, min(0.95, 0.60 + 0.01 * wet_bulb_c))

# ── Economics and carbon (configurable at run setup) ─────────────────────────
DEFAULT_GRID_FACTOR_KG_PER_KWH = 0.716   # India grid weighted average, CEA CO2 Baseline Database v19 (FY 2022-23)
DEFAULT_ELECTRICITY_INR_PER_KWH = 8.0    # typical Indian commercial/industrial tariff
DEFAULT_WATER_INR_PER_KL = 60.0          # typical Indian industrial water tariff per 1000 L

# ── Control policies ─────────────────────────────────────────────────────────
FIXED_POLICY = {"setpoint": 18.0, "crah": 1.0}
REACTIVE_POLICY = {"setpoint": 21.0, "crah": 0.85, "boost_setpoint": 17.0, "boost_crah": 1.1,
                   "trigger_margin_k": 1.0, "release_margin_k": 3.0, "release_hold_s": 300}
PREDICTIVE_SAFETY_MARGIN_K = 2.0  # tuner keeps forecast peak inlet this far below the limit
TUNER_HORIZON_S = 1200
BRANCH_HORIZON_S = 1800           # counterfactual branches look 30 minutes ahead
BRANCH_DT_S = 5.0
ACTION_HOLD_S = 600               # tuner leaves an applied hotspot action alone for 10 minutes

DEFAULT_COST_WEIGHTS = {"energy": 1.0, "temperature": 1.0, "disruption": 1.0}

DECISION_TIMEOUT_S = 30           # wall-clock seconds the operator has to choose a solution

# Model parameters

All values are defined in `backend/model_params.py` and used by the live twin, the training
dataset, the optimizer, the baselines and the benchmark. They are typical engineering values
for a small air-cooled data hall, not measurements from a specific facility; calibrate them
against real telemetry before using the twin for a real building.

## Limits (rack INLET air, ASHRAE TC 9.9 class A1)

| Parameter | Value | Use |
|---|---|---|
| Recommended inlet limit | 27 C | Default limit for alerts, forecasts, violations, optimizer constraints, results |
| Allowable inlet limit | 32 C | Critical alerts; can be chosen as the limit at setup |

Every alert, forecast, violation count and optimizer constraint uses the rack **inlet**
temperature against this one configurable limit. Exhaust temperature is shown separately.

## Time

| Parameter | Value |
|---|---|
| Physics step | 1 s (identical at 1x, 25x, Skip to End, baselines and replays) |
| Forecast interval | 30 s |
| Chart sample interval | 5 s |
| Predictive tuner interval | 300 s |
| Forecast horizons | 5, 10, 15, 30, 60 min |
| Hotspot alert horizon | 15 min |
| Alert cooldown per rack | 600 s |
| Event grouping window | 30 s |
| Operator decision timeout | 30 s (wall clock) |

## Racks

Rack power: `P = Pmax x (idle + (1 - idle) x utilization)`, plus any heat pulse; an optional power cap limits it.

| Type | Pmax (kW, Medium) | Idle share | Mean utilization |
|---|---|---|---|
| Web servers | 7.0 | 0.35 | 45 % |
| Database | 8.0 | 0.40 | 55 % |
| Cache cluster | 6.0 | 0.40 | 50 % |
| Analytics compute | 9.0 | 0.30 | 58 % |
| GPU training | 14.0 | 0.25 | 62 % |
| AI inference | 12.0 | 0.30 | 60 % |
| Storage | 5.0 | 0.55 | 40 % |

Layout repeats: web, db, cache, compute, gpu, gpu, infer, storage, web, db, infer, storage.
Racks fill two rows: zone A (first half) and zone B (second half).
Scale multiplies Pmax: Small 0.7, Medium 1.0, Large 1.35.

Workload: per-rack Ornstein-Uhlenbeck process (time constant 300 s, stationary spread 6 points)
around the mean plus a +-8 point drift with a 90 minute period. Seeded.

## Air path

| Parameter | Value | Meaning |
|---|---|---|
| rho cp of air | 1.207 kJ/(m3 K) | 1.20 kg/m3 x 1.006 kJ/(kg K) |
| Server target rise | 11 K | Fans aim for this inlet-to-exhaust rise |
| Server design rise | 12 K | Defines maximum fan airflow at Pmax |
| Minimum fan airflow | 35 % of design | |
| Rack thermal mass | 60 kJ/K | Servers and chassis; exhaust time constant 1 to 2 min |
| Cold-aisle mixing time constant | 30 s | Inlet response |
| Recirculation, mid-row | 4 % | Share of inlet air that is recirculated exhaust |
| Recirculation, row end | 8 % | |
| Starvation gain | 0.9 | Extra recirculation per unit of CRAH airflow shortfall |
| Zone supply offset | A: 0 K, B: +0.5 K | Zone B is farther from the CRAH units |

Equations, per rack i, every second:

```
inlet_target_i = (1 - r_i) x (supply + zone offset) + r_i x hot_aisle_i + inlet disturbance
d(inlet_i)/dt = (inlet_target_i - inlet_i) / 30 s
60 kJ/K x d(exhaust_i)/dt = P_i - rho cp x Q_i x (exhaust_i - inlet_i)
hot_aisle_i = 0.6 x exhaust_i + 0.4 x mean(exhaust of row neighbours)
r_i = base_i x clamp(2 - ratio, 0.5, 1)                 if CRAH airflow >= server demand
r_i = base_i + (1 - ratio) x weight_i x 0.9             otherwise (weight 0.7 to 1.3 along the row)
```

## Cooling plant (water-cooled chiller, cooling tower, CRAH units)

| Parameter | Value |
|---|---|
| CRAH design airflow | 1.15 x server airflow at Pmax |
| CRAH fan power | 0.8 kW per m3/s at design, cube law |
| Plant capacity | 1.0 x design IT power at 24 C wet-bulb |
| Capacity derate | 3 % per K of wet-bulb above 24 C |
| Supply-air thermal mass | 400 kJ/K per rack (air, coils, chilled-water loop) |
| Supply-air control time constant | 120 s |
| Chilled water approach | 6 K below supply-air setpoint |
| Tower approach / condenser approach | 4 K / 4 K |
| Chiller efficiency | 0.25 x Carnot COP, limited to 2 to 9 |
| Free cooling | Ramps from 0 to 100 % over 4 K once tower water is colder than chilled water |
| Pump power | 3 % of design capacity x (load ratio) squared, minimum 25 % load |
| Tower fan power | 0.8 % of heat rejected |
| Envelope conductance | 0.015 kW/K per rack |
| Default supply setpoint | 20 C (tuner range 16 to 24 C) |
| Default CRAH airflow | 85 % of design (range 45 to 120 %) |

```
capacity = design x plant_avail x (free + (1 - free) x chiller_avail x derate(wet-bulb))
if load > capacity:  400 kJ/K x racks x d(supply)/dt = load - capacity
else:                supply returns to the setpoint with a 120 s time constant
COP = 0.25 x T_evap / (T_cond - T_evap), T_evap = setpoint - 6 K, T_cond = wet-bulb + 8 K
chiller power = mechanical heat removed / COP
```

## Water, carbon, cost

```
evaporation (kg) = heat rejected (kJ) x f_evap / 2430 kJ/kg,  f_evap = clamp(0.60 + 0.01 x wet-bulb, 0.60, 0.95)
blowdown = evaporation / (cycles of concentration - 1),  cycles = 4,  1 kg = 1 L
WUE = water (L) / IT energy (kWh)
carbon = total energy x grid factor
cost = total energy x electricity price + water (kL) x water price
```

| Parameter | Default | Source |
|---|---|---|
| Grid emission factor | 0.716 kg CO2/kWh | India grid weighted average, CEA CO2 Baseline Database for the Indian Power Sector (version 19, FY 2022-23). Check the latest CEA release; configurable at setup. |
| Electricity price | INR 8.0 per kWh | Typical Indian commercial and industrial tariff; configurable. |
| Water price | INR 60 per 1000 L | Typical Indian industrial water tariff; configurable. |

## Control policies

| Policy | Behaviour |
|---|---|
| Fixed cooling | Supply 18 C, CRAH 100 %, never changes |
| Reactive threshold | Supply 21 C, CRAH 85 %; boost to 17 C / 110 % when any inlet reaches limit - 1 K; release after 5 min at limit - 3 K |
| Predictive (this project) | ML forecasts every 30 s; hotspot decisions in cloned twins; tuner every 5 min picks the lowest-energy setpoint and airflow whose 20 minute forecast peak stays 2 K below the limit |

## Hotspot decisions

Options: no action, boost CRAH airflow (+20 points), lower setpoint (-2 C), migrate up to 25
utilization points from the hottest rack to the coolest racks with headroom (operator-set
racks are never touched), cap the hottest rack at 85 % of its power for 15 minutes, and a
combined response (+10 points airflow, -1 C, migrate 15 points). Each option is simulated
30 minutes ahead (5 s steps) in a cloned twin with current conditions held constant.

```
safe = forecast peak inlet <= limit
cost = w_energy x energy change vs no action (%) + w_temperature x 10 x max(0, peak - (limit - 2 K)) + w_disruption x disruption
disruption = 0.05 per utilization point migrated + 2 per kW capped
```

## Events

| Event | Duration | Effect |
|---|---|---|
| Cooling failure | 10 min | Chiller off for 8 min, restarts over 2 min |
| Power loss | 7 min | Whole plant and CRAH fans off for 20 s; chillers locked out 5 min, restart over 2 min |
| Heatwave | 40 min | Outside temperature up to +8 C (10 min ramp) |
| Workload spike | 15 min | +35 points on GPU, inference and compute racks, +10 elsewhere |
| Flood | 20 min | CRAH airflow 50 %, chiller availability 60 % |
| Wildfire smoke | 30 min | CRAH airflow 80 %, no free cooling, outside +3 C |
| Earthquake | 15 min | Zone B racks off 3 min then 100 % for 6 min; chiller availability 50 % for 10 min |
| Cyclone | 40 min | Humidity 95 %, outside -3 C, CRAH 85 %, two 90 s chiller trips |
| Containment breach | 20 min | +25 % recirculation on racks 03 and 04 |
| CRAH fan degradation | 25 min | CRAH airflow 60 % |
| Rack overload | 15 min | Rack 05 at 100 % plus 2 kW of extra heat |

Events change availabilities, weather and workload while active and never overwrite
optimizer actions or operator changes.

## Climates

| Climate | Mean | Daily swing | RH |
|---|---|---|---|
| Temperate | 24 C | +-4 C | 60 % |
| Coastal monsoon | 30 C | +-3 C | 80 % |
| Hot desert | 38 C | +-7 C | 18 % |
| Nordic cold | 4 C | +-3 C | 75 % |
| Extreme humid heat | 38 C | +-4 C | 55 % |

Runs start at 12:00; the daily cycle peaks at 15:00; a seeded random walk adds about 0.6 C of variation.
Wet-bulb uses Stull's (2011) formula.

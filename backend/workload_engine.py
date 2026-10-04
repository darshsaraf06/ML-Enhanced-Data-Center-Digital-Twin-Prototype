"""
Workload engine: seeded rack utilization.

Each rack follows a mean-reverting random process (Ornstein-Uhlenbeck, time constant
5 minutes, stationary spread about 6 points) around a slowly drifting mean
(+-8 points over a 90 minute cycle). Event deltas, workload migrations and operator
overrides are layered on top without changing the random stream, so two runs with
the same seed see the same background workload whatever the control actions are.
"""

import math
from typing import Dict, Optional

import numpy as np

THETA = 1.0 / 300.0
SIGMA = 6.0 * math.sqrt(2.0 * THETA)     # gives a stationary std of 6 points
DRIFT_AMPLITUDE = 8.0
DRIFT_PERIOD_S = 5400.0


class WorkloadEngine:
    def __init__(self, racks, seed: int = 42, level: float = 1.0):
        self.rng = np.random.default_rng(seed)
        self.n = len(racks)
        self.base = np.array([r["baseUtil"] for r in racks], dtype=float) * level
        self.phase = self.rng.uniform(0, 2 * math.pi, size=self.n)
        self.x = np.zeros(self.n)                 # random deviation (points)
        self.offsets: Dict[int, float] = {}       # rack id -> migration offset (optimizer)
        self.overrides: Dict[int, float] = {}     # rack id -> operator-set utilization

    def step(self, t: float, dt: float = 1.0):
        noise = self.rng.standard_normal(self.n)
        self.x += -THETA * self.x * dt + SIGMA * math.sqrt(dt) * noise

    def utilization(self, t: float, rack_id: int, event_delta: float = 0.0,
                    event_set: Optional[float] = None) -> float:
        i = rack_id - 1
        if event_set is not None:
            return float(max(0.0, min(100.0, event_set)))
        if rack_id in self.overrides:
            value = self.overrides[rack_id]
        else:
            drift = DRIFT_AMPLITUDE * math.sin(2 * math.pi * t / DRIFT_PERIOD_S + self.phase[i])
            value = self.base[i] + drift + self.x[i]
        value += self.offsets.get(rack_id, 0.0) + event_delta
        return float(max(0.0, min(100.0, value)))

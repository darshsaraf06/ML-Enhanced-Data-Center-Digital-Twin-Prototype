"""
Global Simulation State Wrapper.
Exposes the central simulation engine singleton to FastAPI routers and WebSocket managers.
"""

from simulation_engine import engine, CentralSimulationEngine


class SimulationState:
    """Compatibility bridge connecting to the CentralSimulationEngine."""

    def __init__(self):
        self.engine = engine

    # Expose underlying modules
    @property
    def physics(self):
        return self.engine.twin

    @property
    def ml(self):
        return self.engine.forecasting

    @property
    def optimizer(self):
        return self.engine.optimizer

    @property
    def benchmark(self):
        return self.engine.benchmarks

    @property
    def weather(self):
        return self.engine.weather

    @property
    def scenarios(self):
        return self.engine.scenarios

    @property
    def energy(self):
        return self.engine.energy

    @property
    def alerts(self):
        return self.engine.alerts

    @property
    def what_if(self):
        return self.engine.what_if

    async def tick(self, n: int = 1):
        for _ in range(n):
            await self.engine.step()
        return self.engine.twin.history[-1] if self.engine.twin.history else {}

    def full_state(self) -> dict:
        return self.engine.to_dict()


sim = SimulationState()

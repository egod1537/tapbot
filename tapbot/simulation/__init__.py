"""Hardware-free robot and camera simulation integration."""

from tapbot.simulation.bridge import (
    CoordinateMapper,
    IdentityCoordinateMapper,
    SimulationBridge,
)
from tapbot.simulation.runner import (
    MockGraphVision,
    SimulationConfig,
    SimulationFailure,
    SimulationFinishedError,
    SimulationOutcome,
    SimulationReplayResult,
    SimulationRunner,
    SimulationStepTrace,
    SimulationTrace,
    SimulationTraceError,
    SimulationVision,
)

__all__ = [
    "CoordinateMapper",
    "IdentityCoordinateMapper",
    "MockGraphVision",
    "SimulationBridge",
    "SimulationConfig",
    "SimulationFailure",
    "SimulationFinishedError",
    "SimulationOutcome",
    "SimulationReplayResult",
    "SimulationRunner",
    "SimulationStepTrace",
    "SimulationTrace",
    "SimulationTraceError",
    "SimulationVision",
]

"""Injected backend contracts.

The wrapper deliberately contains no vendor SDK and does not reach through a
controller's private ``backend`` attribute. Hardware packages implement these
small public protocols and remain independently pinned by Prometheus.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class HandObservation:
    grasp_closure: float
    motor_closure: Mapping[str, float]


class SO101ArmBackend(Protocol):
    @property
    def is_connected(self) -> bool: ...

    @property
    def is_calibrated(self) -> bool: ...

    def offline_validate_calibration(self, robot_id: str) -> None:
        """Validate files and identity attestations without device I/O."""

    def connect_torque_off(self) -> None: ...

    def latch_current_position(self) -> None: ...

    def enable_torque(self) -> None: ...

    def get_observation(self) -> Mapping[str, object]: ...

    def send_positions(self, action: Mapping[str, float]) -> Mapping[str, float]: ...

    def emergency_stop(self, reason: str) -> None: ...

    def disconnect(self) -> None: ...


class AmazingHandBackend(Protocol):
    @property
    def is_connected(self) -> bool: ...

    @property
    def is_calibrated(self) -> bool: ...

    @property
    def is_active(self) -> bool: ...

    def offline_validate_calibration(self, robot_id: str, side: str) -> None:
        """Validate files, schema, and public latch capability without I/O."""

    def connect_torque_off(self) -> None: ...

    def latch_current_position(self) -> None: ...

    def activate(self) -> None: ...

    def observe(self) -> HandObservation: ...

    def command_grasp(self, value: float) -> None: ...

    def emergency_stop(self, reason: str) -> None: ...

    def disconnect(self) -> None: ...


class XLerobotBodyBackend(Protocol):
    @property
    def is_connected(self) -> bool: ...

    @property
    def is_calibrated(self) -> bool: ...

    def offline_validate_calibration(self, robot_id: str) -> None:
        """Validate the body calibration without device I/O."""

    def connect_torque_off(self) -> None: ...

    def latch_current_positions(self) -> None: ...

    def stop_base(self) -> None: ...

    def enable_torque(self) -> None: ...

    def get_observation(self) -> Mapping[str, object]: ...

    def send_action(self, action: Mapping[str, float]) -> Mapping[str, float]: ...

    def emergency_stop(self, reason: str) -> None: ...

    def disconnect(self) -> None: ...

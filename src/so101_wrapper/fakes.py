"""Deterministic no-device backends for CI, integration tests, and ``doctor``."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from .protocols import HandObservation
from .schema import ARM_POSITION_KEYS, SINGLE_ARM_POSITION_KEYS


@dataclass
class FakeSO101Arm:
    events: list[str] = field(default_factory=list)
    fail_at: str | None = None
    calibrated: bool = True
    connected: bool = False
    active: bool = False
    positions: dict[str, float] = field(default_factory=lambda: dict.fromkeys(SINGLE_ARM_POSITION_KEYS, 0.0))

    @property
    def is_connected(self) -> bool:
        return self.connected

    @property
    def is_calibrated(self) -> bool:
        return self.calibrated

    def _event(self, name: str) -> None:
        self.events.append(name)
        if self.fail_at == name:
            raise RuntimeError(f"injected failure at {name}")

    def offline_validate_calibration(self, robot_id: str) -> None:
        self._event("arm.preflight")
        if not self.calibrated:
            raise RuntimeError(f"missing arm calibration for {robot_id}")

    def connect_torque_off(self) -> None:
        self._event("arm.connect_torque_off")
        self.connected = True
        self.active = False

    def latch_current_position(self) -> None:
        self._event("arm.latch")

    def enable_torque(self) -> None:
        self._event("arm.enable")
        self.active = True

    def get_observation(self) -> Mapping[str, object]:
        self._event("arm.observe")
        return dict(self.positions)

    def send_positions(self, action: Mapping[str, float]) -> Mapping[str, float]:
        self._event("arm.command")
        self.positions.update(action)
        return dict(action)

    def emergency_stop(self, reason: str) -> None:
        self.events.append(f"arm.stop:{reason}")
        self.active = False

    def disconnect(self) -> None:
        self.events.append("arm.disconnect")
        self.active = False
        self.connected = False


@dataclass
class FakeAmazingHand:
    side: str
    events: list[str] = field(default_factory=list)
    fail_at: str | None = None
    calibrated: bool = True
    connected: bool = False
    active: bool = False
    grasp: float = 0.0

    @property
    def is_connected(self) -> bool:
        return self.connected

    @property
    def is_calibrated(self) -> bool:
        return self.calibrated

    @property
    def is_active(self) -> bool:
        return self.active

    def _event(self, name: str) -> None:
        label = f"{self.side}_hand.{name}"
        self.events.append(label)
        if self.fail_at == name or self.fail_at == label:
            raise RuntimeError(f"injected failure at {label}")

    def offline_validate_calibration(self, robot_id: str, side: str) -> None:
        self._event("preflight")
        if side != self.side and self.side != "single":
            raise RuntimeError(f"hand side mismatch: backend={self.side}, requested={side}")
        if not self.calibrated:
            raise RuntimeError(f"missing {side} hand calibration for {robot_id}")

    def connect_torque_off(self) -> None:
        self._event("connect_torque_off")
        self.connected = True
        self.active = False

    def latch_current_position(self) -> None:
        self._event("latch")

    def activate(self) -> None:
        self._event("activate")
        self.active = True

    def observe(self) -> HandObservation:
        self._event("observe")
        return HandObservation(
            grasp_closure=self.grasp,
            motor_closure={f"motor_{index}": self.grasp for index in range(1, 9)},
        )

    def command_grasp(self, value: float) -> None:
        self._event("command")
        self.grasp = value

    def emergency_stop(self, reason: str) -> None:
        self.events.append(f"{self.side}_hand.stop:{reason}")
        self.active = False

    def disconnect(self) -> None:
        self.events.append(f"{self.side}_hand.disconnect")
        self.active = False
        self.connected = False


@dataclass
class FakeXLerobotBody:
    events: list[str] = field(default_factory=list)
    fail_at: str | None = None
    calibrated: bool = True
    connected: bool = False
    active: bool = False
    positions: dict[str, float] = field(default_factory=lambda: dict.fromkeys(ARM_POSITION_KEYS, 0.0))
    base_velocity: dict[str, float] = field(
        default_factory=lambda: {"x.vel": 0.0, "y.vel": 0.0, "theta.vel": 0.0}
    )

    @property
    def is_connected(self) -> bool:
        return self.connected

    @property
    def is_calibrated(self) -> bool:
        return self.calibrated

    def _event(self, name: str) -> None:
        self.events.append(name)
        if self.fail_at == name:
            raise RuntimeError(f"injected failure at {name}")

    def offline_validate_calibration(self, robot_id: str) -> None:
        self._event("body.preflight")
        if not self.calibrated:
            raise RuntimeError(f"missing body calibration for {robot_id}")

    def connect_torque_off(self) -> None:
        self._event("body.connect_torque_off")
        self.connected = True
        self.active = False

    def latch_current_positions(self) -> None:
        self._event("body.latch")

    def stop_base(self) -> None:
        self._event("body.stop_base")
        self.base_velocity = dict.fromkeys(self.base_velocity, 0.0)

    def enable_torque(self) -> None:
        self._event("body.enable")
        self.active = True

    def get_observation(self) -> Mapping[str, object]:
        self._event("body.observe")
        return {**self.positions, **self.base_velocity, "head_pan.pos": 0.0, "head_tilt.pos": 0.0}

    def send_action(self, action: Mapping[str, float]) -> Mapping[str, float]:
        self._event("body.command")
        self.positions.update({key: value for key, value in action.items() if key in self.positions})
        self.base_velocity.update({key: value for key, value in action.items() if key in self.base_velocity})
        return dict(action)

    def emergency_stop(self, reason: str) -> None:
        self.events.append(f"body.stop:{reason}")
        self.active = False
        self.base_velocity = dict.fromkeys(self.base_velocity, 0.0)

    def disconnect(self) -> None:
        self.events.append("body.disconnect")
        self.active = False
        self.connected = False

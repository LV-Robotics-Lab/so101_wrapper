"""Public-API-only adapter for ``amazinghand_wrapper``."""

from __future__ import annotations

from typing import Any

from ..config import AmazingHandAttachmentConfig
from ..protocols import HandObservation


class UnsupportedAmazingHandAPI(RuntimeError):
    pass


class AmazingHandControllerAdapter:
    """Adapt an AmazingHand controller without reaching into ``controller.backend``.

    The validated ``amazinghand_wrapper`` commit exposes the required public
    goal-latching method. ``offline_validate_calibration`` still checks the
    capability before the serial port is opened so an old or mismatched checkout
    fails closed instead of falling back to private backend access.
    """

    def __init__(self, controller: Any, config: AmazingHandAttachmentConfig) -> None:
        self.controller = controller
        self.config = config

    @property
    def is_connected(self) -> bool:
        return bool(self.controller.is_connected)

    @property
    def is_calibrated(self) -> bool:
        return bool(self.controller.is_calibrated)

    @property
    def is_active(self) -> bool:
        return bool(self.controller.is_active)

    def offline_validate_calibration(self, robot_id: str, side: str) -> None:
        if not self.config.calibration_file.is_file():
            raise RuntimeError(
                f"{side} AmazingHand calibration for {robot_id!r} is missing: {self.config.calibration_file}"
            )
        calibration = getattr(self.controller, "calibration", None)
        schema = getattr(calibration, "schema", None)
        if schema != self.config.expected_calibration_schema:
            raise RuntimeError(
                f"{side} AmazingHand calibration has unsupported schema {schema!r}; "
                f"expected {self.config.expected_calibration_schema!r}"
            )
        if not callable(getattr(self.controller, "latch_current_position", None)):
            raise UnsupportedAmazingHandAPI(
                "amazinghand_wrapper must expose public latch_current_position(); "
                "private controller.backend access is forbidden"
            )

    def connect_torque_off(self) -> None:
        self.controller.connect()

    def latch_current_position(self) -> None:
        self.controller.latch_current_position()

    def activate(self) -> None:
        self.controller.activate()

    def observe(self) -> HandObservation:
        sample = self.controller.observe()
        return HandObservation(
            grasp_closure=float(sample.grasp_closure),
            motor_closure=dict(sample.motor_closure),
        )

    def command_grasp(self, value: float) -> None:
        self.controller.command_grasp(value)

    def emergency_stop(self, reason: str) -> None:
        if self.is_connected or self.is_active:
            self.controller.emergency_stop(reason)

    def disconnect(self) -> None:
        self.controller.disconnect()

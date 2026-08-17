"""Safe lifecycle adapter for an explicitly loaded upstream XLeRobot object."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path
from typing import Any


class LeRobotXLerobotBodyAdapter:
    """Wrap XLeRobot while bypassing its interactive/early-torque ``connect``.

    This adapter is intentionally initialized with an already constructed upstream
    object. Source loading belongs to :mod:`so101_wrapper.source`, where the checkout
    path and full Git SHA are verified before import.
    """

    def __init__(self, robot: Any) -> None:
        self.robot = robot
        self._calibrations: tuple[dict[str, Any], dict[str, Any]] | None = None
        self._remove_stock_grippers()

    @property
    def is_connected(self) -> bool:
        return bool(
            self.robot.bus1.is_connected
            and self.robot.bus2.is_connected
            and all(camera.is_connected for camera in self.robot.cameras.values())
        )

    @property
    def is_calibrated(self) -> bool:
        descriptor = getattr(type(self.robot), "is_calibrated", None)
        if isinstance(descriptor, property):
            return bool(descriptor.fget(self.robot))
        return bool(self.robot.is_calibrated)

    def _remove_stock_grippers(self) -> None:
        for bus, name in (
            (self.robot.bus1, "left_arm_gripper"),
            (self.robot.bus2, "right_arm_gripper"),
        ):
            bus.motors.pop(name, None)
            bus.calibration.pop(name, None)
            self.robot.calibration.pop(name, None)
        self.robot.left_arm_motors = [
            name for name in self.robot.left_arm_motors if name != "left_arm_gripper"
        ]
        self.robot.right_arm_motors = [
            name for name in self.robot.right_arm_motors if name != "right_arm_gripper"
        ]

    def offline_validate_calibration(self, robot_id: str) -> None:
        if not robot_id:
            raise RuntimeError("XLeRobot requires an explicit robot id")
        expected_path = Path(self.robot.calibration_dir) / f"{robot_id}.json"
        actual_path = Path(self.robot.calibration_fpath)
        if actual_path != expected_path or not expected_path.is_file():
            raise RuntimeError(f"body calibration is missing: {expected_path}")

        calibrations: list[dict[str, Any]] = []
        for label, bus in (("left/head", self.robot.bus1), ("right/base", self.robot.bus2)):
            missing = sorted(set(bus.motors) - set(self.robot.calibration))
            if missing:
                raise RuntimeError(f"body calibration is missing {label} motors: {missing}")
            mismatched = {
                name: (self.robot.calibration[name].id, motor.id)
                for name, motor in bus.motors.items()
                if self.robot.calibration[name].id != motor.id
            }
            if mismatched:
                raise RuntimeError(f"body calibration motor IDs do not match: {mismatched}")
            calibrations.append({name: self.robot.calibration[name] for name in bus.motors})
        self._calibrations = (calibrations[0], calibrations[1])

    def connect_torque_off(self) -> None:
        if self._calibrations is None:
            raise RuntimeError("run offline_validate_calibration before opening XLeRobot buses")
        try:
            self.robot.bus1.connect()
            self.robot.bus1.disable_torque()
            self.robot.bus2.connect()
            self.robot.bus2.disable_torque()
            for camera in self.robot.cameras.values():
                camera.connect()
            for bus, calibration in zip(
                (self.robot.bus1, self.robot.bus2),
                self._calibrations,
                strict=True,
            ):
                bus.calibration = calibration
                bus.write_calibration(calibration)
            if not self.is_calibrated:
                raise RuntimeError("XLeRobot calibration restore did not verify")
            self._configure_torque_off()
        except Exception:
            self.emergency_stop("body connect failure")
            self.disconnect()
            raise

    def _configure_torque_off(self) -> None:
        try:
            from lerobot.motors.feetech import OperatingMode
        except ImportError as error:
            raise ImportError("the pinned LeRobot package is required for XLeRobot") from error
        for bus in (self.robot.bus1, self.robot.bus2):
            bus.disable_torque()
            bus.configure_motors()
        for bus, motors in (
            (self.robot.bus1, self.robot.left_arm_motors),
            (self.robot.bus1, self.robot.head_motors),
            (self.robot.bus2, self.robot.right_arm_motors),
        ):
            for name in motors:
                bus.write("Operating_Mode", name, OperatingMode.POSITION.value)
                bus.write("P_Coefficient", name, 16)
                bus.write("I_Coefficient", name, 0)
                bus.write("D_Coefficient", name, 43)
        for name in self.robot.base_motors:
            self.robot.bus2.write("Operating_Mode", name, OperatingMode.VELOCITY.value)

    def latch_current_positions(self) -> None:
        for bus, motors in (
            (self.robot.bus1, self.robot.left_arm_motors + self.robot.head_motors),
            (self.robot.bus2, self.robot.right_arm_motors),
        ):
            present = bus.sync_read("Present_Position", motors)
            if set(present) != set(motors):
                raise RuntimeError(f"incomplete position read before torque enable: {present}")
            bus.sync_write("Goal_Position", present)

    def stop_base(self) -> None:
        self.robot.stop_base()

    def enable_torque(self) -> None:
        try:
            self.robot.bus1.enable_torque()
            self.robot.bus2.enable_torque()
        except Exception:
            self.emergency_stop("body torque-enable failure")
            raise

    def get_observation(self) -> Mapping[str, object]:
        return dict(self.robot.get_observation())

    def send_action(self, action: Mapping[str, float]) -> Mapping[str, float]:
        # The wrapper owns relative-target limiting with a corrected type. Do not
        # allow the upstream int-only annotation/helper path to run a second time.
        previous = self.robot.config.max_relative_target
        self.robot.config.max_relative_target = None
        try:
            return dict(self.robot.send_action(dict(action)))
        finally:
            self.robot.config.max_relative_target = previous

    def emergency_stop(self, reason: str) -> None:
        del reason
        try:
            if self.robot.bus2.is_connected:
                self.robot.stop_base()
        finally:
            for bus in (self.robot.bus2, self.robot.bus1):
                if bus.is_connected:
                    with suppress(Exception):
                        bus.disable_torque()

    def disconnect(self) -> None:
        errors: list[Exception] = []
        if self.robot.bus2.is_connected:
            try:
                self.robot.stop_base()
            except Exception as error:
                errors.append(error)
        for camera in self.robot.cameras.values():
            if camera.is_connected:
                try:
                    camera.disconnect()
                except Exception as error:
                    errors.append(error)
        for bus in (self.robot.bus2, self.robot.bus1):
            if bus.is_connected:
                try:
                    bus.disable_torque()
                except Exception as error:
                    errors.append(error)
                try:
                    bus.disconnect(True)
                except Exception as error:
                    errors.append(error)
        if errors:
            raise RuntimeError(f"XLeRobot body disconnect failed: {errors}")

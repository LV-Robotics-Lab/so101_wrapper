"""Optional LeRobot registration shim.

LeRobot is a policy dependency, not a submodule of this hardware wrapper. The
shim is installed only when callers supply an explicit SHA-verified XLeRobot
source configuration and have LeRobot plus ``amazinghand_wrapper`` installed.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any

from .adapters import AmazingHandControllerAdapter, LeRobotXLerobotBodyAdapter
from .config import (
    AmazingHandAttachmentConfig,
    XLeRobotSourceConfig,
)
from .config import (
    XLerobotAmazingFollowerConfig as CoreRobotConfig,
)
from .config import (
    XLerobotBiSOLeaderConfig as CoreLeaderConfig,
)
from .controller import XLerobotAmazingFollower as CoreRobot
from .controller import XLerobotBiSOLeader as CoreLeader
from .schema import ActionProfile, RelativeTargetLimit
from .source import load_verified_xlerobot

BackendFactory = Callable[[Any, Any], tuple[Any, Any, Any]]


@dataclass(frozen=True)
class LeRobotPluginTypes:
    XLerobotAmazingFollowerConfig: type
    XLerobotAmazingFollower: type
    XLerobotBiSOLeaderConfig: type
    XLerobotBiSOLeader: type


def install_lerobot_plugin(
    source: XLeRobotSourceConfig,
    *,
    backend_factory: BackendFactory | None = None,
) -> LeRobotPluginTypes:
    """Register and return LeRobot plugin classes for an exact XLeRobot checkout."""

    upstream = load_verified_xlerobot(source)
    try:
        from lerobot.lerobot_types import RobotAction, RobotObservation
        from lerobot.robots.config import RobotConfig
        from lerobot.robots.robot import Robot
        from lerobot.teleoperators.bi_so_leader import BiSOLeader, BiSOLeaderConfig
        from lerobot.teleoperators.config import TeleoperatorConfig
        from lerobot.teleoperators.keyboard import KeyboardTeleop, KeyboardTeleopConfig
        from lerobot.teleoperators.so_leader import SOLeaderConfig
        from lerobot.teleoperators.teleoperator import Teleoperator
    except ImportError as error:
        raise ImportError(
            "the separately pinned LV-Robotics-Lab/lerobot policy package is required"
        ) from error

    factory = backend_factory or _default_backend_factory

    @RobotConfig.register_subclass("xlerobot_amazing_follower")
    @dataclass(kw_only=True)
    class XLerobotAmazingFollowerConfig(upstream.XLerobotConfig):
        left_hand_config: AmazingHandAttachmentConfig
        right_hand_config: AmazingHandAttachmentConfig
        action_profile: str = ActionProfile.ARMS_ONLY.value
        calibration_provenance_verified: bool = False
        motion_authorized: bool = False
        max_relative_target: RelativeTargetLimit = None
        max_base_speed_xy: float = 0.3
        max_base_speed_theta: float = 90.0

    class XLerobotAmazingFollower(Robot):
        config_class = XLerobotAmazingFollowerConfig
        name = "xlerobot_amazing_follower"

        def __init__(self, config: XLerobotAmazingFollowerConfig):
            super().__init__(config)
            self.config = config
            body, left_hand, right_hand = factory(config, upstream)
            self._core = CoreRobot(
                CoreRobotConfig(
                    id=config.id or "",
                    left_hand_config=config.left_hand_config,
                    right_hand_config=config.right_hand_config,
                    action_profile=ActionProfile(config.action_profile),
                    calibration_provenance_verified=config.calibration_provenance_verified,
                    motion_authorized=config.motion_authorized,
                    max_relative_target=config.max_relative_target,
                    xlerobot_source=source,
                    max_base_speed_xy=config.max_base_speed_xy,
                    max_base_speed_theta=config.max_base_speed_theta,
                ),
                body,
                left_hand,
                right_hand,
            )
            self.cameras = body.robot.cameras if hasattr(body, "robot") else {}

        @cached_property
        def action_features(self) -> dict[str, type]:
            return self._core.action_features

        @cached_property
        def observation_features(self) -> dict[str, type | tuple]:
            body = getattr(self._core.body, "robot", None)
            features = dict(getattr(body, "observation_features", {}))
            features["left_arm_gripper.pos"] = float
            features["right_arm_gripper.pos"] = float
            for side, hand_config in (
                ("left", self.config.left_hand_config),
                ("right", self.config.right_hand_config),
            ):
                if hand_config.include_motor_observations:
                    features.update({f"{side}_hand_{index}.pos": float for index in range(1, 9)})
            return features

        @property
        def is_connected(self) -> bool:
            return self._core.is_connected

        @property
        def is_calibrated(self) -> bool:
            return self._core.is_calibrated

        def connect(self, calibrate: bool = True) -> None:
            del calibrate
            self._core.connect()

        def calibrate(self) -> None:
            raise RuntimeError(
                "so101_wrapper never starts interactive calibration from runtime; "
                "use the supervised wrapper-specific calibration workflow"
            )

        def configure(self) -> None:
            if not self.is_connected:
                raise RuntimeError("connect through the fail-closed lifecycle before configure")

        def get_observation(self) -> RobotObservation:
            return self._core.get_observation()

        def send_action(self, action: RobotAction) -> RobotAction:
            return self._core.send_action(action)

        def disconnect(self) -> None:
            self._core.disconnect()

    @TeleoperatorConfig.register_subclass("xlerobot_bi_so_leader")
    @dataclass(kw_only=True)
    class XLerobotBiSOLeaderConfig(TeleoperatorConfig):
        left_arm_config: SOLeaderConfig
        right_arm_config: SOLeaderConfig
        action_profile: str = ActionProfile.ARMS_ONLY.value
        base_speed_levels_xy: tuple[float, ...] = (0.1, 0.2, 0.3)
        base_speed_levels_theta: tuple[float, ...] = (30.0, 60.0, 90.0)
        forward_key: str = "i"
        backward_key: str = "k"
        left_key: str = "j"
        right_key: str = "l"
        rotate_left_key: str = "u"
        rotate_right_key: str = "o"
        speed_up_key: str = "n"
        speed_down_key: str = "m"

        def arms_config(self) -> Any:
            return BiSOLeaderConfig(
                id=self.id,
                calibration_dir=self.calibration_dir,
                left_arm_config=self.left_arm_config,
                right_arm_config=self.right_arm_config,
            )

    class XLerobotBiSOLeader(Teleoperator):
        config_class = XLerobotBiSOLeaderConfig
        name = "xlerobot_bi_so_leader"

        def __init__(self, config: XLerobotBiSOLeaderConfig):
            super().__init__(config)
            self.config = config
            self.arms = BiSOLeader(config.arms_config())
            profile = ActionProfile(config.action_profile)
            self.keyboard = (
                KeyboardTeleop(
                    KeyboardTeleopConfig(
                        id=f"{config.id}_base" if config.id else None,
                        calibration_dir=config.calibration_dir,
                    )
                )
                if profile is ActionProfile.ARMS_BASE
                else None
            )
            self._mapper = CoreLeader(
                CoreLeaderConfig(
                    action_profile=profile,
                    base_speed_levels_xy=config.base_speed_levels_xy,
                    base_speed_levels_theta=config.base_speed_levels_theta,
                    forward_key=config.forward_key,
                    backward_key=config.backward_key,
                    left_key=config.left_key,
                    right_key=config.right_key,
                    rotate_left_key=config.rotate_left_key,
                    rotate_right_key=config.rotate_right_key,
                    speed_up_key=config.speed_up_key,
                    speed_down_key=config.speed_down_key,
                )
            )

        @cached_property
        def action_features(self) -> dict[str, type]:
            return self._mapper.action_features

        @cached_property
        def feedback_features(self) -> dict[str, type]:
            return {_to_robot_key(key): value for key, value in self.arms.feedback_features.items()}

        @property
        def is_connected(self) -> bool:
            return self.arms.is_connected and (self.keyboard is None or self.keyboard.is_connected)

        @property
        def is_calibrated(self) -> bool:
            return self.arms.is_calibrated

        def connect(self, calibrate: bool = True) -> None:
            if self.is_connected:
                return
            try:
                self.arms.connect(calibrate)
                if self.keyboard is not None:
                    self.keyboard.connect()
                    if not self.keyboard.is_connected:
                        raise RuntimeError("base control requires an interactive keyboard session")
            except Exception:
                self._disconnect_best_effort()
                raise

        def calibrate(self) -> None:
            self.arms.calibrate()

        def configure(self) -> None:
            self.arms.configure()

        def get_action(self) -> RobotAction:
            pressed = set(self.keyboard.get_action()) if self.keyboard is not None else None
            return self._mapper.map_action(self.arms.get_action(), pressed_keys=pressed)

        def send_feedback(self, feedback: dict[str, Any]) -> None:
            mapped = {
                _to_leader_key(key): value
                for key, value in feedback.items()
                if key.startswith(("left_arm_", "right_arm_"))
            }
            if mapped:
                self.arms.send_feedback(mapped)

        def _disconnect_best_effort(self) -> list[Exception]:
            errors: list[Exception] = []
            if self.keyboard is not None and self.keyboard.is_connected:
                try:
                    self.keyboard.disconnect()
                except Exception as error:
                    errors.append(error)
            for arm in (self.arms.right_arm, self.arms.left_arm):
                if arm.is_connected:
                    try:
                        arm.disconnect()
                    except Exception as error:
                        errors.append(error)
            return errors

        def disconnect(self) -> None:
            errors = self._disconnect_best_effort()
            if errors:
                raise RuntimeError(f"XLeRobot leader disconnect failed: {errors}")

    return LeRobotPluginTypes(
        XLerobotAmazingFollowerConfig=XLerobotAmazingFollowerConfig,
        XLerobotAmazingFollower=XLerobotAmazingFollower,
        XLerobotBiSOLeaderConfig=XLerobotBiSOLeaderConfig,
        XLerobotBiSOLeader=XLerobotBiSOLeader,
    )


def _default_backend_factory(config: Any, upstream: Any) -> tuple[Any, Any, Any]:
    try:
        from amazinghand_wrapper import (
            AmazingHandConfig,
            AmazingHandController,
            LeRobotFeetechBackend,
        )
    except ImportError as error:
        raise ImportError("install the separately pinned amazinghand_wrapper package") from error

    upstream_robot = upstream.XLerobot(config)
    body = LeRobotXLerobotBodyAdapter(upstream_robot)

    def make_hand(side: str, attachment: AmazingHandAttachmentConfig) -> Any:
        del side
        motor_ids = tuple(range(1, 9))
        hand_config = AmazingHandConfig(
            port=attachment.port,
            calibration_file=Path(attachment.calibration_file),
            motor_ids=motor_ids,
        )
        controller = AmazingHandController(hand_config, LeRobotFeetechBackend(motor_ids))
        return AmazingHandControllerAdapter(controller, attachment)

    return (
        body,
        make_hand("left", config.left_hand_config),
        make_hand("right", config.right_hand_config),
    )


def _to_robot_key(key: str) -> str:
    if key.startswith("left_"):
        return f"left_arm_{key.removeprefix('left_')}"
    if key.startswith("right_"):
        return f"right_arm_{key.removeprefix('right_')}"
    raise ValueError(f"unexpected bimanual leader key: {key}")


def _to_leader_key(key: str) -> str:
    if key.startswith("left_arm_"):
        return f"left_{key.removeprefix('left_arm_')}"
    if key.startswith("right_arm_"):
        return f"right_{key.removeprefix('right_arm_')}"
    raise ValueError(f"unexpected XLeRobot key: {key}")

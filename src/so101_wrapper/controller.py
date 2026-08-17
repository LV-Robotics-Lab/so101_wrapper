"""Fail-closed composition of SO-101 arms, XLeRobot, and AmazingHands."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import suppress
from enum import Enum

from .config import (
    BiSO101AmazingFollowerConfig,
    SO101AmazingFollowerConfig,
    XLerobotAmazingFollowerConfig,
    XLerobotBiSOLeaderConfig,
)
from .protocols import AmazingHandBackend, SO101ArmBackend, XLerobotBodyBackend
from .schema import (
    ARM_POSITION_KEYS,
    BASE_VELOCITY_KEYS,
    SINGLE_ACTION_KEYS,
    SINGLE_ARM_POSITION_KEYS,
    SINGLE_GRIPPER_KEY,
    ActionProfile,
    RelativeTargetLimit,
    limit_relative_targets,
    schema_for,
)


class LifecycleState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    ACTIVE = "active"
    FAULT = "fault"


def _require_provenance(robot_id: str, verified: bool) -> None:
    if not verified:
        raise RuntimeError(
            f"calibration provenance for robot {robot_id!r} is not verified; refusing all device I/O"
        )


def _require_motion_authorization(robot_id: str, authorized: bool) -> None:
    if not authorized:
        raise RuntimeError(
            f"motion for robot {robot_id!r} is not explicitly authorized; refusing all device I/O"
        )


class SO101AmazingFollower:
    """One five-joint SO-101 arm with a scalar AmazingHand grasp channel."""

    name = "so101_amazing_follower"

    def __init__(
        self,
        config: SO101AmazingFollowerConfig,
        arm: SO101ArmBackend,
        hand: AmazingHandBackend,
        *,
        side: str = "single",
    ) -> None:
        self.config = config
        self.arm = arm
        self.hand = hand
        self.side = side
        self.state = LifecycleState.DISCONNECTED
        self.fault_reason: str | None = None

    @property
    def action_features(self) -> dict[str, type]:
        return dict.fromkeys(SINGLE_ACTION_KEYS, float)

    @property
    def is_connected(self) -> bool:
        return (
            self.state is LifecycleState.ACTIVE
            and self.arm.is_connected
            and self.hand.is_connected
            and self.hand.is_active
        )

    @property
    def is_calibrated(self) -> bool:
        return self.arm.is_calibrated and self.hand.is_calibrated

    def preflight(self) -> None:
        _require_provenance(self.config.id, self.config.calibration_provenance_verified)
        _require_motion_authorization(self.config.id, self.config.motion_authorized)
        self.arm.offline_validate_calibration(self.config.id)
        self.hand.offline_validate_calibration(self.config.id, self.side)

    def connect(self) -> None:
        if self.is_connected:
            return
        if self.state is LifecycleState.FAULT:
            raise RuntimeError("disconnect the faulted robot before reconnecting")
        self.preflight()
        self._connect_after_preflight()

    def _connect_after_preflight(self) -> None:
        self.state = LifecycleState.CONNECTING
        try:
            self.arm.connect_torque_off()
            self.hand.connect_torque_off()
            self.arm.latch_current_position()
            self.hand.latch_current_position()
            self.arm.enable_torque()
            self.hand.activate()
            self.state = LifecycleState.ACTIVE
        except Exception as error:
            self._fail_closed(f"connect failure: {error}", disconnect=True)
            raise

    def get_observation(self) -> dict[str, object]:
        self._require_active()
        try:
            observation = dict(self.arm.get_observation())
            hand = self.hand.observe()
            observation[SINGLE_GRIPPER_KEY] = float(hand.grasp_closure)
            if self.config.hand_config.include_motor_observations:
                observation.update(
                    {
                        f"hand_{index}.pos": float(value)
                        for index, value in enumerate(hand.motor_closure.values(), start=1)
                    }
                )
            return observation
        except Exception as error:
            self._fail_closed(f"observation failure: {error}")
            raise

    def send_action(self, action: Mapping[str, object]) -> dict[str, float]:
        self._require_active()
        try:
            validated = _validate_single_action(action)
            if self.config.max_relative_target is not None:
                present = self.arm.get_observation()
                validated = limit_relative_targets(
                    validated,
                    present,
                    self.config.max_relative_target,
                    position_keys=SINGLE_ARM_POSITION_KEYS,
                )
            arm_action = {key: validated[key] for key in SINGLE_ARM_POSITION_KEYS}
            arm_sent = dict(self.arm.send_positions(arm_action))
            self.hand.command_grasp(validated[SINGLE_GRIPPER_KEY])
            return {
                **{key: float(arm_sent.get(key, arm_action[key])) for key in SINGLE_ARM_POSITION_KEYS},
                SINGLE_GRIPPER_KEY: validated[SINGLE_GRIPPER_KEY],
            }
        except Exception as error:
            self._fail_closed(f"command failure: {error}")
            raise

    def _require_active(self) -> None:
        if not self.is_connected:
            raise RuntimeError("SO-101 AmazingHand follower is not active")

    def _fail_closed(self, reason: str, *, disconnect: bool = False) -> None:
        self.fault_reason = reason
        self.state = LifecycleState.FAULT
        for component in (self.hand, self.arm):
            with suppress(Exception):
                component.emergency_stop(reason)
        if disconnect:
            for component in (self.hand, self.arm):
                with suppress(Exception):
                    component.disconnect()

    def disconnect(self) -> None:
        if self.state is LifecycleState.DISCONNECTED:
            return
        errors: list[Exception] = []
        for component in (self.hand, self.arm):
            try:
                component.emergency_stop("disconnect")
            except Exception as error:
                errors.append(error)
            try:
                component.disconnect()
            except Exception as error:
                errors.append(error)
        self.state = LifecycleState.DISCONNECTED
        self.fault_reason = None
        if errors:
            raise RuntimeError(f"SO-101 AmazingHand disconnect failed: {errors}")


class BiSO101AmazingFollower:
    """Two independent SO-101/AmazingHand sides with one 12D contract."""

    name = "bi_so101_amazing_follower"

    def __init__(
        self,
        config: BiSO101AmazingFollowerConfig,
        left_arm: SO101ArmBackend,
        right_arm: SO101ArmBackend,
        left_hand: AmazingHandBackend,
        right_hand: AmazingHandBackend,
    ) -> None:
        self.config = config
        self.left = SO101AmazingFollower(
            SO101AmazingFollowerConfig(
                id=f"{config.id}_left",
                hand_config=config.left_hand_config,
                calibration_provenance_verified=config.calibration_provenance_verified,
                motion_authorized=config.motion_authorized,
                max_relative_target=_side_limit(config.max_relative_target, "left"),
            ),
            left_arm,
            left_hand,
            side="left",
        )
        self.right = SO101AmazingFollower(
            SO101AmazingFollowerConfig(
                id=f"{config.id}_right",
                hand_config=config.right_hand_config,
                calibration_provenance_verified=config.calibration_provenance_verified,
                motion_authorized=config.motion_authorized,
                max_relative_target=_side_limit(config.max_relative_target, "right"),
            ),
            right_arm,
            right_hand,
            side="right",
        )
        self.state = LifecycleState.DISCONNECTED

    @property
    def action_features(self) -> dict[str, type]:
        return dict.fromkeys(schema_for(ActionProfile.ARMS_ONLY).keys, float)

    @property
    def is_connected(self) -> bool:
        return self.state is LifecycleState.ACTIVE and self.left.is_connected and self.right.is_connected

    @property
    def is_calibrated(self) -> bool:
        return self.left.is_calibrated and self.right.is_calibrated

    def connect(self) -> None:
        if self.is_connected:
            return
        if self.state is LifecycleState.FAULT:
            raise RuntimeError("disconnect the faulted robot before reconnecting")
        # Both sides must pass offline checks before either side opens a device.
        self.left.preflight()
        self.right.preflight()
        self.state = LifecycleState.CONNECTING
        self.left.state = LifecycleState.CONNECTING
        self.right.state = LifecycleState.CONNECTING
        try:
            # Stage both sides together. No actuator is enabled while a peer
            # remains unopened or unlatchable.
            self.left.arm.connect_torque_off()
            self.right.arm.connect_torque_off()
            self.left.hand.connect_torque_off()
            self.right.hand.connect_torque_off()
            self.left.arm.latch_current_position()
            self.right.arm.latch_current_position()
            self.left.hand.latch_current_position()
            self.right.hand.latch_current_position()
            self.left.arm.enable_torque()
            self.right.arm.enable_torque()
            self.left.hand.activate()
            self.right.hand.activate()
            self.left.state = LifecycleState.ACTIVE
            self.right.state = LifecycleState.ACTIVE
            self.state = LifecycleState.ACTIVE
        except Exception:
            self.left._fail_closed("bimanual peer connect failure", disconnect=True)
            self.right._fail_closed("bimanual peer connect failure", disconnect=True)
            self.state = LifecycleState.FAULT
            raise

    def get_observation(self) -> dict[str, object]:
        self._require_active()
        try:
            return {
                **_prefix_side(self.left.get_observation(), "left"),
                **_prefix_side(self.right.get_observation(), "right"),
            }
        except Exception:
            self._fault_peer("bimanual observation failure")
            raise

    def send_action(self, action: Mapping[str, object]) -> dict[str, float]:
        self._require_active()
        try:
            validated = schema_for(ActionProfile.ARMS_ONLY).validate(action)
            left_sent = self.left.send_action(_unprefix_side(validated, "left"))
            right_sent = self.right.send_action(_unprefix_side(validated, "right"))
            return {
                **_prefix_side(left_sent, "left"),
                **_prefix_side(right_sent, "right"),
            }
        except Exception:
            self._fault_peer("bimanual command failure")
            raise

    def _require_active(self) -> None:
        if not self.is_connected:
            raise RuntimeError("bimanual SO-101 AmazingHand follower is not active")

    def _fault_peer(self, reason: str) -> None:
        self.left._fail_closed(reason)
        self.right._fail_closed(reason)
        self.state = LifecycleState.FAULT

    def disconnect(self) -> None:
        if self.state is LifecycleState.DISCONNECTED:
            return
        errors: list[Exception] = []
        for robot in (self.right, self.left):
            try:
                robot.disconnect()
            except Exception as error:
                errors.append(error)
        self.state = LifecycleState.DISCONNECTED
        if errors:
            raise RuntimeError(f"bimanual SO-101 disconnect failed: {errors}")


class XLerobotAmazingFollower:
    """Dual SO-101 XLeRobot body with stock grippers routed to AmazingHands."""

    name = "xlerobot_amazing_follower"

    def __init__(
        self,
        config: XLerobotAmazingFollowerConfig,
        body: XLerobotBodyBackend,
        left_hand: AmazingHandBackend,
        right_hand: AmazingHandBackend,
    ) -> None:
        self.config = config
        self.body = body
        self.left_hand = left_hand
        self.right_hand = right_hand
        self.schema = schema_for(config.action_profile)
        self.state = LifecycleState.DISCONNECTED
        self.fault_reason: str | None = None

    @property
    def action_features(self) -> dict[str, type]:
        return dict.fromkeys(self.schema.keys, float)

    @property
    def is_connected(self) -> bool:
        return (
            self.state is LifecycleState.ACTIVE
            and self.body.is_connected
            and self.left_hand.is_connected
            and self.right_hand.is_connected
            and self.left_hand.is_active
            and self.right_hand.is_active
        )

    @property
    def is_calibrated(self) -> bool:
        return self.body.is_calibrated and self.left_hand.is_calibrated and self.right_hand.is_calibrated

    def preflight(self) -> None:
        _require_provenance(self.config.id, self.config.calibration_provenance_verified)
        _require_motion_authorization(self.config.id, self.config.motion_authorized)
        self.body.offline_validate_calibration(self.config.id)
        self.left_hand.offline_validate_calibration(self.config.id, "left")
        self.right_hand.offline_validate_calibration(self.config.id, "right")

    def connect(self) -> None:
        if self.is_connected:
            return
        if self.state is LifecycleState.FAULT:
            raise RuntimeError("disconnect the faulted robot before reconnecting")
        self.preflight()
        self.state = LifecycleState.CONNECTING
        try:
            self.body.connect_torque_off()
            self.left_hand.connect_torque_off()
            self.right_hand.connect_torque_off()
            self.body.latch_current_positions()
            self.body.stop_base()
            self.left_hand.latch_current_position()
            self.right_hand.latch_current_position()
            self.body.enable_torque()
            self.left_hand.activate()
            self.right_hand.activate()
            self.state = LifecycleState.ACTIVE
        except Exception as error:
            self._fail_closed(f"connect failure: {error}", disconnect=True)
            raise

    def get_observation(self) -> dict[str, object]:
        self._require_active()
        try:
            observation = dict(self.body.get_observation())
            for side, hand, hand_config in (
                ("left", self.left_hand, self.config.left_hand_config),
                ("right", self.right_hand, self.config.right_hand_config),
            ):
                sample = hand.observe()
                observation[f"{side}_arm_gripper.pos"] = float(sample.grasp_closure)
                if hand_config.include_motor_observations:
                    observation.update(
                        {
                            f"{side}_hand_{index}.pos": float(value)
                            for index, value in enumerate(sample.motor_closure.values(), start=1)
                        }
                    )
            return observation
        except Exception as error:
            self._fail_closed(f"observation failure: {error}")
            raise

    def send_action(self, action: Mapping[str, object]) -> dict[str, float]:
        self._require_active()
        try:
            validated = self.schema.validate(action)
            if self.config.max_relative_target is not None:
                present = self.body.get_observation()
                validated = limit_relative_targets(
                    validated,
                    present,
                    self.config.max_relative_target,
                    position_keys=ARM_POSITION_KEYS,
                )
            self._validate_base_velocity(validated)
            if self.config.action_profile is ActionProfile.ARMS_ONLY:
                # A 12D policy never inherits a stale mobile-base velocity.
                self.body.stop_base()
            body_action = {
                key: value
                for key, value in validated.items()
                if key in ARM_POSITION_KEYS or key in BASE_VELOCITY_KEYS
            }
            body_sent = dict(self.body.send_action(body_action))
            self.left_hand.command_grasp(validated["left_arm_gripper.pos"])
            self.right_hand.command_grasp(validated["right_arm_gripper.pos"])
            return {
                key: float(body_sent.get(key, validated[key]))
                if key not in {"left_arm_gripper.pos", "right_arm_gripper.pos"}
                else validated[key]
                for key in self.schema.keys
            }
        except Exception as error:
            self._fail_closed(f"command failure: {error}")
            raise

    def _validate_base_velocity(self, action: Mapping[str, float]) -> None:
        if self.config.action_profile is ActionProfile.ARMS_ONLY:
            return
        if abs(action["x.vel"]) > self.config.max_base_speed_xy:
            raise ValueError("x.vel exceeds max_base_speed_xy")
        if abs(action["y.vel"]) > self.config.max_base_speed_xy:
            raise ValueError("y.vel exceeds max_base_speed_xy")
        if abs(action["theta.vel"]) > self.config.max_base_speed_theta:
            raise ValueError("theta.vel exceeds max_base_speed_theta")

    def _require_active(self) -> None:
        if not self.is_connected:
            raise RuntimeError("XLeRobot AmazingHand follower is not active")

    def _fail_closed(self, reason: str, *, disconnect: bool = False) -> None:
        self.fault_reason = reason
        self.state = LifecycleState.FAULT
        with suppress(Exception):
            self.body.stop_base()
        for component in (self.right_hand, self.left_hand, self.body):
            with suppress(Exception):
                component.emergency_stop(reason)
        if disconnect:
            for component in (self.right_hand, self.left_hand, self.body):
                with suppress(Exception):
                    component.disconnect()

    def disconnect(self) -> None:
        if self.state is LifecycleState.DISCONNECTED:
            return
        errors: list[Exception] = []
        try:
            self.body.stop_base()
        except Exception as error:
            errors.append(error)
        for component in (self.right_hand, self.left_hand, self.body):
            try:
                component.emergency_stop("disconnect")
            except Exception as error:
                errors.append(error)
            try:
                component.disconnect()
            except Exception as error:
                errors.append(error)
        self.state = LifecycleState.DISCONNECTED
        self.fault_reason = None
        if errors:
            raise RuntimeError(f"XLeRobot AmazingHand disconnect failed: {errors}")


class XLerobotBiSOLeader:
    """Map standard bimanual SO-leader actions to the selected robot schema."""

    name = "xlerobot_bi_so_leader"

    def __init__(self, config: XLerobotBiSOLeaderConfig) -> None:
        self.config = config
        self.schema = schema_for(config.action_profile)
        self._speed_index = 0
        self._last_pressed: set[str] = set()

    @property
    def action_features(self) -> dict[str, type]:
        return dict.fromkeys(self.schema.keys, float)

    def map_action(
        self,
        bimanual_action: Mapping[str, object],
        *,
        pressed_keys: set[str] | None = None,
    ) -> dict[str, float]:
        mapped: dict[str, object] = {}
        for side in ("left", "right"):
            for local_key in SINGLE_ACTION_KEYS:
                leader_key = f"{side}_{local_key}"
                if leader_key not in bimanual_action:
                    raise ValueError(f"bimanual leader action is missing {leader_key}")
                mapped[f"{side}_arm_{local_key}"] = bimanual_action[leader_key]
        if self.config.action_profile is ActionProfile.ARMS_BASE:
            mapped.update(self._base_action(pressed_keys or set()))
        return self.schema.validate(mapped)

    def _base_action(self, pressed: set[str]) -> dict[str, float]:
        rising = pressed - self._last_pressed
        self._last_pressed = set(pressed)
        if self.config.speed_up_key in rising:
            self._speed_index = min(self._speed_index + 1, len(self.config.base_speed_levels_xy) - 1)
        if self.config.speed_down_key in rising:
            self._speed_index = max(self._speed_index - 1, 0)
        xy_speed = self.config.base_speed_levels_xy[self._speed_index]
        theta_speed = self.config.base_speed_levels_theta[self._speed_index]
        return {
            "x.vel": xy_speed
            * (int(self.config.forward_key in pressed) - int(self.config.backward_key in pressed)),
            "y.vel": xy_speed
            * (int(self.config.left_key in pressed) - int(self.config.right_key in pressed)),
            "theta.vel": theta_speed
            * (int(self.config.rotate_left_key in pressed) - int(self.config.rotate_right_key in pressed)),
        }


def _validate_single_action(action: Mapping[str, object]) -> dict[str, float]:
    from .schema import ActionSchema

    return ActionSchema(ActionProfile.ARMS_ONLY, SINGLE_ACTION_KEYS).validate(action)


def _side_limit(limit: RelativeTargetLimit, side: str) -> RelativeTargetLimit:
    if limit is None or isinstance(limit, float):
        return limit
    prefix = f"{side}_arm_"
    return {key.removeprefix(prefix): value for key, value in limit.items() if key.startswith(prefix)}


def _prefix_side(values: Mapping[str, object], side: str) -> dict[str, object]:
    return {
        f"{side}_{key}" if key.startswith("hand_") else f"{side}_arm_{key}": value
        for key, value in values.items()
    }


def _unprefix_side(values: Mapping[str, float], side: str) -> dict[str, float]:
    prefix = f"{side}_arm_"
    return {key.removeprefix(prefix): value for key, value in values.items() if key.startswith(prefix)}

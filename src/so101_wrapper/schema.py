"""Stable policy-facing action schemas for the SO-101 mobile rig."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from numbers import Real
from typing import TypeAlias

SINGLE_ARM_POSITION_KEYS = (
    "shoulder_pan.pos",
    "shoulder_lift.pos",
    "elbow_flex.pos",
    "wrist_flex.pos",
    "wrist_roll.pos",
)
SINGLE_GRIPPER_KEY = "gripper.pos"
SINGLE_ACTION_KEYS = (*SINGLE_ARM_POSITION_KEYS, SINGLE_GRIPPER_KEY)

LEFT_ARM_POSITION_KEYS = tuple(f"left_arm_{key}" for key in SINGLE_ARM_POSITION_KEYS)
RIGHT_ARM_POSITION_KEYS = tuple(f"right_arm_{key}" for key in SINGLE_ARM_POSITION_KEYS)
ARM_POSITION_KEYS = (*LEFT_ARM_POSITION_KEYS, *RIGHT_ARM_POSITION_KEYS)
GRIPPER_KEYS = ("left_arm_gripper.pos", "right_arm_gripper.pos")
BASE_VELOCITY_KEYS = ("x.vel", "y.vel", "theta.vel")
ARMS_ONLY_KEYS = (
    *LEFT_ARM_POSITION_KEYS,
    GRIPPER_KEYS[0],
    *RIGHT_ARM_POSITION_KEYS,
    GRIPPER_KEYS[1],
)
ARMS_BASE_KEYS = (*ARMS_ONLY_KEYS, *BASE_VELOCITY_KEYS)

RelativeTargetLimit: TypeAlias = float | dict[str, float] | None


class ActionProfile(str, Enum):
    """Policy-visible action layouts.

    Head joints are intentionally absent. A fixed head pose is observation context,
    not an action channel, unless a future version introduces a distinct profile.
    """

    ARMS_ONLY = "arms_only"
    ARMS_BASE = "arms_base"


@dataclass(frozen=True)
class ActionSchema:
    name: ActionProfile
    keys: tuple[str, ...]

    @property
    def dimension(self) -> int:
        return len(self.keys)

    def validate(self, action: Mapping[str, object]) -> dict[str, float]:
        expected = set(self.keys)
        actual = set(action)
        if actual != expected:
            missing = sorted(expected - actual)
            extra = sorted(actual - expected)
            raise ValueError(
                f"{self.name.value} action keys do not match the {self.dimension}D schema; "
                f"missing={missing}, extra={extra}"
            )
        return {key: _finite_float(action[key], label=key) for key in self.keys}

    def dataset_features(self) -> dict[str, type]:
        """Return the ordered scalar features used by collection datasets."""

        return dict.fromkeys(self.keys, float)


ARMS_ONLY_SCHEMA = ActionSchema(ActionProfile.ARMS_ONLY, ARMS_ONLY_KEYS)
ARMS_BASE_SCHEMA = ActionSchema(ActionProfile.ARMS_BASE, ARMS_BASE_KEYS)


def schema_for(profile: ActionProfile | str) -> ActionSchema:
    resolved = ActionProfile(profile)
    return ARMS_ONLY_SCHEMA if resolved is ActionProfile.ARMS_ONLY else ARMS_BASE_SCHEMA


def dataset_action_features(profile: ActionProfile | str) -> dict[str, type]:
    """The dataset contract is the same object-level schema as robot and teleop."""

    return schema_for(profile).dataset_features()


def validate_relative_target_limit(
    limit: RelativeTargetLimit,
    *,
    position_keys: tuple[str, ...],
) -> RelativeTargetLimit:
    """Validate a LeRobot-compatible relative-position limit.

    A scalar must deliberately be a float (for example ``5.0``). This prevents
    reproducing the XLeRobot annotation bug where ``5`` reached LeRobot's helper
    and failed later with a less useful ``TypeError``.
    """

    if limit is None:
        return None
    if isinstance(limit, float):
        _positive_finite_float(limit, label="max_relative_target")
        return limit
    if not isinstance(limit, dict):
        raise TypeError("max_relative_target must be float, dict[str, float], or None")

    expected = set(position_keys)
    actual = set(limit)
    if actual != expected:
        raise ValueError(
            "max_relative_target keys must exactly match position keys; "
            f"missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )
    for key, value in limit.items():
        if not isinstance(value, float):
            raise TypeError(f"max_relative_target[{key!r}] must be a float")
        _positive_finite_float(value, label=f"max_relative_target[{key!r}]")
    return dict(limit)


def limit_relative_targets(
    targets: Mapping[str, float],
    present: Mapping[str, object],
    limit: RelativeTargetLimit,
    *,
    position_keys: tuple[str, ...],
) -> dict[str, float]:
    """Clip arm position targets relative to current positions."""

    validated = validate_relative_target_limit(limit, position_keys=position_keys)
    result = dict(targets)
    if validated is None:
        return result

    missing = sorted(set(position_keys) - set(present))
    if missing:
        raise ValueError(f"current observation is missing position keys: {missing}")
    caps = dict.fromkeys(position_keys, validated) if isinstance(validated, float) else validated
    for key in position_keys:
        current = _finite_float(present[key], label=f"present[{key}]")
        target = _finite_float(result[key], label=f"target[{key}]")
        cap = caps[key]
        result[key] = current + max(-cap, min(cap, target - current))
    return result


def _finite_float(value: object, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{label} must be a finite real number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _positive_finite_float(value: float, *, label: str) -> None:
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{label} must be a positive finite float")

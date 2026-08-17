"""Configuration objects with safety-first defaults."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

from .schema import (
    ARM_POSITION_KEYS,
    SINGLE_ARM_POSITION_KEYS,
    ActionProfile,
    RelativeTargetLimit,
    validate_relative_target_limit,
)

VALID_CALIBRATION_SCHEMA = "lv_robotics.amazinghand_calibration.v1"
VALIDATED_AMAZINGHAND_COMMIT = "3f756af8787e6ee8b2c098a40bd4c60899b9e81c"
VALIDATED_XLEROBOT_COMMIT = "3d14695e40c9c68229c0aacffca6053c75cd3eb6"


@dataclass(frozen=True)
class AmazingHandAttachmentConfig:
    """Metadata passed to a separately installed ``amazinghand_wrapper``."""

    port: str
    calibration_file: Path
    include_motor_observations: bool = False
    expected_calibration_schema: str = VALID_CALIBRATION_SCHEMA

    def __post_init__(self) -> None:
        object.__setattr__(self, "calibration_file", Path(self.calibration_file).expanduser())
        if not self.port:
            raise ValueError("AmazingHand port must not be empty")
        if not self.expected_calibration_schema:
            raise ValueError("expected_calibration_schema must not be empty")


@dataclass(frozen=True)
class SO101AmazingFollowerConfig:
    id: str
    hand_config: AmazingHandAttachmentConfig
    calibration_provenance_verified: bool = False
    motion_authorized: bool = False
    max_relative_target: RelativeTargetLimit = None

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("robot id must not be empty")
        validate_relative_target_limit(
            self.max_relative_target,
            position_keys=SINGLE_ARM_POSITION_KEYS,
        )


@dataclass(frozen=True)
class BiSO101AmazingFollowerConfig:
    id: str
    left_hand_config: AmazingHandAttachmentConfig
    right_hand_config: AmazingHandAttachmentConfig
    calibration_provenance_verified: bool = False
    motion_authorized: bool = False
    max_relative_target: RelativeTargetLimit = None

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("robot id must not be empty")
        if self.left_hand_config.port == self.right_hand_config.port:
            raise ValueError("left and right AmazingHands require independent ports")
        validate_relative_target_limit(self.max_relative_target, position_keys=ARM_POSITION_KEYS)


@dataclass(frozen=True)
class XLeRobotSourceConfig:
    """Explicit source location and immutable identity for the XLeRobot checkout."""

    root: Path
    expected_commit: str = VALIDATED_XLEROBOT_COMMIT

    def __post_init__(self) -> None:
        object.__setattr__(self, "root", Path(self.root).expanduser().resolve())
        commit = self.expected_commit.lower()
        if len(commit) != 40 or any(char not in "0123456789abcdef" for char in commit):
            raise ValueError("expected_commit must be a full 40-character Git SHA")
        object.__setattr__(self, "expected_commit", commit)


@dataclass(frozen=True)
class XLerobotAmazingFollowerConfig:
    id: str
    left_hand_config: AmazingHandAttachmentConfig
    right_hand_config: AmazingHandAttachmentConfig
    action_profile: ActionProfile = ActionProfile.ARMS_ONLY
    calibration_provenance_verified: bool = False
    motion_authorized: bool = False
    max_relative_target: RelativeTargetLimit = None
    xlerobot_source: XLeRobotSourceConfig | None = None
    max_base_speed_xy: float = 0.3
    max_base_speed_theta: float = 90.0

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("robot id must not be empty")
        if self.left_hand_config.port == self.right_hand_config.port:
            raise ValueError("left and right AmazingHands require independent ports")
        object.__setattr__(self, "action_profile", ActionProfile(self.action_profile))
        validate_relative_target_limit(self.max_relative_target, position_keys=ARM_POSITION_KEYS)
        for label, value in (
            ("max_base_speed_xy", self.max_base_speed_xy),
            ("max_base_speed_theta", self.max_base_speed_theta),
        ):
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{label} must be a positive finite float")


@dataclass(frozen=True)
class XLerobotBiSOLeaderConfig:
    action_profile: ActionProfile = ActionProfile.ARMS_ONLY
    base_speed_levels_xy: tuple[float, ...] = field(default_factory=lambda: (0.1, 0.2, 0.3))
    base_speed_levels_theta: tuple[float, ...] = field(default_factory=lambda: (30.0, 60.0, 90.0))
    forward_key: str = "i"
    backward_key: str = "k"
    left_key: str = "j"
    right_key: str = "l"
    rotate_left_key: str = "u"
    rotate_right_key: str = "o"
    speed_up_key: str = "n"
    speed_down_key: str = "m"

    def __post_init__(self) -> None:
        object.__setattr__(self, "action_profile", ActionProfile(self.action_profile))
        if len(self.base_speed_levels_xy) != len(self.base_speed_levels_theta):
            raise ValueError("base speed level lists must have the same length")
        if not self.base_speed_levels_xy:
            raise ValueError("at least one base speed level is required")
        if any(not math.isfinite(value) or value <= 0 for value in self.base_speed_levels_xy):
            raise ValueError("xy speed levels must be positive and finite")
        if any(not math.isfinite(value) or value <= 0 for value in self.base_speed_levels_theta):
            raise ValueError("theta speed levels must be positive and finite")

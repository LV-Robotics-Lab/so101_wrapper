"""Public API for the LV Robotics Lab SO-101 hardware boundary."""

from .config import (
    VALIDATED_AMAZINGHAND_COMMIT,
    VALIDATED_XLEROBOT_COMMIT,
    AmazingHandAttachmentConfig,
    BiSO101AmazingFollowerConfig,
    SO101AmazingFollowerConfig,
    XLerobotAmazingFollowerConfig,
    XLerobotBiSOLeaderConfig,
    XLeRobotSourceConfig,
)
from .controller import (
    BiSO101AmazingFollower,
    LifecycleState,
    SO101AmazingFollower,
    XLerobotAmazingFollower,
    XLerobotBiSOLeader,
)
from .protocols import AmazingHandBackend, HandObservation, SO101ArmBackend, XLerobotBodyBackend
from .schema import (
    ARMS_BASE_SCHEMA,
    ARMS_ONLY_SCHEMA,
    ActionProfile,
    ActionSchema,
    RelativeTargetLimit,
    dataset_action_features,
)
from .source import SourceVerificationError, load_verified_xlerobot, verify_xlerobot_source

__all__ = [
    "ARMS_BASE_SCHEMA",
    "ARMS_ONLY_SCHEMA",
    "ActionProfile",
    "ActionSchema",
    "AmazingHandAttachmentConfig",
    "AmazingHandBackend",
    "BiSO101AmazingFollower",
    "BiSO101AmazingFollowerConfig",
    "HandObservation",
    "LifecycleState",
    "RelativeTargetLimit",
    "SO101AmazingFollower",
    "SO101AmazingFollowerConfig",
    "SO101ArmBackend",
    "SourceVerificationError",
    "VALIDATED_AMAZINGHAND_COMMIT",
    "VALIDATED_XLEROBOT_COMMIT",
    "XLeRobotSourceConfig",
    "XLerobotAmazingFollower",
    "XLerobotAmazingFollowerConfig",
    "XLerobotBiSOLeader",
    "XLerobotBiSOLeaderConfig",
    "XLerobotBodyBackend",
    "load_verified_xlerobot",
    "verify_xlerobot_source",
    "dataset_action_features",
]

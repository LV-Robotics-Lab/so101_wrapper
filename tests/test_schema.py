import pytest

from so101_wrapper.schema import (
    ARM_POSITION_KEYS,
    ARMS_BASE_SCHEMA,
    ARMS_ONLY_SCHEMA,
    limit_relative_targets,
    validate_relative_target_limit,
)


def test_policy_schemas_are_exactly_12d_and_15d_without_head_actions():
    assert ARMS_ONLY_SCHEMA.dimension == 12
    assert ARMS_BASE_SCHEMA.dimension == 15
    assert ARMS_BASE_SCHEMA.keys[:12] == ARMS_ONLY_SCHEMA.keys
    assert not any("head" in key for key in ARMS_BASE_SCHEMA.keys)


def test_action_schema_requires_exact_keys_and_finite_values():
    valid = dict.fromkeys(ARMS_ONLY_SCHEMA.keys, 0.0)
    assert ARMS_ONLY_SCHEMA.validate(valid) == valid
    with pytest.raises(ValueError, match="missing=.*right_arm_gripper"):
        ARMS_ONLY_SCHEMA.validate({key: 0.0 for key in ARMS_ONLY_SCHEMA.keys[:-1]})
    with pytest.raises(ValueError, match="extra=.*head_pan"):
        ARMS_ONLY_SCHEMA.validate({**valid, "head_pan.pos": 0.0})
    with pytest.raises(ValueError, match="must be finite"):
        ARMS_ONLY_SCHEMA.validate({**valid, ARMS_ONLY_SCHEMA.keys[0]: float("nan")})


def test_max_relative_target_accepts_float_dict_or_none_but_not_legacy_int():
    assert validate_relative_target_limit(None, position_keys=ARM_POSITION_KEYS) is None
    assert validate_relative_target_limit(5.0, position_keys=ARM_POSITION_KEYS) == 5.0
    with pytest.raises(TypeError, match="float"):
        validate_relative_target_limit(5, position_keys=ARM_POSITION_KEYS)

    per_joint = dict.fromkeys(ARM_POSITION_KEYS, 2.5)
    assert validate_relative_target_limit(per_joint, position_keys=ARM_POSITION_KEYS) == per_joint
    with pytest.raises(ValueError, match="exactly match"):
        validate_relative_target_limit({ARM_POSITION_KEYS[0]: 2.5}, position_keys=ARM_POSITION_KEYS)


def test_relative_target_limit_clips_arms_and_does_not_change_grippers_or_base():
    targets = dict.fromkeys(ARMS_BASE_SCHEMA.keys, 100.0)
    present = dict.fromkeys(ARM_POSITION_KEYS, 1.0)
    limited = limit_relative_targets(
        targets,
        present,
        5.0,
        position_keys=ARM_POSITION_KEYS,
    )
    assert all(limited[key] == 6.0 for key in ARM_POSITION_KEYS)
    assert limited["left_arm_gripper.pos"] == 100.0
    assert limited["x.vel"] == 100.0

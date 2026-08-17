from pathlib import Path

import pytest

from so101_wrapper import (
    ActionProfile,
    AmazingHandAttachmentConfig,
    BiSO101AmazingFollower,
    BiSO101AmazingFollowerConfig,
    LifecycleState,
    XLerobotAmazingFollower,
    XLerobotAmazingFollowerConfig,
    XLerobotBiSOLeader,
    XLerobotBiSOLeaderConfig,
    dataset_action_features,
)
from so101_wrapper.fakes import FakeAmazingHand, FakeSO101Arm, FakeXLerobotBody


def attachment(side: str) -> AmazingHandAttachmentConfig:
    return AmazingHandAttachmentConfig(
        port=f"fake://{side}",
        calibration_file=Path(f"/fake/{side}.json"),
    )


def robot(
    *,
    profile: ActionProfile = ActionProfile.ARMS_ONLY,
    provenance: bool = True,
    motion_authorized: bool = True,
    max_relative_target=None,
    body=None,
    left=None,
    right=None,
):
    events = []
    body = body or FakeXLerobotBody(events=events)
    left = left or FakeAmazingHand("left", events=events)
    right = right or FakeAmazingHand("right", events=events)
    follower = XLerobotAmazingFollower(
        XLerobotAmazingFollowerConfig(
            id="lv_xlerobot",
            left_hand_config=attachment("left"),
            right_hand_config=attachment("right"),
            action_profile=profile,
            calibration_provenance_verified=provenance,
            motion_authorized=motion_authorized,
            max_relative_target=max_relative_target,
        ),
        body,
        left,
        right,
    )
    return follower, body, left, right, events


def test_calibration_provenance_fails_before_any_backend_preflight_or_io():
    follower, _body, _left, _right, events = robot(provenance=False)
    with pytest.raises(RuntimeError, match="refusing all device I/O"):
        follower.connect()
    assert events == []


def test_motion_authorization_fails_before_any_backend_preflight_or_io():
    follower, _body, _left, _right, events = robot(motion_authorized=False)
    with pytest.raises(RuntimeError, match="not explicitly authorized"):
        follower.connect()
    assert events == []


def test_connect_latches_body_stops_base_and_latches_both_hands_before_enable():
    follower, _body, _left, _right, events = robot()
    follower.connect()
    first_enable = min(index for index, event in enumerate(events) if event.endswith(("enable", "activate")))
    for required in ("body.latch", "body.stop_base", "left_hand.latch", "right_hand.latch"):
        assert events.index(required) < first_enable
    assert follower.is_connected


def test_connect_and_disconnect_are_idempotent():
    follower, _body, _left, _right, events = robot()
    follower.connect()
    connected_events = list(events)
    follower.connect()
    assert events == connected_events
    follower.disconnect()
    disconnected_events = list(events)
    follower.disconnect()
    assert events == disconnected_events
    assert follower.state is LifecycleState.DISCONNECTED


def test_one_hand_activation_failure_rolls_back_body_and_both_hands():
    events = []
    body = FakeXLerobotBody(events=events)
    left = FakeAmazingHand("left", events=events)
    right = FakeAmazingHand("right", events=events, fail_at="activate")
    follower, *_ = robot(body=body, left=left, right=right)
    with pytest.raises(RuntimeError, match="right_hand.activate"):
        follower.connect()
    assert follower.state is LifecycleState.FAULT
    assert not body.active and not body.connected
    assert not left.active and not left.connected
    assert not right.active and not right.connected
    assert any(event.startswith("body.stop:") for event in events)
    assert any(event.startswith("left_hand.stop:") for event in events)
    assert any(event.startswith("right_hand.stop:") for event in events)


def test_arms_only_action_is_12d_and_explicitly_stops_base():
    follower, body, left, right, events = robot(max_relative_target=5.0)
    follower.connect()
    action = dict.fromkeys(follower.action_features, 10.0)
    sent = follower.send_action(action)
    assert len(sent) == 12
    assert set(sent) == set(follower.action_features)
    assert not set(body.base_velocity.values()) - {0.0}
    assert all(body.positions[key] == 5.0 for key in body.positions)
    assert left.grasp == 10.0 and right.grasp == 10.0
    assert events[-3:] == ["body.command", "left_hand.command", "right_hand.command"]
    assert events.index("body.stop_base", events.index("body.observe")) < events.index("body.command")


def test_arms_base_action_is_exactly_15d_and_head_never_enters_action():
    follower, body, _left, _right, _events = robot(profile=ActionProfile.ARMS_BASE)
    follower.connect()
    action = dict.fromkeys(follower.action_features, 0.0)
    action.update({"x.vel": 0.2, "y.vel": -0.1, "theta.vel": 30.0})
    sent = follower.send_action(action)
    assert len(sent) == 15
    assert "head_pan.pos" not in sent
    assert body.base_velocity == {"x.vel": 0.2, "y.vel": -0.1, "theta.vel": 30.0}


def test_invalid_base_velocity_faults_and_stops_the_composite():
    follower, body, left, right, _events = robot(profile=ActionProfile.ARMS_BASE)
    follower.connect()
    action = dict.fromkeys(follower.action_features, 0.0)
    action["x.vel"] = 0.31
    with pytest.raises(ValueError, match="max_base_speed_xy"):
        follower.send_action(action)
    assert follower.state is LifecycleState.FAULT
    assert not body.active and not left.active and not right.active


def test_bimanual_single_arm_composition_uses_same_12d_key_contract():
    events = []
    config = BiSO101AmazingFollowerConfig(
        id="dual",
        left_hand_config=attachment("left"),
        right_hand_config=attachment("right"),
        calibration_provenance_verified=True,
        motion_authorized=True,
        max_relative_target=5.0,
    )
    follower = BiSO101AmazingFollower(
        config,
        FakeSO101Arm(events=events),
        FakeSO101Arm(events=events),
        FakeAmazingHand("left", events=events),
        FakeAmazingHand("right", events=events),
    )
    follower.connect()
    first_enable = min(index for index, event in enumerate(events) if event.endswith(("enable", "activate")))
    assert sum(event.endswith("latch") for event in events[:first_enable]) == 4
    action = dict.fromkeys(follower.action_features, 9.0)
    sent = follower.send_action(action)
    assert len(sent) == 12
    assert set(sent) == set(follower.action_features)
    assert all(value == 5.0 for key, value in sent.items() if not key.endswith("gripper.pos"))


def test_leader_maps_12d_arms_and_optional_3d_base_consistently():
    leader_action = {
        f"{side}_{joint}.pos": 1.0
        for side in ("left", "right")
        for joint in (
            "shoulder_pan",
            "shoulder_lift",
            "elbow_flex",
            "wrist_flex",
            "wrist_roll",
            "gripper",
        )
    }
    arms_only = XLerobotBiSOLeader(XLerobotBiSOLeaderConfig())
    mapped_arms = arms_only.map_action(leader_action)
    assert len(mapped_arms) == 12
    assert list(mapped_arms) == list(dataset_action_features(ActionProfile.ARMS_ONLY))

    arms_base = XLerobotBiSOLeader(XLerobotBiSOLeaderConfig(action_profile=ActionProfile.ARMS_BASE))
    moving = arms_base.map_action(leader_action, pressed_keys={"i", "n"})
    stopped = arms_base.map_action(leader_action, pressed_keys=set())
    assert len(moving) == 15
    assert list(moving) == list(dataset_action_features(ActionProfile.ARMS_BASE))
    assert moving["x.vel"] == 0.2
    assert stopped["x.vel"] == 0.0

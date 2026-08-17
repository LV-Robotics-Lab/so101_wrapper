"""Offline diagnostics. No command in this module opens a real device."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from .config import AmazingHandAttachmentConfig, XLerobotAmazingFollowerConfig
from .controller import XLerobotAmazingFollower
from .fakes import FakeAmazingHand, FakeXLerobotBody
from .schema import ActionProfile


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="so101-wrapper")
    subparsers = parser.add_subparsers(dest="command", required=True)
    doctor = subparsers.add_parser("doctor", help="run the fake-backend lifecycle check")
    doctor.add_argument(
        "--backend",
        choices=("fake",),
        default="fake",
        help="only the no-device fake backend is available from this CLI",
    )
    doctor.add_argument(
        "--profile",
        choices=tuple(profile.value for profile in ActionProfile),
        default=ActionProfile.ARMS_ONLY.value,
    )
    return parser


def _attachment(side: str) -> AmazingHandAttachmentConfig:
    return AmazingHandAttachmentConfig(
        port=f"fake://{side}-hand",
        calibration_file=Path(f"/nonexistent/fake-{side}-calibration.json"),
    )


def run_fake_doctor(profile: ActionProfile) -> dict[str, object]:
    events: list[str] = []
    body = FakeXLerobotBody(events=events)
    left = FakeAmazingHand("left", events=events)
    right = FakeAmazingHand("right", events=events)
    robot = XLerobotAmazingFollower(
        XLerobotAmazingFollowerConfig(
            id="offline-doctor",
            left_hand_config=_attachment("left"),
            right_hand_config=_attachment("right"),
            action_profile=profile,
            calibration_provenance_verified=True,
            motion_authorized=True,
            max_relative_target=5.0,
        ),
        body,
        left,
        right,
    )
    action = dict.fromkeys(robot.action_features, 0.0)
    robot.connect()
    robot.connect()  # prove idempotence
    observation = robot.get_observation()
    sent = robot.send_action(action)
    robot.disconnect()
    robot.disconnect()  # prove idempotence
    return {
        "backend": "fake",
        "device_io": False,
        "profile": profile.value,
        "action_dimension": len(robot.action_features),
        "action_keys": list(robot.action_features),
        "observation_contains_head": {
            "head_pan.pos",
            "head_tilt.pos",
        }.issubset(observation),
        "sent_keys_match_schema": list(sent) == list(robot.action_features),
        "lifecycle": "pass",
        "events": events,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "doctor":
        report = run_fake_doctor(ActionProfile(args.profile))
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    raise AssertionError(f"unhandled command: {args.command}")

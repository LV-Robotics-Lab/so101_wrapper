import importlib
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from so101_wrapper.adapters import AmazingHandControllerAdapter, UnsupportedAmazingHandAPI
from so101_wrapper.config import AmazingHandAttachmentConfig, XLeRobotSourceConfig
from so101_wrapper.source import SourceVerificationError, verify_xlerobot_source


def test_amazinghand_adapter_rejects_missing_public_latch_before_connect(tmp_path):
    calibration = tmp_path / "hand.json"
    calibration.write_text("{}", encoding="utf-8")
    controller = MagicMock(
        is_connected=False,
        is_active=False,
        is_calibrated=True,
        calibration=SimpleNamespace(schema="lv_robotics.amazinghand_calibration.v1"),
    )
    del controller.latch_current_position
    adapter = AmazingHandControllerAdapter(
        controller,
        AmazingHandAttachmentConfig(port="fake://hand", calibration_file=calibration),
    )
    with pytest.raises(UnsupportedAmazingHandAPI, match="public latch_current_position"):
        adapter.offline_validate_calibration("robot", "left")
    controller.connect.assert_not_called()


def test_lerobot_shim_requires_explicit_source_identity(monkeypatch):
    monkeypatch.delenv("SO101_WRAPPER_XLEROBOT_ROOT", raising=False)
    monkeypatch.delenv("SO101_WRAPPER_XLEROBOT_SHA", raising=False)
    shim = importlib.import_module("lerobot_robot_xlerobot_amazing")
    with pytest.raises(RuntimeError, match="configure.*explicitly"):
        _plugin_type = shim.XLerobotAmazingFollower


def _git_source(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "XLeRobot"
    package = root / "software" / "src" / "robots" / "xlerobot"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=CI",
            "-c",
            "user.email=ci@example.invalid",
            "commit",
            "-qm",
            "fixture",
        ],
        check=True,
    )
    sha = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return root, sha


def test_xlerobot_source_requires_exact_full_sha(tmp_path):
    root, sha = _git_source(tmp_path)
    assert verify_xlerobot_source(XLeRobotSourceConfig(root, sha)).name == "xlerobot"
    with pytest.raises(SourceVerificationError, match="does not match"):
        verify_xlerobot_source(XLeRobotSourceConfig(root, "0" * 40))

    package_file = root / "software" / "src" / "robots" / "xlerobot" / "__init__.py"
    package_file.write_text("VALUE = 2\n", encoding="utf-8")
    with pytest.raises(SourceVerificationError, match="tracked modifications"):
        verify_xlerobot_source(XLeRobotSourceConfig(root, sha))

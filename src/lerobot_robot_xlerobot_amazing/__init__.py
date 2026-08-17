"""Lazy compatibility import for the former in-tree LeRobot plugin.

Set ``SO101_WRAPPER_XLEROBOT_ROOT`` and ``SO101_WRAPPER_XLEROBOT_SHA`` to the
explicit Prometheus submodule checkout and pin before importing plugin classes.
No parent-directory search or ``sys.path`` mutation is performed.
"""

from __future__ import annotations

import os
from typing import Any

from so101_wrapper.config import XLeRobotSourceConfig
from so101_wrapper.lerobot import LeRobotPluginTypes, install_lerobot_plugin

_PLUGIN: LeRobotPluginTypes | None = None
_PLUGIN_NAMES = {
    "XLerobotAmazingFollowerConfig",
    "XLerobotAmazingFollower",
    "XLerobotBiSOLeaderConfig",
    "XLerobotBiSOLeader",
}

__all__ = ["configure", *_PLUGIN_NAMES]


def configure(root: str, expected_commit: str) -> LeRobotPluginTypes:
    global _PLUGIN
    if _PLUGIN is None:
        _PLUGIN = install_lerobot_plugin(XLeRobotSourceConfig(root=root, expected_commit=expected_commit))
    return _PLUGIN


def __getattr__(name: str) -> Any:
    if name not in _PLUGIN_NAMES:
        raise AttributeError(name)
    plugin = _PLUGIN
    if plugin is None:
        root = os.environ.get("SO101_WRAPPER_XLEROBOT_ROOT")
        commit = os.environ.get("SO101_WRAPPER_XLEROBOT_SHA")
        if not root or not commit:
            raise RuntimeError(
                "configure the LeRobot shim explicitly with configure(root, full_sha), "
                "or set SO101_WRAPPER_XLEROBOT_ROOT and SO101_WRAPPER_XLEROBOT_SHA"
            )
        plugin = configure(root, commit)
    return getattr(plugin, name)

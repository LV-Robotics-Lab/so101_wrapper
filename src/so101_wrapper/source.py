"""Verified loading of the separately pinned XLeRobot source tree."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

from .config import XLeRobotSourceConfig


class SourceVerificationError(RuntimeError):
    pass


def verify_xlerobot_source(config: XLeRobotSourceConfig) -> Path:
    """Return the package path only when the checkout is exactly the configured SHA."""

    root = config.root
    package_dir = root / "software" / "src" / "robots" / "xlerobot"
    package_file = package_dir / "__init__.py"
    if not package_file.is_file():
        raise SourceVerificationError(f"XLeRobot package is missing: {package_file}")

    try:
        top_level = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        if Path(top_level).resolve() != root:
            raise SourceVerificationError(f"configured XLeRobot root is not the Git checkout root: {root}")
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise SourceVerificationError(f"cannot verify XLeRobot Git identity at {root}: {error}") from error
    actual = result.stdout.strip().lower()
    if actual != config.expected_commit:
        raise SourceVerificationError(
            "XLeRobot checkout does not match the configured pin: "
            f"expected={config.expected_commit}, actual={actual}"
        )
    try:
        dirty = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "status",
                "--porcelain",
                "--untracked-files=no",
                "--",
                "software/src/robots/xlerobot",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as error:
        raise SourceVerificationError(
            f"cannot verify XLeRobot package cleanliness at {root}: {error}"
        ) from error
    if dirty:
        raise SourceVerificationError("XLeRobot package has tracked modifications; refusing to load")
    return package_dir


def load_verified_xlerobot(config: XLeRobotSourceConfig) -> ModuleType:
    """Load XLeRobot without guessing a parent directory or mutating ``sys.path``.

    XLeRobot currently has no installable Python package at the validated commit.
    Loading its package from an explicit, SHA-verified path is therefore isolated to
    this compatibility boundary. The module is registered at the name used by its
    relative imports, but no search path is appended globally.
    """

    package_dir = verify_xlerobot_source(config)
    package_file = package_dir / "__init__.py"
    module_name = "lerobot.robots.xlerobot"

    existing = sys.modules.get(module_name)
    if existing is not None:
        existing_file = Path(getattr(existing, "__file__", "")).resolve()
        if existing_file != package_file.resolve():
            raise SourceVerificationError(
                f"{module_name} is already loaded from an unverified path: {existing_file}"
            )
        return existing

    try:
        import lerobot.robots as lerobot_robots
    except ImportError as error:
        raise ImportError("install the separately pinned LeRobot policy package first") from error

    spec = importlib.util.spec_from_file_location(
        module_name,
        package_file,
        submodule_search_locations=[str(package_dir)],
    )
    if spec is None or spec.loader is None:
        raise SourceVerificationError(f"cannot create a module spec for {package_file}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        lerobot_robots.xlerobot = module
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module

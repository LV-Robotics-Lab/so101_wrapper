from pathlib import Path
from typing import Any

from amazinghand_wrapper import (
    AMAZING_HAND_MOTORS,
    AmazingHandConfig,
    AmazingHandController,
    HandCalibration,
)

from so101_wrapper.adapters import AmazingHandControllerAdapter
from so101_wrapper.config import AmazingHandAttachmentConfig


class FakeBackend:
    def __init__(self) -> None:
        self.positions = dict.fromkeys(range(1, 9), 400)
        self.writes: list[dict[int, int]] = []
        self.torque = False
        self.connected = False

    def connect(self, port: str, baudrate: int) -> None:
        assert port == "fake://left"
        assert baudrate == 1_000_000
        self.connected = True

    def disconnect(self) -> None:
        self.connected = False

    def ping(self, motor_id: int) -> int | None:
        return 1280 if self.connected and motor_id in self.positions else None

    def set_torque(self, enabled: bool) -> None:
        self.torque = enabled

    def read_positions(self) -> dict[int, int]:
        return dict(self.positions)

    def write_positions(self, positions: dict[int, int]) -> None:
        self.positions = dict(positions)
        self.writes.append(dict(positions))

    def latch_current_position(self) -> dict[int, int]:
        current = self.read_positions()
        self.write_positions(current)
        return current

    def read_temperatures(self) -> dict[int, float] | None:
        return dict.fromkeys(self.positions, 25.0)

    def read_loads(self) -> dict[int, float] | None:
        return dict.fromkeys(self.positions, 0.0)


class PublicOnlyController:
    """Raise if the adapter attempts to inspect the controller's backend."""

    def __init__(self, controller: AmazingHandController) -> None:
        object.__setattr__(self, "_controller", controller)

    def __getattr__(self, name: str) -> Any:
        if name == "backend":
            raise AssertionError("so101_wrapper must not access controller.backend")
        return getattr(self._controller, name)


def _calibration(path: Path) -> None:
    HandCalibration(
        open_raw={name: 200 for name in AMAZING_HAND_MOTORS},
        closed_raw={name: 600 for name in AMAZING_HAND_MOTORS},
    ).save(path)


def test_pinned_amazinghand_public_latch_contract_has_no_private_backend_access(tmp_path: Path):
    calibration_file = tmp_path / "left.json"
    _calibration(calibration_file)
    backend = FakeBackend()
    controller = AmazingHandController(
        AmazingHandConfig(port="fake://left", calibration_file=calibration_file),
        backend,
    )
    adapter = AmazingHandControllerAdapter(
        PublicOnlyController(controller),
        AmazingHandAttachmentConfig(
            port="fake://left",
            calibration_file=calibration_file,
        ),
    )

    adapter.offline_validate_calibration("lv_xlerobot", "left")
    adapter.connect_torque_off()
    adapter.latch_current_position()

    assert backend.writes == [dict.fromkeys(range(1, 9), 400)]
    assert backend.torque is False
    adapter.disconnect()

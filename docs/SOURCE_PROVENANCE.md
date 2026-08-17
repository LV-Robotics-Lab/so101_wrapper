# Source provenance

This repository is a clean hardware-boundary extraction of behavior previously
split between the LV Robotics Lab LeRobot fork and its XLeRobot and AmazingHand
dependencies. It copies no submodule contents, workstation data, calibration
payloads, camera captures, or vendor SDKs.

## LeRobot source map

Repository: <https://github.com/LV-Robotics-Lab/lerobot>

Historical main integration commits:

- `c3f16db`, `d0d6c65`, `08ea939`, `95a5c0d`, `845ac9b`

`hardware/amazinghand-so101`-only commits preserved by this extraction:

- `86196b4` — XLeRobot + AmazingHand integration
- `ffe5418` — legacy pair-specific calibration migration procedure
- `5407fcc` — workstation-artifact boundary
- `2e79478` — ignored local data boundary
- `19ee03a` — non-interactive, fail-closed startup
- `858136a`, `574b2a9` — forward merges into the final branch state

Source paths consulted:

- `src/lerobot/robots/so101_amazing_follower/`
- `integrations/lerobot_robot_xlerobot_amazing/src/`
- `tests/robots/test_so101_amazing_follower.py`
- `tests/robots/test_xlerobot_amazing_plugin.py`
- `docs/source/xlerobot_amazinghand.mdx`

Behavior retained or corrected here:

- scalar AmazingHand grasp preserves the conventional six-channel SO-101 side;
- bimanual `arms_only` is exactly 12D;
- mobile `arms_base` is exactly 15D;
- head joints are observation-only;
- robot, teleoperator, and dataset key order is one shared schema;
- the upstream 17-feature declaration versus 12D teleoperator mismatch is removed;
- `max_relative_target` is corrected from XLeRobot's `int | None` annotation to
  `float | dict[str, float] | None` and tested with `5.0`;
- calibration and public latch capabilities fail before device I/O;
- all partial connect, activation, observation, command, and disconnect failures
  trigger composite rollback.

Not migrated:

- `data/README.md` and any ignored `data/so101/` payload;
- `examples/hardware/so101_camera_preview.py` (diagnostic scratch utility);
- either dependency gitlink;
- raw calibration JSON or persistent device paths.

## Dependency identities

- XLeRobot validated source:
  `Vector-Wangel/XLeRobot@3d14695e40c9c68229c0aacffca6053c75cd3eb6`
- AmazingHand validated source:
  `LV-Robotics-Lab/amazinghand_wrapper@3f756af8787e6ee8b2c098a40bd4c60899b9e81c`

Prometheus must pin XLeRobot, this repository, and AmazingHand directly. This
repository records validated identities but deliberately does not make either
dependency a nested submodule.

## Public API boundary

The historical integration latched AmazingHand goals using private
`hand.backend.read_positions()` and `hand.backend.write_positions()` calls. The
validated AmazingHand revision now owns an equivalent public
`latch_current_position()` operation on both its controller and backend protocol.
The adapter requires that capability during offline preflight and refuses to open
hardware when it is absent; it never falls back to private `.backend` access.

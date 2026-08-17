# so101_wrapper

`so101_wrapper` is the LV Robotics Lab hardware boundary for SO-101 arms,
XLeRobot, and AmazingHand end effectors. It preserves a stable policy-facing
schema while keeping vendor drivers and training frameworks in separately pinned
repositories.

This repository does **not** vendor or submodule XLeRobot, AmazingHand, or
LeRobot. A Prometheus hardware branch should pin these siblings directly:

```text
hardware/amazinghand-so101
├── xlerobot                  mechanical layout and body implementation
├── so101_wrapper             composition, schemas, lifecycle, adapters
└── amazinghand_wrapper       hand driver, calibration, health, torque
```

LeRobot remains a policy/training dependency. The optional compatibility shim in
this package can register the historical robot and teleoperator names when that
separately pinned policy package is installed.

## Stable action contracts

| Profile | Dimension | Channels |
| --- | ---: | --- |
| `arms_only` (default) | 12 | 5 SO-101 joints + 1 scalar AmazingHand grasp, per side |
| `arms_base` | 15 | `arms_only` + `x.vel`, `y.vel`, `theta.vel` |

Both robot and leader adapters use exactly the same ordered keys. Head pan/tilt
can be present in observations, but never silently enter either action schema.
An `arms_only` command explicitly stops the base so a 12D policy cannot inherit
a stale velocity target.

`max_relative_target` is deliberately `float | dict[str, float] | None`.
Use `5.0`, not the legacy integer `5`. A dictionary must contain exactly the ten
arm position keys; the scalar grasp and three base velocities have their own
device-specific safeguards.

## Offline doctor

Python 3.10 or newer is supported. The CLI has no real-hardware backend and
therefore cannot open a serial port:

```bash
python -m pip install -e '.[dev]'
so101-wrapper doctor --backend fake --profile arms_only
so101-wrapper doctor --backend fake --profile arms_base
pytest -q
```

The fake doctor exercises preflight, torque-off connect, position latching,
activation, observation, command routing, fail-stop disconnect, and idempotent
connect/disconnect. Passing it is not evidence of live-robot readiness.

## Fail-closed lifecycle

Runtime composition follows this order:

1. Require the operator's calibration-provenance attestation.
2. Require an explicit per-run `motion_authorized=true` gate. The default is
   false and fails before backend preflight or device I/O.
3. Validate all body and hand calibration files, IDs, schemas, and required
   public adapter capabilities without device I/O.
4. Connect the body and both hands with torque off.
5. Latch current arm, head, and hand goals; write zero base velocity.
6. Enable the body, then each hand. Any partial failure stops and disconnects
   every component in reverse order.
7. Any observation or command failure stops the base and faults both hands and
   the body.

`connect()` never reads stdin and never launches interactive calibration.
Calibration is an explicitly supervised workflow outside policy evaluation,
collection, and inference processes.

## Hardware adapters

The core uses injected protocols from `so101_wrapper.protocols`; tests use only
`so101_wrapper.fakes`. A hardware integration must provide public methods for
offline validation, torque-off connect, position latching, activation, emergency
stop, and disconnect.

The AmazingHand adapter intentionally refuses current
`LV-Robotics-Lab/amazinghand_wrapper@c4e7045` before opening its port because that
revision has no public `latch_current_position()` method. The former LeRobot
integration reached through `controller.backend` to write goals. This repository
does not cross that ownership boundary. Update the hand wrapper with the public
operation, pin that new commit, and then clear this live gate.

The XLeRobot loader likewise accepts no guessed relative path. It requires an
explicit checkout root and full Git SHA, verifies `git rev-parse HEAD`, and loads
the package without appending anything to `sys.path`:

```python
from so101_wrapper import XLeRobotSourceConfig, load_verified_xlerobot

source = XLeRobotSourceConfig(
    root="/absolute/path/to/xlerobot",
    expected_commit="3d14695e40c9c68229c0aacffca6053c75cd3eb6",
)
module = load_verified_xlerobot(source)
```

## Optional LeRobot shim

When the separately pinned LeRobot policy environment is active, configure the
former plugin import explicitly:

```python
from lerobot_robot_xlerobot_amazing import configure

types = configure(
    "/absolute/path/to/xlerobot",
    "3d14695e40c9c68229c0aacffca6053c75cd3eb6",
)
```

The shim registers `xlerobot_amazing_follower` and
`xlerobot_bi_so_leader`, then delegates lifecycle and schema enforcement to this
wrapper. Environment variables `SO101_WRAPPER_XLEROBOT_ROOT` and
`SO101_WRAPPER_XLEROBOT_SHA` are supported for LeRobot's import-based discovery,
but both are mandatory; there is no fallback search.

## Live validation still required

Before collection or inference on the exact rig, complete and record:

- persistent udev paths for both body buses, both hands, leaders, and cameras;
- pair-specific body/hand calibration provenance and device-side identity;
- the new public AmazingHand goal-latch API and its torque-off ordering test;
- read-only device probes, low-speed bounded motion, and base zeroing;
- camera frame/geometry checks, physical emergency-stop rehearsal, and soak test;
- one 12D collection/replay test and, separately, one guarded 15D base test.

No live hardware validation is claimed by this repository's CI.

## Provenance and license

See [`docs/SOURCE_PROVENANCE.md`](docs/SOURCE_PROVENANCE.md) for the exact source
paths and commit map. The migrated behavior and this reimplementation are
Apache-2.0; upstream copyright and license notices are preserved in `NOTICE`.

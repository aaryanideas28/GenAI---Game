"""Tests for vertical.py (Teammate 3). No camera needed."""

from types import SimpleNamespace

import pytest

import vertical
from event_bus import (
    EVENT_ACTION,
    EVENT_CALIBRATE,
    EVENT_CALIBRATED,
    EVENT_POSE_FRAME,
    EventBus,
)
from vision import build_pose_frame

W, H = 640, 480


def make_frame(t, y=0.5, width=0.2, detected=True):
    """PoseFrame with shoulders at height y and the given normalized width."""
    if not detected:
        return build_pose_frame(None, W, H, t)
    lms = [SimpleNamespace(x=0.5, y=0.3, visibility=1.0) for _ in range(33)]
    lms[11] = SimpleNamespace(x=0.5 - width / 2, y=y, visibility=1.0)
    lms[12] = SimpleNamespace(x=0.5 + width / 2, y=y, visibility=1.0)
    return build_pose_frame(lms, W, H, t)


class Harness:
    def __init__(self):
        self.bus = EventBus()
        vertical.register(self.bus)
        self.actions, self.calibrated = [], []
        self.bus.subscribe(EVENT_ACTION, lambda p: self.actions.append(p["action"]))
        self.bus.subscribe(EVENT_CALIBRATED, lambda p: self.calibrated.append(p["module"]))
        self.t = 0.0

    def feed(self, y=0.5, n=1, width=0.2, detected=True):
        for _ in range(n):
            self.t += 0.04
            self.bus.publish(EVENT_POSE_FRAME, make_frame(self.t, y, width, detected))

    def calibrate(self):
        self.bus.publish(EVENT_CALIBRATE, {"timestamp": self.t})
        self.feed(0.5, n=vertical.CALIBRATION_FRAMES + 2)


@pytest.fixture
def h():
    return Harness()


def test_no_action_before_calibration(h):
    h.feed(0.3, n=10)
    h.feed(0.7, n=10)
    assert h.actions == []


def test_calibration_publishes_event(h):
    h.calibrate()
    assert h.calibrated == ["vertical"]


def test_jump_fires_once(h):
    h.calibrate()
    h.feed(0.5, n=5)
    h.feed(0.38, n=15)  # stays up for a long time
    assert h.actions == ["JUMP"]


def test_crouch_fires_once(h):
    h.calibrate()
    h.feed(0.62, n=20)
    assert h.actions == ["CROUCH"]


def test_crouch_needs_hold_frames(h):
    h.calibrate()
    h.feed(0.65, n=1)
    h.feed(0.5, n=10)
    assert h.actions == []


def test_rearm_after_return_to_neutral(h):
    h.calibrate()
    h.feed(0.38, n=5)
    h.feed(0.5, n=30)  # back to neutral + cooldown passes
    h.feed(0.38, n=5)
    assert h.actions == ["JUMP", "JUMP"]


def test_cooldown_blocks_rapid_repeat(h):
    h.calibrate()
    h.feed(0.38, n=3)
    h.feed(0.5, n=3)  # re-armed but still inside cooldown (~0.5 s total < 0.6 s)
    h.feed(0.38, n=2)
    assert h.actions == ["JUMP"]


def test_stepping_closer_is_not_a_crouch(h):
    h.calibrate()
    h.feed(0.62, n=15, width=0.30)  # wider AND lower = closer to camera
    assert h.actions == []


def test_small_wobble_ignored(h):
    h.calibrate()
    for y in (0.48, 0.52, 0.47, 0.53) * 10:
        h.feed(y)
    assert h.actions == []


def test_pose_lost_never_fires_and_recovers(h):
    h.calibrate()
    h.feed(detected=False, n=10)
    assert h.actions == []
    h.feed(0.38, n=5)
    assert h.actions == ["JUMP"]


def test_recalibrate_resets_baseline(h):
    h.calibrate()
    h.bus.publish(EVENT_CALIBRATE, {"timestamp": h.t})
    h.feed(0.6, n=vertical.CALIBRATION_FRAMES + 2)  # new standing height = 0.6
    assert h.calibrated == ["vertical", "vertical"]
    h.feed(0.6, n=10)
    assert h.actions == []  # 0.6 is now neutral, not a crouch
    h.feed(0.48, n=5)       # 0.12 rise at width 0.2 = 0.6 widths -> jump
    assert h.actions == ["JUMP"]


def test_hud_threshold_lines(h):
    assert vertical._module.jump_line_y() is None
    h.calibrate()
    m = vertical._module
    assert m.jump_line_y() < m.baseline_y < m.crouch_line_y()


def test_crouch_with_natural_forward_lean(h):
    """When squatting, shoulders naturally lean forward (+20% width). Must still fire CROUCH on deliberate squat."""
    h.calibrate()
    # Baseline is y=0.5, width=0.20. Drop to y=0.64 with forward lean width=0.24 (+20% width, drop = 0.583 widths > 0.50)
    h.feed(0.64, n=15, width=0.24)
    assert h.actions == ["CROUCH"]


def test_slight_dip_ignored_and_deliberate_squat_fires(h):
    """Slight dip (0.32 widths) is ignored under widened 0.50 threshold; deliberate squat (0.60 widths) fires CROUCH."""
    h.calibrate()
    h.feed(0.565, n=10)
    assert h.actions == []
    h.feed(0.62, n=10)
    assert h.actions == ["CROUCH"]


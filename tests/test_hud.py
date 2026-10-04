"""Tests for Teammate 5: HUD and camera overlays (hud.py)."""

from __future__ import annotations

from types import SimpleNamespace
import numpy as np
import pytest

import event_bus as eb
import hud
from vision import build_pose_frame


def make_dummy_frame(width=640, height=480):
    return np.zeros((height, width, 3), dtype=np.uint8)


def make_dummy_pose_frame(width=640, height=480, shoulder_w=0.2):
    lms = [SimpleNamespace(x=0.5, y=0.5, visibility=1.0) for _ in range(33)]
    lms[11] = SimpleNamespace(x=0.5 - shoulder_w / 2, y=0.5, visibility=1.0)
    lms[12] = SimpleNamespace(x=0.5 + shoulder_w / 2, y=0.5, visibility=1.0)
    return build_pose_frame(lms, width, height, 100.0, make_dummy_frame(width, height))


def test_draw_lane_dividers():
    img = make_dummy_frame()
    hud.draw_lane_dividers(img, center_x=0.5, threshold=0.07)

    # Cyan is (255, 255, 0) in BGR
    # x_left = int(round(0.43 * 640)) = 275
    # x_right = int(round(0.57 * 640)) = 365
    left_x = int(round(0.43 * 640))
    right_x = int(round(0.57 * 640))

    assert (img[240, left_x] == hud.COLOR_LANE_DIVIDER).all()
    assert (img[240, right_x] == hud.COLOR_LANE_DIVIDER).all()
    # Center should remain clean/untouched
    assert (img[240, 320] == [0, 0, 0]).all()


def test_draw_threshold_lines():
    img = make_dummy_frame()
    jump_y, base_y, crouch_y = 0.35, 0.50, 0.65
    hud.draw_threshold_lines(img, jump_y=jump_y, base_y=base_y, crouch_y=crouch_y)

    py_jump = int(round(jump_y * 480))
    py_base = int(round(base_y * 480))
    py_crouch = int(round(crouch_y * 480))

    # Test pixels on the 1px lines (outside text area)
    assert (img[py_jump, 50] == hud.COLOR_JUMP_LINE).all()
    assert (img[py_base, 50] == hud.COLOR_STAND_LINE).all()
    assert (img[py_crouch, 50] == hud.COLOR_CROUCH_LINE).all()


def test_draw_threshold_lines_none_safe():
    img = make_dummy_frame()
    # Should not throw when uncalibrated / None
    hud.draw_threshold_lines(img, jump_y=None, base_y=None, crouch_y=None)
    assert img.sum() == 0


def test_draw_status_panel():
    img = make_dummy_frame()
    hud.draw_status_panel(img, lane="LEFT", action="JUMP", fps=30.0, cooldown=0.25, tracked=True)
    # Status panel should have drawn text
    assert img.sum() > 0
    # No large blackout: the majority of the frame should remain untouched
    non_zero_ratio = (img > 0).mean()
    assert non_zero_ratio < 0.05  # subtle, crisp text uses less than 5% of pixels


def test_hud_module_event_subscriptions():
    bus = eb.EventBus()
    module = hud.register(bus)

    assert module.lane == "CENTER"
    assert module.current_action() == "-"

    # Publish lane change
    bus.publish(eb.EVENT_LANE_CHANGED, eb.make_lane_event("RIGHT", 10.0))
    assert module.lane == "RIGHT"

    # Publish action
    bus.publish(eb.EVENT_ACTION, eb.make_action_event("CROUCH", 10.1))
    assert module.current_action(now=10.2) == "CROUCH"
    # Action fades after timeout
    assert module.current_action(now=12.0) == "-"


def test_hud_render_full_frame():
    bus = eb.EventBus()
    module = hud.register(bus)
    pf = make_dummy_pose_frame()

    # Mock horizontal and vertical modules
    h_tracker = SimpleNamespace(center_x=0.5, threshold=0.07)
    v_module = SimpleNamespace(
        calibrated=True,
        jump_line_y=lambda: 0.35,
        baseline_y=0.50,
        crouch_line_y=lambda: 0.65,
        detector=SimpleNamespace(cooldown_remaining=lambda now: 0.0),
    )

    rendered = module.render(
        pf.frame,
        pose_frame=pf,
        horizontal_tracker=h_tracker,
        vertical_module=v_module,
        fps=30.0,
    )

    assert rendered.shape == pf.frame.shape
    assert rendered.sum() > 0
    # Original frame must be unmodified
    assert pf.frame.sum() == 0


def test_no_camera_blackout_or_countdown():
    """Verify camera feed is NOT darkened by blackout boxes or countdown circles."""
    bus = eb.EventBus()
    module = hud.register(bus)
    frame = np.full((480, 640, 3), 128, dtype=np.uint8)

    rendered = module.render(frame, fps=30.0)
    # If there was a blackout or full-screen overlay, mean brightness would plummet significantly
    assert rendered.mean() > 120  # Brightness preserved; no darkening overlay

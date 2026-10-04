"""Tests for Teammate 2: Horizontal Movement Logic."""

from __future__ import annotations

import numpy as np
import pytest

import event_bus as eb
from horizontal import HorizontalTracker, register
from vision import NUM_LANDMARKS, build_pose_frame


class MockLandmark:

    def __init__(self, x: float, y: float, visibility: float = 1.0) -> None:
        self.x = x
        self.y = y
        self.visibility = visibility


def make_test_pose_frame(
    left_x: float = 0.4,
    right_x: float = 0.6,
    y: float = 0.4,
    timestamp: float = 100.0,
):
    """Helper to generate synthetic PoseFrame with specific shoulder X coordinates."""
    lms = [MockLandmark(0.5, 0.5) for _ in range(NUM_LANDMARKS)]
    lms[11] = MockLandmark(left_x, y)  # LEFT_SHOULDER
    lms[12] = MockLandmark(right_x, y)  # RIGHT_SHOULDER
    return build_pose_frame(lms, 640, 480, timestamp, np.zeros((480, 640, 3), np.uint8))


def test_initial_auto_calibration():
    bus = eb.EventBus()
    tracker = HorizontalTracker(bus, threshold=0.1)

    # Initial frame with mid_shoulder_x = 0.5
    pf = make_test_pose_frame(left_x=0.4, right_x=0.6)
    tracker.on_pose_frame(pf)

    assert tracker.is_calibrated is True
    assert tracker.center_x == pytest.approx(0.5)
    assert tracker.current_lane == eb.LANE_CENTER


def test_recalibration_via_event(capsys):
    bus = eb.EventBus()
    tracker = HorizontalTracker(bus, threshold=0.1)
    calibrated_events = []

    bus.subscribe(eb.EVENT_CALIBRATED, calibrated_events.append)

    # Frame 1: center at 0.5
    pf1 = make_test_pose_frame(left_x=0.4, right_x=0.6, timestamp=10.0)
    tracker.on_pose_frame(pf1)
    assert tracker.center_x == pytest.approx(0.5)

    # Move player to 0.7 and trigger calibration ('c' key)
    pf2 = make_test_pose_frame(left_x=0.6, right_x=0.8, timestamp=11.0)
    tracker.on_pose_frame(pf2)

    tracker.on_calibrate({"timestamp": 12.0})

    assert tracker.center_x == pytest.approx(0.7)
    assert len(calibrated_events) == 2  # 1 initial auto-cal + 1 manual cal
    assert calibrated_events[-1] == {"module": "horizontal", "timestamp": 12.0}


def test_lane_transitions_left_right_center(capsys):
    bus = eb.EventBus()
    tracker = HorizontalTracker(bus, threshold=0.1, hysteresis=0.02)
    lane_events = []

    bus.subscribe(eb.EVENT_LANE_CHANGED, lane_events.append)

    # 1. Calibrate standing at mid_x = 0.5
    pf_center = make_test_pose_frame(left_x=0.4, right_x=0.6, timestamp=1.0)
    tracker.on_pose_frame(pf_center)
    assert tracker.current_lane == eb.LANE_CENTER

    # 2. Shift left: mid_x = 0.35 (dx = -0.15, threshold = 0.1)
    pf_left = make_test_pose_frame(left_x=0.25, right_x=0.45, timestamp=2.0)
    tracker.on_pose_frame(pf_left)

    captured = capsys.readouterr()
    assert "LANE: LEFT" in captured.out
    assert tracker.current_lane == eb.LANE_LEFT
    assert len(lane_events) == 1
    assert lane_events[-1] == {"lane": "LEFT", "timestamp": 2.0}

    # 3. Shift right: mid_x = 0.65 (dx = +0.15)
    pf_right = make_test_pose_frame(left_x=0.55, right_x=0.75, timestamp=3.0)
    tracker.on_pose_frame(pf_right)

    captured = capsys.readouterr()
    assert "LANE: RIGHT" in captured.out
    assert tracker.current_lane == eb.LANE_RIGHT
    assert len(lane_events) == 2
    assert lane_events[-1] == {"lane": "RIGHT", "timestamp": 3.0}

    # 4. Return to center: mid_x = 0.50
    pf_center2 = make_test_pose_frame(left_x=0.4, right_x=0.6, timestamp=4.0)
    tracker.on_pose_frame(pf_center2)

    captured = capsys.readouterr()
    assert "LANE: CENTER" in captured.out
    assert tracker.current_lane == eb.LANE_CENTER
    assert len(lane_events) == 3
    assert lane_events[-1] == {"lane": "CENTER", "timestamp": 4.0}


def test_no_duplicate_lane_events_on_same_movement():
    bus = eb.EventBus()
    tracker = HorizontalTracker(bus, threshold=0.1)
    lane_events = []

    bus.subscribe(eb.EVENT_LANE_CHANGED, lane_events.append)

    # Initial frame
    tracker.on_pose_frame(make_test_pose_frame(left_x=0.4, right_x=0.6, timestamp=1.0))

    # Move left once
    tracker.on_pose_frame(make_test_pose_frame(left_x=0.2, right_x=0.4, timestamp=2.0))
    assert len(lane_events) == 1

    # Stay left for 10 consecutive frames
    for i in range(10):
        tracker.on_pose_frame(make_test_pose_frame(left_x=0.2, right_x=0.4, timestamp=3.0 + i))

    # Events list must still be 1 (no spamming!)
    assert len(lane_events) == 1


def test_register_subscribes_to_bus():
    bus = eb.EventBus()
    t = register(bus)

    lane_events = []
    bus.subscribe(eb.EVENT_LANE_CHANGED, lane_events.append)

    # Publish pose frame via bus
    pf_center = make_test_pose_frame(left_x=0.4, right_x=0.6, timestamp=1.0)
    bus.publish(eb.EVENT_POSE_FRAME, pf_center)

    # Publish shifted frame via bus
    pf_left = make_test_pose_frame(left_x=0.2, right_x=0.4, timestamp=2.0)
    bus.publish(eb.EVENT_POSE_FRAME, pf_left)

    assert len(lane_events) == 1
    assert lane_events[0]["lane"] == "LEFT"

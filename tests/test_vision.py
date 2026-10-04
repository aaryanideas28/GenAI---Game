"""Webcam-free tests: everything uses synthetic landmarks."""

from __future__ import annotations

import math
import sys
import types
from dataclasses import FrozenInstanceError, dataclass

import numpy as np
import pytest

import event_bus as eb
import main
import vision


@dataclass
class LM:
    x: float = 0.5
    y: float = 0.5
    visibility: float = 1.0


def make_landmarks(nose=(0.5, 0.2), left=(0.4, 0.4), right=(0.6, 0.4), vis=1.0):
    lms = [LM(0.5, 0.5, vis) for _ in range(vision.NUM_LANDMARKS)]
    lms[vision.NOSE] = LM(*nose, vis)
    lms[vision.LEFT_SHOULDER] = LM(*left, vis)
    lms[vision.RIGHT_SHOULDER] = LM(*right, vis)
    return lms


def make_pf(**kw):
    return vision.build_pose_frame(make_landmarks(**kw), 640, 480, 123.0, np.zeros((480, 640, 3), np.uint8))


# --- PoseFrame / landmarks ---------------------------------------------------
def test_mid_shoulder_and_pixels():
    pf = make_pf(left=(0.3, 0.4), right=(0.7, 0.6))
    assert pf.pose_detected
    assert pf.mid_shoulder == pytest.approx((0.5, 0.5))
    assert pf.mid_shoulder_px == (320, 240)
    assert pf.nose == pytest.approx((0.5, 0.2))


def test_shoulder_width():
    pf = make_pf(left=(0.3, 0.4), right=(0.7, 0.4))
    assert pf.shoulder_width == pytest.approx(0.4)
    pf2 = make_pf(left=(0.0, 0.0), right=(0.3, 0.4))
    assert pf2.shoulder_width == pytest.approx(math.hypot(0.3, 0.4))


def test_shoulder_width_grows_when_closer():
    far = make_pf(left=(0.45, 0.4), right=(0.55, 0.4))
    near = make_pf(left=(0.30, 0.4), right=(0.70, 0.4))
    assert near.shoulder_width > far.shoulder_width


def test_shoulder_visibility_is_min():
    lms = make_landmarks()
    lms[vision.LEFT_SHOULDER].visibility = 0.9
    lms[vision.RIGHT_SHOULDER].visibility = 0.3
    pf = vision.build_pose_frame(lms, 640, 480, 0.0)
    assert pf.shoulder_visibility == pytest.approx(0.3)


def test_no_stale_data_when_pose_lost():
    good = make_pf()
    lost = vision.build_pose_frame(None, 640, 480, 124.0)
    assert good.pose_detected and not lost.pose_detected
    for field in ("landmarks", "nose", "left_shoulder", "right_shoulder",
                  "mid_shoulder", "mid_shoulder_px", "shoulder_width"):
        assert getattr(lost, field) is None
    assert lost.shoulder_visibility == 0.0


def test_poseframe_is_frozen_and_to_dict_complete():
    pf = make_pf()
    with pytest.raises(FrozenInstanceError):
        pf.pose_detected = False  # type: ignore[misc]
    d = pf.to_dict()
    for key in ("frame_width", "frame_height", "timestamp", "pose_detected", "landmarks", "nose",
                "left_shoulder", "right_shoulder", "mid_shoulder", "mid_shoulder_px",
                "shoulder_visibility", "shoulder_width", "frame"):
        assert key in d


# --- Payload helpers ---------------------------------------------------------
def test_horizontal_payload():
    p = vision.get_horizontal_payload(make_pf())
    assert set(p) >= {"pose_detected", "mid_shoulder_x", "mid_shoulder_y", "frame_width",
                      "frame_height", "timestamp", "shoulder_width"}
    assert p["mid_shoulder_x"] == pytest.approx(0.5)


def test_vertical_payload():
    p = vision.get_vertical_payload(make_pf())
    assert set(p) == {"pose_detected", "mid_shoulder_y", "nose_y", "shoulder_width", "timestamp"}
    assert p["nose_y"] == pytest.approx(0.2)
    assert p["mid_shoulder_y"] == pytest.approx(0.4)


def test_payloads_when_no_pose():
    lost = vision.build_pose_frame(None, 640, 480, 1.0)
    h = vision.get_horizontal_payload(lost)
    v = vision.get_vertical_payload(lost)
    assert h["pose_detected"] is False and h["mid_shoulder_x"] is None
    assert v["pose_detected"] is False and v["mid_shoulder_y"] is None and v["nose_y"] is None


# --- Event contract ----------------------------------------------------------
def test_event_constants_unique():
    names = [eb.EVENT_POSE_FRAME, eb.EVENT_POSE_LOST, eb.EVENT_POSE_FOUND, eb.EVENT_CALIBRATE,
             eb.EVENT_CALIBRATED, eb.EVENT_LANE_CHANGED, eb.EVENT_ACTION]
    assert len(set(names)) == len(names)
    assert eb.EVENT_POSE_FRAME == "pose_frame"
    assert eb.EVENT_LANE_CHANGED == "lane_changed"
    assert eb.EVENT_ACTION == "action"


def test_event_payload_shapes():
    assert eb.make_lane_event("LEFT", 1.0) == {"lane": "LEFT", "timestamp": 1.0}
    assert eb.make_action_event("JUMP", 2.0) == {"action": "JUMP", "timestamp": 2.0}
    assert eb.make_calibrated_event("horizontal", 3.0) == {"module": "horizontal", "timestamp": 3.0}
    with pytest.raises(ValueError):
        eb.make_lane_event("UP", 0.0)
    with pytest.raises(ValueError):
        eb.make_action_event("DANCE", 0.0)


def test_bus_delivers_and_isolates_errors():
    bus = eb.EventBus()
    got = []

    def bad(_):
        raise RuntimeError("boom")

    bus.subscribe("x", bad)
    bus.subscribe("x", got.append)
    bus.publish("x", 42)
    assert got == [42]


def test_bus_unsubscribe_and_clear():
    bus = eb.EventBus()
    got = []
    bus.subscribe("x", got.append)
    assert bus.unsubscribe("x", got.append)
    bus.publish("x", 1)
    assert got == []
    bus.subscribe("x", got.append)
    bus.clear()
    bus.publish("x", 2)
    assert got == []


def test_bus_rejects_non_callable():
    with pytest.raises(TypeError):
        eb.EventBus().subscribe("x", 123)  # type: ignore[arg-type]


# --- Plugin loader -----------------------------------------------------------
def _install_fake(name, register):
    mod = types.ModuleType(name)
    if register is not None:
        mod.register = register
    sys.modules[name] = mod


def test_plugin_loader_isolates_crashing_and_missing_modules():
    calls = []

    def ok_register(bus):
        bus.subscribe("ping", lambda p: calls.append(p))

    def crash_register(bus):
        raise RuntimeError("teammate bug")

    _install_fake("fake_ok", ok_register)
    _install_fake("fake_crash", crash_register)
    _install_fake("fake_noreg", None)

    bus = eb.EventBus()
    status = main.load_teammate_modules(
        bus, ("fake_crash", "fake_missing_module", "fake_noreg", "fake_ok"))
    assert status == {"fake_crash": False, "fake_missing_module": False,
                      "fake_noreg": False, "fake_ok": True}
    bus.publish("ping", 1)
    assert calls == [1]


def test_register_module_returns_false_on_error():
    def bad(bus):
        raise ValueError("x")
    assert main.register_module(eb.EventBus(), "bad", bad) is False


def test_stub_modules_load_cleanly():
    bus = eb.EventBus()
    status = main.load_teammate_modules(bus, main.TEAMMATE_MODULES)
    assert all(status.values()), status
    # events flow into stubs without errors
    bus.publish(eb.EVENT_LANE_CHANGED, eb.make_lane_event("LEFT", 0.0))
    bus.publish(eb.EVENT_ACTION, eb.make_action_event("JUMP", 0.0))
    bus.publish(eb.EVENT_CALIBRATE, {"timestamp": 0.0})


def test_overlay_state_tracks_events():
    st = main.OverlayState()
    st.on_lane({"lane": "RIGHT"})
    st.on_action({"action": "JUMP"})
    st.on_calibrated({"module": "vertical"})
    text = " ".join(st.lines())
    assert "RIGHT" in text and "JUMP" in text and "vertical" in text


# --- Overlay -----------------------------------------------------------------
def test_draw_debug_with_and_without_pose():
    pipe = vision.VisionPipeline()
    pf = make_pf()
    out = pipe.draw_debug(pf.frame, pf, ["LANE: LEFT"])
    assert out.shape == pf.frame.shape and not np.array_equal(out, pf.frame)
    assert pf.frame.sum() == 0  # original untouched

    lost = vision.build_pose_frame(None, 640, 480, 0.0, np.zeros((480, 640, 3), np.uint8))
    out2 = pipe.draw_debug(lost.frame, lost)
    assert out2.shape == lost.frame.shape


def test_read_requires_start():
    with pytest.raises(RuntimeError):
        vision.VisionPipeline().read()
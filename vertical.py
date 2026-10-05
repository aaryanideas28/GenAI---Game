"""TEAMMATE 3: JUMP / CROUCH detection.

Contract (see event_bus.py):

* Subscribes to EVENT_POSE_FRAME and reads vision.get_vertical_payload(pose_frame).
* Subscribes to EVENT_CALIBRATE ('c' key): averages the standing posture over the
  next CALIBRATION_FRAMES valid frames, then publishes EVENT_CALIBRATED
  (make_calibrated_event("vertical", ts)).
* Publishes EVENT_ACTION (make_action_event) with "JUMP" or "CROUCH", ONCE per gesture.

How it works
------------
Image y grows DOWNWARD, so jumping = mid-shoulder y decreases, crouching = it increases.
The offset from the standing baseline is measured in SHOULDER-WIDTHS, so it does not
depend on body size or distance to the camera. If the current shoulder width differs
from the calibrated one by more than DEPTH_TOLERANCE, the player stepped closer /
farther (not a squat) and vertical actions are suppressed.

Public API for Teammate 5's HUD (all read-only):
    module.baseline_y, module.baseline_width, module.calibrated, module.cooldown_remaining(now)
    jump_line_y()  / crouch_line_y()  -> normalized y of the threshold lines
"""

from __future__ import annotations

import logging
import statistics
from typing import Any

from event_bus import (
    ACTION_CROUCH,
    ACTION_JUMP,
    EVENT_ACTION,
    EVENT_CALIBRATE,
    EVENT_CALIBRATED,
    EVENT_POSE_FRAME,
    EventBus,
    make_action_event,
    make_calibrated_event,
)
from vision import PoseFrame, get_vertical_payload

logger = logging.getLogger("vertical")

# ---- Tunables (adjust while testing live) -----------------------------------
JUMP_THRESHOLD: float = 0.28       # shoulders must rise this many shoulder-widths (deliberate jump)
CROUCH_THRESHOLD: float = 0.28     # shoulders must drop this many shoulder-widths (deliberate squat)
REARM_BAND: float = 0.16           # must return within this of baseline to re-arm
CROUCH_HOLD_FRAMES: int = 2        # crouch must persist 2 frames (~60ms) for responsive rolls
COOLDOWN_S: float = 0.35           # minimum seconds between two actions
SMOOTH_ALPHA: float = 0.65         # EMA smoothing (1.0 = none)
DEPTH_TOLERANCE: float = 0.45      # max width ratio increase for stepping closer
CALIBRATION_FRAMES: int = 15       # valid frames averaged on 'c' (~0.5 s at 30 FPS)
MAX_CALIBRATION_GAP_S: float = 3.0  # abort calibration if no valid pose for this long
DRIFT_ALPHA: float = 0.015         # slow neutral baseline tracking to prevent drift lockout



class VerticalDetector:
    """Pure logic (no bus, no camera): feed it payload dicts, get actions back."""

    def __init__(self) -> None:
        self.baseline_y: float | None = None
        self.baseline_width: float | None = None
        self.calibrated: bool = False
        self.y_rel: float = 0.0
        self.depth_ok: bool = True
        self._smooth: float = 0.0
        self._crouch_frames: int = 0
        self._armed: bool = True
        self._last_action_t: float = float("-inf")
        self._prev_y: float | None = None

    # -- calibration ---------------------------------------------------------
    def set_baseline(self, y: float, width: float) -> None:
        self.baseline_y, self.baseline_width = y, width
        self.calibrated = True
        self._smooth = 0.0
        self._crouch_frames = 0
        self._armed = True
        self._prev_y = None

    def reset(self) -> None:
        """Forget calibration (called when 'c' is pressed so no action fires mid-calibration)."""
        self.calibrated = False
        self._crouch_frames = 0
        self._prev_y = None

    # -- per frame -----------------------------------------------------------
    def cooldown_remaining(self, now: float) -> float:
        return max(0.0, COOLDOWN_S - (now - self._last_action_t))

    def update(self, payload: dict[str, Any]) -> str | None:
        """Return "JUMP", "CROUCH" or None for this frame."""
        if not self.calibrated or not payload.get("pose_detected"):
            self._crouch_frames = 0
            self._prev_y = None
            return None
        y, width = payload.get("mid_shoulder_y"), payload.get("shoulder_width")
        if y is None or not width or width < 1e-3:
            self._crouch_frames = 0
            self._prev_y = None
            return None
        now = payload["timestamp"]

        # Vertical velocity: positive = moving down, negative = moving up
        dy = (y - self._prev_y) if self._prev_y is not None else 0.0
        self._prev_y = y

        # Stepping significantly closer to camera expands apparent shoulder width.
        # When ratio > 1.35 (e.g. +50% in test_stepping_closer_is_not_a_crouch), suppress crouch.
        ratio = width / self.baseline_width if self.baseline_width else 1.0
        self.depth_ok = (ratio <= 1.0 + DEPTH_TOLERANCE)

        # Distance-invariant vertical offset in units of current shoulder width, smoothed.
        raw = (y - self.baseline_y) / width
        self._smooth = SMOOTH_ALPHA * raw + (1.0 - SMOOTH_ALPHA) * self._smooth
        self.y_rel = rel = self._smooth

        # Adaptive baseline: gently track standing height while in neutral posture (|raw| < 0.18).
        # This prevents player posture drift or standing up after launch from causing lockouts.
        if abs(raw) < 0.18 and self.depth_ok:
            self.baseline_y = (1.0 - DRIFT_ALPHA) * self.baseline_y + DRIFT_ALPHA * y
            if self.baseline_width:
                self.baseline_width = (1.0 - DRIFT_ALPHA) * self.baseline_width + DRIFT_ALPHA * width

        # Re-arm when returning near neutral posture
        if abs(rel) < REARM_BAND:
            self._armed = True
            self._crouch_frames = 0

        # Crouch hold tracking:
        # Crucial: if player is moving UPWARD (dy < -0.004), they are pushing off into a JUMP
        # or standing back up. Moving upward immediately cancels crouch accumulation!
        is_moving_up = (dy < -0.004)
        if rel > CROUCH_THRESHOLD and self.depth_ok and not is_moving_up:
            self._crouch_frames += 1
        else:
            self._crouch_frames = 0

        if not self._armed or self.cooldown_remaining(now) > 0.0:
            return None

        action: str | None = None
        if rel < -JUMP_THRESHOLD:
            action = ACTION_JUMP
        elif self._crouch_frames >= CROUCH_HOLD_FRAMES:
            action = ACTION_CROUCH

        if action:
            self._armed = False
            self._last_action_t = now
            self._crouch_frames = 0
        return action


class VerticalModule:
    """Wires VerticalDetector to the event bus."""

    def __init__(self, bus: EventBus) -> None:
        self.bus = bus
        self.detector = VerticalDetector()
        self._calibrating: bool = False
        self._samples: list[tuple[float, float]] = []
        self._last_valid_t: float = 0.0

    # -- HUD helpers (Teammate 5) -------------------------------------------
    @property
    def calibrated(self) -> bool:
        return self.detector.calibrated

    @property
    def baseline_y(self) -> float | None:
        return self.detector.baseline_y

    def jump_line_y(self) -> float | None:
        d = self.detector
        if not d.calibrated:
            return None
        return d.baseline_y - JUMP_THRESHOLD * d.baseline_width

    def crouch_line_y(self) -> float | None:
        d = self.detector
        if not d.calibrated:
            return None
        return d.baseline_y + CROUCH_THRESHOLD * d.baseline_width

    # -- bus callbacks -------------------------------------------------------
    def on_calibrate(self, payload: Any) -> None:
        self.detector.reset()
        self._calibrating = True
        self._samples = []
        self._last_valid_t = float((payload or {}).get("timestamp", 0.0))
        logger.info("Vertical calibration started: stand straight.")

    def on_pose_frame(self, pose_frame: PoseFrame) -> None:
        payload = get_vertical_payload(pose_frame)
        if self._calibrating:
            self._collect(payload)
            return
        action = self.detector.update(payload)
        if action:
            logger.info("ACTION: %s", action)
            self.bus.publish(EVENT_ACTION, make_action_event(action, payload["timestamp"]))

    def _collect(self, payload: dict[str, Any]) -> None:
        ts = payload["timestamp"]
        y, width = payload.get("mid_shoulder_y"), payload.get("shoulder_width")
        if payload.get("pose_detected") and y is not None and width and width > 1e-3:
            self._samples.append((y, width))
            self._last_valid_t = ts
        elif self._last_valid_t and ts - self._last_valid_t > MAX_CALIBRATION_GAP_S:
            self._calibrating = False  # user left the frame; they can press 'c' again
            logger.warning("Vertical calibration aborted: no pose. Press 'c' again.")
            return
        if len(self._samples) >= CALIBRATION_FRAMES:
            ys = [s[0] for s in self._samples]
            ws = [s[1] for s in self._samples]
            self.detector.set_baseline(statistics.median(ys), statistics.median(ws))
            self._calibrating = False
            logger.info("Vertical calibrated: y=%.3f width=%.3f",
                        self.detector.baseline_y, self.detector.baseline_width)
            self.bus.publish(EVENT_CALIBRATED, make_calibrated_event("vertical", ts))


_module: VerticalModule | None = None


def register(bus: EventBus) -> None:
    """Entry point called by main.py."""
    global _module
    _module = VerticalModule(bus)
    bus.subscribe(EVENT_POSE_FRAME, _module.on_pose_frame)
    bus.subscribe(EVENT_CALIBRATE, _module.on_calibrate)

"""TEAMMATE 2: Horizontal Movement Logic (Left / Center / Right)

Responsibility:
  * Implement calibration step: calculate center X position of torso when standing straight.
  * Define lane boundaries: left shift -> LANE_LEFT, right shift -> LANE_RIGHT, center band -> LANE_CENTER.
  * Publish EVENT_LANE_CHANGED only when crossing thresholds (state change) to prevent key spamming.
"""

from __future__ import annotations

import time
from typing import Any

from event_bus import (
    EVENT_CALIBRATE,
    EVENT_CALIBRATED,
    EVENT_LANE_CHANGED,
    EVENT_POSE_FRAME,
    LANE_CENTER,
    LANE_LEFT,
    LANE_RIGHT,
    EventBus,
    make_calibrated_event,
    make_lane_event,
)
from vision import PoseFrame, get_horizontal_payload

DEFAULT_THRESHOLD: float = 0.07
DEFAULT_HYSTERESIS: float = 0.015


class HorizontalTracker:
    """Tracks torso mid-shoulder X position and determines player lane (LEFT / CENTER / RIGHT)."""

    def __init__(
        self,
        bus: EventBus | None = None,
        threshold: float = DEFAULT_THRESHOLD,
        hysteresis: float = DEFAULT_HYSTERESIS,
    ) -> None:
        self.bus = bus
        self.threshold = threshold
        self.hysteresis = hysteresis

        self.center_x: float = 0.5
        self.current_lane: str = LANE_CENTER
        self.is_calibrated: bool = False
        self._pending_calibration: bool = False
        self._latest_mid_shoulder_x: float | None = None

    def calibrate(self, center_x: float, timestamp: float) -> None:
        """Set baseline center X position and publish calibration event."""
        self.center_x = center_x
        self.is_calibrated = True
        self._pending_calibration = False
        print(f"[horizontal] Calibrated standing center X: {center_x:.3f}")
        if self.bus:
            self.bus.publish(
                EVENT_CALIBRATED,
                make_calibrated_event("horizontal", timestamp),
            )

    def on_calibrate(self, payload: dict[str, Any]) -> None:
        """Handle EVENT_CALIBRATE ('c' key event)."""
        ts = payload.get("timestamp", time.time())
        if self._latest_mid_shoulder_x is not None:
            self.calibrate(self._latest_mid_shoulder_x, ts)
        else:
            self._pending_calibration = True
            print("[horizontal] Calibration requested, awaiting pose frame...")

    def on_pose_frame(self, pose_frame: PoseFrame) -> str | None:
        """Process incoming pose frame and detect lane state changes."""
        payload = get_horizontal_payload(pose_frame)
        if not payload["pose_detected"] or payload["mid_shoulder_x"] is None:
            return None

        x: float = payload["mid_shoulder_x"]
        ts: float = payload["timestamp"]
        shoulder_w: float | None = payload.get("shoulder_width")

        self._latest_mid_shoulder_x = x

        # Auto-calibrate on first pose frame if not calibrated yet or pending
        if not self.is_calibrated or self._pending_calibration:
            self.calibrate(x, ts)

        # Scale threshold dynamically based on shoulder width if available
        effective_threshold = self.threshold
        if shoulder_w is not None and shoulder_w > 0:
            effective_threshold = max(self.threshold, shoulder_w * 0.35)

        dx = x - self.center_x

        # Evaluate lane with hysteresis
        if self.current_lane == LANE_CENTER:
            if dx < -effective_threshold:
                new_lane = LANE_LEFT
            elif dx > effective_threshold:
                new_lane = LANE_RIGHT
            else:
                new_lane = LANE_CENTER
        elif self.current_lane == LANE_LEFT:
            if dx > -effective_threshold + self.hysteresis:
                if dx > effective_threshold:
                    new_lane = LANE_RIGHT
                else:
                    new_lane = LANE_CENTER
            else:
                new_lane = LANE_LEFT
        elif self.current_lane == LANE_RIGHT:
            if dx < effective_threshold - self.hysteresis:
                if dx < -effective_threshold:
                    new_lane = LANE_LEFT
                else:
                    new_lane = LANE_CENTER
            else:
                new_lane = LANE_RIGHT
        else:
            new_lane = LANE_CENTER

        if new_lane != self.current_lane:
            self.current_lane = new_lane
            print(f"LANE: {new_lane}")
            if self.bus:
                self.bus.publish(
                    EVENT_LANE_CHANGED,
                    make_lane_event(new_lane, ts),
                )

        return self.current_lane


# Module-level default instance for simple bus registration
_tracker: HorizontalTracker | None = None


def register(bus: EventBus) -> HorizontalTracker:
    """Entry point called by main.py."""
    global _tracker
    _tracker = HorizontalTracker(bus)
    bus.subscribe(EVENT_POSE_FRAME, _tracker.on_pose_frame)
    bus.subscribe(EVENT_CALIBRATE, _tracker.on_calibrate)
    return _tracker
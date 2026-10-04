"""TEAMMATE 2: replace this stub with lean LEFT / CENTER / RIGHT logic.

Contract:
  * Subscribe to EVENT_POSE_FRAME; use vision.get_horizontal_payload(pose_frame).
  * Subscribe to EVENT_CALIBRATE ('c' key) to capture the standing center X, then
    publish EVENT_CALIBRATED via make_calibrated_event("horizontal", ts).
  * Publish EVENT_LANE_CHANGED (make_lane_event) ONLY when the lane changes.
"""

from __future__ import annotations

from event_bus import EVENT_CALIBRATE, EVENT_POSE_FRAME, EventBus
from vision import PoseFrame, get_horizontal_payload

PRINT_EVERY_N_FRAMES = 60
_count = 0


def _on_pose_frame(pose_frame: PoseFrame) -> None:
    global _count
    _count += 1
    if _count % PRINT_EVERY_N_FRAMES == 0:
        payload = get_horizontal_payload(pose_frame)
        print(f"[horizontal STUB] mid_shoulder_x={payload['mid_shoulder_x']}")


def _on_calibrate(payload: dict) -> None:
    print("[horizontal STUB] calibrate requested (TEAMMATE 2: capture center X here)")


def register(bus: EventBus) -> None:
    """Entry point called by main.py. TEAMMATE 2: replace this."""
    bus.subscribe(EVENT_POSE_FRAME, _on_pose_frame)
    bus.subscribe(EVENT_CALIBRATE, _on_calibrate)
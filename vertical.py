"""TEAMMATE 3: replace this stub with JUMP / CROUCH logic.

Contract:
  * Subscribe to EVENT_POSE_FRAME; use vision.get_vertical_payload(pose_frame).
  * Normalize vertical movement by shoulder_width so stepping closer/farther
    from the camera does not trigger false actions.
  * Subscribe to EVENT_CALIBRATE ('c' key) to capture the standing baseline Y, then
    publish EVENT_CALIBRATED via make_calibrated_event("vertical", ts).
  * Publish EVENT_ACTION (make_action_event) with "JUMP" or "CROUCH".
"""

from __future__ import annotations

from event_bus import EVENT_CALIBRATE, EVENT_POSE_FRAME, EventBus
from vision import PoseFrame, get_vertical_payload

PRINT_EVERY_N_FRAMES = 60
_count = 0


def _on_pose_frame(pose_frame: PoseFrame) -> None:
    global _count
    _count += 1
    if _count % PRINT_EVERY_N_FRAMES == 0:
        payload = get_vertical_payload(pose_frame)
        print(f"[vertical STUB] mid_shoulder_y={payload['mid_shoulder_y']} "
              f"shoulder_width={payload['shoulder_width']}")


def _on_calibrate(payload: dict) -> None:
    print("[vertical STUB] calibrate requested (TEAMMATE 3: capture baseline Y here)")


def register(bus: EventBus) -> None:
    """Entry point called by main.py. TEAMMATE 3: replace this."""
    bus.subscribe(EVENT_POSE_FRAME, _on_pose_frame)
    bus.subscribe(EVENT_CALIBRATE, _on_calibrate)
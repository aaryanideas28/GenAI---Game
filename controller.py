"""TEAMMATE 4: OpenCV gesture controller + game integration.

Contract:
  * EVENT_LANE_CHANGED -> {"lane": "LEFT"|"CENTER"|"RIGHT", "timestamp": float}
  * EVENT_ACTION       -> {"action": "JUMP"|"CROUCH", "timestamp": float}
Maps these to game commands (game.commands) so the runner responds live.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from event_bus import (
    EVENT_ACTION,
    EVENT_CALIBRATE,
    EVENT_CALIBRATED,
    EVENT_LANE_CHANGED,
    EVENT_POSE_FRAME,
    EventBus,
)
from game import commands

logger = logging.getLogger("controller")

_stop_event = threading.Event()
_vision_thread: threading.Thread | None = None
_active_bus: EventBus | None = None


def trigger_calibration() -> None:
    """Publish EVENT_CALIBRATE on the active vision bus so posture recalibrates."""
    if _active_bus is not None:
        _active_bus.publish(EVENT_CALIBRATE, {"timestamp": time.time()})
        logger.info("[controller] Triggered posture calibration.")


def _on_lane(payload: dict[str, Any]) -> None:
    lane = payload.get("lane")
    if lane:
        lane_str = str(lane).upper()
        logger.info("[controller] LANE -> %s", lane_str)
        commands.push_lane(lane_str)


def _on_action(payload: dict[str, Any]) -> None:
    action = payload.get("action")
    if action:
        act_str = str(action).upper()
        logger.info("[controller] ACTION -> %s", act_str)
        commands.push_action(act_str)


def _on_calibrated(payload: dict[str, Any]) -> None:
    mod = payload.get("module")
    if mod == "vertical":
        commands.push_action("CALIBRATED")


def register(bus: EventBus) -> None:
    """Entry point called by main.py."""
    bus.subscribe(EVENT_LANE_CHANGED, _on_lane)
    bus.subscribe(EVENT_ACTION, _on_action)
    bus.subscribe(EVENT_CALIBRATED, _on_calibrated)
    logger.info("Controller registered for EVENT_LANE_CHANGED, EVENT_ACTION, and EVENT_CALIBRATED.")


def run_vision_loop(camera_index: int = 0, headless: bool = True,
                    bus: EventBus | None = None) -> None:
    """Runs the OpenCV camera capture and MediaPipe gesture loop in a background thread."""
    global _active_bus
    if bus is None:
        bus = EventBus()
    _active_bus = bus

    # Track overlay state for debug window
    overlay_lines_fn = None
    if not headless:
        try:
            from main import OverlayState
            overlay = OverlayState()
            bus.subscribe(EVENT_LANE_CHANGED, overlay.on_lane)
            bus.subscribe(EVENT_ACTION, overlay.on_action)
            bus.subscribe(EVENT_CALIBRATED, overlay.on_calibrated)
            overlay_lines_fn = overlay.lines
        except Exception:
            pass

    # Register teammate modules
    h_tracker = None
    try:
        import horizontal
        h_tracker = horizontal.register(bus)
    except Exception as exc:
        logger.warning("Could not register horizontal tracker: %s", exc)

    v_module = None
    try:
        import vertical
        vertical.register(bus)
        v_module = getattr(vertical, "_module", None)
    except Exception as exc:
        logger.warning("Could not register vertical tracker: %s", exc)

    hud_module = None
    try:
        import hud
        hud_module = hud.register(bus)
    except Exception as exc:
        logger.warning("Could not register hud module: %s", exc)

    register(bus)

    try:
        from vision import VisionPipeline
        pipeline = VisionPipeline(camera_index=camera_index)
        pipeline.start()
    except Exception as exc:
        logger.warning("Webcam not available (%s). Playing in keyboard mode.", exc)
        return

    logger.info("OpenCV gesture pipeline active on camera %d (cv_window=%s).",
                camera_index, not headless)
    calibrated = False
    stable_frames = 0

    try:
        while not _stop_event.is_set():
            pf = pipeline.read()
            if pf is None:
                time.sleep(0.005)
                continue

            bus.publish(EVENT_POSE_FRAME, pf)

            # Auto-trigger vertical calibration once user pose is stable
            if not calibrated:
                if pf.pose_detected and pf.mid_shoulder is not None:
                    stable_frames += 1
                    if stable_frames >= 12:
                        bus.publish(EVENT_CALIBRATE, {"timestamp": time.time()})
                        calibrated = True
                else:
                    stable_frames = 0

            if not headless and pf.frame is not None:
                import cv2
                extra_lines = []
                # Add real-time posture indicators to overlay
                try:
                    if v_module and v_module.calibrated:
                        det = v_module.detector
                        extra_lines.append(f"POSTURE: rel={det.y_rel:+.2f} (CROUCH > 0.50)")
                        extra_lines.append(f"DEPTH: {'OK' if det.depth_ok else 'TOO CLOSE / FAR'}")
                except Exception:
                    pass

                # Draw skeleton without default status text
                debug_img = pipeline.draw_debug(pf.frame, pf, show_status=False)

                # Render Teammate 5 HUD (thin 1px cyan lane boundary dividers, 1px threshold lines & status panel)
                if hud_module is not None:
                    debug_img = hud_module.render(
                        debug_img,
                        pose_frame=pf,
                        horizontal_tracker=h_tracker,
                        vertical_module=v_module,
                        fps=pipeline.get_fps(),
                        extra_lines=extra_lines,
                    )

                cv2.imshow("Subway Surfers - Gesture Cam", debug_img)
                key = cv2.waitKey(1) & 0xFF
                if key in (27, ord("q")):
                    break
                elif key == ord("c"):
                    bus.publish(EVENT_CALIBRATE, {"timestamp": time.time()})
    finally:
        pipeline.stop()
        if not headless:
            try:
                import cv2
                cv2.destroyAllWindows()
            except Exception:
                pass
        logger.info("Vision pipeline stopped.")


def start_vision_thread(camera_index: int = 0, show_feed: bool = False) -> threading.Thread | None:
    """Start the OpenCV gesture pipeline asynchronously in a daemon thread."""
    global _vision_thread
    _stop_event.clear()
    thread = threading.Thread(
        target=run_vision_loop,
        kwargs={"camera_index": camera_index, "headless": not show_feed},
        name="OpenCV-Gesture-Thread",
        daemon=True,
    )
    thread.start()
    _vision_thread = thread
    return thread


def stop_vision_thread() -> None:
    """Stop the running vision thread."""
    _stop_event.set()
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
    try:
        import horizontal
        horizontal.register(bus)
    except Exception as exc:
        logger.warning("Could not register horizontal tracker: %s", exc)

    try:
        import vertical
        vertical.register(bus)
    except Exception as exc:
        logger.warning("Could not register vertical tracker: %s", exc)

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
                lines = overlay_lines_fn() if overlay_lines_fn else []
                # Add real-time posture indicators to overlay
                try:
                    import vertical as v_mod
                    if getattr(v_mod, "_module", None) and v_mod._module.calibrated:
                        det = v_mod._module.detector
                        lines.append(f"POSTURE: rel={det.y_rel:+.2f} (CROUCH > {v_mod.CROUCH_THRESHOLD})")
                        lines.append(f"DEPTH: {'OK' if det.depth_ok else 'TOO CLOSE / FAR'}")
                except Exception:
                    pass

                debug_img = pipeline.draw_debug(pf.frame, pf, lines)

                # Draw horizontal guideline thresholds on camera feed
                try:
                    import vertical as v_mod
                    if getattr(v_mod, "_module", None) and v_mod._module.calibrated:
                        h_img, w_img = debug_img.shape[:2]
                        m = v_mod._module
                        y_jump = int(round(m.jump_line_y() * h_img))
                        y_base = int(round(m.baseline_y * h_img))
                        y_crouch = int(round(m.crouch_line_y() * h_img))

                        # Jump threshold line (yellow)
                        cv2.line(debug_img, (0, y_jump), (w_img, y_jump), (0, 255, 255), 1, cv2.LINE_AA)
                        cv2.putText(debug_img, "JUMP", (w_img - 70, max(15, y_jump - 4)),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1, cv2.LINE_AA)

                        # Standing baseline (cyan)
                        cv2.line(debug_img, (0, y_base), (w_img, y_base), (255, 255, 0), 1, cv2.LINE_AA)
                        cv2.putText(debug_img, "STAND", (w_img - 80, max(15, y_base - 4)),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 0), 1, cv2.LINE_AA)

                        # Crouch threshold line (orange / red)
                        cv2.line(debug_img, (0, y_crouch), (w_img, y_crouch), (0, 140, 255), 2, cv2.LINE_AA)
                        cv2.putText(debug_img, "CROUCH / ROLL", (w_img - 150, min(h_img - 5, y_crouch + 14)),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 140, 255), 1, cv2.LINE_AA)
                except Exception:
                    pass

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
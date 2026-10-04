"""
MAIN LOOP (Teammate 1: Lead Integrator)

  python main.py                 live debug window (q / ESC = quit, c = calibrate)
  python main.py --headless      no window
  python main.py --selftest      measure FPS, exit non-zero if below 30 FPS

Teammate modules (horizontal.py, vertical.py, controller.py) are loaded as plugins:
each exposes ``register(bus)``. A missing or crashing module is logged and skipped.
"""

from __future__ import annotations

import argparse
import importlib
import logging
import sys
import time
from typing import Any, Callable

import cv2

from event_bus import (
    EVENT_ACTION,
    EVENT_CALIBRATE,
    EVENT_CALIBRATED,
    EVENT_LANE_CHANGED,
    EVENT_POSE_FOUND,
    EVENT_POSE_FRAME,
    EVENT_POSE_LOST,
    EventBus,
)
from vision import (
    DEFAULT_CAMERA_INDEX,
    DEFAULT_FRAME_HEIGHT,
    DEFAULT_FRAME_WIDTH,
    DEFAULT_MODEL_COMPLEXITY,
    PoseFrame,
    VisionPipeline,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                    datefmt="%H:%M:%S")
logger = logging.getLogger("main")

# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------
WINDOW_NAME = "Pose Debug"
KEY_QUIT = ord("q")
KEY_ESC = 27
KEY_CALIBRATE = ord("c")
TARGET_FPS = 30.0
FPS_TOLERANCE = 0.95                 # camera jitter: 28.5+ counts as 30
SELFTEST_WARMUP_FRAMES = 15
SELFTEST_MEASURE_FRAMES = 90
SELFTEST_TIMEOUT_S = 30.0
ACTION_DISPLAY_S = 1.0               # how long the last action stays on screen
TELEMETRY_EVERY_N_FRAMES = 30

# Teammate modules to load. Add a line here to plug in a new module.
TEAMMATE_MODULES: tuple[str, ...] = ("horizontal", "vertical", "controller")


# -----------------------------------------------------------------------------
# Plugin mechanism
# -----------------------------------------------------------------------------
def register_module(bus: EventBus, name: str, register_fn: Callable[[EventBus], None]) -> bool:
    """Run ``register_fn(bus)`` safely. Returns False (and logs) if it raises."""
    try:
        register_fn(bus)
        logger.info("Module '%s' registered.", name)
        return True
    except Exception:  # noqa: BLE001 - a bad teammate module must not kill the loop
        logger.exception("Module '%s' failed to register; skipped.", name)
        return False


def load_teammate_modules(bus: EventBus, module_names: tuple[str, ...] = TEAMMATE_MODULES) -> dict[str, bool]:
    """Import each module and call its ``register(bus)``. Never raises."""
    status: dict[str, bool] = {}
    for name in module_names:
        try:
            module = importlib.import_module(name)
            register_fn = getattr(module, "register")
        except Exception:  # noqa: BLE001 - ImportError, SyntaxError, missing register...
            logger.exception("Could not load module '%s'; skipped.", name)
            status[name] = False
            continue
        status[name] = register_module(bus, name, register_fn)
    return status


# -----------------------------------------------------------------------------
# Demo subscribers + overlay state
# -----------------------------------------------------------------------------
class TelemetryLogger:
    """EXAMPLE subscriber: logs mid-shoulder every N frames."""

    def __init__(self, every: int = TELEMETRY_EVERY_N_FRAMES) -> None:
        self.every = every
        self.count = 0

    def on_pose_frame(self, pf: PoseFrame) -> None:
        self.count += 1
        if self.count % self.every == 0:
            if pf.pose_detected and pf.mid_shoulder:
                logger.info("mid_shoulder=(%.3f, %.3f) shoulder_width=%.3f vis=%.2f",
                            pf.mid_shoulder[0], pf.mid_shoulder[1], pf.shoulder_width or 0.0,
                            pf.shoulder_visibility)
            else:
                logger.info("no pose detected")


def on_pose_found(_: PoseFrame) -> None:
    """EXAMPLE subscriber."""
    logger.info("POSE FOUND")


def on_pose_lost(_: PoseFrame) -> None:
    """EXAMPLE subscriber."""
    logger.warning("POSE LOST")


class OverlayState:
    """Remembers the latest lane / action / calibration events for the debug overlay."""

    def __init__(self) -> None:
        self.lane: str = "-"
        self.action: str = "-"
        self.action_time: float = 0.0
        self.calibrated: set[str] = set()

    def on_lane(self, payload: dict[str, Any]) -> None:
        self.lane = payload.get("lane", "-")

    def on_action(self, payload: dict[str, Any]) -> None:
        self.action = payload.get("action", "-")
        self.action_time = time.time()

    def on_calibrated(self, payload: dict[str, Any]) -> None:
        self.calibrated.add(payload.get("module", "?"))

    def lines(self) -> list[str]:
        action = self.action if time.time() - self.action_time < ACTION_DISPLAY_S else "-"
        cal = ",".join(sorted(self.calibrated)) or "none"
        return [f"LANE: {self.lane}", f"ACTION: {action}", f"CAL: {cal}  ('c' to calibrate)"]


def build_bus(overlay: OverlayState | None = None) -> EventBus:
    """Create the bus with demo subscribers, overlay tracking and teammate plugins."""
    bus = EventBus()
    telemetry = TelemetryLogger()
    bus.subscribe(EVENT_POSE_FRAME, telemetry.on_pose_frame)
    bus.subscribe(EVENT_POSE_FOUND, on_pose_found)
    bus.subscribe(EVENT_POSE_LOST, on_pose_lost)
    if overlay is not None:
        bus.subscribe(EVENT_LANE_CHANGED, overlay.on_lane)
        bus.subscribe(EVENT_ACTION, overlay.on_action)
        bus.subscribe(EVENT_CALIBRATED, overlay.on_calibrated)
    load_teammate_modules(bus)
    return bus


# -----------------------------------------------------------------------------
# Live loop
# -----------------------------------------------------------------------------
def run_pipeline(camera_index: int, width: int, height: int, complexity: int, headless: bool) -> None:
    overlay = OverlayState()
    bus = build_bus(overlay)
    pipeline = VisionPipeline(camera_index=camera_index, width=width, height=height,
                              model_complexity=complexity)
    prev_detected: bool | None = None

    try:
        pipeline.start()
        logger.info("Pipeline started. q/ESC = quit, c = calibrate.")
        while True:
            pose_frame = pipeline.read()

            if pose_frame is not None:
                bus.publish(EVENT_POSE_FRAME, pose_frame)
                detected = pose_frame.pose_detected
                if prev_detected is not None and detected != prev_detected:
                    bus.publish(EVENT_POSE_FOUND if detected else EVENT_POSE_LOST, pose_frame)
                elif prev_detected is None and detected:
                    bus.publish(EVENT_POSE_FOUND, pose_frame)
                prev_detected = detected

            if headless:
                continue

            if pose_frame is not None:
                cv2.imshow(WINDOW_NAME, pipeline.draw_debug(pose_frame.frame, pose_frame, overlay.lines()))
            key = cv2.waitKey(1) & 0xFF
            if key in (KEY_QUIT, KEY_ESC):
                break
            if key == KEY_CALIBRATE:
                logger.info("Calibrate requested.")
                bus.publish(EVENT_CALIBRATE, {"timestamp": time.time()})
    except KeyboardInterrupt:
        logger.info("Interrupted.")
    finally:
        pipeline.stop()
        if not headless:
            cv2.destroyAllWindows()
        logger.info("Pipeline stopped; camera released.")


# -----------------------------------------------------------------------------
# Self-test
# -----------------------------------------------------------------------------
def run_selftest(camera_index: int, width: int, height: int, complexity: int) -> int:
    """Return 0 if average FPS >= 30 (with tolerance), 1 on camera failure, 2 if too slow."""
    print("=" * 60)
    print(" VISION SELF-TEST")
    print("=" * 60)
    pipeline = VisionPipeline(camera_index=camera_index, width=width, height=height,
                              model_complexity=complexity)
    try:
        pipeline.start()
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] Camera could not be opened: {exc}")
        return 1
    print("[PASS] Camera opened.")

    try:
        deadline = time.perf_counter() + SELFTEST_TIMEOUT_S
        warm = 0
        while warm < SELFTEST_WARMUP_FRAMES and time.perf_counter() < deadline:
            if pipeline.read() is not None:
                warm += 1

        frames = detected = 0
        start = time.perf_counter()
        while frames < SELFTEST_MEASURE_FRAMES and time.perf_counter() < deadline:
            pf = pipeline.read()
            if pf is None:
                continue
            frames += 1
            detected += int(pf.pose_detected)
        elapsed = time.perf_counter() - start

        if frames < SELFTEST_MEASURE_FRAMES:
            print(f"[FAIL] Only {frames}/{SELFTEST_MEASURE_FRAMES} frames received before timeout.")
            return 1

        avg_fps = frames / elapsed
        cap_fps = pipeline.get_capture_fps()
        inf_fps = pipeline.get_inference_fps()
        threshold = TARGET_FPS * FPS_TOLERANCE

        print(f"Frames measured       : {frames} in {elapsed:.2f}s")
        print(f"Capture FPS (camera)  : {cap_fps:.1f}")
        print(f"Inference FPS (model) : {inf_fps:.1f}")
        print(f"Overall pipeline FPS  : {avg_fps:.1f}  (target {TARGET_FPS:.0f}, pass >= {threshold:.1f})")
        print(f"Pose detected         : {detected}/{frames} ({100.0 * detected / frames:.0f}%)")

        if avg_fps >= threshold:
            print("[PASS] FPS target met.")
            return 0

        if cap_fps < threshold:
            hint = ("CAMERA: it delivers fewer than 30 FPS. Improve lighting (webcams drop FPS in dim "
                    "light), turn off auto low-light mode, try another USB port, close other camera apps.")
        elif inf_fps < threshold:
            hint = "MODEL: MediaPipe inference is too slow. Use --complexity 0 and lower --width/--height."
        else:
            hint = "MAIN LOOP: overhead outside the camera and the model (plugins or drawing)."
        print(f"[FAIL] Below target. Bottleneck -> {hint}")
        return 2
    finally:
        pipeline.stop()


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Motion-controlled runner: vision pipeline")
    p.add_argument("--selftest", action="store_true", help="measure FPS and exit")
    p.add_argument("--camera", type=int, default=DEFAULT_CAMERA_INDEX)
    p.add_argument("--width", type=int, default=DEFAULT_FRAME_WIDTH)
    p.add_argument("--height", type=int, default=DEFAULT_FRAME_HEIGHT)
    p.add_argument("--complexity", type=int, choices=[0, 1], default=DEFAULT_MODEL_COMPLEXITY)
    p.add_argument("--headless", action="store_true", help="no debug window")
    return p.parse_args(argv)


def main() -> None:
    args = parse_args()
    if args.selftest:
        sys.exit(run_selftest(args.camera, args.width, args.height, args.complexity))
    run_pipeline(args.camera, args.width, args.height, args.complexity, args.headless)


if __name__ == "__main__":
    main()

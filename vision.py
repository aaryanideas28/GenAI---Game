"""
VISION PIPELINE (Teammate 1) + HAND-OFF CONTRACT
================================================

COORDINATE SYSTEM (applies to every landmark / payload)
  * Normalized floats, 0.0 .. 1.0, relative to the MIRRORED frame.
  * Origin (0, 0) = top-left.  x grows to the RIGHT, y grows DOWNWARD.
  * The frame is mirrored (cv2.flip(frame, 1)): stepping to your real-life LEFT
    moves the dots toward x = 0.0. Nobody downstream needs to invert anything.

PER-FRAME PAYLOAD: ``PoseFrame`` (see dataclass below)
  * ``pose_detected == False``  ->  every landmark field is None and
    shoulder_visibility == 0.0.  Stale data from earlier frames is NEVER returned.
  * ``shoulder_width`` = normalized distance between landmarks 11 and 12.
    Teammate 3 uses it to compensate for the player stepping closer / farther.

HELPERS
  * ``get_horizontal_payload(pose_frame)`` -> Teammate 2
  * ``get_vertical_payload(pose_frame)``   -> Teammate 3
  Raw 33 landmarks are in ``pose_frame.landmarks`` (index constants below).

PERFORMANCE DESIGN
  * A background thread reads the camera nonstop and keeps ONLY the newest frame,
    so inference never waits on camera I/O and never processes old frames.
"""

from __future__ import annotations

import collections
import math
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any, Sequence

import cv2
import numpy as np

# -----------------------------------------------------------------------------
# MediaPipe landmark indices
# -----------------------------------------------------------------------------
NOSE: int = 0
LEFT_SHOULDER: int = 11
RIGHT_SHOULDER: int = 12
LEFT_ELBOW: int = 13
RIGHT_ELBOW: int = 14
LEFT_WRIST: int = 15
RIGHT_WRIST: int = 16
LEFT_HIP: int = 23
RIGHT_HIP: int = 24
LEFT_KNEE: int = 25
RIGHT_KNEE: int = 26
LEFT_ANKLE: int = 27
RIGHT_ANKLE: int = 28
LEFT_HEEL: int = 29
RIGHT_HEEL: int = 30
LEFT_FOOT_INDEX: int = 31
RIGHT_FOOT_INDEX: int = 32
NUM_LANDMARKS: int = 33

# Body-only skeleton (face mesh omitted on purpose: cleaner overlay)
SKELETON_CONNECTIONS: tuple[tuple[int, int], ...] = (
    (11, 12), (11, 13), (13, 15), (12, 14), (14, 16),
    (11, 23), (12, 24), (23, 24),
    (23, 25), (25, 27), (24, 26), (26, 28),
    (27, 29), (29, 31), (28, 30), (30, 32),
)
SKELETON_JOINTS: tuple[int, ...] = (
    13, 14, 15, 16, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32,
)

# -----------------------------------------------------------------------------
# Defaults / thresholds
# -----------------------------------------------------------------------------
VISIBILITY_THRESHOLD: float = 0.5
DEFAULT_CAMERA_INDEX: int = 0
DEFAULT_FRAME_WIDTH: int = 640
DEFAULT_FRAME_HEIGHT: int = 480
DEFAULT_MODEL_COMPLEXITY: int = 0          # 0 = fastest; needed for 30 FPS on CPU
DEFAULT_MIN_DETECTION_CONFIDENCE: float = 0.5
DEFAULT_MIN_TRACKING_CONFIDENCE: float = 0.5
TARGET_CAMERA_FPS: float = 30.0
FPS_WINDOW: int = 30                       # rolling-average window (frames)
READ_TIMEOUT_S: float = 0.5                # max wait for a new camera frame
CAPTURE_BUFFER_SIZE: int = 1

# Overlay styling (BGR)
COLOR_BONE = (230, 230, 230)
COLOR_JOINT = (0, 200, 255)
COLOR_NOSE = (0, 255, 0)
COLOR_LEFT_SH = (255, 255, 0)
COLOR_RIGHT_SH = (0, 165, 255)
COLOR_MID = (0, 255, 255)
COLOR_TEXT = (255, 255, 255)
COLOR_SHADOW = (0, 0, 0)
COLOR_WARN = (0, 0, 255)
COLOR_OK = (0, 255, 0)
BONE_THICKNESS: int = 1
JOINT_RADIUS: int = 2
KEY_DOT_RADIUS: int = 4
MID_RING_RADIUS: int = 8
FONT = cv2.FONT_HERSHEY_SIMPLEX


# -----------------------------------------------------------------------------
# Payload
# -----------------------------------------------------------------------------
@dataclass(frozen=True)
class PoseFrame:
    """Everything downstream modules need for one camera frame."""

    frame_width: int
    frame_height: int
    timestamp: float
    pose_detected: bool
    landmarks: list[Any] | None
    nose: tuple[float, float] | None
    left_shoulder: tuple[float, float] | None
    right_shoulder: tuple[float, float] | None
    mid_shoulder: tuple[float, float] | None
    mid_shoulder_px: tuple[int, int] | None
    shoulder_visibility: float
    frame: np.ndarray | None
    shoulder_width: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return the payload as a plain dict."""
        return {
            "frame_width": self.frame_width,
            "frame_height": self.frame_height,
            "timestamp": self.timestamp,
            "pose_detected": self.pose_detected,
            "landmarks": self.landmarks,
            "nose": self.nose,
            "left_shoulder": self.left_shoulder,
            "right_shoulder": self.right_shoulder,
            "mid_shoulder": self.mid_shoulder,
            "mid_shoulder_px": self.mid_shoulder_px,
            "shoulder_visibility": self.shoulder_visibility,
            "shoulder_width": self.shoulder_width,
            "frame": self.frame,
        }


def build_pose_frame(
    landmarks: Sequence[Any] | None,
    frame_width: int,
    frame_height: int,
    timestamp: float,
    frame: np.ndarray | None = None,
) -> PoseFrame:
    """Turn raw landmarks (objects with .x .y .visibility) into a PoseFrame.

    Pure function (no camera / MediaPipe needed) so it is easy to unit-test.
    ``landmarks=None`` means "no pose" and yields an all-None frame.
    """
    if landmarks is None or len(landmarks) <= RIGHT_SHOULDER:
        return PoseFrame(
            frame_width=frame_width, frame_height=frame_height, timestamp=timestamp,
            pose_detected=False, landmarks=None, nose=None, left_shoulder=None,
            right_shoulder=None, mid_shoulder=None, mid_shoulder_px=None,
            shoulder_visibility=0.0, frame=frame, shoulder_width=None,
        )

    raw = list(landmarks)
    nose_lm, left_lm, right_lm = raw[NOSE], raw[LEFT_SHOULDER], raw[RIGHT_SHOULDER]

    mid_x = (left_lm.x + right_lm.x) / 2.0
    mid_y = (left_lm.y + right_lm.y) / 2.0

    return PoseFrame(
        frame_width=frame_width,
        frame_height=frame_height,
        timestamp=timestamp,
        pose_detected=True,
        landmarks=raw,
        nose=(float(nose_lm.x), float(nose_lm.y)),
        left_shoulder=(float(left_lm.x), float(left_lm.y)),
        right_shoulder=(float(right_lm.x), float(right_lm.y)),
        mid_shoulder=(float(mid_x), float(mid_y)),
        mid_shoulder_px=(int(round(mid_x * frame_width)), int(round(mid_y * frame_height))),
        shoulder_visibility=float(min(left_lm.visibility, right_lm.visibility)),
        frame=frame,
        shoulder_width=float(math.hypot(left_lm.x - right_lm.x, left_lm.y - right_lm.y)),
    )


def get_horizontal_payload(pose_frame: PoseFrame) -> dict[str, Any]:
    """Payload for Teammate 2 (horizontal movement)."""
    ms = pose_frame.mid_shoulder
    return {
        "pose_detected": pose_frame.pose_detected,
        "mid_shoulder_x": ms[0] if ms else None,
        "mid_shoulder_y": ms[1] if ms else None,
        "shoulder_width": pose_frame.shoulder_width,
        "frame_width": pose_frame.frame_width,
        "frame_height": pose_frame.frame_height,
        "timestamp": pose_frame.timestamp,
    }


def get_vertical_payload(pose_frame: PoseFrame) -> dict[str, Any]:
    """Payload for Teammate 3 (jump / crouch). Contains data only, no logic."""
    ms = pose_frame.mid_shoulder
    return {
        "pose_detected": pose_frame.pose_detected,
        "mid_shoulder_y": ms[1] if ms else None,
        "nose_y": pose_frame.nose[1] if pose_frame.nose else None,
        "shoulder_width": pose_frame.shoulder_width,
        "timestamp": pose_frame.timestamp,
    }


# -----------------------------------------------------------------------------
# Background camera reader (keeps only the newest frame)
# -----------------------------------------------------------------------------
class _LatestFrameCapture(threading.Thread):
    """Continuously reads the camera; consumers always get the newest frame."""

    def __init__(self, cap: cv2.VideoCapture) -> None:
        super().__init__(name="camera-capture", daemon=True)
        self._cap = cap
        self._cond = threading.Condition()
        self._frame: np.ndarray | None = None
        self._timestamp: float = 0.0
        self._seq: int = 0
        self._stopped = False
        self._times: collections.deque[float] = collections.deque(maxlen=FPS_WINDOW)

    def run(self) -> None:
        while not self._stopped:
            ok, frame = self._cap.read()
            if not ok or frame is None:
                time.sleep(0.005)
                continue
            now = time.time()
            with self._cond:
                self._frame, self._timestamp = frame, now
                self._seq += 1
                self._times.append(now)
                self._cond.notify_all()

    def get_latest(self, last_seq: int, timeout: float) -> tuple[np.ndarray, float, int] | None:
        """Block until a frame newer than ``last_seq`` exists (or timeout)."""
        with self._cond:
            self._cond.wait_for(lambda: self._seq != last_seq or self._stopped, timeout)
            if self._stopped or self._seq == last_seq or self._frame is None:
                return None
            return self._frame, self._timestamp, self._seq

    def fps(self) -> float:
        with self._cond:
            if len(self._times) < 2:
                return 0.0
            span = self._times[-1] - self._times[0]
            return (len(self._times) - 1) / span if span > 0 else 0.0

    def stop(self) -> None:
        with self._cond:
            self._stopped = True
            self._cond.notify_all()


# -----------------------------------------------------------------------------
# Pipeline
# -----------------------------------------------------------------------------
class VisionPipeline:
    """Camera -> mirror -> MediaPipe Pose -> PoseFrame."""

    NOSE = NOSE
    LEFT_SHOULDER = LEFT_SHOULDER
    RIGHT_SHOULDER = RIGHT_SHOULDER

    def __init__(
        self,
        camera_index: int = DEFAULT_CAMERA_INDEX,
        width: int = DEFAULT_FRAME_WIDTH,
        height: int = DEFAULT_FRAME_HEIGHT,
        min_detection_confidence: float = DEFAULT_MIN_DETECTION_CONFIDENCE,
        min_tracking_confidence: float = DEFAULT_MIN_TRACKING_CONFIDENCE,
        model_complexity: int = DEFAULT_MODEL_COMPLEXITY,
    ) -> None:
        self.camera_index = camera_index
        self.width = width
        self.height = height
        self.min_detection_confidence = min_detection_confidence
        self.min_tracking_confidence = min_tracking_confidence
        self.model_complexity = model_complexity

        self.cap: cv2.VideoCapture | None = None
        self.pose: Any | None = None
        self._capture: _LatestFrameCapture | None = None
        self._last_seq: int = 0
        self._running: bool = False
        self._out_times: collections.deque[float] = collections.deque(maxlen=FPS_WINDOW)
        self._infer_durations: collections.deque[float] = collections.deque(maxlen=FPS_WINDOW)

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> None:
        """Open the camera + MediaPipe. Raises RuntimeError if the camera fails."""
        if self._running:
            return

        import mediapipe as mp  # lazy: keeps unit tests light

        backend = cv2.CAP_DSHOW if sys.platform.startswith("win") else cv2.CAP_ANY
        cap = cv2.VideoCapture(self.camera_index, backend)
        if not cap.isOpened():
            cap.release()
            cap = cv2.VideoCapture(self.camera_index)  # fallback: default backend
        if not cap.isOpened():
            raise RuntimeError(
                f"Cannot open camera index {self.camera_index}. Check that it is connected, "
                "not used by another app (Zoom/Teams/browser) and camera permission is granted."
            )

        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))  # MJPG allows 30 FPS
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, float(self.width))
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(self.height))
        cap.set(cv2.CAP_PROP_FPS, TARGET_CAMERA_FPS)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, CAPTURE_BUFFER_SIZE)
        self.cap = cap

        self.pose = mp.solutions.pose.Pose(
            static_image_mode=False,
            model_complexity=self.model_complexity,
            smooth_landmarks=True,
            enable_segmentation=False,
            min_detection_confidence=self.min_detection_confidence,
            min_tracking_confidence=self.min_tracking_confidence,
        )

        self._out_times.clear()
        self._infer_durations.clear()
        self._last_seq = 0
        self._capture = _LatestFrameCapture(cap)
        self._capture.start()
        self._running = True

    def stop(self) -> None:
        """Stop the capture thread, release the camera and close MediaPipe."""
        self._running = False
        if self._capture is not None:
            self._capture.stop()
            self._capture.join(timeout=2.0)
            self._capture = None
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        if self.pose is not None:
            self.pose.close()
            self.pose = None
        self._out_times.clear()
        self._infer_durations.clear()

    def __enter__(self) -> "VisionPipeline":
        self.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.stop()

    # ------------------------------------------------------------------ reading
    def read(self) -> PoseFrame | None:
        """Return a PoseFrame for the newest camera frame, or None on timeout."""
        if not self._running or self._capture is None or self.pose is None:
            raise RuntimeError("VisionPipeline not started. Call start() or use `with`.")

        latest = self._capture.get_latest(self._last_seq, READ_TIMEOUT_S)
        if latest is None:
            return None
        raw, timestamp, seq = latest
        self._last_seq = seq

        mirrored = cv2.flip(raw, 1)
        height, width = mirrored.shape[:2]
        rgb = cv2.cvtColor(mirrored, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False

        t0 = time.perf_counter()
        results = self.pose.process(rgb)
        self._infer_durations.append(time.perf_counter() - t0)
        self._out_times.append(time.time())

        landmarks = list(results.pose_landmarks.landmark) if results.pose_landmarks else None
        return build_pose_frame(landmarks, width, height, timestamp, mirrored)

    # ------------------------------------------------------------------ metrics
    def get_fps(self) -> float:
        """Rolling-average FPS of processed (output) frames."""
        if len(self._out_times) < 2:
            return 0.0
        span = self._out_times[-1] - self._out_times[0]
        return (len(self._out_times) - 1) / span if span > 0 else 0.0

    def get_capture_fps(self) -> float:
        """Rolling-average FPS the camera is actually delivering."""
        return self._capture.fps() if self._capture else 0.0

    def get_inference_fps(self) -> float:
        """FPS the model alone could sustain (1 / mean inference time)."""
        if not self._infer_durations:
            return 0.0
        mean = sum(self._infer_durations) / len(self._infer_durations)
        return 1.0 / mean if mean > 0 else 0.0

    # ------------------------------------------------------------------ overlay
    def draw_debug(
        self,
        frame: np.ndarray | None,
        pose_frame: PoseFrame,
        overlay_lines: Sequence[str] | None = None,
    ) -> np.ndarray:
        """Return a copy of the frame with a thin skeleton, key dots, FPS and status text."""
        source = frame if frame is not None else pose_frame.frame
        if source is None:
            source = np.zeros(
                (pose_frame.frame_height or DEFAULT_FRAME_HEIGHT,
                 pose_frame.frame_width or DEFAULT_FRAME_WIDTH, 3), dtype=np.uint8)
        img = source.copy()
        h, w = img.shape[:2]

        def px(x: float, y: float) -> tuple[int, int]:
            return int(round(x * w)), int(round(y * h))

        if pose_frame.pose_detected and pose_frame.landmarks is not None:
            lms = pose_frame.landmarks
            for a, b in SKELETON_CONNECTIONS:
                if lms[a].visibility >= VISIBILITY_THRESHOLD and lms[b].visibility >= VISIBILITY_THRESHOLD:
                    cv2.line(img, px(lms[a].x, lms[a].y), px(lms[b].x, lms[b].y),
                             COLOR_BONE, BONE_THICKNESS, cv2.LINE_AA)
            for idx in SKELETON_JOINTS:
                if lms[idx].visibility >= VISIBILITY_THRESHOLD:
                    cv2.circle(img, px(lms[idx].x, lms[idx].y), JOINT_RADIUS, COLOR_JOINT, -1, cv2.LINE_AA)

            if pose_frame.nose:
                cv2.circle(img, px(*pose_frame.nose), KEY_DOT_RADIUS, COLOR_NOSE, -1, cv2.LINE_AA)
            if pose_frame.left_shoulder:
                cv2.circle(img, px(*pose_frame.left_shoulder), KEY_DOT_RADIUS, COLOR_LEFT_SH, -1, cv2.LINE_AA)
            if pose_frame.right_shoulder:
                cv2.circle(img, px(*pose_frame.right_shoulder), KEY_DOT_RADIUS, COLOR_RIGHT_SH, -1, cv2.LINE_AA)
            if pose_frame.mid_shoulder_px:
                cv2.circle(img, pose_frame.mid_shoulder_px, MID_RING_RADIUS, COLOR_MID, 1, cv2.LINE_AA)
                cv2.circle(img, pose_frame.mid_shoulder_px, 2, COLOR_MID, -1, cv2.LINE_AA)

        fps = self.get_fps()
        lines: list[tuple[str, tuple[int, int, int]]] = [
            (f"FPS {fps:4.1f}", COLOR_OK if fps >= TARGET_CAMERA_FPS * 0.95 else COLOR_WARN),
            ("TRACKED" if pose_frame.pose_detected else "NO POSE", COLOR_OK if pose_frame.pose_detected else COLOR_WARN),
        ]
        for extra in overlay_lines or []:
            lines.append((extra, COLOR_TEXT))
        for i, (text, color) in enumerate(lines):
            org = (8, 18 + i * 18)
            cv2.putText(img, text, org, FONT, 0.5, COLOR_SHADOW, 3, cv2.LINE_AA)
            cv2.putText(img, text, org, FONT, 0.5, color, 1, cv2.LINE_AA)
        return img
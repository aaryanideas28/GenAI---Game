"""TEAMMATE 5: HUD, Visual Feedback & Camera Guidelines.

Provides crisp, clean, unobtrusive visual overlays for the OpenCV camera feed:
- Subtle, thin 1-pixel Cyan vertical lane boundary lines (Left / Center / Right)
- Subtle, thin 1-pixel horizontal threshold reference lines (Jump, Stand, Crouch)
  with concise right-aligned text tags
- Clean status panel (Lane, Action, FPS, Cooldown)
- No camera-blocking blackout boxes, dark overlays, or countdown circles
"""

from __future__ import annotations

import time
from typing import Any

import cv2
import numpy as np

from event_bus import (
    EVENT_ACTION,
    EVENT_CALIBRATED,
    EVENT_LANE_CHANGED,
    EVENT_POSE_FRAME,
    EventBus,
)
from vision import PoseFrame

# ---- Overlay Styling Constants (BGR) ----------------------------------------
COLOR_LANE_DIVIDER = (255, 255, 0)   # Clean, subtle 1px Cyan
COLOR_JUMP_LINE = (0, 255, 255)      # 1px Yellow
COLOR_STAND_LINE = (255, 255, 0)     # 1px Cyan
COLOR_CROUCH_LINE = (0, 140, 255)    # 1px Orange/Coral
COLOR_TEXT = (255, 255, 255)         # Crisp White
COLOR_OUTLINE = (0, 0, 0)            # Minimal 1-2px shadow outline for legibility
COLOR_OK = (0, 255, 0)               # Green
COLOR_WARN = (0, 0, 255)             # Red
COLOR_WAIT = (0, 165, 255)           # Orange

FONT = cv2.FONT_HERSHEY_SIMPLEX
ACTION_DISPLAY_S = 1.0


def draw_lane_dividers(
    frame: np.ndarray,
    center_x: float = 0.5,
    threshold: float = 0.07,
    shoulder_width: float | None = None,
) -> None:
    """Draw subtle, thin 1-pixel Cyan vertical lines separating Left, Center, and Right zones."""
    h, w = frame.shape[:2]
    effective_threshold = threshold
    if shoulder_width is not None and shoulder_width > 0:
        effective_threshold = max(threshold, shoulder_width * 0.35)

    x_left = int(round((center_x - effective_threshold) * w))
    x_right = int(round((center_x + effective_threshold) * w))

    if 0 <= x_left < w:
        cv2.line(frame, (x_left, 0), (x_left, h), COLOR_LANE_DIVIDER, 1, cv2.LINE_8)
    if 0 <= x_right < w:
        cv2.line(frame, (x_right, 0), (x_right, h), COLOR_LANE_DIVIDER, 1, cv2.LINE_8)


def draw_threshold_lines(
    frame: np.ndarray,
    jump_y: float | None,
    base_y: float | None,
    crouch_y: float | None,
) -> None:
    """Draw subtle 1-pixel horizontal reference lines (Jump, Stand, Crouch) with concise right-aligned text tags."""
    h, w = frame.shape[:2]

    # Jump line (yellow)
    if jump_y is not None:
        y_jump = int(round(jump_y * h))
        if 0 <= y_jump < h:
            cv2.line(frame, (0, y_jump), (w, y_jump), COLOR_JUMP_LINE, 1, cv2.LINE_8)
            tag = "JUMP"
            (tw, th), _ = cv2.getTextSize(tag, FONT, 0.4, 1)
            tx = max(0, w - tw - 10)
            ty = max(th + 2, y_jump - 4)
            cv2.putText(frame, tag, (tx, ty), FONT, 0.4, COLOR_OUTLINE, 2, cv2.LINE_AA)
            cv2.putText(frame, tag, (tx, ty), FONT, 0.4, COLOR_JUMP_LINE, 1, cv2.LINE_AA)

    # Standing baseline (cyan)
    if base_y is not None:
        y_base = int(round(base_y * h))
        if 0 <= y_base < h:
            cv2.line(frame, (0, y_base), (w, y_base), COLOR_STAND_LINE, 1, cv2.LINE_8)
            tag = "STAND"
            (tw, th), _ = cv2.getTextSize(tag, FONT, 0.4, 1)
            tx = max(0, w - tw - 10)
            ty = max(th + 2, y_base - 4)
            cv2.putText(frame, tag, (tx, ty), FONT, 0.4, COLOR_OUTLINE, 2, cv2.LINE_AA)
            cv2.putText(frame, tag, (tx, ty), FONT, 0.4, COLOR_STAND_LINE, 1, cv2.LINE_AA)

    # Crouch threshold line (orange / coral)
    if crouch_y is not None:
        y_crouch = int(round(crouch_y * h))
        if 0 <= y_crouch < h:
            cv2.line(frame, (0, y_crouch), (w, y_crouch), COLOR_CROUCH_LINE, 1, cv2.LINE_8)
            tag = "CROUCH"
            (tw, th), _ = cv2.getTextSize(tag, FONT, 0.4, 1)
            tx = max(0, w - tw - 10)
            ty = min(h - 4, y_crouch + th + 4)
            cv2.putText(frame, tag, (tx, ty), FONT, 0.4, COLOR_OUTLINE, 2, cv2.LINE_AA)
            cv2.putText(frame, tag, (tx, ty), FONT, 0.4, COLOR_CROUCH_LINE, 1, cv2.LINE_AA)


def draw_status_panel(
    frame: np.ndarray,
    lane: str = "CENTER",
    action: str = "-",
    fps: float = 0.0,
    cooldown: float = 0.0,
    tracked: bool = True,
    extra_lines: list[str] | None = None,
) -> None:
    """Draw clean, non-intrusive status panel (Lane, Action, FPS, Cooldown) at top-left."""
    fps_color = COLOR_OK if fps >= 28.5 else COLOR_WARN
    cooldown_str = f"{cooldown:.2f}s" if cooldown > 0.0 else "READY"
    cooldown_color = COLOR_WAIT if cooldown > 0.0 else COLOR_OK
    track_str = "TRACKED" if tracked else "NO POSE"
    track_color = COLOR_OK if tracked else COLOR_WARN

    panel_items: list[tuple[str, tuple[int, int, int]]] = [
        (f"FPS: {fps:4.1f} ({track_str})", fps_color if tracked else track_color),
        (f"LANE: {lane.upper()}", COLOR_TEXT),
        (f"ACTION: {action.upper()}", COLOR_JUMP_LINE if action != "-" else COLOR_TEXT),
        (f"COOLDOWN: {cooldown_str}", cooldown_color),
    ]

    if extra_lines:
        for ex in extra_lines:
            panel_items.append((ex, COLOR_TEXT))

    for i, (text, color) in enumerate(panel_items):
        org = (10, 20 + i * 20)
        cv2.putText(frame, text, org, FONT, 0.45, COLOR_OUTLINE, 2, cv2.LINE_AA)
        cv2.putText(frame, text, org, FONT, 0.45, color, 1, cv2.LINE_AA)


class HUDModule:
    """Teammate 5 HUD manager. Subscribes to events and renders camera overlays."""

    def __init__(self, bus: EventBus | None = None) -> None:
        self.bus = bus
        self.lane: str = "CENTER"
        self.action: str = "-"
        self.action_time: float = 0.0
        self.calibrated_modules: set[str] = set()

    def on_lane(self, payload: dict[str, Any]) -> None:
        self.lane = payload.get("lane", "CENTER")

    def on_action(self, payload: dict[str, Any]) -> None:
        self.action = payload.get("action", "-")
        ts = payload.get("timestamp")
        self.action_time = float(ts) if ts is not None else time.time()

    def on_calibrated(self, payload: dict[str, Any]) -> None:
        mod = payload.get("module")
        if mod:
            self.calibrated_modules.add(mod)

    def current_action(self, now: float | None = None) -> str:
        t = now if now is not None else time.time()
        return self.action if (t - self.action_time < ACTION_DISPLAY_S) else "-"

    def render(
        self,
        frame: np.ndarray,
        pose_frame: PoseFrame | None = None,
        horizontal_tracker: Any = None,
        vertical_module: Any = None,
        fps: float = 0.0,
        extra_lines: list[str] | None = None,
    ) -> np.ndarray:
        """Render complete HUD onto a copy of the frame without blocking camera view."""
        out = frame.copy()
        now = time.time()

        # 1. Lane boundary dividers (1px Cyan)
        center_x = 0.5
        threshold = 0.07
        shoulder_width = None
        if horizontal_tracker is not None:
            center_x = getattr(horizontal_tracker, "center_x", 0.5)
            threshold = getattr(horizontal_tracker, "threshold", 0.07)
        if pose_frame is not None and pose_frame.shoulder_width:
            shoulder_width = pose_frame.shoulder_width

        draw_lane_dividers(out, center_x=center_x, threshold=threshold, shoulder_width=shoulder_width)

        # 2. Horizontal threshold guidelines (1px Jump, Stand, Crouch)
        jump_y = None
        base_y = None
        crouch_y = None
        cooldown = 0.0

        if vertical_module is not None:
            if getattr(vertical_module, "calibrated", False):
                jump_y = vertical_module.jump_line_y()
                base_y = vertical_module.baseline_y
                crouch_y = vertical_module.crouch_line_y()
            if hasattr(vertical_module, "detector"):
                cooldown = vertical_module.detector.cooldown_remaining(now)

        draw_threshold_lines(out, jump_y=jump_y, base_y=base_y, crouch_y=crouch_y)

        # 3. Status panel (Lane, Action, FPS, Cooldown)
        tracked = bool(pose_frame and pose_frame.pose_detected)
        draw_status_panel(
            out,
            lane=self.lane,
            action=self.current_action(now),
            fps=fps,
            cooldown=cooldown,
            tracked=tracked,
            extra_lines=extra_lines,
        )

        return out


_module: HUDModule | None = None


def register(bus: EventBus) -> HUDModule:
    """Entry point called by main.py or controller.py."""
    global _module
    _module = HUDModule(bus)
    bus.subscribe(EVENT_LANE_CHANGED, _module.on_lane)
    bus.subscribe(EVENT_ACTION, _module.on_action)
    bus.subscribe(EVENT_CALIBRATED, _module.on_calibrated)
    return _module


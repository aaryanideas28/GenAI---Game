"""
EVENT BUS + EVENT CONTRACT
==========================

A tiny, decoupled, thread-safe publish/subscribe bus. Every teammate talks to the
others ONLY through the event names and payload shapes defined here.

EVENT CONTRACT
--------------
EVENT_POSE_FRAME      (Teammate 1 publishes, every frame)
    payload: vision.PoseFrame

EVENT_POSE_FOUND      (Teammate 1, once when a pose appears / returns)
EVENT_POSE_LOST       (Teammate 1, once when a pose disappears)
    payload: vision.PoseFrame

EVENT_CALIBRATE       (Teammate 1, when the user presses 'c' in the debug window)
    payload: {"timestamp": float}
    Teammates 2 and 3 listen to this to (re)capture their standing baseline.

EVENT_CALIBRATED      (Teammates 2 / 3 publish when calibration finished)
    payload: {"module": str, "timestamp": float}

EVENT_LANE_CHANGED    (Teammate 2 publishes ONLY when the lane changes)
    payload: {"lane": "LEFT" | "CENTER" | "RIGHT", "timestamp": float}

EVENT_ACTION          (Teammate 3 publishes when an action is triggered)
    payload: {"action": "JUMP" | "CROUCH", "timestamp": float}

Teammate 4 (controller) subscribes to EVENT_LANE_CHANGED and EVENT_ACTION.
"""

from __future__ import annotations

import logging
import threading
from collections import defaultdict
from typing import Any, Callable

logger = logging.getLogger("event_bus")

# --- Vision events (Teammate 1) ----------------------------------------------
EVENT_POSE_FRAME: str = "pose_frame"
EVENT_POSE_LOST: str = "pose_lost"
EVENT_POSE_FOUND: str = "pose_found"
EVENT_CALIBRATE: str = "calibrate"

# --- Movement events (Teammates 2 / 3) ---------------------------------------
EVENT_CALIBRATED: str = "calibrated"
EVENT_LANE_CHANGED: str = "lane_changed"
EVENT_ACTION: str = "action"

# --- Allowed values ----------------------------------------------------------
LANE_LEFT: str = "LEFT"
LANE_CENTER: str = "CENTER"
LANE_RIGHT: str = "RIGHT"
LANES: tuple[str, ...] = (LANE_LEFT, LANE_CENTER, LANE_RIGHT)

ACTION_JUMP: str = "JUMP"
ACTION_CROUCH: str = "CROUCH"
ACTIONS: tuple[str, ...] = (ACTION_JUMP, ACTION_CROUCH)


def make_lane_event(lane: str, timestamp: float) -> dict[str, Any]:
    """Build a validated EVENT_LANE_CHANGED payload."""
    if lane not in LANES:
        raise ValueError(f"lane must be one of {LANES}, got {lane!r}")
    return {"lane": lane, "timestamp": timestamp}


def make_action_event(action: str, timestamp: float) -> dict[str, Any]:
    """Build a validated EVENT_ACTION payload."""
    if action not in ACTIONS:
        raise ValueError(f"action must be one of {ACTIONS}, got {action!r}")
    return {"action": action, "timestamp": timestamp}


def make_calibrated_event(module: str, timestamp: float) -> dict[str, Any]:
    """Build an EVENT_CALIBRATED payload."""
    return {"module": module, "timestamp": timestamp}


class EventBus:
    """Synchronous pub/sub bus. Subscriber exceptions are logged, never propagated."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable[[Any], None]]] = defaultdict(list)
        self._lock = threading.Lock()

    def subscribe(self, event_name: str, callback: Callable[[Any], None]) -> None:
        """Register ``callback`` for ``event_name`` (duplicates are ignored)."""
        if not callable(callback):
            raise TypeError(f"callback must be callable, got {type(callback)}")
        with self._lock:
            if callback not in self._subscribers[event_name]:
                self._subscribers[event_name].append(callback)

    def unsubscribe(self, event_name: str, callback: Callable[[Any], None]) -> bool:
        """Remove a callback. Returns True if it was registered."""
        with self._lock:
            subs = self._subscribers.get(event_name, [])
            if callback in subs:
                subs.remove(callback)
                return True
        return False

    def publish(self, event_name: str, payload: Any = None) -> None:
        """Deliver ``payload`` to every subscriber; a failing subscriber never stops the rest."""
        with self._lock:
            callbacks = list(self._subscribers.get(event_name, []))
        for callback in callbacks:
            try:
                callback(payload)
            except Exception:  # noqa: BLE001 - isolation is the point
                logger.exception(
                    "Subscriber %r failed on event %r",
                    getattr(callback, "__name__", callback),
                    event_name,
                )

    def clear(self, event_name: str | None = None) -> None:
        """Remove all subscribers, or only those of one event."""
        with self._lock:
            if event_name is None:
                self._subscribers.clear()
            elif event_name in self._subscribers:
                self._subscribers[event_name].clear()
"""
GAME EVENT HOOK DISPATCHER
==========================

Emits and listens to core game-state events consumed by power-ups, the UI,
and any future game-logic extensions.

Events
------
  EVENT_JUMP          – player performed a jump gesture
  EVENT_ROLL          – player performed a crouch/roll gesture
  EVENT_COIN_COLLECT  – a coin was collected (real or magnet-pulled)
  EVENT_LANE_CHANGE   – player switched lane (LEFT | CENTER | RIGHT)
  EVENT_FRAME         – every processed vision frame (30+ fps heartbeat)
  EVENT_POWERUP_START – a power-up was activated
  EVENT_POWERUP_END   – a power-up timer expired or was cancelled

All callbacks receive a typed ``GameEvent`` dataclass so subscribers never
have to parse raw dicts. Thread-safe: publish() can be called from any thread.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from event_bus import (
    EVENT_ACTION,
    EVENT_LANE_CHANGED,
    EVENT_POSE_FRAME,
    EventBus,
)
from vision import PoseFrame

logger = logging.getLogger("game_events")

# ---------------------------------------------------------------------------
# Game event names
# ---------------------------------------------------------------------------
EVENT_JUMP: str = "game:jump"
EVENT_ROLL: str = "game:roll"
EVENT_COIN_COLLECT: str = "game:coin_collect"
EVENT_LANE_CHANGE: str = "game:lane_change"
EVENT_FRAME: str = "game:frame"
EVENT_POWERUP_START: str = "game:powerup_start"
EVENT_POWERUP_END: str = "game:powerup_end"


# ---------------------------------------------------------------------------
# Typed event payloads
# ---------------------------------------------------------------------------
@dataclass
class GameEvent:
    """Base payload for every game event."""
    name: str
    timestamp: float = field(default_factory=time.time)
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FrameEvent(GameEvent):
    """Per-frame heartbeat carrying the latest PoseFrame."""
    pose_frame: Optional[PoseFrame] = None
    fps: float = 0.0


@dataclass
class LaneChangeEvent(GameEvent):
    """Lane transition event."""
    lane: str = "CENTER"          # LEFT | CENTER | RIGHT
    prev_lane: str = "CENTER"


@dataclass
class JumpEvent(GameEvent):
    """Jump / leap gesture event."""
    height_norm: float = 0.0      # normalised lift delta (0-1)


@dataclass
class RollEvent(GameEvent):
    """Crouch / roll gesture event."""
    depth_norm: float = 0.0


@dataclass
class CoinEvent(GameEvent):
    """Single coin collected."""
    x_norm: float = 0.0           # normalised position
    y_norm: float = 0.0
    magnet_assisted: bool = False


@dataclass
class PowerUpEvent(GameEvent):
    """Power-up lifecycle notification."""
    powerup_name: str = ""
    duration_s: float = 0.0
    stacked: bool = False


# ---------------------------------------------------------------------------
# Hook Dispatcher
# ---------------------------------------------------------------------------
Callback = Callable[[GameEvent], None]


class GameEventDispatcher:
    """
    Thread-safe hook dispatcher that bridges the existing EventBus to typed
    game-layer events. Instantiate once and call ``connect(bus)`` to wire up
    the pose pipeline.

    Usage
    -----
    >>> dispatcher = GameEventDispatcher()
    >>> dispatcher.on(EVENT_JUMP, my_callback)
    >>> dispatcher.connect(bus)          # wires pose & action events
    >>> dispatcher.emit(CoinEvent(name=EVENT_COIN_COLLECT, magnet_assisted=True))
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subs: Dict[str, List[Callback]] = {}
        self._frame_count: int = 0
        self._fps_times: List[float] = []
        self._fps_window: int = 30
        self._prev_lane: str = "CENTER"

    # ------------------------------------------------------------------
    # Subscription API
    # ------------------------------------------------------------------
    def on(self, event_name: str, callback: Callback) -> None:
        """Register a callback for ``event_name``. Duplicates ignored."""
        if not callable(callback):
            raise TypeError(f"callback must be callable, got {type(callback)}")
        with self._lock:
            self._subs.setdefault(event_name, [])
            if callback not in self._subs[event_name]:
                self._subs[event_name].append(callback)

    def off(self, event_name: str, callback: Callback) -> bool:
        """Unregister a callback. Returns True if it was found."""
        with self._lock:
            lst = self._subs.get(event_name, [])
            if callback in lst:
                lst.remove(callback)
                return True
        return False

    def emit(self, event: GameEvent) -> None:
        """Dispatch ``event`` to all registered handlers for its name."""
        with self._lock:
            callbacks = list(self._subs.get(event.name, []))
        for cb in callbacks:
            try:
                cb(event)
            except Exception:           # noqa: BLE001
                logger.exception("Handler %r raised on event %r", cb, event.name)

    # ------------------------------------------------------------------
    # Bridge from existing EventBus
    # ------------------------------------------------------------------
    def connect(self, bus: EventBus) -> None:
        """Subscribe to the existing EventBus and translate events to game events."""
        bus.subscribe(EVENT_POSE_FRAME, self._on_pose_frame)
        bus.subscribe(EVENT_ACTION, self._on_action)
        bus.subscribe(EVENT_LANE_CHANGED, self._on_lane_changed)
        logger.info("GameEventDispatcher connected to EventBus.")

    # ------------------------------------------------------------------
    # Internal translators
    # ------------------------------------------------------------------
    def _on_pose_frame(self, pf: PoseFrame) -> None:
        now = time.time()
        self._frame_count += 1
        self._fps_times.append(now)
        if len(self._fps_times) > self._fps_window:
            self._fps_times = self._fps_times[-self._fps_window:]

        fps = self._calc_fps()
        self.emit(FrameEvent(
            name=EVENT_FRAME,
            timestamp=now,
            pose_frame=pf,
            fps=fps,
            data={"frame_count": self._frame_count},
        ))

    def _on_action(self, payload: dict) -> None:
        action = payload.get("action", "")
        ts = payload.get("timestamp", time.time())
        if action == "JUMP":
            self.emit(JumpEvent(name=EVENT_JUMP, timestamp=ts,
                                data=payload))
        elif action == "CROUCH":
            self.emit(RollEvent(name=EVENT_ROLL, timestamp=ts,
                                data=payload))

    def _on_lane_changed(self, payload: dict) -> None:
        lane = payload.get("lane", "CENTER")
        ts = payload.get("timestamp", time.time())
        prev = self._prev_lane
        self._prev_lane = lane
        self.emit(LaneChangeEvent(
            name=EVENT_LANE_CHANGE,
            timestamp=ts,
            lane=lane,
            prev_lane=prev,
            data=payload,
        ))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _calc_fps(self) -> float:
        times = self._fps_times
        if len(times) < 2:
            return 0.0
        span = times[-1] - times[0]
        return (len(times) - 1) / span if span > 0 else 0.0

    def emit_coin(self, x: float = 0.5, y: float = 0.5,
                  magnet: bool = False) -> None:
        """Convenience: fire a coin-collect event."""
        self.emit(CoinEvent(
            name=EVENT_COIN_COLLECT,
            x_norm=x,
            y_norm=y,
            magnet_assisted=magnet,
            data={"magnet": magnet},
        ))

    def emit_powerup(self, pu_name: str, duration: float,
                     started: bool, stacked: bool = False) -> None:
        """Convenience: fire power-up start/end event."""
        ev_name = EVENT_POWERUP_START if started else EVENT_POWERUP_END
        self.emit(PowerUpEvent(
            name=ev_name,
            powerup_name=pu_name,
            duration_s=duration,
            stacked=stacked,
            data={"powerup": pu_name, "duration": duration},
        ))

    @property
    def frame_count(self) -> int:
        return self._frame_count

"""
SUBWAY SURFERS POWER-UP ENGINE
===============================

All 6 canonical Subway Surfers power-ups with:
  * Lifecycle countdown timers (threading.Timer)
  * Stackability (activating again while active resets/extends timer)
  * Active-state HUD data (query via PowerUpManager.hud_state())
  * Integration hooks into GameEventDispatcher

Power-ups
---------
  CoinMagnet      – interpolates coin positions toward player across lanes
  Jetpack         – elevates player above obstacles for duration, smooth landing
  SuperSneakers   – increases jump velocity + hangtime
  ScoreMultiplier – doubles active score accumulation (2x)
  Hoverboard      – extra life: absorbs 1 fatal hit, brief invincibility after
  Shield          – smashes through obstacles without dying (headstart / shield)

Usage
-----
    from powerups import PowerUpManager, PowerUpName
    from game_events import GameEventDispatcher

    dispatcher = GameEventDispatcher()
    manager    = PowerUpManager(dispatcher)

    # Activate a power-up programmatically (e.g. from guardrail or game logic):
    manager.activate(PowerUpName.JETPACK)

    # Query HUD data each frame:
    hud = manager.hud_state()   # list of active-powerup dicts

    # Register custom hooks:
    manager.on_activate(PowerUpName.COIN_MAGNET, my_callback)
    manager.on_expire(PowerUpName.COIN_MAGNET, my_callback)
"""

from __future__ import annotations

import logging
import math
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from game_events import (
    EVENT_COIN_COLLECT,
    EVENT_FRAME,
    EVENT_JUMP,
    EVENT_LANE_CHANGE,
    EVENT_POWERUP_END,
    EVENT_POWERUP_START,
    CoinEvent,
    FrameEvent,
    GameEvent,
    GameEventDispatcher,
    JumpEvent,
    LaneChangeEvent,
    PowerUpEvent,
)

logger = logging.getLogger("powerups")

# ---------------------------------------------------------------------------
# Power-up catalogue
# ---------------------------------------------------------------------------
class PowerUpName(str, Enum):
    COIN_MAGNET      = "CoinMagnet"
    JETPACK          = "Jetpack"
    SUPER_SNEAKERS   = "SuperSneakers"
    SCORE_MULTIPLIER = "ScoreMultiplier"
    HOVERBOARD       = "Hoverboard"
    SHIELD           = "Shield"


# Default durations (seconds) – can be overridden at runtime
DEFAULT_DURATIONS: Dict[PowerUpName, float] = {
    PowerUpName.COIN_MAGNET:      10.0,
    PowerUpName.JETPACK:          15.0,
    PowerUpName.SUPER_SNEAKERS:   10.0,
    PowerUpName.SCORE_MULTIPLIER: 12.0,
    PowerUpName.HOVERBOARD:       0.0,   # event-driven, not time-driven
    PowerUpName.SHIELD:           8.0,
}

# Lane positions (normalized 0-1 x-axis)
LANE_X: Dict[str, float] = {"LEFT": 0.2, "CENTER": 0.5, "RIGHT": 0.8}

# Magnet interpolation speed (fraction per second)
MAGNET_LERP_SPEED: float = 5.0

# Jetpack sky Y offset (how far above normal shoulder position, normalized)
JETPACK_SKY_Y: float = 0.15

# Super sneaker jump multipliers
SNEAKER_VEL_MULT: float = 1.65
SNEAKER_HANG_MULT: float = 1.5

# Post-hoverboard crash invincibility window (seconds)
HOVERBOARD_INVINC_S: float = 2.5


# ---------------------------------------------------------------------------
# Internal power-up state
# ---------------------------------------------------------------------------
@dataclass
class _PowerUpState:
    name: PowerUpName
    duration: float          # seconds (0 = not time-limited)
    activated_at: float = field(default_factory=time.time)
    expires_at: float = 0.0
    active: bool = True
    # Hoverboard-specific
    charges: int = 1
    post_crash_invincible: bool = False
    post_crash_until: float = 0.0

    def remaining(self) -> float:
        if self.expires_at == 0.0:
            return float("inf")
        return max(0.0, self.expires_at - time.time())

    def fraction_remaining(self) -> float:
        if self.expires_at == 0.0 or self.duration == 0.0:
            return 1.0
        return self.remaining() / self.duration


# ---------------------------------------------------------------------------
# Individual power-up behaviours
# ---------------------------------------------------------------------------
class _PowerUp:
    """Abstract behaviour mixin. Each subclass implements game-layer effects."""

    name: PowerUpName = PowerUpName.SHIELD   # overridden by subclass

    def on_activate(self, state: _PowerUpState, manager: "PowerUpManager") -> None:
        """Called when the power-up becomes active (or is re-activated)."""

    def on_expire(self, state: _PowerUpState, manager: "PowerUpManager") -> None:
        """Called when the timer fires or the power-up is cancelled."""

    def on_frame(self, state: _PowerUpState, manager: "PowerUpManager",
                 ev: FrameEvent) -> None:
        """Called each vision frame while active."""

    def on_jump(self, state: _PowerUpState, manager: "PowerUpManager",
                ev: JumpEvent) -> None:
        """Called when a JUMP event fires while active."""

    def on_lane_change(self, state: _PowerUpState, manager: "PowerUpManager",
                       ev: LaneChangeEvent) -> None:
        """Called when the lane changes while active."""


class _CoinMagnetPowerUp(_PowerUp):
    """
    Coin Magnet – interpolates nearby coins toward the player's lane.

    Simulates: coins within ±2 lane-widths are attracted to player_x with
    MAGNET_LERP_SPEED lerp per second. Each attract step fires
    GameEventDispatcher.emit_coin(magnet=True) for the HUD counter.
    """
    name = PowerUpName.COIN_MAGNET

    def __init__(self) -> None:
        self._coin_positions: List[Tuple[float, float]] = []
        self._lock = threading.Lock()

    def add_coins(self, positions: List[Tuple[float, float]]) -> None:
        """Add world coin positions to attract. Called by game world."""
        with self._lock:
            self._coin_positions.extend(positions)

    def on_activate(self, state, manager) -> None:
        logger.info("[CoinMagnet] ACTIVATED – attracting coins for %.1fs", state.duration)

    def on_expire(self, state, manager) -> None:
        with self._lock:
            self._coin_positions.clear()
        logger.info("[CoinMagnet] EXPIRED – magnet off.")

    def on_frame(self, state, manager, ev: FrameEvent) -> None:
        dt = 1.0 / max(ev.fps, 1.0)
        player_x = manager.player_x
        collected: List[Tuple[float, float]] = []
        remaining: List[Tuple[float, float]] = []

        with self._lock:
            for cx, cy in self._coin_positions:
                # Lerp coin toward player X
                new_cx = cx + (player_x - cx) * min(MAGNET_LERP_SPEED * dt, 1.0)
                dist = abs(new_cx - player_x)
                if dist < 0.05:          # close enough → collected
                    collected.append((new_cx, cy))
                else:
                    remaining.append((new_cx, cy))
            self._coin_positions = remaining

        for cx, cy in collected:
            manager.dispatcher.emit_coin(cx, cy, magnet=True)


class _JetpackPowerUp(_PowerUp):
    """
    Jetpack – elevates player into sky runway, smooth landing on expiry.

    Simulates sky Y offset, high forward speed, then interpolates back down.
    """
    name = PowerUpName.JETPACK

    def on_activate(self, state, manager) -> None:
        manager.player_y_offset = -JETPACK_SKY_Y   # negative = up in screen coords
        manager.speed_multiplier = 2.0
        logger.info("[Jetpack] ACTIVATED – player elevated to sky runway.")

    def on_expire(self, state, manager) -> None:
        manager._jetpack_landing = True
        manager.speed_multiplier = 1.0
        logger.info("[Jetpack] EXPIRED – initiating smooth landing.")

    def on_frame(self, state, manager, ev: FrameEvent) -> None:
        if getattr(manager, "_jetpack_landing", False):
            dt = 1.0 / max(ev.fps, 1.0)
            manager.player_y_offset += 3.0 * dt    # lerp back to 0
            if manager.player_y_offset >= 0.0:
                manager.player_y_offset = 0.0
                manager._jetpack_landing = False
                logger.info("[Jetpack] Landing complete.")


class _SuperSneakersPowerUp(_PowerUp):
    """
    Super Sneakers – increases jump velocity and hang-time.

    Applies velocity/hang multipliers; resets on expiry.
    """
    name = PowerUpName.SUPER_SNEAKERS

    def on_activate(self, state, manager) -> None:
        manager.jump_velocity_mult = SNEAKER_VEL_MULT
        manager.jump_hang_mult     = SNEAKER_HANG_MULT
        logger.info("[SuperSneakers] ACTIVATED – jump_vel=×%.2f hang=×%.2f",
                    SNEAKER_VEL_MULT, SNEAKER_HANG_MULT)

    def on_expire(self, state, manager) -> None:
        manager.jump_velocity_mult = 1.0
        manager.jump_hang_mult     = 1.0
        logger.info("[SuperSneakers] EXPIRED – jump stats restored.")

    def on_jump(self, state, manager, ev: JumpEvent) -> None:
        logger.debug("[SuperSneakers] Jump boosted – vel×%.2f", manager.jump_velocity_mult)


class _ScoreMultiplierPowerUp(_PowerUp):
    """
    2× Score Multiplier – doubles score accumulation rate.
    """
    name = PowerUpName.SCORE_MULTIPLIER

    def on_activate(self, state, manager) -> None:
        manager.score_multiplier = 2
        logger.info("[ScoreMultiplier] ACTIVATED – score ×%d", manager.score_multiplier)

    def on_expire(self, state, manager) -> None:
        manager.score_multiplier = 1
        logger.info("[ScoreMultiplier] EXPIRED – score ×1.")


class _HoverboardPowerUp(_PowerUp):
    """
    Hoverboard – acts as an extra life absorbing exactly 1 fatal collision.

    On fatal hit:
      1. Board shatters (animation signal in manager.hoverboard_shatter = True)
      2. Player recovers (brief stumble)
      3. POST_CRASH_INVINCIBLE window grants temporary immunity
    Must be re-picked-up to restore.
    """
    name = PowerUpName.HOVERBOARD

    def on_activate(self, state, manager) -> None:
        state.charges = 1
        state.post_crash_invincible = False
        logger.info("[Hoverboard] ACTIVATED – 1 extra life ready.")

    def absorb_hit(self, state: _PowerUpState, manager: "PowerUpManager") -> bool:
        """
        Call when a fatal collision is detected.
        Returns True if the board absorbed the hit (player survives), False otherwise.
        """
        if state.charges > 0 and state.active:
            state.charges -= 1
            manager.hoverboard_shatter = True
            state.post_crash_invincible = True
            state.post_crash_until = time.time() + HOVERBOARD_INVINC_S
            logger.info("[Hoverboard] ABSORBED hit – post-crash invincibility for %.1fs",
                        HOVERBOARD_INVINC_S)
            # Auto-expire the board after absorbing
            manager._expire_powerup(PowerUpName.HOVERBOARD)
            return True
        return False

    def on_frame(self, state, manager, ev: FrameEvent) -> None:
        if state.post_crash_invincible and time.time() > state.post_crash_until:
            state.post_crash_invincible = False
            manager.hoverboard_shatter = False
            logger.info("[Hoverboard] Post-crash invincibility ended.")

    def on_expire(self, state, manager) -> None:
        logger.info("[Hoverboard] Board expired/consumed.")


class _ShieldPowerUp(_PowerUp):
    """
    Shield / Headstart – smashes through obstacles without dying.
    Player is invincible for the duration.
    """
    name = PowerUpName.SHIELD

    def on_activate(self, state, manager) -> None:
        manager.is_shielded = True
        manager.speed_multiplier = max(manager.speed_multiplier, 1.5)
        logger.info("[Shield] ACTIVATED – invincible for %.1fs", state.duration)

    def on_expire(self, state, manager) -> None:
        manager.is_shielded = False
        manager.speed_multiplier = 1.0
        logger.info("[Shield] EXPIRED – shield down.")


# ---------------------------------------------------------------------------
# Power-up registry
# ---------------------------------------------------------------------------
_POWERUP_BEHAVIOURS: Dict[PowerUpName, _PowerUp] = {
    PowerUpName.COIN_MAGNET:      _CoinMagnetPowerUp(),
    PowerUpName.JETPACK:          _JetpackPowerUp(),
    PowerUpName.SUPER_SNEAKERS:   _SuperSneakersPowerUp(),
    PowerUpName.SCORE_MULTIPLIER: _ScoreMultiplierPowerUp(),
    PowerUpName.HOVERBOARD:       _HoverboardPowerUp(),
    PowerUpName.SHIELD:           _ShieldPowerUp(),
}


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------
class PowerUpManager:
    """
    Central power-up manager. Owns all active states, timers, and game
    parameters modified by power-ups. Thread-safe.

    Game parameters (read by renderer / game logic):
      player_x              – normalized X position of player (0-1)
      player_y_offset       – vertical offset applied by jetpack (normalized)
      speed_multiplier      – applied to forward game speed
      jump_velocity_mult    – jump height multiplier
      jump_hang_mult        – jump hang-time multiplier
      score_multiplier      – score accumulation multiplier (1 or 2)
      is_shielded           – True while Shield is active
      hoverboard_shatter    – True for one frame when board is consumed
    """

    def __init__(self, dispatcher: GameEventDispatcher) -> None:
        self.dispatcher = dispatcher

        # Game state parameters modified by power-ups
        self.player_x: float = 0.5
        self.player_y_offset: float = 0.0
        self.speed_multiplier: float = 1.0
        self.jump_velocity_mult: float = 1.0
        self.jump_hang_mult: float = 1.0
        self.score_multiplier: int = 1
        self.is_shielded: bool = False
        self.hoverboard_shatter: bool = False

        # Internal state
        self._lock = threading.Lock()
        self._active: Dict[PowerUpName, _PowerUpState] = {}
        self._timers: Dict[PowerUpName, threading.Timer] = {}
        self._activate_hooks: Dict[PowerUpName, List[Callable]] = {n: [] for n in PowerUpName}
        self._expire_hooks:   Dict[PowerUpName, List[Callable]] = {n: [] for n in PowerUpName}
        self._jetpack_landing: bool = False

        # Wire frame/jump/lane events for per-power-up callbacks
        dispatcher.on(EVENT_FRAME,       self._dispatch_frame)
        dispatcher.on(EVENT_JUMP,        self._dispatch_jump)
        dispatcher.on(EVENT_LANE_CHANGE, self._dispatch_lane)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def activate(self, name: PowerUpName,
                 duration: Optional[float] = None) -> None:
        """
        Activate (or re-activate/stack) a power-up.

        If the power-up is already active, its timer is reset to a fresh
        ``duration`` (stackable behaviour).
        """
        dur = duration if duration is not None else DEFAULT_DURATIONS[name]
        now = time.time()

        with self._lock:
            stacked = name in self._active
            if stacked:
                # Cancel existing timer and reset
                self._cancel_timer(name)

            state = _PowerUpState(
                name=name,
                duration=dur,
                activated_at=now,
                expires_at=now + dur if dur > 0 else 0.0,
                active=True,
            )
            self._active[name] = state

        behaviour = _POWERUP_BEHAVIOURS[name]
        behaviour.on_activate(state, self)

        if dur > 0:
            timer = threading.Timer(dur, self._expire_powerup, args=(name,))
            timer.daemon = True
            timer.start()
            with self._lock:
                self._timers[name] = timer

        # Fire game event
        self.dispatcher.emit_powerup(name.value, dur, started=True, stacked=stacked)

        # Call registered hooks
        for cb in self._activate_hooks.get(name, []):
            try:
                cb(state)
            except Exception:           # noqa: BLE001
                logger.exception("Activate hook %r raised.", cb)

        logger.info("[PowerUpManager] %s %s (%.1fs).",
                    name.value, "STACKED" if stacked else "ACTIVATED", dur)

    def deactivate(self, name: PowerUpName) -> None:
        """Manually cancel an active power-up."""
        self._expire_powerup(name)

    def hoverboard_hit(self) -> bool:
        """
        Signal a fatal collision to the hoverboard.
        Returns True if the board absorbed the hit (player lives).
        """
        with self._lock:
            state = self._active.get(PowerUpName.HOVERBOARD)
        if state:
            behaviour = _POWERUP_BEHAVIOURS[PowerUpName.HOVERBOARD]
            return behaviour.absorb_hit(state, self)  # type: ignore[attr-defined]
        return False

    def is_active(self, name: PowerUpName) -> bool:
        with self._lock:
            st = self._active.get(name)
        return st is not None and st.active

    def remaining(self, name: PowerUpName) -> float:
        """Seconds left for the named power-up (inf if not time-limited, 0 if inactive)."""
        with self._lock:
            st = self._active.get(name)
        return st.remaining() if st else 0.0

    def hud_state(self) -> List[Dict[str, Any]]:
        """
        Return a list of dicts describing all currently active power-ups.
        Designed for rendering on-screen HUD overlays.
        """
        with self._lock:
            states = list(self._active.values())
        result = []
        for st in states:
            extra: Dict[str, Any] = {}
            if st.name == PowerUpName.HOVERBOARD:
                extra["charges"] = st.charges
                extra["post_crash_invincible"] = st.post_crash_invincible
            result.append({
                "name": st.name.value,
                "remaining_s": round(st.remaining(), 2),
                "fraction": round(st.fraction_remaining(), 3),
                "active": st.active,
                **extra,
            })
        return result

    def add_magnet_coins(self, positions: List[Tuple[float, float]]) -> None:
        """Feed world coin positions to the magnet (if active)."""
        behaviour = _POWERUP_BEHAVIOURS[PowerUpName.COIN_MAGNET]
        behaviour.add_coins(positions)  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Hook registration
    # ------------------------------------------------------------------
    def on_activate(self, name: PowerUpName, cb: Callable) -> None:
        """Register a callback fired when the power-up activates."""
        self._activate_hooks[name].append(cb)

    def on_expire(self, name: PowerUpName, cb: Callable) -> None:
        """Register a callback fired when the power-up expires/deactivates."""
        self._expire_hooks[name].append(cb)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _expire_powerup(self, name: PowerUpName) -> None:
        """Timer callback – expires one power-up."""
        with self._lock:
            state = self._active.pop(name, None)
            self._cancel_timer(name)
        if state is None:
            return
        state.active = False

        behaviour = _POWERUP_BEHAVIOURS[name]
        behaviour.on_expire(state, self)

        self.dispatcher.emit_powerup(name.value, state.duration, started=False)

        for cb in self._expire_hooks.get(name, []):
            try:
                cb(state)
            except Exception:           # noqa: BLE001
                logger.exception("Expire hook %r raised.", cb)

        logger.info("[PowerUpManager] %s EXPIRED.", name.value)

    def _cancel_timer(self, name: PowerUpName) -> None:
        """Cancel a pending timer (must be called under self._lock)."""
        t = self._timers.pop(name, None)
        if t is not None:
            t.cancel()

    def _dispatch_frame(self, ev: FrameEvent) -> None:
        with self._lock:
            items = list(self._active.items())
        for name, state in items:
            _POWERUP_BEHAVIOURS[name].on_frame(state, self, ev)

    def _dispatch_jump(self, ev: JumpEvent) -> None:
        with self._lock:
            items = list(self._active.items())
        for name, state in items:
            _POWERUP_BEHAVIOURS[name].on_jump(state, self, ev)
        # Update player_x from lane
        # (already handled by _dispatch_lane; jump is vertical only)

    def _dispatch_lane(self, ev: LaneChangeEvent) -> None:
        self.player_x = LANE_X.get(ev.lane, 0.5)
        with self._lock:
            items = list(self._active.items())
        for name, state in items:
            _POWERUP_BEHAVIOURS[name].on_lane_change(state, self, ev)
